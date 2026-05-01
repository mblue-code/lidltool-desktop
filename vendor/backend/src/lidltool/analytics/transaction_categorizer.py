from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Sequence

from sqlalchemy import event, select
from sqlalchemy.orm import Session, selectinload

from lidltool.ai.codex_oauth import complete_text_with_codex_oauth
from lidltool.ai.config import get_ai_oauth_access_token
from lidltool.ai.item_categorizer import resolve_item_categorizer_settings
from lidltool.analytics.finance_taxonomy import FINANCE_CATEGORIES, FINANCE_TAXONOMY_VERSION, ensure_finance_taxonomy
from lidltool.analytics.item_categorizer import JsonCompletionRequest, RuntimeTask, resolve_model_runtime
from lidltool.config import AppConfig
from lidltool.db.models import FinanceCategoryRule, Transaction, TransactionItem


TRANSACTION_CATEGORIZER_VERSION = "transaction-categorizer-v1"
_MANUAL_METHODS = {"manual"}
_EVENTS_REGISTERED = False
LOGGER = logging.getLogger(__name__)
_FALLBACK_CATEGORIES = {"", "other", "uncategorized"}
_VALID_DIRECTIONS = {"inflow", "outflow", "transfer", "neutral"}


@dataclass(frozen=True, slots=True)
class FinanceCategoryResult:
    direction: str
    category_id: str
    method: str
    confidence: float
    source_value: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FinanceModelPrediction:
    transaction_id: str
    direction: str | None
    category_id: str | None
    confidence: float | None
    reason_code: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_id: str
    category_id: str
    direction: str
    patterns: tuple[str, ...]
    tags: tuple[str, ...] = ()
    confidence: float = 0.92

    def matches(self, text: str) -> bool:
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in self.patterns)


RULES: tuple[_Rule, ...] = (
    _Rule("income_salary", "income:salary", "inflow", (r"\b(salary|payroll|gehalt|lohn)\b",)),
    _Rule("credit", "credit:repayment", "outflow", (r"\b(kredit|loan|darlehen|rate)\b",), ("debt",)),
    _Rule("getsafe", "insurance:liability", "outflow", (r"getsafe\s+digital\s+gmbh", r"\bversicherung\b", r"\binsurance\b"), ("insurance",)),
    _Rule("rent", "housing:rent", "outflow", (r"\b(rent|miete|vermieter)\b",), ("housing",)),
    _Rule("electricity", "housing:electricity", "outflow", (r"\b(electricity|strom|vattenfall|e\.?on|enbw)\b",), ("housing",)),
    _Rule("heating", "housing:heating", "outflow", (r"\b(heating|heizung|gas|waerme|wärme)\b",), ("housing",)),
    _Rule("internet", "housing:internet", "outflow", (r"\b(telekom|vodafone|o2|internet|dsl|glasfaser)\b",), ("housing", "communication")),
    _Rule("train", "mobility:train", "outflow", (r"\b(deutsche\s+bahn|db\s+fernverkehr|bahn|train|ice|flixtrain)\b",), ("mobility",)),
    _Rule("public_transit", "mobility:public_transit", "outflow", (r"\b(bvg|hvv|mvg|vbb|oepnv|öpnv|transit|nahverkehr)\b",), ("mobility",)),
    _Rule("car_fuel", "car:fuel", "outflow", (r"\b(aral|shell|esso|totalenergies|jet|tankstelle|fuel|benzin|diesel)\b",), ("car",)),
    _Rule("car_charging", "car:charging", "outflow", (r"\b(ionity|tesla\s+supercharger|enbw\s+mobility|charging|laden)\b",), ("car",)),
    _Rule("investment", "investment:broker_transfer", "transfer", (r"\b(trade\s+republic|scalable|broker|depot|investment|sparplan|etf|aktien)\b",), ("investment",)),
    _Rule("catapult_news", "subscriptions:news", "outflow", (r"\b(catapult|katapult)(\s+(magazine|magazin))?\b",), ("subscription", "news")),
    _Rule("substack_publications", "education:publications", "outflow", (r"\bsubstack\b",), ("knowledge",)),
    _Rule("fitness_subscription", "subscriptions:fitness", "outflow", (r"\b(swift|fitx|urban\s+sports|fitness\s+first|gymondo|mcfit)\b",), ("subscription", "fitness")),
    _Rule("software_subscription", "subscriptions:software", "outflow", (r"\b(openai|github|notion|adobe|microsoft|apple\.com/bill|icloud)\b",), ("subscription",)),
    _Rule("streaming_subscription", "subscriptions:streaming", "outflow", (r"\b(netflix|spotify|disney|prime video|youtube premium)\b",), ("subscription",)),
    _Rule("amazon_online_retail", "shopping:online_retail", "outflow", (r"\bamazon(\s+marketplace|\.de|\s+payments)?\b",), ("shopping", "online")),
    _Rule("drugstore", "personal_care:drugstore", "outflow", (r"\b(dm[-\s]?drogerie|drogerie\s+markt|rossmann|mueller\s+drogerie|müller\s+drogerie)\b", r"\bdm\b"), ("drugstore",)),
    _Rule("kiosk_convenience", "shopping:convenience", "outflow", (r"\b(kiosk|spaeti|späti)\b",), ("convenience",)),
    _Rule("fees_bank", "fees:bank", "outflow", (r"\b(fee|gebuehr|gebühr|kontofuehrung|kontoführung)\b",), ("fee",)),
    _Rule("tax", "tax:income_tax", "outflow", (r"\b(finanzamt|tax|steuer)\b",), ("tax",)),
    _Rule("groceries", "groceries", "outflow", (r"\b(lidl|aldi|rewe|edeka|kaufland|netto|penny|supermarkt|grocery|groceries)\b",), ("grocery",)),
)


def categorize_transaction(
    *,
    merchant_name: str | None,
    source_id: str | None,
    source_kind: str | None,
    source_account_ref: str | None = None,
    total_gross_cents: int = 0,
    items: Iterable[TransactionItem] = (),
) -> FinanceCategoryResult:
    text = " ".join(
        part
        for part in [
            merchant_name or "",
            source_id or "",
            source_kind or "",
            source_account_ref or "",
            " ".join(item.name for item in items),
        ]
        if part
    ).casefold()
    for rule in RULES:
        if rule.matches(text):
            return FinanceCategoryResult(
                direction=rule.direction,
                category_id=rule.category_id,
                method="rule",
                confidence=rule.confidence,
                source_value=rule.rule_id,
                tags=rule.tags,
            )
    if total_gross_cents < 0:
        return FinanceCategoryResult("inflow", "income:other", "fallback", 0.5, "negative_amount")
    return FinanceCategoryResult("outflow", "other", "fallback", 0.45, "fallback_other")


def apply_transaction_category(
    transaction: Transaction,
    *,
    session: Session | None = None,
    source_kind: str | None = None,
    source_account_ref: str | None = None,
    force: bool = False,
) -> FinanceCategoryResult:
    if (
        not force
        and transaction.finance_category_method in _MANUAL_METHODS
        and transaction.finance_category_id
    ):
        return FinanceCategoryResult(
            direction=transaction.direction or "outflow",
            category_id=transaction.finance_category_id,
            method=transaction.finance_category_method,
            confidence=float(transaction.finance_category_confidence or 1),
            source_value=transaction.finance_category_source_value or "manual",
            tags=tuple(transaction.finance_tags_json or []),
        )
    if session is not None:
        rule_result = _category_from_learned_rule(session, transaction)
        if rule_result is not None:
            static_result = categorize_transaction(
                merchant_name=transaction.merchant_name,
                source_id=transaction.source_id,
                source_kind=source_kind or (transaction.source.kind if transaction.source else None),
                source_account_ref=source_account_ref,
                total_gross_cents=transaction.total_gross_cents,
                items=transaction.items,
            )
            if _should_prefer_static_rule(static_result, rule_result):
                _apply_finance_result(transaction, static_result)
                return static_result
            _apply_finance_result(transaction, rule_result)
            return rule_result
    result = categorize_transaction(
        merchant_name=transaction.merchant_name,
        source_id=transaction.source_id,
        source_kind=source_kind or (transaction.source.kind if transaction.source else None),
        source_account_ref=source_account_ref,
        total_gross_cents=transaction.total_gross_cents,
        items=transaction.items,
    )
    _apply_finance_result(transaction, result)
    return result


def recategorize_finance_transactions(
    session: Session,
    *,
    config: AppConfig | None = None,
    force: bool = False,
    only_uncategorized: bool = False,
    transaction_ids: Sequence[str] | None = None,
    require_model_runtime: bool = False,
) -> dict[str, int]:
    ensure_finance_taxonomy(session)
    stmt = select(Transaction).options(selectinload(Transaction.items), selectinload(Transaction.source))
    if transaction_ids:
        stmt = stmt.where(Transaction.id.in_(list(transaction_ids)))
    rows = session.execute(stmt).scalars().all()
    updated = 0
    skipped_manual = 0
    model_candidates: list[Transaction] = []
    for transaction in rows:
        if (
            not force
            and transaction.finance_category_method in _MANUAL_METHODS
            and transaction.finance_category_id
        ):
            skipped_manual += 1
            continue
        if only_uncategorized and not _is_uncategorized_finance_transaction(transaction):
            continue
        previous = (
            transaction.direction,
            transaction.finance_category_id,
            transaction.finance_category_method,
            transaction.finance_category_confidence,
        )
        apply_transaction_category(transaction, session=session, force=force)
        if _is_fallback_category(transaction.finance_category_id):
            model_candidates.append(transaction)
        if (
            transaction.direction,
            transaction.finance_category_id,
            transaction.finance_category_method,
            transaction.finance_category_confidence,
        ) != previous:
            updated += 1

    model_updated = 0
    if model_candidates:
        predictions = _predict_finance_categories_with_model(
            config=config,
            transactions=model_candidates,
            require_model_runtime=require_model_runtime,
        )
        by_id = {prediction.transaction_id: prediction for prediction in predictions}
        valid_categories = {entry.category_id for entry in FINANCE_CATEGORIES}
        for transaction in model_candidates:
            prediction = by_id.get(transaction.id)
            if prediction is None:
                continue
            category_id = (prediction.category_id or "").strip()
            confidence = prediction.confidence
            if (
                category_id not in valid_categories
                or _is_fallback_category(category_id)
                or confidence is None
                or confidence < 0.55
            ):
                continue
            direction = (prediction.direction or transaction.direction or "outflow").strip()
            if direction not in _VALID_DIRECTIONS:
                direction = transaction.direction or "outflow"
            previous = (
                transaction.direction,
                transaction.finance_category_id,
                transaction.finance_category_method,
                transaction.finance_category_confidence,
            )
            transaction.direction = direction
            transaction.finance_category_id = category_id
            transaction.finance_category_method = "model"
            transaction.finance_category_confidence = Decimal(str(confidence))
            transaction.finance_category_source_value = prediction.reason_code or "categorization_agent"
            transaction.finance_category_version = f"{TRANSACTION_CATEGORIZER_VERSION}:model"
            transaction.finance_tags_json = list(prediction.tags)
            if (
                transaction.direction,
                transaction.finance_category_id,
                transaction.finance_category_method,
                transaction.finance_category_confidence,
            ) != previous:
                model_updated += 1
                updated += 1
                learn_finance_category_rule(
                    session,
                    transaction=transaction,
                    source="model",
                    confidence=confidence,
                    metadata={"reason_code": prediction.reason_code or "categorization_agent"},
                )
    session.flush()
    return {
        "updated": updated,
        "updated_by_model": model_updated,
        "skipped_manual": skipped_manual,
        "total": len(rows),
        "candidates": len(model_candidates),
    }


def learn_finance_category_rule(
    session: Session,
    *,
    transaction: Transaction,
    source: str,
    confidence: float | Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> FinanceCategoryRule | None:
    merchant_name = (transaction.merchant_name or "").strip()
    category_id = (transaction.finance_category_id or "").strip()
    direction = (transaction.direction or "outflow").strip()
    if not merchant_name or _is_fallback_category(category_id) or direction not in _VALID_DIRECTIONS:
        return None
    normalized = _normalize_rule_pattern(merchant_name)
    if not normalized:
        return None
    existing = session.execute(
        select(FinanceCategoryRule).where(
            FinanceCategoryRule.rule_type == "merchant",
            FinanceCategoryRule.normalized_pattern == normalized,
        )
    ).scalar_one_or_none()
    confidence_decimal = Decimal(str(confidence)) if confidence is not None else transaction.finance_category_confidence
    metadata_json = {
        "merchant_name": merchant_name,
        "transaction_id": transaction.id,
        "source_id": transaction.source_id,
        **(metadata or {}),
    }
    if existing is None:
        rule = FinanceCategoryRule(
            rule_type="merchant",
            pattern=merchant_name,
            normalized_pattern=normalized,
            category_id=category_id,
            direction=direction,
            source=source,
            confidence=confidence_decimal,
            hit_count=0,
            enabled=True,
            metadata_json=metadata_json,
        )
        session.add(rule)
        return rule
    existing.pattern = merchant_name
    existing.category_id = category_id
    existing.direction = direction
    existing.source = source
    existing.confidence = confidence_decimal
    existing.enabled = True
    existing.metadata_json = {**(existing.metadata_json or {}), **metadata_json}
    return existing


def _category_from_learned_rule(session: Session, transaction: Transaction) -> FinanceCategoryResult | None:
    merchant_name = (transaction.merchant_name or "").strip()
    normalized = _normalize_rule_pattern(merchant_name)
    if not normalized:
        return None
    rules = session.execute(
        select(FinanceCategoryRule).where(
            FinanceCategoryRule.enabled.is_(True),
            FinanceCategoryRule.rule_type == "merchant",
        )
    ).scalars().all()
    for rule in rules:
        pattern = _normalize_rule_pattern(rule.pattern or rule.normalized_pattern)
        if not pattern:
            continue
        if normalized == pattern or (len(pattern) > 3 and pattern in normalized):
            rule.hit_count = int(rule.hit_count or 0) + 1
            return FinanceCategoryResult(
                direction=rule.direction or "outflow",
                category_id=rule.category_id,
                method="learned_rule",
                confidence=float(rule.confidence or Decimal("0.98")),
                source_value=rule.id,
                tags=(rule.source,),
            )
    return None


def _apply_finance_result(transaction: Transaction, result: FinanceCategoryResult) -> None:
    transaction.direction = result.direction
    transaction.finance_category_id = result.category_id
    transaction.finance_category_method = result.method
    transaction.finance_category_confidence = Decimal(str(result.confidence))
    transaction.finance_category_source_value = result.source_value
    transaction.finance_category_version = TRANSACTION_CATEGORIZER_VERSION
    transaction.finance_tags_json = list(result.tags)


def _normalize_rule_pattern(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()


def _is_fallback_category(category_id: str | None) -> bool:
    return (category_id or "").strip().lower() in _FALLBACK_CATEGORIES


def _is_uncategorized_finance_transaction(transaction: Transaction) -> bool:
    method = (transaction.finance_category_method or "").strip().lower()
    confidence = float(transaction.finance_category_confidence or 0)
    return (
        _is_fallback_category(transaction.finance_category_id)
        or method in {"", "fallback"}
        or confidence <= 0
    )


def _should_prefer_static_rule(static_result: FinanceCategoryResult, learned_result: FinanceCategoryResult) -> bool:
    if static_result.method != "rule" or learned_result.method != "learned_rule":
        return False
    if "manual" in learned_result.tags:
        return False
    if static_result.category_id == learned_result.category_id:
        return False
    trusted_refinement_rules = {
        "amazon_online_retail",
        "catapult_news",
        "substack_publications",
        "fitness_subscription",
        "drugstore",
        "kiosk_convenience",
        "getsafe",
        "credit",
    }
    if static_result.source_value in trusted_refinement_rules:
        return True
    return ":" in static_result.category_id and ":" not in learned_result.category_id


def _predict_finance_categories_with_model(
    *,
    config: AppConfig | None,
    transactions: Sequence[Transaction],
    require_model_runtime: bool,
) -> list[FinanceModelPrediction]:
    if not transactions:
        return []
    if config is None:
        if require_model_runtime:
            raise RuntimeError("categorization runtime is not configured")
        return []
    settings = resolve_item_categorizer_settings(config)
    if not settings.enabled:
        if require_model_runtime:
            raise RuntimeError("categorization runtime is not configured")
        return []

    provider = (getattr(config, "item_categorizer_provider", "") or "").strip()
    payload = {
        "taxonomy": [entry.category_id for entry in FINANCE_CATEGORIES if entry.category_id not in {"other", "uncategorized"}],
        "directions": sorted(_VALID_DIRECTIONS),
        "transactions": [_transaction_model_payload(transaction) for transaction in transactions],
    }
    try:
        if provider == "oauth_codex":
            bearer_token = get_ai_oauth_access_token(config)
            if not bearer_token:
                if require_model_runtime:
                    raise RuntimeError("categorization runtime is not configured")
                return []
            response = complete_text_with_codex_oauth(
                bearer_token=bearer_token,
                model=settings.model,
                instructions=_finance_model_prompt(),
                input_items=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                timeout_s=max(settings.timeout_s, 30.0),
            )
            text = response.text
        else:
            runtime = resolve_model_runtime(config, task=RuntimeTask.ITEM_CATEGORIZATION)
            if runtime is None:
                if require_model_runtime:
                    raise RuntimeError("categorization runtime is not configured")
                return []
            completion = runtime.complete_json(
                JsonCompletionRequest(
                    task=RuntimeTask.ITEM_CATEGORIZATION,
                    system_prompt=_finance_model_prompt(),
                    payload=payload,
                    model=settings.model,
                    temperature=0,
                    max_tokens=max(512, 160 * len(transactions)),
                    timeout_s=max(settings.timeout_s, 30.0),
                    max_retries=settings.max_retries,
                )
            )
            text = completion.text
    except Exception:
        if require_model_runtime:
            raise
        LOGGER.exception("transaction.finance_categorization.model_failed")
        return []
    return _parse_finance_model_predictions(text)


def _transaction_model_payload(transaction: Transaction) -> dict[str, Any]:
    return {
        "transaction_id": transaction.id,
        "merchant_name": transaction.merchant_name,
        "source_id": transaction.source_id,
        "source_kind": transaction.source.kind if transaction.source else None,
        "source_transaction_id": transaction.source_transaction_id,
        "amount_cents": transaction.total_gross_cents,
        "currency": transaction.currency,
        "purchased_at": transaction.purchased_at.isoformat() if transaction.purchased_at else None,
        "current_direction": transaction.direction,
        "current_category_id": transaction.finance_category_id,
        "items": [
            {
                "name": item.name,
                "amount_cents": item.line_total_cents,
                "category": item.category,
            }
            for item in transaction.items[:20]
        ],
    }


def _finance_model_prompt() -> str:
    return (
        "Classify personal finance transactions. Return strict JSON with a top-level "
        "'transactions' array. Each entry must contain transaction_id, direction, category_id, "
        "confidence from 0 to 1, reason_code, and optional tags. Use only the provided taxonomy "
        "category_id values. Prefer specific child categories when evidence supports them. "
        "Investment support is narrow: classify only outflows or transfers toward investments; "
        "do not infer holdings, gains, losses, balances, or performance. Do not invent merchants."
    )


def _parse_finance_model_predictions(text: str) -> list[FinanceModelPrediction]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    raw_predictions = payload.get("transactions") if isinstance(payload, dict) else payload
    if not isinstance(raw_predictions, list):
        return []
    predictions: list[FinanceModelPrediction] = []
    for raw in raw_predictions:
        if not isinstance(raw, dict):
            continue
        transaction_id = str(raw.get("transaction_id") or "").strip()
        if not transaction_id:
            continue
        confidence_raw = raw.get("confidence")
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        tags = raw.get("tags")
        predictions.append(
            FinanceModelPrediction(
                transaction_id=transaction_id,
                direction=str(raw.get("direction") or "").strip() or None,
                category_id=str(raw.get("category_id") or "").strip() or None,
                confidence=confidence,
                reason_code=str(raw.get("reason_code") or "").strip() or None,
                tags=tuple(str(tag).strip() for tag in tags if str(tag).strip()) if isinstance(tags, list) else (),
            )
        )
    return predictions


def register_transaction_categorizer_events() -> None:
    global _EVENTS_REGISTERED
    if _EVENTS_REGISTERED:
        return

    @event.listens_for(Session, "before_flush")
    def _categorize_pending_transactions(
        session: Session,
        _flush_context: object,
        _instances: object,
    ) -> None:
        for obj in session.new.union(session.dirty):
            if not isinstance(obj, Transaction):
                continue
            if obj.finance_category_method in _MANUAL_METHODS and obj.finance_category_id:
                continue
            if obj.finance_category_id and obj.finance_category_method:
                continue
            apply_transaction_category(obj, session=session)

    _EVENTS_REGISTERED = True
