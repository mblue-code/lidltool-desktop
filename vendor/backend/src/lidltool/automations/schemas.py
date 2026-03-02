from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

ALLOWED_RULE_TYPES = {
    "category_auto_tagging",
    "budget_alert",
    "weekly_summary",
    "recurring_due_soon_alert",
    "recurring_overdue_alert",
    "recurring_amount_spike_alert",
}


def normalize_rule_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in ALLOWED_RULE_TYPES:
        raise ValueError(f"unsupported rule_type: {value}")
    return normalized


def _as_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def validate_trigger_config(value: dict[str, Any] | None) -> dict[str, Any]:
    trigger = _as_dict(value)
    schedule = trigger.get("schedule")
    if schedule is None:
        schedule = {}
    if not isinstance(schedule, dict):
        raise ValueError("trigger_config.schedule must be an object")
    interval_seconds = int(schedule.get("interval_seconds", 3600))
    if interval_seconds < 60:
        raise ValueError("trigger_config.schedule.interval_seconds must be >= 60")
    out: dict[str, Any] = {"schedule": {"interval_seconds": interval_seconds}}
    merchant_contains = trigger.get("merchant_contains")
    if merchant_contains is not None:
        out["merchant_contains"] = str(merchant_contains).strip()
    min_total_cents = trigger.get("min_total_cents")
    if min_total_cents is not None:
        out["min_total_cents"] = int(min_total_cents)
    return out


def validate_action_config(rule_type: str, value: dict[str, Any] | None) -> dict[str, Any]:
    action = _as_dict(value)
    out: dict[str, Any] = {}
    if rule_type == "category_auto_tagging":
        pattern = str(action.get("pattern", "")).strip()
        category = str(action.get("category", "")).strip()
        if not pattern:
            raise ValueError("category_auto_tagging requires action_config.pattern")
        if not category:
            raise ValueError("category_auto_tagging requires action_config.category")
        out["pattern"] = pattern
        out["category"] = category
        out["lookback_days"] = int(action.get("lookback_days", 7))
        return out
    if rule_type == "budget_alert":
        budget_cents = int(action.get("budget_cents", 0))
        if budget_cents <= 0:
            raise ValueError("budget_alert requires action_config.budget_cents > 0")
        out["budget_cents"] = budget_cents
        out["period"] = str(action.get("period", "monthly")).strip().lower()
        if out["period"] not in {"monthly", "yearly"}:
            raise ValueError("budget_alert action_config.period must be monthly or yearly")
        return out
    if rule_type == "weekly_summary":
        out["months_back"] = int(action.get("months_back", 3))
        out["include_breakdown"] = bool(action.get("include_breakdown", True))
        if out["months_back"] < 1:
            raise ValueError("weekly_summary action_config.months_back must be >= 1")
        return out
    if rule_type == "recurring_due_soon_alert":
        out["days_ahead"] = int(action.get("days_ahead", 3))
        if out["days_ahead"] < 1:
            raise ValueError("recurring_due_soon_alert action_config.days_ahead must be >= 1")
        out["include_upcoming"] = bool(action.get("include_upcoming", True))
        return out
    if rule_type == "recurring_overdue_alert":
        out["min_days_overdue"] = int(action.get("min_days_overdue", 1))
        if out["min_days_overdue"] < 1:
            raise ValueError(
                "recurring_overdue_alert action_config.min_days_overdue must be >= 1"
            )
        return out
    if rule_type == "recurring_amount_spike_alert":
        out["spike_pct"] = float(action.get("spike_pct", 0.2))
        out["lookback_occurrences"] = int(action.get("lookback_occurrences", 12))
        if out["spike_pct"] <= 0:
            raise ValueError("recurring_amount_spike_alert action_config.spike_pct must be > 0")
        if out["lookback_occurrences"] < 2:
            raise ValueError(
                "recurring_amount_spike_alert action_config.lookback_occurrences must be >= 2"
            )
        return out
    raise ValueError(f"unsupported rule_type: {rule_type}")


def next_run_at(*, trigger_config: dict[str, Any], from_time: datetime | None = None) -> datetime:
    base = from_time or datetime.now(tz=UTC)
    schedule = trigger_config.get("schedule") if isinstance(trigger_config, dict) else {}
    if not isinstance(schedule, dict):
        schedule = {}
    interval_seconds = int(schedule.get("interval_seconds", 3600))
    return base + timedelta(seconds=max(interval_seconds, 60))
