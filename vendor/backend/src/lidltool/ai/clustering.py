from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.ai.config import get_ai_api_key, get_ai_oauth_access_token
from lidltool.analytics.workbench import create_product, manual_product_match
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope
from lidltool.db.models import Product, ProductAlias, TransactionItem

_BATCH_SIZE = 60


@dataclass(slots=True)
class ClusteringJobState:
    status: str
    total_batches: int
    completed_batches: int = 0
    products_created: int = 0
    aliases_created: int = 0
    items_matched: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "total_batches": self.total_batches,
            "completed_batches": self.completed_batches,
            "products_created": self.products_created,
            "aliases_created": self.aliases_created,
            "items_matched": self.items_matched,
            "errors": list(self.errors),
        }


_JOBS: dict[str, ClusteringJobState] = {}
_JOBS_LOCK = threading.Lock()


def _set_job_state(job_id: str, state: ClusteringJobState) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = state


def _update_job_state(job_id: str, mutate: Any) -> None:
    with _JOBS_LOCK:
        state = _JOBS.get(job_id)
        if state is None:
            return
        mutate(state)


def get_cluster_job_progress(job_id: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        state = _JOBS.get(job_id)
        if state is None:
            return None
        return state.to_dict()


def cluster_products_with_llm(
    *,
    sessions: sessionmaker[Session],
    config: AppConfig,
    force: bool = False,
) -> dict[str, Any]:
    names = _collect_item_names(sessions=sessions, force=force)
    batches = [names[index : index + _BATCH_SIZE] for index in range(0, len(names), _BATCH_SIZE)]
    job_id = str(uuid4())
    _set_job_state(
        job_id,
        ClusteringJobState(
            status="running",
            total_batches=len(batches),
        ),
    )
    thread = threading.Thread(
        target=_run_cluster_job,
        kwargs={
            "job_id": job_id,
            "batches": batches,
            "sessions": sessions,
            "config": config,
        },
        daemon=True,
        name=f"product-cluster-{job_id}",
    )
    thread.start()
    return {"job_id": job_id, "status": "running"}


def _collect_item_names(*, sessions: sessionmaker[Session], force: bool) -> list[str]:
    with session_scope(sessions) as session:
        distinct_names = sorted(
            {
                str(name).strip()
                for name in session.execute(select(TransactionItem.name).distinct()).scalars().all()
                if isinstance(name, str) and name.strip()
            }
        )
        if force:
            return distinct_names
        existing_aliases = {
            str(raw_name).strip().lower()
            for raw_name in session.execute(select(ProductAlias.raw_name).distinct()).scalars().all()
            if isinstance(raw_name, str) and raw_name.strip()
        }
        return [name for name in distinct_names if name.lower() not in existing_aliases]


def _run_cluster_job(
    *,
    job_id: str,
    batches: list[list[str]],
    sessions: sessionmaker[Session],
    config: AppConfig,
) -> None:
    try:
        base_url = (config.ai_base_url or "").strip()
        token = get_ai_oauth_access_token(config) or get_ai_api_key(config)
        if not base_url:
            raise RuntimeError("AI base_url is not configured")
        if not token:
            raise RuntimeError("AI credentials are not configured")
        model = (config.ai_model or "").strip()
        if not model:
            raise RuntimeError("AI model is not configured")

        client = OpenAI(base_url=base_url, api_key=token)
        for batch in batches:
            try:
                payload = _cluster_batch_with_model(client=client, model=model, batch=batch)
                _apply_cluster_payload(job_id=job_id, payload=payload, sessions=sessions)
            except Exception as exc:  # noqa: BLE001
                _update_job_state(job_id, lambda state: state.errors.append(str(exc)))
            finally:
                _update_job_state(job_id, lambda state: setattr(state, "completed_batches", state.completed_batches + 1))
        _update_job_state(job_id, lambda state: setattr(state, "status", "completed"))
    except Exception as exc:  # noqa: BLE001
        _update_job_state(
            job_id,
            lambda state: (
                state.errors.append(str(exc)),
                setattr(state, "status", "error"),
            ),
        )


def _cluster_batch_with_model(*, client: OpenAI, model: str, batch: list[str]) -> list[dict[str, Any]]:
    item_lines = "\n".join(f"- {name}" for name in batch)
    prompt = (
        "You are a German grocery receipt parser. Group these abbreviated receipt item names "
        "into canonical products.\n\n"
        "Rules:\n"
        '- Group name variants of the same product together (e.g. "Rockstar Blueb.Mint 0,5L" '
        'and "Rockstar Energy 0,5L" -> canonical "Rockstar Energy")\n'
        "- Keep genuinely distinct products separate\n"
        "- Use clean German canonical names without abbreviations or sizes\n"
        "- Identify brand where possible\n"
        "- Category must be one of: beverages, dairy, produce, bakery, meat, frozen, snacks, "
        "household, personal_care, other\n\n"
        'Return ONLY JSON as {"items":[{"canonical_name":"...","brand":"...",'
        '"category":"...","aliases":["raw name 1","raw name 2"]}]}\n\n'
        f"Item names:\n{item_lines}\n"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content if response.choices else None
    if not content:
        return []
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        items = parsed.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _apply_cluster_payload(
    *,
    job_id: str,
    payload: list[dict[str, Any]],
    sessions: sessionmaker[Session],
) -> None:
    for cluster in payload:
        canonical_name = str(cluster.get("canonical_name") or "").strip()
        if not canonical_name:
            continue
        brand_raw = cluster.get("brand")
        brand = str(brand_raw).strip() if isinstance(brand_raw, str) and brand_raw.strip() else None
        aliases_raw = cluster.get("aliases")
        if not isinstance(aliases_raw, list):
            aliases_raw = []
        aliases = [
            str(value).strip()
            for value in aliases_raw
            if isinstance(value, str) and value.strip()
        ]
        if not aliases:
            continue
        with session_scope(sessions) as session:
            product = session.execute(
                select(Product).where(func.lower(Product.canonical_name) == canonical_name.lower())
            ).scalar_one_or_none()
            product_id = product.product_id if product is not None else None
            if product_id is None:
                created = create_product(
                    session,
                    canonical_name=canonical_name,
                    brand=brand,
                    is_ai_generated=True,
                )
                product_id = str(created["product_id"])
                _update_job_state(
                    job_id,
                    lambda state: setattr(state, "products_created", state.products_created + 1),
                )
            elif brand and not product.brand:
                product.brand = brand

            for alias in aliases:
                alias_exists = session.execute(
                    select(ProductAlias.alias_id).where(
                        ProductAlias.product_id == product_id,
                        func.lower(ProductAlias.raw_name) == alias.lower(),
                        ProductAlias.source_kind.is_(None),
                    )
                ).scalar_one_or_none()
                result = manual_product_match(
                    session,
                    product_id=product_id,
                    raw_name=alias,
                    source_kind=None,
                )
                if alias_exists is None:
                    _update_job_state(
                        job_id,
                        lambda state: setattr(state, "aliases_created", state.aliases_created + 1),
                    )
                matched_count = int(result.get("matched_item_count") or 0)
                if matched_count > 0:
                    _update_job_state(
                        job_id,
                        lambda state: setattr(state, "items_matched", state.items_matched + matched_count),
                    )
