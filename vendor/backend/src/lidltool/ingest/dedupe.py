from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import DiscountEvent, Receipt, Transaction


def compute_fingerprint(*, purchased_at: str, total_cents: int, item_names: list[str]) -> str:
    payload = {
        "purchased_at": purchased_at,
        "total_cents": total_cents,
        "items": sorted(item_names),
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def receipt_exists(session: Session, receipt_id: str) -> bool:
    return session.get(Receipt, receipt_id) is not None


def fingerprint_exists(session: Session, fingerprint: str) -> bool:
    stmt = select(Receipt.id).where(Receipt.fingerprint == fingerprint).limit(1)
    return session.execute(stmt).first() is not None


def canonical_transaction_for_source(
    session: Session, *, source_id: str, source_transaction_id: str
) -> Transaction | None:
    stmt = (
        select(Transaction)
        .where(
            Transaction.source_id == source_id,
            Transaction.source_transaction_id == source_transaction_id,
        )
        .order_by(Transaction.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def canonical_transaction_for_fingerprint(
    session: Session, *, source_id: str, fingerprint: str
) -> Transaction | None:
    stmt = (
        select(Transaction)
        .where(
            Transaction.source_id == source_id,
            Transaction.fingerprint == fingerprint,
        )
        .order_by(Transaction.created_at.desc())
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def canonical_transaction_exists(
    session: Session, *, source_id: str, source_transaction_id: str
) -> bool:
    return (
        canonical_transaction_for_source(
            session,
            source_id=source_id,
            source_transaction_id=source_transaction_id,
        )
        is not None
    )


def canonical_fingerprint_exists(session: Session, *, source_id: str, fingerprint: str) -> bool:
    return (
        canonical_transaction_for_fingerprint(
            session,
            source_id=source_id,
            fingerprint=fingerprint,
        )
        is not None
    )


def build_discount_event_key(
    *,
    source_id: str,
    source_transaction_id: str,
    source_discount_code: str | None,
    source_label: str,
    amount_cents: int,
    scope: str,
    source_item_ref: str | None,
) -> str:
    payload = {
        "amount_cents": amount_cents,
        "scope": scope,
        "source_discount_code": source_discount_code,
        "source_id": source_id,
        "source_item_ref": source_item_ref,
        "source_label": source_label,
        "source_transaction_id": source_transaction_id,
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def canonical_discount_event_exists(
    session: Session,
    *,
    transaction_id: str,
    transaction_item_id: str | None,
    source: str,
    source_discount_code: str | None,
    source_label: str,
    scope: str,
    amount_cents: int,
) -> bool:
    stmt = select(DiscountEvent.id).where(
        DiscountEvent.transaction_id == transaction_id,
        DiscountEvent.source == source,
        DiscountEvent.source_discount_code == source_discount_code,
        DiscountEvent.source_label == source_label,
        DiscountEvent.scope == scope,
        DiscountEvent.amount_cents == amount_cents,
    )
    if transaction_item_id is None:
        stmt = stmt.where(DiscountEvent.transaction_item_id.is_(None))
    else:
        stmt = stmt.where(DiscountEvent.transaction_item_id == transaction_item_id)
    return session.execute(stmt.limit(1)).first() is not None
