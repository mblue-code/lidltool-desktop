from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from lidltool.analytics.categorization import load_compiled_rules
from lidltool.analytics.item_categorizer import (
    apply_item_categorization,
    canonicalize_category_name,
    resolve_item_categorizer_runtime_client,
)
from lidltool.analytics.normalization import NormalizationBundle, load_normalization_bundle
from lidltool.analytics.observations import refresh_observations_for_transaction
from lidltool.config import AppConfig
from lidltool.db.models import Source, Transaction, TransactionItem


@dataclass(slots=True)
class RecategorizationSummary:
    transaction_count: int = 0
    candidate_item_count: int = 0
    updated_transaction_count: int = 0
    updated_item_count: int = 0
    skipped_transaction_count: int = 0
    method_counts: dict[str, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["method_counts"] = dict(self.method_counts or {})
        return payload


def recategorize_transactions(
    *,
    session: Session,
    config: AppConfig,
    transaction_ids: Sequence[str] | None = None,
    source_id: str | None = None,
    only_fallback_other: bool = True,
    include_suspect_model_items: bool = False,
    max_transactions: int | None = None,
    require_model_runtime: bool = True,
    progress_callback: Callable[[RecategorizationSummary], None] | None = None,
) -> RecategorizationSummary:
    summary = RecategorizationSummary(method_counts={})
    model_client = resolve_item_categorizer_runtime_client(config)
    if require_model_runtime and model_client is None:
        raise RuntimeError("item categorizer runtime is not configured")

    compiled_rules = load_compiled_rules(session)
    bundle_cache: dict[str, NormalizationBundle] = {}

    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.items))
        .order_by(Transaction.purchased_at.desc(), Transaction.id.desc())
    )
    if transaction_ids:
        stmt = stmt.where(Transaction.id.in_(list(transaction_ids)))
    if source_id:
        stmt = stmt.where(Transaction.source_id == source_id)
    if max_transactions is not None:
        stmt = stmt.limit(max_transactions)

    transactions = session.execute(stmt).scalars().all()
    summary.transaction_count = len(transactions)
    _publish_progress(summary, progress_callback)

    for transaction in transactions:
        source = session.get(Source, transaction.source_id)
        if source is None:
            summary.skipped_transaction_count += 1
            _publish_progress(summary, progress_callback)
            session.commit()
            continue
        bundle = bundle_cache.get(source.id)
        if bundle is None:
            bundle = load_normalization_bundle(session, source=source.id)
            bundle_cache[source.id] = bundle

        items = [
            item
            for item in transaction.items
            if _should_recategorize_item(
                item,
                only_fallback_other=only_fallback_other,
                include_suspect_model_items=include_suspect_model_items,
            )
        ]
        if not items:
            summary.skipped_transaction_count += 1
            _publish_progress(summary, progress_callback)
            session.commit()
            continue
        summary.candidate_item_count += len(items)
        _publish_progress(summary, progress_callback)

        before = {
            item.id: (
                item.category,
                item.category_id,
            )
            for item in items
        }
        apply_item_categorization(
            session=session,
            source=source,
            items=items,
            normalization_bundle=bundle,
            rules=compiled_rules,
            config=config,
            merchant_name=transaction.merchant_name,
            model_client=model_client,
        )
        changed_for_transaction = 0
        for item in items:
            previous = before[item.id]
            current = (
                item.category,
                item.category_id,
            )
            if current == previous:
                continue
            changed_for_transaction += 1
            method = (item.category_method or "unknown").strip() or "unknown"
            summary.method_counts[method] = summary.method_counts.get(method, 0) + 1
        if changed_for_transaction <= 0:
            _publish_progress(summary, progress_callback)
            session.commit()
            continue
        summary.updated_transaction_count += 1
        summary.updated_item_count += changed_for_transaction
        refresh_observations_for_transaction(session, transaction_id=transaction.id)
        _publish_progress(summary, progress_callback)
        session.commit()

    summary.method_counts = dict(sorted(Counter(summary.method_counts or {}).items()))
    _publish_progress(summary, progress_callback)
    return summary


def _publish_progress(
    summary: RecategorizationSummary,
    callback: Callable[[RecategorizationSummary], None] | None,
) -> None:
    if callback is None:
        return
    callback(
        RecategorizationSummary(
            transaction_count=summary.transaction_count,
            candidate_item_count=summary.candidate_item_count,
            updated_transaction_count=summary.updated_transaction_count,
            updated_item_count=summary.updated_item_count,
            skipped_transaction_count=summary.skipped_transaction_count,
            method_counts=dict(summary.method_counts or {}),
        )
    )


def _should_recategorize_item(
    item: TransactionItem,
    *,
    only_fallback_other: bool,
    include_suspect_model_items: bool,
) -> bool:
    if item.is_deposit:
        return False
    method_value = (item.category_method or "").strip().lower()
    if method_value == "manual":
        return False
    category_value = (item.category or "").strip().lower()
    if only_fallback_other or include_suspect_model_items:
        if only_fallback_other and (category_value in {"", "other"} or method_value == "fallback_other"):
            return True
        if include_suspect_model_items and (
            method_value == "qwen_local"
            or (
                method_value == "source_native"
                and _looks_like_synthetic_source_native(item)
            )
        ):
            return True
        return False
    return True


def _looks_like_synthetic_source_native(item: TransactionItem) -> bool:
    if (item.category_method or "").strip().lower() != "source_native":
        return False
    raw_payload = item.raw_payload if isinstance(item.raw_payload, dict) else {}
    raw_category = raw_payload.get("category")
    if isinstance(raw_category, str) and raw_category.strip():
        return False
    source_value = (item.category_source_value or item.category or "").strip()
    if not source_value:
        return False
    return canonicalize_category_name(source_value) is not None
