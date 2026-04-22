from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lidltool.analytics.queries import dashboard_window_totals
from lidltool.analytics.scope import VisibilityContext, visible_transaction_ids_subquery
from lidltool.db.models import CashflowEntry, Goal, RecurringBillOccurrence, Transaction, TransactionItem

GOAL_TYPES = {
    "monthly_spend_cap",
    "category_spend_cap",
    "savings_target",
    "recurring_bill_reduction",
}


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _normalize_goal_type(goal_type: str) -> str:
    normalized = goal_type.strip().lower()
    if normalized not in GOAL_TYPES:
        raise ValueError(f"unsupported goal_type: {goal_type}")
    return normalized


def _goal_window(goal: Goal, *, from_date: date, to_date: date) -> tuple[date, date]:
    if goal.period == "current_month":
        return to_date.replace(day=1), to_date
    return from_date, to_date


def _serialize_goal(goal: Goal, progress: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": goal.id,
        "user_id": goal.user_id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "target_amount_cents": goal.target_amount_cents,
        "currency": goal.currency,
        "period": goal.period,
        "category": goal.category,
        "merchant_name": goal.merchant_name,
        "recurring_bill_id": goal.recurring_bill_id,
        "target_date": goal.target_date.isoformat() if goal.target_date else None,
        "notes": goal.notes,
        "active": goal.active,
        "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
        "created_at": goal.created_at.isoformat(),
        "updated_at": goal.updated_at.isoformat(),
    }
    if progress is not None:
        payload["progress"] = progress
    return payload


def _goal_progress(
    session: Session,
    *,
    goal: Goal,
    from_date: date,
    to_date: date,
    visibility: VisibilityContext,
) -> dict[str, Any]:
    window_from, window_to = _goal_window(goal, from_date=from_date, to_date=to_date)
    target_cents = max(goal.target_amount_cents, 1)
    current_cents = 0
    unit_label = "spent"

    if goal.goal_type == "savings_target":
        entries = session.execute(
            select(CashflowEntry).where(
                CashflowEntry.user_id == goal.user_id,
                CashflowEntry.effective_date >= window_from,
                CashflowEntry.effective_date <= window_to,
            )
        ).scalars().all()
        inflow_cents = sum(entry.amount_cents for entry in entries if entry.direction == "inflow")
        outflow_cents = sum(entry.amount_cents for entry in entries if entry.direction == "outflow")
        current_cents = max(inflow_cents - outflow_cents, 0)
        unit_label = "saved"
    elif goal.goal_type == "category_spend_cap":
        stmt = (
            select(func.coalesce(func.sum(TransactionItem.line_total_cents), 0))
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .where(
                Transaction.purchased_at >= datetime.combine(window_from, datetime.min.time(), tzinfo=UTC),
                Transaction.purchased_at <= datetime.combine(window_to, datetime.max.time(), tzinfo=UTC),
            )
        )
        stmt = stmt.where(Transaction.id.in_(visible_transaction_ids_subquery(visibility)))
        if goal.category:
            stmt = stmt.where(func.lower(func.coalesce(TransactionItem.category, "")) == goal.category.lower())
        if goal.merchant_name:
            stmt = stmt.where(func.lower(func.coalesce(Transaction.merchant_name, "")) == goal.merchant_name.lower())
        current_cents = int(session.execute(stmt).scalar_one() or 0)
    elif goal.goal_type == "recurring_bill_reduction":
        stmt = select(func.coalesce(func.sum(RecurringBillOccurrence.actual_amount_cents), 0)).where(
            RecurringBillOccurrence.due_date >= window_from,
            RecurringBillOccurrence.due_date <= window_to,
        )
        if goal.recurring_bill_id:
            stmt = stmt.where(RecurringBillOccurrence.bill_id == goal.recurring_bill_id)
        current_cents = int(session.execute(stmt).scalar_one() or 0)
    else:
        totals = dashboard_window_totals(
            session,
            from_date=datetime.combine(window_from, datetime.min.time(), tzinfo=UTC),
            to_date=datetime.combine(window_to, datetime.max.time(), tzinfo=UTC),
            visibility=visibility,
        )
        current_cents = int(totals["net_cents"])

    ratio = round(current_cents / target_cents, 4)
    today = _utcnow().date()
    effective_target_date = goal.target_date or window_to

    if goal.goal_type == "savings_target":
        remaining_cents = max(goal.target_amount_cents - current_cents, 0)
        status = "completed" if current_cents >= goal.target_amount_cents else "on_track"
        if status != "completed" and effective_target_date <= today:
            status = "at_risk"
    else:
        remaining_cents = goal.target_amount_cents - current_cents
        if current_cents > goal.target_amount_cents:
            status = "over_target"
        elif effective_target_date < today and current_cents <= goal.target_amount_cents:
            status = "completed"
        elif ratio >= 0.85:
            status = "at_risk"
        else:
            status = "on_track"

    return {
        "window_from": window_from.isoformat(),
        "window_to": window_to.isoformat(),
        "current_amount_cents": current_cents,
        "target_amount_cents": goal.target_amount_cents,
        "remaining_amount_cents": remaining_cents,
        "progress_ratio": min(max(ratio, 0.0), 2.0),
        "status": status,
        "unit_label": unit_label,
    }


def list_goals(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    from_date: date,
    to_date: date,
    include_inactive: bool = False,
) -> dict[str, Any]:
    stmt = select(Goal).where(Goal.user_id == user_id)
    if not include_inactive:
        stmt = stmt.where(Goal.active.is_(True))
    goals = session.execute(stmt.order_by(Goal.active.desc(), Goal.created_at.asc())).scalars().all()
    items = [
        _serialize_goal(
            goal,
            progress=_goal_progress(
                session,
                goal=goal,
                from_date=from_date,
                to_date=to_date,
                visibility=visibility,
            ),
        )
        for goal in goals
    ]
    return {"count": len(items), "items": items}


def goals_summary(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    listing = list_goals(
        session,
        user_id=user_id,
        visibility=visibility,
        from_date=from_date,
        to_date=to_date,
        include_inactive=False,
    )
    items = listing["items"]
    completed_count = sum(1 for item in items if item["progress"]["status"] == "completed")
    at_risk_count = sum(
        1 for item in items if item["progress"]["status"] in {"at_risk", "over_target"}
    )
    return {
        "count": listing["count"],
        "completed_count": completed_count,
        "at_risk_count": at_risk_count,
        "items": items[:6],
    }


def create_goal(
    session: Session,
    *,
    user_id: str,
    name: str,
    goal_type: str,
    target_amount_cents: int,
    currency: str = "EUR",
    period: str = "current_window",
    category: str | None = None,
    merchant_name: str | None = None,
    recurring_bill_id: str | None = None,
    target_date: date | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    normalized_goal_type = _normalize_goal_type(goal_type)
    goal = Goal(
        user_id=user_id,
        name=name.strip(),
        goal_type=normalized_goal_type,
        target_amount_cents=target_amount_cents,
        currency=currency.strip().upper()[:8] or "EUR",
        period=(period or "current_window").strip() or "current_window",
        category=category.strip() if category else None,
        merchant_name=merchant_name.strip() if merchant_name else None,
        recurring_bill_id=recurring_bill_id,
        target_date=target_date,
        notes=notes.strip() if notes else None,
        active=True,
    )
    session.add(goal)
    session.flush()
    return _serialize_goal(goal)


def update_goal(
    session: Session,
    *,
    user_id: str,
    goal_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    goal = session.get(Goal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise ValueError("goal not found")

    if "name" in payload and payload["name"] is not None:
        goal.name = str(payload["name"]).strip()
    if "goal_type" in payload and payload["goal_type"] is not None:
        goal.goal_type = _normalize_goal_type(str(payload["goal_type"]))
    if "target_amount_cents" in payload and payload["target_amount_cents"] is not None:
        goal.target_amount_cents = int(payload["target_amount_cents"])
    if "currency" in payload and payload["currency"] is not None:
        goal.currency = str(payload["currency"]).strip().upper()[:8] or "EUR"
    if "period" in payload and payload["period"] is not None:
        goal.period = str(payload["period"]).strip() or goal.period
    if "category" in payload:
        goal.category = str(payload["category"]).strip() or None if payload["category"] is not None else None
    if "merchant_name" in payload:
        goal.merchant_name = (
            str(payload["merchant_name"]).strip() or None if payload["merchant_name"] is not None else None
        )
    if "recurring_bill_id" in payload:
        goal.recurring_bill_id = str(payload["recurring_bill_id"]).strip() or None if payload["recurring_bill_id"] is not None else None
    if "target_date" in payload:
        goal.target_date = payload["target_date"]
    if "notes" in payload:
        goal.notes = str(payload["notes"]).strip() or None if payload["notes"] is not None else None
    if "active" in payload and payload["active"] is not None:
        goal.active = bool(payload["active"])

    goal.updated_at = _utcnow()
    session.flush()
    return _serialize_goal(goal)


def delete_goal(
    session: Session,
    *,
    user_id: str,
    goal_id: str,
) -> dict[str, Any]:
    goal = session.get(Goal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise ValueError("goal not found")
    session.delete(goal)
    session.flush()
    return {"deleted": True, "id": goal_id}
