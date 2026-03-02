from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from lidltool.analytics.normalization import (
    NormalizationBundle,
    load_normalization_bundle,
    normalize_merchant_name,
)
from lidltool.db.models import RecurringBill, RecurringBillOccurrence, Transaction


@dataclass(slots=True)
class MatchCandidate:
    transaction_id: str
    score: float
    match_method: str
    merchant_score: float
    amount_score: float
    date_score: float
    purchased_at: str
    merchant_name: str | None
    total_gross_cents: int


def _merchant_score(
    *,
    bill: RecurringBill,
    tx: Transaction,
    normalized_merchant: str | None,
) -> tuple[float, str]:
    canonical = (bill.merchant_canonical or "").strip().lower()
    alias_pattern = (bill.merchant_alias_pattern or "").strip()
    tx_merchant_raw = (tx.merchant_name or "").strip().lower()
    tx_merchant_normalized = (normalized_merchant or "").strip().lower()

    if canonical:
        if tx_merchant_normalized == canonical or tx_merchant_raw == canonical:
            return 1.0, "merchant_canonical_exact"
        if canonical in tx_merchant_normalized or canonical in tx_merchant_raw:
            return 0.75, "merchant_canonical_contains"
        return 0.0, "merchant_canonical_miss"

    if alias_pattern:
        try:
            compiled = re.compile(alias_pattern, re.IGNORECASE)
        except re.error:
            return 0.0, "merchant_alias_invalid"
        if compiled.search(tx.merchant_name or "") or compiled.search(normalized_merchant or ""):
            return 1.0, "merchant_alias_pattern"
        return 0.0, "merchant_alias_miss"

    return 0.5, "merchant_unspecified"


def _amount_score(*, bill: RecurringBill, tx_total_cents: int) -> float:
    if bill.amount_cents is None:
        return 0.8
    expected = bill.amount_cents
    tolerance = max(1, int(abs(expected) * max(float(bill.amount_tolerance_pct), 0.0)))
    diff = abs(tx_total_cents - expected)
    if diff <= tolerance:
        return 1.0
    if diff <= tolerance * 2:
        return 0.6
    if diff <= tolerance * 4:
        return 0.25
    return 0.0


def _date_score(*, due_at: datetime, purchased_at: datetime) -> float:
    diff_days = abs((purchased_at.date() - due_at.date()).days)
    if diff_days <= 1:
        return 1.0
    if diff_days <= 3:
        return 0.8
    if diff_days <= 7:
        return 0.5
    return 0.0


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def find_match_candidates(
    session: Session,
    *,
    bill: RecurringBill,
    occurrence: RecurringBillOccurrence,
    include_unowned_transactions: bool = False,
) -> list[MatchCandidate]:
    due_start = datetime.combine(occurrence.due_date, time.min, tzinfo=UTC)
    window_start = due_start - timedelta(days=7)
    window_end = due_start + timedelta(days=7, hours=23, minutes=59, seconds=59)

    filters = [
        Transaction.purchased_at >= window_start,
        Transaction.purchased_at <= window_end,
    ]
    if include_unowned_transactions:
        filters.append(or_(Transaction.user_id == bill.user_id, Transaction.user_id.is_(None)))
    else:
        filters.append(Transaction.user_id == bill.user_id)

    tx_rows = (
        session.execute(
            select(Transaction)
            .where(*filters)
            .order_by(Transaction.purchased_at.asc(), Transaction.id.asc())
        )
        .scalars()
        .all()
    )

    bundle_by_source: dict[str, NormalizationBundle] = {}
    candidates: list[MatchCandidate] = []
    for tx in tx_rows:
        source_key = tx.source_id
        bundle = bundle_by_source.get(source_key)
        if bundle is None:
            bundle = load_normalization_bundle(session, source=source_key)
            bundle_by_source[source_key] = bundle
        normalized_merchant = normalize_merchant_name(tx.merchant_name, bundle)

        merchant_score, merchant_method = _merchant_score(
            bill=bill,
            tx=tx,
            normalized_merchant=normalized_merchant,
        )
        amount_score = _amount_score(bill=bill, tx_total_cents=tx.total_gross_cents)
        date_score = _date_score(due_at=due_start, purchased_at=_to_utc(tx.purchased_at))
        total_score = (merchant_score * 0.5) + (amount_score * 0.3) + (date_score * 0.2)

        candidates.append(
            MatchCandidate(
                transaction_id=tx.id,
                score=round(total_score, 4),
                match_method=merchant_method,
                merchant_score=round(merchant_score, 4),
                amount_score=round(amount_score, 4),
                date_score=round(date_score, 4),
                purchased_at=_to_utc(tx.purchased_at).isoformat(),
                merchant_name=tx.merchant_name,
                total_gross_cents=tx.total_gross_cents,
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.score,
            candidate.date_score,
            candidate.amount_score,
            candidate.transaction_id,
        ),
        reverse=True,
    )
    return candidates
