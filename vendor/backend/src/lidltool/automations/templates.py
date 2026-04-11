from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from lidltool.analytics.queries import dashboard_totals, dashboard_trends
from lidltool.config import AppConfig
from lidltool.db.models import (
    AutomationRule,
    DiscountEvent,
    RecurringBill,
    RecurringBillOccurrence,
    Transaction,
    TransactionItem,
)
from lidltool.offers.service import run_offer_refresh


@dataclass(slots=True)
class TemplateResult:
    status: str
    payload: dict[str, Any]


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def execute_template(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
    config: AppConfig | None = None,
) -> TemplateResult:
    if rule.rule_type == "category_auto_tagging":
        return _category_auto_tagging(session, rule=rule, triggered_at=triggered_at)
    if rule.rule_type == "budget_alert":
        return _budget_alert(session, rule=rule, triggered_at=triggered_at)
    if rule.rule_type == "offer_refresh":
        return _offer_refresh(session, rule=rule, triggered_at=triggered_at, config=config)
    if rule.rule_type == "weekly_summary":
        return _weekly_summary(session, rule=rule, triggered_at=triggered_at)
    if rule.rule_type == "recurring_due_soon_alert":
        return _recurring_due_soon_alert(session, rule=rule, triggered_at=triggered_at)
    if rule.rule_type == "recurring_overdue_alert":
        return _recurring_overdue_alert(session, rule=rule, triggered_at=triggered_at)
    if rule.rule_type == "recurring_amount_spike_alert":
        return _recurring_amount_spike_alert(session, rule=rule, triggered_at=triggered_at)
    raise RuntimeError(f"unknown automation template: {rule.rule_type}")


def _offer_refresh(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
    config: AppConfig | None,
) -> TemplateResult:
    if config is None:
        raise RuntimeError("offer_refresh requires automation service config")
    action = rule.action_config or {}
    result = run_offer_refresh(
        session,
        config=config,
        source_ids=list(action.get("source_ids") or []),
        requested_by_user_id=None,
        trigger_kind="schedule",
        automation_rule_id=rule.id,
        discovery_limit=_coerce_int(action.get("discovery_limit"), 0) or None,
    )
    status = "success" if result["failure_count"] == 0 else ("failed" if result["success_count"] == 0 else "success")
    return TemplateResult(
        status=status,
        payload={
            "template": "offer_refresh",
            "triggered_at": triggered_at.astimezone(UTC).isoformat(),
            "refresh_run": result,
        },
    )


def _category_auto_tagging(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    trigger = rule.trigger_config or {}
    lookback_days = _coerce_int(action.get("lookback_days", 7), 7)
    threshold = trigger.get("min_total_cents")
    merchant_filter = str(trigger.get("merchant_contains", "")).strip().lower()
    pattern = f"%{str(action.get('pattern', '')).strip().lower()}%"
    category = str(action.get("category", "")).strip()
    window_start = triggered_at - timedelta(days=max(lookback_days, 1))

    query = (
        select(TransactionItem)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            Transaction.purchased_at >= window_start,
            Transaction.purchased_at <= triggered_at,
            func.lower(TransactionItem.name).like(pattern),
        )
    )
    filters: list[Any] = []
    if merchant_filter:
        filters.append(
            func.lower(func.coalesce(Transaction.merchant_name, "")).like(f"%{merchant_filter}%")
        )
    if threshold is not None:
        filters.append(Transaction.total_gross_cents >= _coerce_int(threshold, 0))
    if filters:
        query = query.where(and_(*filters))

    items = session.execute(query).scalars().all()
    updated = 0
    for item in items:
        if item.category == category:
            continue
        item.category = category
        updated += 1
    return TemplateResult(
        status="success",
        payload={
            "template": "category_auto_tagging",
            "matched_items": len(items),
            "updated_items": updated,
            "category": category,
            "pattern": action.get("pattern"),
            "lookback_days": lookback_days,
        },
    )


def _budget_alert(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    budget_cents = _coerce_int(action.get("budget_cents", 0), 0)
    period = str(action.get("period", "monthly")).strip().lower()
    year = triggered_at.year
    month = triggered_at.month if period == "monthly" else None
    totals = dashboard_totals(session, year=year, month=month)["totals"]
    paid_cents = int(totals["paid_cents"])
    remaining = budget_cents - paid_cents
    crossed = paid_cents > budget_cents
    status = "success" if crossed else "skipped"
    return TemplateResult(
        status=status,
        payload={
            "template": "budget_alert",
            "period": period,
            "year": year,
            "month": month,
            "budget_cents": budget_cents,
            "spent_cents": paid_cents,
            "remaining_cents": remaining,
            "alert_triggered": crossed,
        },
    )


def _weekly_summary(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    start = triggered_at - timedelta(days=7)
    paid_cents = int(
        session.execute(
            select(func.coalesce(func.sum(Transaction.total_gross_cents), 0)).where(
                Transaction.purchased_at >= start,
                Transaction.purchased_at < triggered_at,
            )
        ).scalar_one()
    )
    saved_cents = int(
        session.execute(
            select(func.coalesce(func.sum(DiscountEvent.amount_cents), 0))
            .join(Transaction, Transaction.id == DiscountEvent.transaction_id)
            .where(
                Transaction.purchased_at >= start,
                Transaction.purchased_at < triggered_at,
            )
        ).scalar_one()
    )
    tx_count = int(
        session.execute(
            select(func.count(Transaction.id)).where(
                Transaction.purchased_at >= start,
                Transaction.purchased_at < triggered_at,
            )
        ).scalar_one()
    )
    trends = dashboard_trends(
        session,
        year=triggered_at.year,
        months_back=_coerce_int(action.get("months_back", 3), 3),
        end_month=triggered_at.month,
    )
    return TemplateResult(
        status="success",
        payload={
            "template": "weekly_summary",
            "window_start": start.astimezone(UTC).isoformat(),
            "window_end": triggered_at.astimezone(UTC).isoformat(),
            "totals": {
                "transactions": tx_count,
                "paid_cents": paid_cents,
                "saved_cents": saved_cents,
            },
            "trends": trends,
        },
    )


def _recurring_due_soon_alert(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    days_ahead = max(_coerce_int(action.get("days_ahead", 3), 3), 1)
    include_upcoming = bool(action.get("include_upcoming", True))
    status_filter = ["due", "upcoming"] if include_upcoming else ["due"]

    today = triggered_at.date()
    window_end = today + timedelta(days=days_ahead)
    rows = session.execute(
        select(RecurringBillOccurrence, RecurringBill)
        .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
        .where(
            RecurringBill.active.is_(True),
            RecurringBillOccurrence.status.in_(status_filter),
            RecurringBillOccurrence.due_date >= today,
            RecurringBillOccurrence.due_date <= window_end,
        )
        .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBill.name.asc())
    ).all()

    payload_items = [
        {
            "occurrence_id": occurrence.id,
            "bill_id": bill.id,
            "bill_name": bill.name,
            "due_date": occurrence.due_date.isoformat(),
            "status": occurrence.status,
            "expected_amount_cents": occurrence.expected_amount_cents,
            "currency": bill.currency,
        }
        for occurrence, bill in rows
    ]
    return TemplateResult(
        status="success" if payload_items else "skipped",
        payload={
            "template": "recurring_due_soon_alert",
            "window_start": today.isoformat(),
            "window_end": window_end.isoformat(),
            "count": len(payload_items),
            "items": payload_items,
            "alert_triggered": len(payload_items) > 0,
        },
    )


def _recurring_overdue_alert(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    min_days_overdue = max(_coerce_int(action.get("min_days_overdue", 1), 1), 1)
    cutoff = triggered_at.date() - timedelta(days=min_days_overdue)
    rows = session.execute(
        select(RecurringBillOccurrence, RecurringBill)
        .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
        .where(
            RecurringBill.active.is_(True),
            RecurringBillOccurrence.status.in_(["overdue", "unmatched"]),
            RecurringBillOccurrence.due_date <= cutoff,
        )
        .order_by(RecurringBillOccurrence.due_date.asc(), RecurringBill.name.asc())
    ).all()
    payload_items = [
        {
            "occurrence_id": occurrence.id,
            "bill_id": bill.id,
            "bill_name": bill.name,
            "due_date": occurrence.due_date.isoformat(),
            "status": occurrence.status,
            "expected_amount_cents": occurrence.expected_amount_cents,
            "days_late": max((triggered_at.date() - occurrence.due_date).days, 0),
            "currency": bill.currency,
        }
        for occurrence, bill in rows
    ]
    return TemplateResult(
        status="success" if payload_items else "skipped",
        payload={
            "template": "recurring_overdue_alert",
            "min_days_overdue": min_days_overdue,
            "count": len(payload_items),
            "items": payload_items,
            "alert_triggered": len(payload_items) > 0,
        },
    )


def _recurring_amount_spike_alert(
    session: Session,
    *,
    rule: AutomationRule,
    triggered_at: datetime,
) -> TemplateResult:
    action = rule.action_config or {}
    spike_pct = float(action.get("spike_pct", 0.2))
    lookback_occurrences = max(_coerce_int(action.get("lookback_occurrences", 12), 12), 2)

    # Keep this template lightweight: look for paid occurrences where actual amount spikes
    # versus expected amount by threshold.
    window_start = triggered_at.date() - timedelta(days=lookback_occurrences * 40)
    rows = session.execute(
        select(RecurringBillOccurrence, RecurringBill)
        .join(RecurringBill, RecurringBill.id == RecurringBillOccurrence.bill_id)
        .where(
            RecurringBill.active.is_(True),
            RecurringBillOccurrence.status == "paid",
            RecurringBillOccurrence.actual_amount_cents.is_not(None),
            RecurringBillOccurrence.expected_amount_cents.is_not(None),
            RecurringBillOccurrence.due_date >= window_start,
            RecurringBillOccurrence.due_date <= date.today(),
        )
        .order_by(RecurringBillOccurrence.due_date.desc(), RecurringBillOccurrence.id.desc())
    ).all()

    alerts: list[dict[str, Any]] = []
    for occurrence, bill in rows[: max(lookback_occurrences * 5, 25)]:
        expected = int(occurrence.expected_amount_cents or 0)
        actual = int(occurrence.actual_amount_cents or 0)
        if expected <= 0:
            continue
        change_pct = (actual - expected) / expected
        if change_pct >= spike_pct:
            alerts.append(
                {
                    "occurrence_id": occurrence.id,
                    "bill_id": bill.id,
                    "bill_name": bill.name,
                    "due_date": occurrence.due_date.isoformat(),
                    "expected_amount_cents": expected,
                    "actual_amount_cents": actual,
                    "change_pct": round(change_pct, 4),
                    "currency": bill.currency,
                }
            )

    return TemplateResult(
        status="success" if alerts else "skipped",
        payload={
            "template": "recurring_amount_spike_alert",
            "spike_pct": spike_pct,
            "lookback_occurrences": lookback_occurrences,
            "count": len(alerts),
            "items": alerts,
            "alert_triggered": len(alerts) > 0,
        },
    )
