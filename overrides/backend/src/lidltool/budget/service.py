from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lidltool.analytics.advanced import budget_utilization
from lidltool.analytics.queries import dashboard_totals
from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import (
    BudgetMonth,
    CashflowEntry,
    RecurringBill,
    RecurringBillOccurrence,
    Transaction,
)
from lidltool.recurring.service import sync_recurring_occurrences_for_window
from lidltool.shared_groups.ownership import assign_owner, ownership_filter, resource_belongs_to_workspace

_VALID_DIRECTIONS = {"inflow", "outflow"}


def _normalize_cashflow_text(value: str | None) -> str:
    return (value or "").strip()


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _serialize_budget_month(
    budget_month: BudgetMonth | None,
    *,
    year: int,
    month: int,
    user_id: str,
) -> dict[str, Any]:
    if budget_month is None:
        return {
            "id": None,
            "user_id": user_id,
            "shared_group_id": None,
            "workspace_kind": "personal",
            "year": year,
            "month": month,
            "planned_income_cents": None,
            "target_savings_cents": None,
            "opening_balance_cents": None,
            "currency": "EUR",
            "notes": None,
            "created_at": None,
            "updated_at": None,
        }
    return {
        "id": budget_month.id,
        "user_id": budget_month.user_id,
        "shared_group_id": budget_month.shared_group_id,
        "workspace_kind": "shared_group" if budget_month.shared_group_id else "personal",
        "year": budget_month.year,
        "month": budget_month.month,
        "planned_income_cents": budget_month.planned_income_cents,
        "target_savings_cents": budget_month.target_savings_cents,
        "opening_balance_cents": budget_month.opening_balance_cents,
        "currency": budget_month.currency,
        "notes": budget_month.notes,
        "created_at": budget_month.created_at.isoformat(),
        "updated_at": budget_month.updated_at.isoformat(),
    }


def _serialize_cashflow_entry(
    entry: CashflowEntry,
    *,
    linked_transaction: Transaction | None = None,
) -> dict[str, Any]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "shared_group_id": entry.shared_group_id,
        "workspace_kind": "shared_group" if entry.shared_group_id else "personal",
        "effective_date": entry.effective_date.isoformat(),
        "direction": entry.direction,
        "category": entry.category,
        "amount_cents": entry.amount_cents,
        "currency": entry.currency,
        "description": entry.description,
        "source_type": entry.source_type,
        "linked_transaction_id": entry.linked_transaction_id,
        "is_reconciled": entry.linked_transaction_id is not None,
        "linked_transaction": (
            {
                "id": linked_transaction.id,
                "purchased_at": linked_transaction.purchased_at.isoformat(),
                "merchant_name": linked_transaction.merchant_name,
                "total_gross_cents": linked_transaction.total_gross_cents,
                "currency": linked_transaction.currency,
            }
            if linked_transaction is not None
            else None
        ),
        "linked_recurring_occurrence_id": entry.linked_recurring_occurrence_id,
        "notes": entry.notes,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def _normalize_direction(direction: str) -> str:
    normalized = direction.strip().lower()
    if normalized not in _VALID_DIRECTIONS:
        raise ValueError("direction must be one of: inflow, outflow")
    return normalized


def _get_budget_month_row(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext | None,
    year: int,
    month: int,
) -> BudgetMonth | None:
    stmt = select(BudgetMonth).where(BudgetMonth.year == year, BudgetMonth.month == month)
    if visibility is not None:
        stmt = stmt.where(ownership_filter(BudgetMonth, visibility=visibility))
    else:
        stmt = stmt.where(BudgetMonth.user_id == user_id)
    return session.execute(stmt).scalar_one_or_none()


def _resolve_linked_transaction(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext | None,
    linked_transaction_id: str | None,
) -> Transaction | None:
    if linked_transaction_id is None:
        return None
    transaction = session.get(Transaction, linked_transaction_id)
    if transaction is None:
        raise ValueError("linked_transaction_id does not reference an existing transaction")
    if visibility is not None:
        allowed = resource_belongs_to_workspace(
            visibility=visibility,
            resource_user_id=transaction.user_id,
            resource_shared_group_id=transaction.shared_group_id,
        )
        if not allowed:
            raise ValueError("linked_transaction_id is not accessible to the current workspace")
    elif transaction.user_id not in (None, user_id):
        raise ValueError("linked_transaction_id is not accessible to the current user")
    return transaction


def get_budget_month(
    session: Session,
    *,
    user_id: str,
    year: int,
    month: int,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    _month_bounds(year, month)
    return _serialize_budget_month(
        _get_budget_month_row(session, user_id=user_id, visibility=visibility, year=year, month=month),
        year=year,
        month=month,
        user_id=user_id,
    )


def upsert_budget_month(
    session: Session,
    *,
    user_id: str,
    year: int,
    month: int,
    planned_income_cents: int | None = None,
    target_savings_cents: int | None = None,
    opening_balance_cents: int | None = None,
    currency: str = "EUR",
    notes: str | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    _month_bounds(year, month)
    budget_month = _get_budget_month_row(
        session,
        user_id=user_id,
        visibility=visibility,
        year=year,
        month=month,
    )
    if budget_month is None:
        budget_month = BudgetMonth(
            user_id=user_id,
            year=year,
            month=month,
        )
        if visibility is not None:
            assign_owner(budget_month, visibility=visibility, user_id=user_id)
        session.add(budget_month)

    budget_month.planned_income_cents = planned_income_cents
    budget_month.target_savings_cents = target_savings_cents
    budget_month.opening_balance_cents = opening_balance_cents
    budget_month.currency = currency.strip().upper()[:8] or "EUR"
    budget_month.notes = notes.strip() if notes else None
    budget_month.updated_at = _utcnow()
    session.flush()
    return _serialize_budget_month(budget_month, year=year, month=month, user_id=user_id)


def list_cashflow_entries(
    session: Session,
    *,
    user_id: str,
    year: int,
    month: int,
    direction: str | None = None,
    category: str | None = None,
    reconciled: bool | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _month_bounds(year, month)
    stmt = select(CashflowEntry).where(
        CashflowEntry.effective_date >= start,
        CashflowEntry.effective_date < end,
    )
    if visibility is not None:
        stmt = stmt.where(ownership_filter(CashflowEntry, visibility=visibility))
    else:
        stmt = stmt.where(CashflowEntry.user_id == user_id)
    if direction is not None:
        stmt = stmt.where(CashflowEntry.direction == _normalize_direction(direction))
    if category is not None and category.strip():
        stmt = stmt.where(func.lower(CashflowEntry.category) == category.strip().lower())
    if reconciled is True:
        stmt = stmt.where(CashflowEntry.linked_transaction_id.is_not(None))
    elif reconciled is False:
        stmt = stmt.where(CashflowEntry.linked_transaction_id.is_(None))

    rows = (
        session.execute(
            stmt.order_by(CashflowEntry.effective_date.desc(), CashflowEntry.created_at.desc())
        )
        .scalars()
        .all()
    )
    linked_transaction_ids = {row.linked_transaction_id for row in rows if row.linked_transaction_id}
    linked_transactions: dict[str, Transaction] = {}
    if linked_transaction_ids:
        linked_transactions = {
            tx.id: tx
            for tx in session.execute(
                select(Transaction).where(Transaction.id.in_(linked_transaction_ids))
            )
            .scalars()
            .all()
        }
    return {
        "count": len(rows),
        "total": len(rows),
        "items": [
            _serialize_cashflow_entry(
                row,
                linked_transaction=linked_transactions.get(row.linked_transaction_id or ""),
            )
            for row in rows
        ],
    }


def create_cashflow_entry(
    session: Session,
    *,
    user_id: str,
    effective_date: date,
    direction: str,
    category: str,
    amount_cents: int,
    currency: str = "EUR",
    description: str | None = None,
    source_type: str = "manual",
    linked_transaction_id: str | None = None,
    linked_recurring_occurrence_id: str | None = None,
    notes: str | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    normalized_direction = _normalize_direction(direction)
    if amount_cents < 0:
        raise ValueError("amount_cents must be non-negative")
    normalized_category = category.strip() or "uncategorized"
    normalized_currency = currency.strip().upper()[:8] or "EUR"
    normalized_description = _normalize_cashflow_text(description)
    normalized_source_type = source_type.strip() or "manual"
    normalized_notes = _normalize_cashflow_text(notes)
    linked_transaction = _resolve_linked_transaction(
        session,
        user_id=user_id,
        visibility=visibility,
        linked_transaction_id=linked_transaction_id,
    )
    duplicate_stmt = select(CashflowEntry).where(
        CashflowEntry.effective_date == effective_date,
        CashflowEntry.direction == normalized_direction,
        CashflowEntry.category == normalized_category,
        CashflowEntry.amount_cents == int(amount_cents),
        CashflowEntry.currency == normalized_currency,
        CashflowEntry.source_type == normalized_source_type,
    )
    if visibility is not None:
        duplicate_stmt = duplicate_stmt.where(ownership_filter(CashflowEntry, visibility=visibility))
    else:
        duplicate_stmt = duplicate_stmt.where(
            CashflowEntry.user_id == user_id,
            CashflowEntry.shared_group_id.is_(None),
        )
    if linked_transaction_id:
        duplicate_stmt = duplicate_stmt.where(CashflowEntry.linked_transaction_id == linked_transaction_id)
    else:
        duplicate_stmt = duplicate_stmt.where(CashflowEntry.linked_transaction_id.is_(None))
    if linked_recurring_occurrence_id:
        duplicate_stmt = duplicate_stmt.where(
            CashflowEntry.linked_recurring_occurrence_id == linked_recurring_occurrence_id
        )
    else:
        duplicate_stmt = duplicate_stmt.where(CashflowEntry.linked_recurring_occurrence_id.is_(None))
    duplicate_rows = (
        session.execute(duplicate_stmt.order_by(CashflowEntry.created_at.desc()).limit(25))
        .scalars()
        .all()
    )
    for duplicate in duplicate_rows:
        if _normalize_cashflow_text(duplicate.description) != normalized_description:
            continue
        if _normalize_cashflow_text(duplicate.notes) != normalized_notes:
            continue
        return _serialize_cashflow_entry(duplicate, linked_transaction=linked_transaction)

    entry = CashflowEntry(
        user_id=user_id,
        effective_date=effective_date,
        direction=normalized_direction,
        category=normalized_category,
        amount_cents=int(amount_cents),
        currency=normalized_currency,
        description=normalized_description or None,
        source_type=normalized_source_type,
        linked_transaction_id=linked_transaction_id,
        linked_recurring_occurrence_id=linked_recurring_occurrence_id,
        notes=normalized_notes or None,
    )
    if visibility is not None:
        assign_owner(entry, visibility=visibility, user_id=user_id)
    session.add(entry)
    session.flush()
    return _serialize_cashflow_entry(entry, linked_transaction=linked_transaction)


def update_cashflow_entry(
    session: Session,
    *,
    user_id: str,
    entry_id: str,
    payload: dict[str, Any],
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = select(CashflowEntry).where(CashflowEntry.id == entry_id)
    if visibility is not None:
        stmt = stmt.where(ownership_filter(CashflowEntry, visibility=visibility))
    else:
        stmt = stmt.where(CashflowEntry.user_id == user_id)
    entry = session.execute(stmt).scalar_one_or_none()
    if entry is None:
        raise RuntimeError("cashflow entry not found")

    if "effective_date" in payload and payload["effective_date"] is not None:
        raw_date = payload["effective_date"]
        entry.effective_date = raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date))
    if "direction" in payload and payload["direction"] is not None:
        entry.direction = _normalize_direction(str(payload["direction"]))
    if "category" in payload and payload["category"] is not None:
        entry.category = str(payload["category"]).strip() or "uncategorized"
    if "amount_cents" in payload and payload["amount_cents"] is not None:
        amount_cents = int(payload["amount_cents"])
        if amount_cents < 0:
            raise ValueError("amount_cents must be non-negative")
        entry.amount_cents = amount_cents
    if "currency" in payload and payload["currency"] is not None:
        entry.currency = str(payload["currency"]).strip().upper()[:8] or "EUR"
    if "description" in payload:
        description = payload.get("description")
        entry.description = str(description).strip() if description else None
    if "source_type" in payload and payload["source_type"] is not None:
        entry.source_type = str(payload["source_type"]).strip() or "manual"
    if "linked_transaction_id" in payload:
        linked_transaction_id = payload.get("linked_transaction_id")
        linked_transaction = _resolve_linked_transaction(
            session,
            user_id=user_id,
            visibility=visibility,
            linked_transaction_id=str(linked_transaction_id) if linked_transaction_id else None,
        )
        entry.linked_transaction_id = linked_transaction.id if linked_transaction is not None else None
    else:
        linked_transaction = (
            session.get(Transaction, entry.linked_transaction_id)
            if entry.linked_transaction_id is not None
            else None
        )
    if "linked_recurring_occurrence_id" in payload:
        linked_recurring_occurrence_id = payload.get("linked_recurring_occurrence_id")
        entry.linked_recurring_occurrence_id = (
            str(linked_recurring_occurrence_id) if linked_recurring_occurrence_id else None
        )
    if "notes" in payload:
        notes = payload.get("notes")
        entry.notes = str(notes).strip() if notes else None

    entry.updated_at = _utcnow()
    session.flush()
    return _serialize_cashflow_entry(entry, linked_transaction=linked_transaction)


def delete_cashflow_entry(
    session: Session,
    *,
    user_id: str,
    entry_id: str,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = select(CashflowEntry).where(CashflowEntry.id == entry_id)
    if visibility is not None:
        stmt = stmt.where(ownership_filter(CashflowEntry, visibility=visibility))
    else:
        stmt = stmt.where(CashflowEntry.user_id == user_id)
    entry = session.execute(stmt).scalar_one_or_none()
    if entry is None:
        raise RuntimeError("cashflow entry not found")
    session.delete(entry)
    session.flush()
    return {"deleted": True, "id": entry_id}


def monthly_budget_summary(
    session: Session,
    *,
    user_id: str,
    year: int,
    month: int,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _month_bounds(year, month)
    budget_month = _get_budget_month_row(
        session,
        user_id=user_id,
        visibility=visibility,
        year=year,
        month=month,
    )
    budget_month_payload = _serialize_budget_month(
        budget_month,
        year=year,
        month=month,
        user_id=user_id,
    )
    planned_income_cents = int(budget_month.planned_income_cents or 0) if budget_month else 0
    target_savings_cents = int(budget_month.target_savings_cents or 0) if budget_month else 0
    opening_balance_cents = int(budget_month.opening_balance_cents or 0) if budget_month else 0

    actual_income_cents = int(
        session.execute(
            select(func.coalesce(func.sum(CashflowEntry.amount_cents), 0)).where(
                CashflowEntry.direction == "inflow",
                CashflowEntry.effective_date >= start,
                CashflowEntry.effective_date < end,
                ownership_filter(CashflowEntry, visibility=visibility)
                if visibility is not None
                else CashflowEntry.user_id == user_id,
            )
        ).scalar_one()
    )
    manual_outflow_cents = int(
        session.execute(
            select(func.coalesce(func.sum(CashflowEntry.amount_cents), 0)).where(
                CashflowEntry.direction == "outflow",
                CashflowEntry.linked_transaction_id.is_(None),
                CashflowEntry.effective_date >= start,
                CashflowEntry.effective_date < end,
                ownership_filter(CashflowEntry, visibility=visibility)
                if visibility is not None
                else CashflowEntry.user_id == user_id,
            )
        ).scalar_one()
    )

    income_basis = "actual" if actual_income_cents > 0 else "planned"
    income_basis_cents = actual_income_cents if actual_income_cents > 0 else planned_income_cents

    dashboard = dashboard_totals(
        session,
        year=year,
        month=month,
        visibility=visibility,
    )
    receipt_spend_cents = int(dashboard["totals"]["paid_cents"])
    total_outflow_cents = receipt_spend_cents + manual_outflow_cents
    available_cents = opening_balance_cents + income_basis_cents
    remaining_cents = available_cents - total_outflow_cents
    saved_cents = income_basis_cents - total_outflow_cents
    savings_delta_cents = saved_cents - target_savings_cents

    sync_recurring_occurrences_for_window(
        session=session,
        user_id=user_id,
        visibility=visibility,
        start_date=start,
        end_date=end - date.resolution,
    )
    recurring_rows = session.execute(
        select(RecurringBillOccurrence, RecurringBill)
        .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
        .where(
            RecurringBill.active.is_(True),
            RecurringBillOccurrence.due_date >= start,
            RecurringBillOccurrence.due_date < end,
            ownership_filter(RecurringBill, visibility=visibility)
            if visibility is not None
            else RecurringBill.user_id == user_id,
        )
        .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBill.name.asc())
    ).all()
    recurring_items = [
        {
            "occurrence_id": occurrence.id,
            "bill_id": bill.id,
            "bill_name": bill.name,
            "due_date": occurrence.due_date.isoformat(),
            "status": occurrence.status,
            "expected_amount_cents": occurrence.expected_amount_cents,
            "actual_amount_cents": occurrence.actual_amount_cents,
        }
        for occurrence, bill in recurring_rows
    ]
    recurring_expected_cents = sum(int(item["expected_amount_cents"] or 0) for item in recurring_items)
    recurring_paid_cents = sum(
        int(item["actual_amount_cents"] or item["expected_amount_cents"] or 0)
        for item in recurring_items
        if item["status"] == "paid"
    )
    recurring_paid_count = sum(1 for item in recurring_items if item["status"] == "paid")

    budget_rules = budget_utilization(
        session,
        year=year,
        month=month,
        visibility=visibility,
        user_id=user_id,
    )["rows"]

    cashflow_counts = session.execute(
        select(CashflowEntry.direction, func.count())
        .where(
            CashflowEntry.effective_date >= start,
            CashflowEntry.effective_date < end,
            ownership_filter(CashflowEntry, visibility=visibility)
            if visibility is not None
            else CashflowEntry.user_id == user_id,
        )
        .group_by(CashflowEntry.direction)
    ).all()
    counts_by_direction = {direction: int(count) for direction, count in cashflow_counts}
    reconciled_count = int(
        session.execute(
            select(func.count())
            .select_from(CashflowEntry)
            .where(
                CashflowEntry.effective_date >= start,
                CashflowEntry.effective_date < end,
                CashflowEntry.linked_transaction_id.is_not(None),
                ownership_filter(CashflowEntry, visibility=visibility)
                if visibility is not None
                else CashflowEntry.user_id == user_id,
            )
        ).scalar_one()
    )

    return {
        "period": {"year": year, "month": month},
        "month": budget_month_payload,
        "totals": {
            "planned_income_cents": planned_income_cents,
            "actual_income_cents": actual_income_cents,
            "income_basis_cents": income_basis_cents,
            "income_basis": income_basis,
            "target_savings_cents": target_savings_cents,
            "opening_balance_cents": opening_balance_cents,
            "receipt_spend_cents": receipt_spend_cents,
            "manual_outflow_cents": manual_outflow_cents,
            "total_outflow_cents": total_outflow_cents,
            "recurring_expected_cents": recurring_expected_cents,
            "recurring_paid_cents": recurring_paid_cents,
            "available_cents": available_cents,
            "remaining_cents": remaining_cents,
            "saved_cents": saved_cents,
            "savings_delta_cents": savings_delta_cents,
        },
        "budget_rules": budget_rules,
        "recurring": {
            "count": len(recurring_items),
            "paid_count": recurring_paid_count,
            "unpaid_count": len(recurring_items) - recurring_paid_count,
            "items": recurring_items,
        },
        "cashflow": {
            "count": sum(counts_by_direction.values()),
            "inflow_count": counts_by_direction.get("inflow", 0),
            "outflow_count": counts_by_direction.get("outflow", 0),
            "reconciled_count": reconciled_count,
        },
    }
