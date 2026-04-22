from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.analytics.advanced import budget_utilization
from lidltool.analytics.queries import (
    dashboard_category_spend_summary,
    dashboard_merchant_summary,
    dashboard_window_totals,
    grocery_workspace_summary,
)
from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import RecurringBill, RecurringBillOccurrence
from lidltool.goals.service import goals_summary


def _month_window(value: date) -> tuple[datetime, datetime]:
    from_dt = datetime(value.year, value.month, 1, tzinfo=UTC)
    if value.month == 12:
        next_month = datetime(value.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(value.year, value.month + 1, 1, tzinfo=UTC)
    return from_dt, next_month - timedelta(seconds=1)


def build_report_templates(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(to_date, datetime.max.time(), tzinfo=UTC)
    totals = dashboard_window_totals(session, from_date=from_dt, to_date=to_dt, visibility=visibility)
    merchants = dashboard_merchant_summary(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, limit=20
    )
    categories = dashboard_category_spend_summary(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, limit=12
    )
    groceries = grocery_workspace_summary(
        session, from_date=from_dt, to_date=to_dt, visibility=visibility, limit=10
    )
    budget = budget_utilization(
        session,
        year=to_date.year,
        month=to_date.month,
        visibility=visibility,
        user_id=user_id,
    )
    goals = goals_summary(
        session,
        user_id=user_id,
        visibility=visibility,
        from_date=from_date,
        to_date=to_date,
    )
    recurring_rows = (
        session.execute(
            select(RecurringBillOccurrence, RecurringBill)
            .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
            .where(
                RecurringBill.user_id == user_id,
                RecurringBillOccurrence.due_date >= from_date,
                RecurringBillOccurrence.due_date <= to_date,
            )
            .order_by(RecurringBillOccurrence.due_date.asc())
        )
        .all()
    )
    recurring_items = [
        {
            "bill_name": bill.name,
            "due_date": occurrence.due_date.isoformat(),
            "status": occurrence.status,
            "expected_amount_cents": occurrence.expected_amount_cents,
            "actual_amount_cents": occurrence.actual_amount_cents,
        }
        for occurrence, bill in recurring_rows
    ]
    templates = [
        {
            "slug": "monthly-overview",
            "title": "Monthly overview",
            "description": "Top-line spend, categories, and merchant concentration.",
            "format": "json",
            "payload": {
                "period": {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
                "totals": totals,
                "categories": categories,
                "merchants": merchants,
            },
        },
        {
            "slug": "grocery-review",
            "title": "Grocery review",
            "description": "Basket size, category breakdown, and recent grocery receipts.",
            "format": "json",
            "payload": groceries,
        },
        {
            "slug": "budget-health",
            "title": "Budget health",
            "description": "Current month budget posture with goal and recurring bill context.",
            "format": "json",
            "payload": {
                "budget": budget,
                "goals": goals,
                "recurring": recurring_items,
            },
        },
    ]
    return {
        "period": {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
        "count": len(templates),
        "templates": templates,
    }
