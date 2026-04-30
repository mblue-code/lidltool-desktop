from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.analytics.normalization import (
    load_normalization_bundle,
    normalize_merchant_name,
)
from lidltool.db.audit import record_audit_event
from lidltool.db.engine import session_scope
from lidltool.db.models import DiscountEvent, Source, SourceAccount, Transaction, TransactionItem
from lidltool.ingest.dedupe import canonical_transaction_for_source, compute_fingerprint

MANUAL_SOURCE_ID = "manual_entry"
AGENT_SOURCE_ID = "agent_ingest"


@dataclass(slots=True)
class ManualItemInput:
    name: str
    line_total_cents: int
    qty: Decimal = Decimal("1.0")
    unit: str | None = None
    unit_price_cents: int | None = None
    category: str | None = None
    line_no: int | None = None
    source_item_id: str | None = None
    shared: bool = False
    shared_group_id: str | None = None
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ManualDiscountInput:
    source_label: str
    amount_cents: int
    scope: str = "transaction"
    transaction_item_line_no: int | None = None
    source_discount_code: str | None = None
    kind: str = "manual"
    subkind: str | None = None
    funded_by: str = "unknown"
    is_loyalty_program: bool = False
    raw_payload: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ManualTransactionInput:
    purchased_at: datetime
    merchant_name: str
    total_gross_cents: int
    direction: str = "outflow"
    ledger_scope: str = "household"
    dashboard_include: bool = True
    source_id: str = MANUAL_SOURCE_ID
    source_kind: str = "manual"
    source_display_name: str = "Manual Entries"
    source_account_ref: str | None = "manual"
    source_transaction_id: str | None = None
    idempotency_key: str | None = None
    user_id: str | None = None
    shared_group_id: str | None = None
    currency: str = "EUR"
    discount_total_cents: int | None = None
    allocation_mode: str = "personal"
    confidence: float | None = None
    items: list[ManualItemInput] = field(default_factory=list)
    discounts: list[ManualDiscountInput] = field(default_factory=list)
    raw_payload: dict[str, object] = field(default_factory=dict)
    ingest_channel: str = "manual"


class ManualIngestService:
    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def ingest_transaction(
        self,
        *,
        payload: ManualTransactionInput,
        actor_type: str,
        actor_id: str | None,
        audit_action: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            source, account = _ensure_source_account(
                session,
                source_id=payload.source_id,
                source_kind=payload.source_kind,
                source_display_name=payload.source_display_name,
                source_account_ref=payload.source_account_ref,
                source_user_id=payload.user_id,
                source_shared_group_id=payload.shared_group_id,
            )

            source_transaction_id = _resolve_source_transaction_id(payload)
            existing = canonical_transaction_for_source(
                session,
                source_id=source.id,
                source_transaction_id=source_transaction_id,
            )
            if existing is not None:
                record_audit_event(
                    session,
                    action=audit_action,
                    source=source.id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    entity_type="transaction",
                    entity_id=existing.id,
                    details={
                        "reused": True,
                        "ingest_channel": payload.ingest_channel,
                        "source_transaction_id": source_transaction_id,
                        "reason": reason,
                    },
                )
                return _result_payload(
                    transaction=existing,
                    source_transaction_id=source_transaction_id,
                    reused=True,
                )

            merchant_name = _normalize_merchant_name(
                session,
                source_id=source.id,
                merchant_name=payload.merchant_name,
            )
            fingerprint = compute_fingerprint(
                purchased_at=_to_utc(payload.purchased_at).isoformat(),
                total_cents=payload.total_gross_cents,
                item_names=[item.name for item in payload.items],
            )
            discount_total_cents = payload.discount_total_cents
            if discount_total_cents is None and payload.discounts:
                discount_total_cents = sum(discount.amount_cents for discount in payload.discounts)

            merged_raw_payload = dict(payload.raw_payload)
            merged_raw_payload["ingest_channel"] = payload.ingest_channel
            if payload.idempotency_key:
                merged_raw_payload["idempotency_key"] = payload.idempotency_key
            if reason:
                merged_raw_payload["ingest_reason"] = reason
            target_shared_group_id = payload.shared_group_id or source.shared_group_id
            if payload.allocation_mode in {"shared_receipt", "split_items"} and not target_shared_group_id:
                raise ValueError("shared allocations require a shared_group_id")
            transaction_shared_group_id = (
                target_shared_group_id if payload.allocation_mode == "shared_receipt" else None
            )

            transaction = Transaction(
                source_id=source.id,
                user_id=payload.user_id,
                shared_group_id=transaction_shared_group_id,
                source_account_id=account.id,
                source_transaction_id=source_transaction_id,
                purchased_at=_to_utc(payload.purchased_at),
                merchant_name=merchant_name,
                total_gross_cents=payload.total_gross_cents,
                direction=_normalize_direction(payload.direction),
                ledger_scope=_normalize_ledger_scope(payload.ledger_scope),
                dashboard_include=bool(payload.dashboard_include),
                currency=payload.currency.upper().strip() or "EUR",
                discount_total_cents=discount_total_cents,
                confidence=_to_decimal(payload.confidence),
                fingerprint=fingerprint,
                raw_payload=merged_raw_payload,
            )
            session.add(transaction)
            session.flush()

            item_id_by_line_no: dict[int, str] = {}
            for idx, item in enumerate(payload.items, start=1):
                line_no = item.line_no if item.line_no is not None else idx
                if line_no in item_id_by_line_no:
                    raise ValueError(f"duplicate item line_no: {line_no}")
                source_item_id = item.source_item_id or f"{source_transaction_id}:{line_no}"
                item_shared_group_id = transaction.shared_group_id
                if item_shared_group_id is None and payload.allocation_mode == "split_items" and item.shared:
                    item_shared_group_id = item.shared_group_id or target_shared_group_id
                row = TransactionItem(
                    transaction_id=transaction.id,
                    shared_group_id=item_shared_group_id,
                    source_item_id=source_item_id,
                    line_no=line_no,
                    name=item.name,
                    qty=item.qty,
                    unit=item.unit,
                    unit_price_cents=item.unit_price_cents,
                    line_total_cents=item.line_total_cents,
                    category=item.category,
                    confidence=None,
                    raw_payload=item.raw_payload,
                )
                session.add(row)
                session.flush()
                item_id_by_line_no[line_no] = row.id

            for discount in payload.discounts:
                transaction_item_id: str | None = None
                if discount.scope == "item":
                    if discount.transaction_item_line_no is None:
                        raise ValueError("item-scope discount requires transaction_item_line_no")
                    transaction_item_id = item_id_by_line_no.get(discount.transaction_item_line_no)
                    if transaction_item_id is None:
                        raise ValueError(
                            "discount transaction_item_line_no does not match any item"
                        )

                session.add(
                    DiscountEvent(
                        transaction_id=transaction.id,
                        transaction_item_id=transaction_item_id,
                        source=source.id,
                        source_discount_code=discount.source_discount_code,
                        source_label=discount.source_label,
                        scope=discount.scope,
                        amount_cents=discount.amount_cents,
                        currency=payload.currency.upper().strip() or "EUR",
                        kind=discount.kind,
                        subkind=discount.subkind,
                        funded_by=discount.funded_by,
                        is_loyalty_program=discount.is_loyalty_program,
                        confidence=None,
                        raw_payload=discount.raw_payload,
                    )
                )

            record_audit_event(
                session,
                action=audit_action,
                source=source.id,
                actor_type=actor_type,
                actor_id=actor_id,
                entity_type="transaction",
                entity_id=transaction.id,
                details={
                    "reused": False,
                    "ingest_channel": payload.ingest_channel,
                    "source_transaction_id": source_transaction_id,
                    "items_count": len(payload.items),
                    "discounts_count": len(payload.discounts),
                    "reason": reason,
                },
            )
            session.flush()
            return _result_payload(
                transaction=transaction,
                source_transaction_id=source_transaction_id,
                reused=False,
            )


def _result_payload(
    *,
    transaction: Transaction,
    source_transaction_id: str,
    reused: bool,
) -> dict[str, Any]:
    return {
        "transaction_id": transaction.id,
        "source_id": transaction.source_id,
        "source_transaction_id": source_transaction_id,
        "reused": reused,
    }


def _resolve_source_transaction_id(payload: ManualTransactionInput) -> str:
    explicit = (payload.source_transaction_id or "").strip()
    if explicit:
        return explicit

    if payload.idempotency_key:
        digest = hashlib.sha256(payload.idempotency_key.encode("utf-8")).hexdigest()[:20]
        return f"manual-idem:{digest}"

    base = {
        "purchased_at": _to_utc(payload.purchased_at).isoformat(),
        "merchant_name": payload.merchant_name.strip(),
        "total_gross_cents": payload.total_gross_cents,
        "currency": payload.currency.upper().strip() or "EUR",
        "items": [
            {
                "name": item.name,
                "line_total_cents": item.line_total_cents,
                "qty": str(item.qty),
            }
            for item in payload.items
        ],
    }
    digest = hashlib.sha256(
        json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"manual-hash:{digest}"


def _normalize_merchant_name(
    session: Session,
    *,
    source_id: str,
    merchant_name: str,
) -> str:
    bundle = load_normalization_bundle(session, source=source_id)
    normalized = normalize_merchant_name(merchant_name, bundle)
    return (normalized or merchant_name).strip()


def _normalize_direction(value: str | None) -> str:
    normalized = (value or "outflow").strip().lower()
    return normalized if normalized in {"outflow", "inflow"} else "outflow"


def _normalize_ledger_scope(value: str | None) -> str:
    normalized = (value or "household").strip().lower()
    return normalized if normalized in {"household", "investment", "internal", "unknown"} else "unknown"


def _ensure_source_account(
    session: Session,
    *,
    source_id: str,
    source_kind: str,
    source_display_name: str,
    source_account_ref: str | None,
    source_user_id: str | None,
    source_shared_group_id: str | None,
) -> tuple[Source, SourceAccount]:
    source = session.get(Source, source_id)
    if source is None:
        source = Source(
            id=source_id,
            user_id=source_user_id,
            shared_group_id=source_shared_group_id,
            kind=source_kind,
            display_name=source_display_name,
            status="healthy",
            enabled=True,
        )
        session.add(source)
        session.flush()
    elif source.shared_group_id is None and source_shared_group_id is not None:
        source.shared_group_id = source_shared_group_id

    account_stmt = select(SourceAccount).where(SourceAccount.source_id == source.id)
    if source_account_ref:
        account_stmt = account_stmt.where(SourceAccount.account_ref == source_account_ref)
    account = session.execute(
        account_stmt.order_by(SourceAccount.created_at.asc()).limit(1)
    ).scalar_one_or_none()
    if account is None:
        account = SourceAccount(
            source_id=source.id,
            account_ref=source_account_ref or "default",
            status="connected",
        )
        session.add(account)
        session.flush()

    return source, account


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(f"{value:.3f}")


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
