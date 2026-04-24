from __future__ import annotations

from datetime import UTC, date, datetime
from statistics import median
from typing import Any

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from lidltool.analytics.scope import VisibilityContext
from lidltool.db.engine import session_scope
from lidltool.db.models import (
    RecurringBill,
    RecurringBillMatch,
    RecurringBillOccurrence,
    Transaction,
)
from lidltool.recurring.matcher import find_match_candidates
from lidltool.recurring.scheduler import SUPPORTED_FREQUENCIES, generate_occurrence_dates
from lidltool.shared_groups.ownership import assign_owner, ownership_filter, resource_belongs_to_workspace

RECURRING_STATUSES = {"upcoming", "due", "paid", "overdue", "skipped", "unmatched"}
RESOLVED_STATUSES = {"paid", "skipped"}
UNRESOLVED_STATUSES = {"upcoming", "due", "overdue", "unmatched"}

_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "upcoming": {"due", "paid", "skipped", "overdue", "unmatched"},
    "due": {"paid", "skipped", "overdue", "unmatched", "upcoming"},
    "unmatched": {"paid", "skipped", "overdue", "due"},
    "overdue": {"paid", "skipped", "unmatched", "due"},
    "paid": {"unmatched"},
    "skipped": {"upcoming", "due"},
}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_statuses(raw_statuses: str | list[str] | None) -> list[str] | None:
    if raw_statuses is None:
        return None
    if isinstance(raw_statuses, str):
        candidates = [value.strip().lower() for value in raw_statuses.split(",")]
    else:
        candidates = [str(value).strip().lower() for value in raw_statuses]
    parsed = [status for status in candidates if status]
    if not parsed:
        return None
    invalid = [status for status in parsed if status not in RECURRING_STATUSES]
    if invalid:
        raise RuntimeError(f"unsupported occurrence status filter: {', '.join(sorted(set(invalid)))}")
    return parsed


def _monthly_factor(frequency: str, interval_value: int) -> float:
    interval = max(interval_value, 1)
    if frequency == "weekly":
        return 52.0 / 12.0 / interval
    if frequency == "biweekly":
        return 26.0 / 12.0 / interval
    if frequency == "monthly":
        return 1.0 / interval
    if frequency == "quarterly":
        return 1.0 / (3.0 * interval)
    if frequency == "yearly":
        return 1.0 / (12.0 * interval)
    return 0.0


def _month_start(any_day: date) -> date:
    return any_day.replace(day=1)


def _month_end(any_day: date) -> date:
    return _month_start(any_day) + relativedelta(months=1) - relativedelta(days=1)


def _default_status_for_due_date(*, due_date: date, today: date) -> str:
    if due_date > today:
        return "upcoming"
    if due_date == today:
        return "due"
    return "overdue"


def _sync_bill_occurrences(
    *,
    session: Session,
    bill: RecurringBill,
    start_date: date,
    end_date: date,
    today: date | None = None,
) -> dict[str, int]:
    if start_date > end_date:
        raise RuntimeError("from_date must be <= to_date")

    effective_today = today or date.today()
    occurrence_dates = generate_occurrence_dates(
        anchor_date=date.fromisoformat(bill.anchor_date),
        frequency=bill.frequency,
        interval_value=bill.interval_value,
        from_date=start_date,
        to_date=end_date,
    )
    existing_rows = (
        session.execute(
            select(RecurringBillOccurrence).where(
                RecurringBillOccurrence.bill_id == bill.id,
                RecurringBillOccurrence.due_date >= start_date,
                RecurringBillOccurrence.due_date <= end_date,
            )
        )
        .scalars()
        .all()
    )
    by_due_date = {occurrence.due_date: occurrence for occurrence in existing_rows}

    created = 0
    updated = 0
    for due_date in occurrence_dates:
        existing = by_due_date.get(due_date)
        if existing is None:
            session.add(
                RecurringBillOccurrence(
                    bill_id=bill.id,
                    due_date=due_date,
                    status=_default_status_for_due_date(due_date=due_date, today=effective_today),
                    expected_amount_cents=bill.amount_cents,
                )
            )
            created += 1
            continue

        changed = False
        if existing.expected_amount_cents != bill.amount_cents:
            existing.expected_amount_cents = bill.amount_cents
            changed = True
        if existing.status in {"upcoming", "due", "overdue"}:
            recomputed = _default_status_for_due_date(due_date=existing.due_date, today=effective_today)
            if recomputed != existing.status:
                existing.status = recomputed
                changed = True
        if changed:
            existing.updated_at = _utcnow()
            updated += 1

    return {"created": created, "updated": updated}


def _default_sync_window_for_bill(
    *,
    session: Session,
    bill: RecurringBill,
    today: date | None = None,
    horizon_months: int = 12,
) -> tuple[date, date]:
    effective_today = today or date.today()
    horizon_start = _month_start(effective_today) - relativedelta(months=1)
    horizon_end = _month_end(
        _month_start(effective_today) + relativedelta(months=max(horizon_months - 1, 0))
    )
    anchor_date = date.fromisoformat(bill.anchor_date)
    min_due_date, max_due_date = session.execute(
        select(
            func.min(RecurringBillOccurrence.due_date),
            func.max(RecurringBillOccurrence.due_date),
        ).where(RecurringBillOccurrence.bill_id == bill.id)
    ).one()

    start_candidates = [horizon_start, _month_start(anchor_date)]
    end_candidates = [horizon_end, _month_end(anchor_date)]
    if min_due_date is not None:
        start_candidates.append(_month_start(min_due_date))
    if max_due_date is not None:
        end_candidates.append(_month_end(max_due_date))

    return min(start_candidates), max(end_candidates)


def sync_recurring_occurrences_for_window(
    *,
    session: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    bill_id: str | None = None,
    include_inactive_bills: bool = False,
    visibility: VisibilityContext | None = None,
) -> dict[str, int]:
    if start_date > end_date:
        raise RuntimeError("from_date must be <= to_date")

    stmt = select(RecurringBill)
    if visibility is not None:
        stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
    else:
        stmt = stmt.where(RecurringBill.user_id == user_id)
    if bill_id is not None:
        stmt = stmt.where(RecurringBill.id == bill_id)
    if not include_inactive_bills:
        stmt = stmt.where(RecurringBill.active.is_(True))

    bills = session.execute(stmt).scalars().all()
    created = 0
    updated = 0
    for bill in bills:
        counts = _sync_bill_occurrences(
            session=session,
            bill=bill,
            start_date=start_date,
            end_date=end_date,
        )
        created += counts["created"]
        updated += counts["updated"]

    if created > 0 or updated > 0:
        session.flush()

    return {"bill_count": len(bills), "created": created, "updated": updated}


class RecurringBillsService:
    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_bills(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        clamped_limit = min(max(limit, 1), 200)
        clamped_offset = max(offset, 0)
        with session_scope(self._session_factory) as session:
            stmt = select(RecurringBill)
            if visibility is not None:
                stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
            else:
                stmt = stmt.where(RecurringBill.user_id == user_id)
            if not include_inactive:
                stmt = stmt.where(RecurringBill.active.is_(True))
            total = int(
                session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
            )
            bills = (
                session.execute(
                    stmt.order_by(RecurringBill.created_at.desc(), RecurringBill.id.desc())
                    .offset(clamped_offset)
                    .limit(clamped_limit)
                )
                .scalars()
                .all()
            )
            return {
                "count": len(bills),
                "total": total,
                "limit": clamped_limit,
                "offset": clamped_offset,
                "items": [self._serialize_bill(bill) for bill in bills],
            }

    def get_bill(
        self,
        *,
        user_id: str,
        bill_id: str,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any] | None:
        with session_scope(self._session_factory) as session:
            bill = self._get_scoped_bill(
                session=session,
                user_id=user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            if bill is None:
                return None
            return self._serialize_bill(bill)

    def create_bill(
        self,
        *,
        user_id: str,
        name: str,
        frequency: str,
        anchor_date: date,
        merchant_canonical: str | None = None,
        merchant_alias_pattern: str | None = None,
        category: str = "uncategorized",
        interval_value: int = 1,
        amount_cents: int | None = None,
        amount_tolerance_pct: float = 0.1,
        currency: str = "EUR",
        active: bool = True,
        notes: str | None = None,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        normalized_frequency = self._normalize_frequency(frequency)
        normalized_name = name.strip()
        if not normalized_name:
            raise RuntimeError("bill name is required")
        if interval_value < 1:
            raise RuntimeError("interval_value must be >= 1")
        if amount_tolerance_pct < 0:
            raise RuntimeError("amount_tolerance_pct must be >= 0")

        with session_scope(self._session_factory) as session:
            bill = RecurringBill(
                user_id=user_id,
                name=normalized_name,
                merchant_canonical=(merchant_canonical.strip() if merchant_canonical else None),
                merchant_alias_pattern=(
                    merchant_alias_pattern.strip() if merchant_alias_pattern else None
                ),
                category=category.strip() if category.strip() else "uncategorized",
                frequency=normalized_frequency,
                interval_value=interval_value,
                amount_cents=amount_cents,
                amount_tolerance_pct=amount_tolerance_pct,
                currency=(currency.strip().upper() or "EUR")[:8],
                anchor_date=anchor_date.isoformat(),
                active=active,
                notes=notes.strip() if notes else None,
            )
            if visibility is not None:
                assign_owner(bill, visibility=visibility, user_id=user_id)
            session.add(bill)
            session.flush()
            if bill.active:
                start_date, end_date = _default_sync_window_for_bill(session=session, bill=bill)
                _sync_bill_occurrences(
                    session=session,
                    bill=bill,
                    start_date=start_date,
                    end_date=end_date,
                )
                session.flush()
            return self._serialize_bill(bill)

    def update_bill(
        self,
        *,
        user_id: str,
        bill_id: str,
        payload: dict[str, Any],
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            bill = self._require_scoped_bill(
                session=session,
                user_id=user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            should_sync_occurrences = False
            if "name" in payload and payload["name"] is not None:
                next_name = str(payload["name"]).strip()
                if not next_name:
                    raise RuntimeError("bill name cannot be empty")
                bill.name = next_name
            if "merchant_canonical" in payload:
                merchant_canonical = payload.get("merchant_canonical")
                bill.merchant_canonical = (
                    str(merchant_canonical).strip() if merchant_canonical else None
                )
            if "merchant_alias_pattern" in payload:
                merchant_alias_pattern = payload.get("merchant_alias_pattern")
                bill.merchant_alias_pattern = (
                    str(merchant_alias_pattern).strip() if merchant_alias_pattern else None
                )
            if "category" in payload and payload["category"] is not None:
                category = str(payload["category"]).strip()
                bill.category = category if category else "uncategorized"
            if "frequency" in payload and payload["frequency"] is not None:
                bill.frequency = self._normalize_frequency(str(payload["frequency"]))
                should_sync_occurrences = True
            if "interval_value" in payload and payload["interval_value"] is not None:
                interval_value = int(payload["interval_value"])
                if interval_value < 1:
                    raise RuntimeError("interval_value must be >= 1")
                bill.interval_value = interval_value
                should_sync_occurrences = True
            if "amount_cents" in payload:
                amount_raw = payload.get("amount_cents")
                if amount_raw is not None and int(amount_raw) < 0:
                    raise RuntimeError("amount_cents must be >= 0")
                bill.amount_cents = int(amount_raw) if amount_raw is not None else None
                should_sync_occurrences = True
            if "amount_tolerance_pct" in payload and payload["amount_tolerance_pct"] is not None:
                tolerance_pct = float(payload["amount_tolerance_pct"])
                if tolerance_pct < 0:
                    raise RuntimeError("amount_tolerance_pct must be >= 0")
                bill.amount_tolerance_pct = tolerance_pct
            if "currency" in payload and payload["currency"] is not None:
                bill.currency = str(payload["currency"]).strip().upper()[:8] or "EUR"
            if "anchor_date" in payload and payload["anchor_date"] is not None:
                parsed_anchor = payload["anchor_date"]
                if isinstance(parsed_anchor, date):
                    bill.anchor_date = parsed_anchor.isoformat()
                else:
                    bill.anchor_date = date.fromisoformat(str(parsed_anchor).strip()).isoformat()
                should_sync_occurrences = True
            if "active" in payload and payload["active"] is not None:
                bill.active = bool(payload["active"])
                should_sync_occurrences = True
            if "notes" in payload:
                notes_raw = payload.get("notes")
                bill.notes = str(notes_raw).strip() if notes_raw else None
            bill.updated_at = _utcnow()
            session.flush()
            if bill.active and should_sync_occurrences:
                start_date, end_date = _default_sync_window_for_bill(session=session, bill=bill)
                _sync_bill_occurrences(
                    session=session,
                    bill=bill,
                    start_date=start_date,
                    end_date=end_date,
                )
                session.flush()
            return self._serialize_bill(bill)

    def delete_bill(
        self,
        *,
        user_id: str,
        bill_id: str,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            bill = self._require_scoped_bill(
                session=session,
                user_id=user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            bill.active = False
            bill.updated_at = _utcnow()
            session.flush()
            return {"deleted": True, "id": bill.id, "active": bill.active}

    def generate_occurrences(
        self,
        *,
        user_id: str,
        bill_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
        horizon_months: int = 6,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            bill = self._require_scoped_bill(
                session=session,
                user_id=user_id,
                visibility=visibility,
                bill_id=bill_id,
            )
            today = date.today()
            start_date = from_date or (_month_start(today) - relativedelta(months=1))
            end_date = to_date or _month_end(
                _month_start(today) + relativedelta(months=max(horizon_months - 1, 0))
            )
            counts = _sync_bill_occurrences(
                session=session,
                bill=bill,
                start_date=start_date,
                end_date=end_date,
                today=today,
            )
            session.flush()
            touched = (
                session.execute(
                    select(RecurringBillOccurrence).where(
                        RecurringBillOccurrence.bill_id == bill.id,
                        RecurringBillOccurrence.due_date >= start_date,
                        RecurringBillOccurrence.due_date <= end_date,
                    )
                )
                .scalars()
                .all()
            )
            touched.sort(key=lambda occurrence: (occurrence.due_date, occurrence.id))
            return {
                "bill_id": bill.id,
                "created": counts["created"],
                "updated": counts["updated"],
                "count": len(touched),
                "items": [self._serialize_occurrence(occurrence) for occurrence in touched],
            }

    def list_occurrences(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
        bill_id: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        status: str | list[str] | None = None,
        include_inactive_bills: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        parsed_statuses = _parse_statuses(status)
        clamped_limit = min(max(limit, 1), 500)
        clamped_offset = max(offset, 0)

        with session_scope(self._session_factory) as session:
            self._roll_occurrence_statuses(session=session, user_id=user_id, visibility=visibility)
            stmt = select(RecurringBillOccurrence).join(
                RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id
            )
            stmt = stmt.options(selectinload(RecurringBillOccurrence.matches))
            if visibility is not None:
                stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
            else:
                stmt = stmt.where(RecurringBill.user_id == user_id)
            if not include_inactive_bills:
                stmt = stmt.where(RecurringBill.active.is_(True))
            if bill_id is not None:
                stmt = stmt.where(RecurringBillOccurrence.bill_id == bill_id)
            if from_date is not None:
                stmt = stmt.where(RecurringBillOccurrence.due_date >= from_date)
            if to_date is not None:
                stmt = stmt.where(RecurringBillOccurrence.due_date <= to_date)
            if parsed_statuses:
                stmt = stmt.where(RecurringBillOccurrence.status.in_(parsed_statuses))

            total = int(
                session.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
            )
            rows = (
                session.execute(
                    stmt.order_by(RecurringBillOccurrence.due_date.asc(), RecurringBillOccurrence.id.asc())
                    .offset(clamped_offset)
                    .limit(clamped_limit)
                )
                .scalars()
                .all()
            )
            return {
                "count": len(rows),
                "total": total,
                "limit": clamped_limit,
                "offset": clamped_offset,
                "items": [self._serialize_occurrence(row) for row in rows],
            }

    def run_matching(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
        bill_id: str | None = None,
        include_unowned_transactions: bool = False,
        auto_match_threshold: float = 0.9,
        review_threshold: float = 0.7,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            self._roll_occurrence_statuses(session=session, user_id=user_id, visibility=visibility)

            occ_stmt = (
                select(RecurringBillOccurrence)
                .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                .where(
                    RecurringBill.active.is_(True),
                    RecurringBillOccurrence.status.in_(UNRESOLVED_STATUSES),
                )
                .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBillOccurrence.id.asc())
            )
            if visibility is not None:
                occ_stmt = occ_stmt.where(ownership_filter(RecurringBill, visibility=visibility))
            else:
                occ_stmt = occ_stmt.where(RecurringBill.user_id == user_id)
            if bill_id is not None:
                occ_stmt = occ_stmt.where(RecurringBillOccurrence.bill_id == bill_id)
            occurrences = session.execute(occ_stmt).scalars().all()
            if not occurrences:
                return {
                    "processed": 0,
                    "auto_matched": 0,
                    "review_candidates": 0,
                    "unmatched": 0,
                    "items": [],
                }

            used_transaction_ids = set(
                session.execute(select(RecurringBillMatch.transaction_id)).scalars().all()
            )

            auto_matched = 0
            review_items: list[dict[str, Any]] = []
            unmatched = 0
            processed = 0

            for occurrence in occurrences:
                bill = session.get(RecurringBill, occurrence.bill_id)
                if bill is None:
                    continue
                processed += 1
                candidates = find_match_candidates(
                    session,
                    bill=bill,
                    occurrence=occurrence,
                    include_unowned_transactions=include_unowned_transactions,
                )
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.transaction_id not in used_transaction_ids
                ]
                if not candidates:
                    if occurrence.status in {"due", "overdue"}:
                        occurrence.status = "unmatched"
                        occurrence.updated_at = _utcnow()
                    unmatched += 1
                    continue

                top = candidates[0]
                if top.score >= auto_match_threshold:
                    tx = session.get(Transaction, top.transaction_id)
                    if tx is None:
                        unmatched += 1
                        continue
                    match = RecurringBillMatch(
                        occurrence_id=occurrence.id,
                        transaction_id=tx.id,
                        match_confidence=top.score,
                        match_method=f"auto:{top.match_method}",
                        matched_at=_utcnow(),
                    )
                    session.add(match)
                    occurrence.status = "paid"
                    occurrence.actual_amount_cents = tx.total_gross_cents
                    occurrence.updated_at = _utcnow()
                    used_transaction_ids.add(tx.id)
                    auto_matched += 1
                    continue

                if top.score >= review_threshold:
                    if occurrence.status in {"due", "overdue"}:
                        occurrence.status = "unmatched"
                        occurrence.updated_at = _utcnow()
                    review_items.append(
                        {
                            "occurrence": self._serialize_occurrence(occurrence),
                            "best_score": top.score,
                            "candidates": [
                                {
                                    "transaction_id": candidate.transaction_id,
                                    "score": candidate.score,
                                    "match_method": candidate.match_method,
                                    "merchant_score": candidate.merchant_score,
                                    "amount_score": candidate.amount_score,
                                    "date_score": candidate.date_score,
                                    "purchased_at": candidate.purchased_at,
                                    "merchant_name": candidate.merchant_name,
                                    "total_gross_cents": candidate.total_gross_cents,
                                }
                                for candidate in candidates[:5]
                            ],
                        }
                    )
                else:
                    if occurrence.status in {"due", "overdue"}:
                        occurrence.status = "unmatched"
                        occurrence.updated_at = _utcnow()
                    unmatched += 1

            session.flush()
            return {
                "processed": processed,
                "auto_matched": auto_matched,
                "review_candidates": len(review_items),
                "unmatched": unmatched,
                "items": review_items,
            }

    def reconcile_occurrence(
        self,
        *,
        user_id: str,
        occurrence_id: str,
        transaction_id: str,
        include_unowned_transactions: bool = False,
        match_confidence: float = 1.0,
        match_method: str = "manual",
        notes: str | None = None,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            occurrence = self._require_scoped_occurrence(
                session=session,
                user_id=user_id,
                visibility=visibility,
                occurrence_id=occurrence_id,
            )
            tx = self._get_scoped_transaction(
                session=session,
                user_id=user_id,
                visibility=visibility,
                transaction_id=transaction_id,
                include_unowned_transactions=include_unowned_transactions,
            )
            if tx is None:
                raise RuntimeError("transaction not found")

            existing = session.execute(
                select(RecurringBillMatch).where(
                    RecurringBillMatch.occurrence_id == occurrence.id,
                    RecurringBillMatch.transaction_id == tx.id,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    RecurringBillMatch(
                        occurrence_id=occurrence.id,
                        transaction_id=tx.id,
                        match_confidence=max(float(match_confidence), 0.0),
                        match_method=match_method.strip() or "manual",
                        matched_at=_utcnow(),
                    )
                )
            occurrence.status = "paid"
            occurrence.actual_amount_cents = tx.total_gross_cents
            if notes is not None:
                occurrence.notes = notes.strip() if notes.strip() else None
            occurrence.updated_at = _utcnow()
            session.flush()
            refreshed = self._require_scoped_occurrence(
                session=session,
                user_id=user_id,
                visibility=visibility,
                occurrence_id=occurrence.id,
            )
            return self._serialize_occurrence(refreshed)

    def skip_occurrence(
        self,
        *,
        user_id: str,
        occurrence_id: str,
        notes: str | None = None,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        return self.update_occurrence_status(
            user_id=user_id,
            visibility=visibility,
            occurrence_id=occurrence_id,
            status="skipped",
            notes=notes,
        )

    def update_occurrence_status(
        self,
        *,
        user_id: str,
        occurrence_id: str,
        status: str,
        notes: str | None = None,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        normalized_status = status.strip().lower()
        if normalized_status not in RECURRING_STATUSES:
            raise RuntimeError(f"unsupported occurrence status: {status}")
        with session_scope(self._session_factory) as session:
            occurrence = self._require_scoped_occurrence(
                session=session,
                user_id=user_id,
                visibility=visibility,
                occurrence_id=occurrence_id,
            )
            self._validate_status_transition(current=occurrence.status, next_status=normalized_status)
            occurrence.status = normalized_status
            if notes is not None:
                occurrence.notes = notes.strip() if notes.strip() else None
            if normalized_status != "paid":
                occurrence.actual_amount_cents = None
            elif occurrence.actual_amount_cents is None:
                occurrence.actual_amount_cents = occurrence.expected_amount_cents
            occurrence.updated_at = _utcnow()
            session.flush()
            return self._serialize_occurrence(occurrence)

    def get_overview(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            today = date.today()
            self._roll_occurrence_statuses(session=session, user_id=user_id, visibility=visibility)

            active_bills = int(
                session.execute(
                    select(func.count())
                    .select_from(RecurringBill)
                    .where(RecurringBill.active.is_(True))
                    .where(
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id
                    )
                ).scalar_one()
            )

            status_counts_rows = session.execute(
                select(RecurringBillOccurrence.status, func.count())
                .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                .where(
                    RecurringBill.active.is_(True),
                )
                .where(
                    ownership_filter(RecurringBill, visibility=visibility)
                    if visibility is not None
                    else RecurringBill.user_id == user_id
                )
                .group_by(RecurringBillOccurrence.status)
            ).all()
            status_counts = {
                status: int(count)
                for status, count in status_counts_rows
            }

            due_this_week = int(
                session.execute(
                    select(func.count())
                    .select_from(RecurringBillOccurrence)
                    .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                    .where(
                        RecurringBill.user_id == user_id,
                        RecurringBill.active.is_(True),
                        RecurringBillOccurrence.status.in_(UNRESOLVED_STATUSES),
                        RecurringBillOccurrence.due_date >= today,
                        RecurringBillOccurrence.due_date <= (today + relativedelta(days=7)),
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id,
                    )
                ).scalar_one()
            )

            overdue = int(
                session.execute(
                    select(func.count())
                    .select_from(RecurringBillOccurrence)
                    .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                    .where(
                        RecurringBill.user_id == user_id,
                        RecurringBill.active.is_(True),
                        RecurringBillOccurrence.status.in_(["overdue", "unmatched"]),
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id,
                    )
                ).scalar_one()
            )

            bills = (
                session.execute(
                    select(RecurringBill).where(
                        RecurringBill.active.is_(True),
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id,
                    )
                )
                .scalars()
                .all()
            )
            monthly_committed_cents = 0
            for bill in bills:
                if bill.amount_cents is None:
                    continue
                factor = _monthly_factor(bill.frequency, bill.interval_value)
                monthly_committed_cents += int(round(float(bill.amount_cents) * factor))

            return {
                "active_bills": active_bills,
                "due_this_week": due_this_week,
                "overdue": overdue,
                "monthly_committed_cents": monthly_committed_cents,
                "status_counts": status_counts,
                "currency": "EUR",
            }

    def get_calendar(
        self,
        *,
        user_id: str,
        year: int,
        month: int,
        include_inactive_bills: bool = False,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        if month < 1 or month > 12:
            raise RuntimeError("month must be between 1 and 12")
        first_day = date(year, month, 1)
        last_day = _month_end(first_day)

        with session_scope(self._session_factory) as session:
            self._roll_occurrence_statuses(session=session, user_id=user_id, visibility=visibility)
            stmt = (
                select(RecurringBillOccurrence, RecurringBill)
                .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                .where(
                    RecurringBillOccurrence.due_date >= first_day,
                    RecurringBillOccurrence.due_date <= last_day,
                )
                .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBill.name.asc())
            )
            if visibility is not None:
                stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
            else:
                stmt = stmt.where(RecurringBill.user_id == user_id)
            if not include_inactive_bills:
                stmt = stmt.where(RecurringBill.active.is_(True))

            rows = session.execute(stmt).all()
            by_day: dict[str, list[dict[str, Any]]] = {}
            for occurrence, bill in rows:
                key = occurrence.due_date.isoformat()
                by_day.setdefault(key, []).append(
                    {
                        "occurrence_id": occurrence.id,
                        "bill_id": bill.id,
                        "bill_name": bill.name,
                        "status": occurrence.status,
                        "expected_amount_cents": occurrence.expected_amount_cents,
                        "actual_amount_cents": occurrence.actual_amount_cents,
                    }
                )

            days = [
                {
                    "date": day,
                    "items": items,
                    "count": len(items),
                    "total_expected_cents": sum(
                        int(item["expected_amount_cents"] or 0) for item in items
                    ),
                }
                for day, items in sorted(by_day.items())
            ]
            return {
                "year": year,
                "month": month,
                "days": days,
                "count": len(days),
            }

    def get_forecast(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
        months: int = 6,
    ) -> dict[str, Any]:
        clamped_months = min(max(months, 1), 24)
        today = date.today()
        start = _month_start(today)
        end = _month_end(start + relativedelta(months=clamped_months - 1))

        with session_scope(self._session_factory) as session:
            bills = (
                session.execute(
                    select(RecurringBill).where(
                        RecurringBill.active.is_(True),
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id,
                    )
                )
                .scalars()
                .all()
            )
            estimate_by_bill: dict[str, int] = {}
            for bill in bills:
                estimate_by_bill[bill.id] = self._estimate_bill_amount_cents(session=session, bill=bill)

            totals_by_month: dict[str, int] = {}
            for offset in range(clamped_months):
                month_date = start + relativedelta(months=offset)
                key = month_date.strftime("%Y-%m")
                totals_by_month[key] = 0

            for bill in bills:
                expected_amount_cents = estimate_by_bill[bill.id]
                if expected_amount_cents <= 0:
                    continue
                dates = generate_occurrence_dates(
                    anchor_date=date.fromisoformat(bill.anchor_date),
                    frequency=bill.frequency,
                    interval_value=bill.interval_value,
                    from_date=start,
                    to_date=end,
                )
                for due_date in dates:
                    key = due_date.strftime("%Y-%m")
                    if key in totals_by_month:
                        totals_by_month[key] += expected_amount_cents

            points = [
                {"period": month_key, "projected_cents": projected_cents, "currency": "EUR"}
                for month_key, projected_cents in sorted(totals_by_month.items())
            ]
            return {
                "months": clamped_months,
                "points": points,
                "total_projected_cents": sum(point["projected_cents"] for point in points),
                "currency": "EUR",
            }

    def get_gaps(
        self,
        *,
        user_id: str,
        visibility: VisibilityContext | None = None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            self._roll_occurrence_statuses(session=session, user_id=user_id, visibility=visibility)
            rows = (
                session.execute(
                    select(RecurringBillOccurrence)
                    .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
                    .where(
                        RecurringBill.active.is_(True),
                        RecurringBillOccurrence.status.in_(["overdue", "unmatched"]),
                        ownership_filter(RecurringBill, visibility=visibility)
                        if visibility is not None
                        else RecurringBill.user_id == user_id,
                    )
                    .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBillOccurrence.id.asc())
                )
                .scalars()
                .all()
            )
            return {
                "count": len(rows),
                "items": [self._serialize_occurrence(row) for row in rows],
            }

    def _serialize_bill(self, bill: RecurringBill) -> dict[str, Any]:
        return {
            "id": bill.id,
            "user_id": bill.user_id,
            "shared_group_id": bill.shared_group_id,
            "workspace_kind": "shared_group" if bill.shared_group_id else "personal",
            "name": bill.name,
            "merchant_canonical": bill.merchant_canonical,
            "merchant_alias_pattern": bill.merchant_alias_pattern,
            "category": bill.category,
            "frequency": bill.frequency,
            "interval_value": bill.interval_value,
            "amount_cents": bill.amount_cents,
            "amount_tolerance_pct": bill.amount_tolerance_pct,
            "currency": bill.currency,
            "anchor_date": bill.anchor_date,
            "active": bill.active,
            "notes": bill.notes,
            "created_at": bill.created_at.isoformat(),
            "updated_at": bill.updated_at.isoformat(),
        }

    def _serialize_occurrence(self, occurrence: RecurringBillOccurrence) -> dict[str, Any]:
        return {
            "id": occurrence.id,
            "bill_id": occurrence.bill_id,
            "due_date": occurrence.due_date.isoformat(),
            "status": occurrence.status,
            "expected_amount_cents": occurrence.expected_amount_cents,
            "actual_amount_cents": occurrence.actual_amount_cents,
            "notes": occurrence.notes,
            "created_at": occurrence.created_at.isoformat(),
            "updated_at": occurrence.updated_at.isoformat(),
            "matches": [self._serialize_match(match) for match in occurrence.matches],
        }

    def _serialize_match(self, match: RecurringBillMatch) -> dict[str, Any]:
        return {
            "id": match.id,
            "occurrence_id": match.occurrence_id,
            "transaction_id": match.transaction_id,
            "match_confidence": match.match_confidence,
            "match_method": match.match_method,
            "matched_at": match.matched_at.isoformat(),
            "created_at": match.created_at.isoformat(),
        }

    def _normalize_frequency(self, frequency: str) -> str:
        normalized = frequency.strip().lower()
        if normalized not in SUPPORTED_FREQUENCIES:
            raise RuntimeError(f"unsupported frequency: {frequency}")
        return normalized

    def _get_scoped_bill(
        self,
        *,
        session: Session,
        user_id: str,
        visibility: VisibilityContext | None,
        bill_id: str,
    ) -> RecurringBill | None:
        stmt = select(RecurringBill).where(RecurringBill.id == bill_id)
        if visibility is not None:
            stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
        else:
            stmt = stmt.where(RecurringBill.user_id == user_id)
        return session.execute(stmt).scalar_one_or_none()

    def _require_scoped_bill(
        self,
        *,
        session: Session,
        user_id: str,
        visibility: VisibilityContext | None,
        bill_id: str,
    ) -> RecurringBill:
        bill = self._get_scoped_bill(
            session=session,
            user_id=user_id,
            visibility=visibility,
            bill_id=bill_id,
        )
        if bill is None:
            raise RuntimeError("recurring bill not found")
        return bill

    def _require_scoped_occurrence(
        self,
        *,
        session: Session,
        user_id: str,
        visibility: VisibilityContext | None,
        occurrence_id: str,
    ) -> RecurringBillOccurrence:
        stmt = (
            select(RecurringBillOccurrence)
            .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
            .where(RecurringBillOccurrence.id == occurrence_id)
        )
        if visibility is not None:
            stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
        else:
            stmt = stmt.where(RecurringBill.user_id == user_id)
        occurrence = session.execute(stmt).scalar_one_or_none()
        if occurrence is None:
            raise RuntimeError("recurring occurrence not found")
        return occurrence

    def _get_scoped_transaction(
        self,
        *,
        session: Session,
        user_id: str,
        visibility: VisibilityContext | None,
        transaction_id: str,
        include_unowned_transactions: bool,
    ) -> Transaction | None:
        stmt = select(Transaction).where(Transaction.id == transaction_id)
        if visibility is not None:
            stmt = stmt.where(
                or_(
                    ownership_filter(Transaction, visibility=visibility),
                    Transaction.shared_group_id.is_(None)
                    & (Transaction.user_id == user_id if not include_unowned_transactions else or_(Transaction.user_id == user_id, Transaction.user_id.is_(None))),
                )
            )
        elif include_unowned_transactions:
            stmt = stmt.where(or_(Transaction.user_id == user_id, Transaction.user_id.is_(None)))
        else:
            stmt = stmt.where(Transaction.user_id == user_id)
        return session.execute(stmt).scalar_one_or_none()

    def _validate_status_transition(self, *, current: str, next_status: str) -> None:
        if current == next_status:
            return
        allowed = _VALID_STATUS_TRANSITIONS.get(current, set())
        if next_status not in allowed:
            raise RuntimeError(f"invalid occurrence status transition: {current} -> {next_status}")

    def _roll_occurrence_statuses(
        self,
        *,
        session: Session,
        user_id: str,
        visibility: VisibilityContext | None,
    ) -> None:
        today = date.today()
        stmt = (
            select(RecurringBillOccurrence)
            .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
            .where(RecurringBillOccurrence.status.in_(UNRESOLVED_STATUSES))
        )
        if visibility is not None:
            stmt = stmt.where(ownership_filter(RecurringBill, visibility=visibility))
        else:
            stmt = stmt.where(RecurringBill.user_id == user_id)
        rows = session.execute(stmt).scalars().all()
        changed = False
        for occurrence in rows:
            next_status = occurrence.status
            if occurrence.due_date > today:
                if occurrence.status in {"due", "overdue"}:
                    next_status = "upcoming"
            elif occurrence.due_date == today:
                if occurrence.status in {"upcoming", "overdue"}:
                    next_status = "due"
            elif occurrence.due_date < today:
                if occurrence.status in {"upcoming", "due"}:
                    next_status = "overdue"

            if next_status != occurrence.status:
                occurrence.status = next_status
                occurrence.updated_at = _utcnow()
                changed = True

        if changed:
            session.flush()

    def _estimate_bill_amount_cents(self, *, session: Session, bill: RecurringBill) -> int:
        if bill.amount_cents is not None:
            return max(int(bill.amount_cents), 0)

        rows = session.execute(
            select(RecurringBillOccurrence.actual_amount_cents)
            .where(
                RecurringBillOccurrence.bill_id == bill.id,
                RecurringBillOccurrence.status == "paid",
                RecurringBillOccurrence.actual_amount_cents.is_not(None),
            )
            .order_by(RecurringBillOccurrence.due_date.desc())
            .limit(12)
        ).scalars().all()
        values = [int(value) for value in rows if value is not None and int(value) > 0]
        if not values:
            expected_rows = session.execute(
                select(RecurringBillOccurrence.expected_amount_cents)
                .where(
                    RecurringBillOccurrence.bill_id == bill.id,
                    RecurringBillOccurrence.expected_amount_cents.is_not(None),
                )
                .order_by(RecurringBillOccurrence.due_date.desc())
                .limit(12)
            ).scalars().all()
            values = [int(value) for value in expected_rows if value is not None and int(value) > 0]
        if not values:
            return 0
        return int(median(values))
