from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

SUPPORTED_FREQUENCIES = {"weekly", "biweekly", "monthly", "quarterly", "yearly"}


def _step_delta(frequency: str, interval_value: int) -> timedelta | relativedelta:
    if interval_value < 1:
        raise ValueError("interval_value must be >= 1")
    if frequency == "weekly":
        return timedelta(days=7 * interval_value)
    if frequency == "biweekly":
        return timedelta(days=14 * interval_value)
    if frequency == "monthly":
        return relativedelta(months=interval_value)
    if frequency == "quarterly":
        return relativedelta(months=3 * interval_value)
    if frequency == "yearly":
        return relativedelta(years=interval_value)
    raise ValueError(f"unsupported frequency: {frequency}")


def _weekly_step_days(frequency: str, interval_value: int) -> int:
    if frequency == "weekly":
        return 7 * interval_value
    if frequency == "biweekly":
        return 14 * interval_value
    raise ValueError(f"unsupported weekly frequency: {frequency}")


def _monthly_step_months(frequency: str, interval_value: int) -> int:
    if frequency == "monthly":
        return interval_value
    if frequency == "quarterly":
        return 3 * interval_value
    raise ValueError(f"unsupported monthly frequency: {frequency}")


def _jump_to_first_candidate(
    *,
    anchor_date: date,
    from_date: date,
    frequency: str,
    interval_value: int,
) -> date:
    if anchor_date >= from_date:
        return anchor_date

    if frequency in {"weekly", "biweekly"}:
        step_days = _weekly_step_days(frequency, interval_value)
        diff_days = (from_date - anchor_date).days
        skip_count = max(diff_days // step_days, 0)
        return anchor_date + timedelta(days=skip_count * step_days)

    if frequency in {"monthly", "quarterly"}:
        step_months = _monthly_step_months(frequency, interval_value)
        month_diff = (from_date.year - anchor_date.year) * 12 + (from_date.month - anchor_date.month)
        skip_count = max(month_diff // step_months, 0)
        return anchor_date + relativedelta(months=skip_count * step_months)

    if frequency == "yearly":
        year_diff = from_date.year - anchor_date.year
        skip_count = max(year_diff // interval_value, 0)
        return anchor_date + relativedelta(years=skip_count * interval_value)

    raise ValueError(f"unsupported frequency: {frequency}")


def generate_occurrence_dates(
    *,
    anchor_date: date,
    frequency: str,
    interval_value: int,
    from_date: date,
    to_date: date,
) -> list[date]:
    normalized_frequency = frequency.strip().lower()
    if normalized_frequency not in SUPPORTED_FREQUENCIES:
        raise ValueError(f"unsupported frequency: {frequency}")
    if from_date > to_date:
        return []

    step = _step_delta(normalized_frequency, interval_value)
    cursor = _jump_to_first_candidate(
        anchor_date=anchor_date,
        from_date=from_date,
        frequency=normalized_frequency,
        interval_value=interval_value,
    )
    while cursor < from_date:
        cursor = cursor + step

    dates: list[date] = []
    while cursor <= to_date:
        dates.append(cursor)
        cursor = cursor + step
    return dates
