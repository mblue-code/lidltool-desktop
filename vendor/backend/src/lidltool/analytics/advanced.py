from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Integer, and_, case, cast, func, select
from sqlalchemy.orm import Session

from lidltool.analytics.scope import (
    VisibilityContext,
    observation_visibility_filter,
    visible_transaction_ids_subquery,
)
from lidltool.db.models import BudgetRule, ItemObservation, Transaction, TransactionItem


def _today() -> date:
    return datetime.now(tz=UTC).date()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _date_window(date_from: date | None, date_to: date | None, default_days: int = 365) -> tuple[date, date]:
    end = date_to or _today()
    start = date_from or (end - timedelta(days=default_days))
    if start > end:
        raise ValueError("date_from must be before or equal to date_to")
    return start, end


def _validate_timing_value(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"net", "gross", "count"}:
        raise ValueError("value must be one of: net, gross, count")
    return normalized


def _normalized_source_kinds(source_kinds: list[str] | None) -> list[str] | None:
    if source_kinds is None:
        return None
    normalized = sorted({source_kind.strip() for source_kind in source_kinds if source_kind.strip()})
    return normalized or None


def _shifted_transaction_datetime_expr(tz_offset_minutes: int) -> Any:
    if tz_offset_minutes == 0:
        return Transaction.purchased_at
    return func.datetime(Transaction.purchased_at, f"{tz_offset_minutes:+d} minutes")


def _timing_hour_expr(shifted_datetime_expr: Any) -> Any:
    return cast(func.strftime("%H", shifted_datetime_expr), Integer)


def _timing_weekday_expr(shifted_datetime_expr: Any) -> Any:
    return (cast(func.strftime("%w", shifted_datetime_expr), Integer) + 6) % 7


def _timing_aggregate_rows(
    session: Session,
    *,
    group_columns: list[Any],
    date_from: date,
    date_to: date,
    value: str,
    source_kinds: list[str] | None,
    tz_offset_minutes: int,
    visibility: VisibilityContext | None,
) -> list[tuple[Any, ...]]:
    shifted_datetime = _shifted_transaction_datetime_expr(tz_offset_minutes)
    shifted_date = func.date(shifted_datetime)
    value_col = (
        ItemObservation.line_total_net_cents
        if value == "net"
        else ItemObservation.line_total_gross_cents
    )
    value_sum = func.coalesce(func.sum(value_col), 0) if value != "count" else cast(0, Integer)

    stmt = (
        select(
            *group_columns,
            value_sum.label("value_cents"),
            func.count(func.distinct(Transaction.id)).label("count"),
        )
        .select_from(ItemObservation)
        .join(Transaction, Transaction.id == ItemObservation.transaction_id)
        .where(
            shifted_date >= date_from.isoformat(),
            shifted_date <= date_to.isoformat(),
        )
        .group_by(*group_columns)
        .order_by(*group_columns)
    )
    if visibility is not None:
        stmt = stmt.where(
            observation_visibility_filter(visibility),
            Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
        )
    if source_kinds:
        stmt = stmt.where(ItemObservation.source_kind.in_(source_kinds))
    return session.execute(stmt).all()


def _zero_filled_hour_points() -> list[dict[str, Any]]:
    return [{"hour": hour, "value_cents": 0, "count": 0, "value": 0} for hour in range(24)]


def _point_value(value_mode: str, *, value_cents: int, count: int) -> int:
    return count if value_mode == "count" else value_cents


def weekday_heatmap(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    source_kinds: list[str] | None = None,
    value: str = "net",
    tz_offset_minutes: int = 0,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to, default_days=365)
    normalized_value = _validate_timing_value(value)
    normalized_source_kinds = _normalized_source_kinds(source_kinds)
    shifted_datetime = _shifted_transaction_datetime_expr(tz_offset_minutes)
    local_date = func.date(shifted_datetime).label("local_date")
    rows = _timing_aggregate_rows(
        session,
        group_columns=[local_date],
        date_from=start,
        date_to=end,
        value=normalized_value,
        source_kinds=normalized_source_kinds,
        tz_offset_minutes=tz_offset_minutes,
        visibility=visibility,
    )

    points: list[dict[str, Any]] = []
    weekday_totals: dict[int, dict[str, int]] = {
        index: {"value_cents": 0, "count": 0} for index in range(7)
    }
    for day_iso, value_cents_raw, count_raw in rows:
        day_obj = date.fromisoformat(str(day_iso))
        weekday_index = day_obj.weekday()
        value_cents = int(value_cents_raw or 0)
        count = int(count_raw or 0)
        value_value = _point_value(normalized_value, value_cents=value_cents, count=count)
        weekday_totals[weekday_index]["value_cents"] += value_cents
        weekday_totals[weekday_index]["count"] += count
        points.append(
            {
                "date": day_obj.isoformat(),
                "weekday": weekday_index,
                "week": int(day_obj.strftime("%V")),
                "value_cents": value_cents,
                "count": count,
                "value": value_value,
            }
        )

    return {
        "value": normalized_value,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "source_kinds": normalized_source_kinds,
        "tz_offset_minutes": tz_offset_minutes,
        "points": sorted(points, key=lambda row: row["date"]),
        "weekday_totals": [
            {
                "weekday": weekday,
                "value_cents": weekday_totals[weekday]["value_cents"],
                "count": weekday_totals[weekday]["count"],
                "value": _point_value(
                    normalized_value,
                    value_cents=weekday_totals[weekday]["value_cents"],
                    count=weekday_totals[weekday]["count"],
                ),
            }
            for weekday in range(7)
        ],
    }


def hour_heatmap(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    source_kind: str | None = None,
    value: str = "net",
    tz_offset_minutes: int = 0,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to, default_days=365)
    normalized_value = _validate_timing_value(value)
    source_kinds = [source_kind] if source_kind else None
    shifted_datetime = _shifted_transaction_datetime_expr(tz_offset_minutes)
    hour_column = _timing_hour_expr(shifted_datetime).label("hour")
    rows = _timing_aggregate_rows(
        session,
        group_columns=[hour_column],
        date_from=start,
        date_to=end,
        value=normalized_value,
        source_kinds=source_kinds,
        tz_offset_minutes=tz_offset_minutes,
        visibility=visibility,
    )

    points = _zero_filled_hour_points()
    total_value_cents = 0
    total_count = 0
    for hour_raw, value_cents_raw, count_raw in rows:
        hour = int(hour_raw)
        value_cents = int(value_cents_raw or 0)
        count = int(count_raw or 0)
        total_value_cents += value_cents
        total_count += count
        points[hour] = {
            "hour": hour,
            "value_cents": value_cents,
            "count": count,
            "value": _point_value(normalized_value, value_cents=value_cents, count=count),
        }

    return {
        "value": normalized_value,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "source_kind": source_kind,
        "tz_offset_minutes": tz_offset_minutes,
        "points": points,
        "totals": {
            "value_cents": total_value_cents,
            "count": total_count,
        },
    }


def timing_matrix(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    source_kind: str | None = None,
    value: str = "net",
    tz_offset_minutes: int = 0,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to, default_days=365)
    normalized_value = _validate_timing_value(value)
    source_kinds = [source_kind] if source_kind else None
    shifted_datetime = _shifted_transaction_datetime_expr(tz_offset_minutes)
    weekday_column = _timing_weekday_expr(shifted_datetime).label("weekday")
    hour_column = _timing_hour_expr(shifted_datetime).label("hour")
    rows = _timing_aggregate_rows(
        session,
        group_columns=[weekday_column, hour_column],
        date_from=start,
        date_to=end,
        value=normalized_value,
        source_kinds=source_kinds,
        tz_offset_minutes=tz_offset_minutes,
        visibility=visibility,
    )

    by_cell: dict[tuple[int, int], dict[str, int]] = {}
    for weekday_raw, hour_raw, value_cents_raw, count_raw in rows:
        weekday = int(weekday_raw)
        hour = int(hour_raw)
        by_cell[(weekday, hour)] = {
            "value_cents": int(value_cents_raw or 0),
            "count": int(count_raw or 0),
        }

    weekday_totals = {
        weekday: {"value_cents": 0, "count": 0}
        for weekday in range(7)
    }
    hour_totals = {
        hour: {"value_cents": 0, "count": 0}
        for hour in range(24)
    }
    grid: list[dict[str, Any]] = []
    grand_total_value_cents = 0
    grand_total_count = 0
    for weekday in range(7):
        for hour in range(24):
            cell = by_cell.get((weekday, hour), {"value_cents": 0, "count": 0})
            value_cents = int(cell["value_cents"])
            count = int(cell["count"])
            weekday_totals[weekday]["value_cents"] += value_cents
            weekday_totals[weekday]["count"] += count
            hour_totals[hour]["value_cents"] += value_cents
            hour_totals[hour]["count"] += count
            grand_total_value_cents += value_cents
            grand_total_count += count
            grid.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "value_cents": value_cents,
                    "count": count,
                    "value": _point_value(normalized_value, value_cents=value_cents, count=count),
                }
            )

    return {
        "value": normalized_value,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "source_kind": source_kind,
        "tz_offset_minutes": tz_offset_minutes,
        "grid": grid,
        "weekday_totals": [
            {
                "weekday": weekday,
                "value_cents": weekday_totals[weekday]["value_cents"],
                "count": weekday_totals[weekday]["count"],
                "value": _point_value(
                    normalized_value,
                    value_cents=weekday_totals[weekday]["value_cents"],
                    count=weekday_totals[weekday]["count"],
                ),
            }
            for weekday in range(7)
        ],
        "hour_totals": [
            {
                "hour": hour,
                "value_cents": hour_totals[hour]["value_cents"],
                "count": hour_totals[hour]["count"],
                "value": _point_value(
                    normalized_value,
                    value_cents=hour_totals[hour]["value_cents"],
                    count=hour_totals[hour]["count"],
                ),
            }
            for hour in range(24)
        ],
        "grand_total": {
            "value_cents": grand_total_value_cents,
            "count": grand_total_count,
        },
    }


def retailer_price_index(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    grain: str = "month",
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to, default_days=365)
    if grain != "month":
        raise ValueError("grain must be month")

    period = func.substr(ItemObservation.date, 1, 7).label("period")
    per_source_product = (
        select(
            period,
            ItemObservation.source_kind.label("source_kind"),
            ItemObservation.product_id.label("product_id"),
            func.avg(ItemObservation.unit_price_net_cents).label("avg_source_price"),
        )
        .where(
            ItemObservation.product_id.is_not(None),
            ItemObservation.date >= start.isoformat(),
            ItemObservation.date <= end.isoformat(),
        )
        .group_by(period, ItemObservation.source_kind, ItemObservation.product_id)
        .subquery()
    )
    if visibility is not None:
        per_source_product = (
            select(
                period,
                ItemObservation.source_kind.label("source_kind"),
                ItemObservation.product_id.label("product_id"),
                func.avg(ItemObservation.unit_price_net_cents).label("avg_source_price"),
            )
            .where(
                ItemObservation.product_id.is_not(None),
                ItemObservation.date >= start.isoformat(),
                ItemObservation.date <= end.isoformat(),
                observation_visibility_filter(visibility),
            )
            .group_by(period, ItemObservation.source_kind, ItemObservation.product_id)
            .subquery()
        )
    global_product = (
        select(
            per_source_product.c.period,
            per_source_product.c.product_id,
            func.avg(per_source_product.c.avg_source_price).label("avg_global_price"),
        )
        .group_by(per_source_product.c.period, per_source_product.c.product_id)
        .subquery()
    )
    indexed = (
        select(
            per_source_product.c.period,
            per_source_product.c.source_kind,
            (
                func.avg(
                    case(
                        (global_product.c.avg_global_price > 0, (per_source_product.c.avg_source_price / global_product.c.avg_global_price) * 100),
                        else_=None,
                    )
                )
            ).label("index_value"),
            func.count(func.distinct(per_source_product.c.product_id)).label("product_count"),
        )
        .join(
            global_product,
            and_(
                global_product.c.period == per_source_product.c.period,
                global_product.c.product_id == per_source_product.c.product_id,
            ),
        )
        .group_by(per_source_product.c.period, per_source_product.c.source_kind)
        .order_by(per_source_product.c.period.asc(), per_source_product.c.source_kind.asc())
    )
    rows = session.execute(indexed).all()
    return {
        "grain": grain,
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "points": [
            {
                "period": str(period_key),
                "source_kind": str(source_kind),
                "index": round(float(index_value or 0), 3),
                "product_count": int(product_count or 0),
            }
            for period_key, source_kind, index_value, product_count in rows
        ],
    }


def basket_compare(
    session: Session,
    *,
    items: list[dict[str, Any]],
    net: bool = True,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    normalized_items: list[dict[str, Any]] = []
    for item in items:
        product_id = str(item.get("product_id") or "").strip()
        if not product_id:
            continue
        quantity = float(item.get("quantity", 1))
        normalized_items.append(
            {
                "product_id": product_id,
                "quantity": max(quantity, 0.0),
            }
        )
    if not normalized_items:
        raise ValueError("basket requires at least one product_id")

    price_col = ItemObservation.unit_price_net_cents if net else ItemObservation.unit_price_gross_cents
    source_map: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total_cents": 0, "covered_items": 0, "missing_items": 0, "line_items": []}
    )
    for basket_item in normalized_items:
        product_id = basket_item["product_id"]
        quantity = basket_item["quantity"]
        per_source_stmt = (
            select(
                ItemObservation.source_kind,
                func.max(ItemObservation.date).label("latest_date"),
            )
            .where(ItemObservation.product_id == product_id)
            .group_by(ItemObservation.source_kind)
        )
        if visibility is not None:
            per_source_stmt = per_source_stmt.where(observation_visibility_filter(visibility))
        per_source_rows = session.execute(per_source_stmt).all()
        row_map: dict[str, int] = {}
        for source_kind, latest_date in per_source_rows:
            price_stmt = (
                select(price_col)
                .where(
                    ItemObservation.product_id == product_id,
                    ItemObservation.source_kind == source_kind,
                    ItemObservation.date == latest_date,
                )
                .order_by(ItemObservation.transaction_id.desc())
                .limit(1)
            )
            if visibility is not None:
                price_stmt = price_stmt.where(observation_visibility_filter(visibility))
            price_row = session.execute(price_stmt).scalar_one_or_none()
            if price_row is None:
                continue
            row_map[str(source_kind)] = int(price_row)

        all_sources_stmt = select(func.distinct(ItemObservation.source_kind))
        if visibility is not None:
            all_sources_stmt = all_sources_stmt.where(observation_visibility_filter(visibility))
        all_sources = {
            str(source_kind)
            for source_kind in session.execute(all_sources_stmt).scalars().all()
        }
        for source_kind in all_sources:
            source_bucket = source_map[source_kind]
            price = row_map.get(source_kind)
            if price is None:
                source_bucket["missing_items"] += 1
                source_bucket["line_items"].append(
                    {
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit_price_cents": None,
                        "line_total_cents": None,
                        "missing": True,
                    }
                )
                continue
            line_total = int(round(price * quantity))
            source_bucket["total_cents"] += line_total
            source_bucket["covered_items"] += 1
            source_bucket["line_items"].append(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price_cents": price,
                    "line_total_cents": line_total,
                    "missing": False,
                }
            )

    rows = sorted(
        [
            {
                "source_kind": source_kind,
                "total_cents": int(bucket["total_cents"]),
                "covered_items": int(bucket["covered_items"]),
                "missing_items": int(bucket["missing_items"]),
                "coverage_rate": (
                    round(float(bucket["covered_items"]) / len(normalized_items), 6)
                    if normalized_items
                    else 0.0
                ),
                "line_items": bucket["line_items"],
            }
            for source_kind, bucket in source_map.items()
        ],
        key=lambda row: (row["missing_items"], row["total_cents"]),
    )
    return {
        "net": net,
        "basket_items": normalized_items,
        "retailers": rows,
    }


def list_budget_rules(session: Session, *, user_id: str | None = None) -> dict[str, Any]:
    stmt = select(BudgetRule)
    if user_id is not None:
        stmt = stmt.where(BudgetRule.user_id == user_id)
    rows = session.execute(stmt.order_by(BudgetRule.created_at.desc())).scalars().all()
    return {
        "items": [
            {
                "rule_id": row.rule_id,
                "user_id": row.user_id,
                "scope_type": row.scope_type,
                "scope_value": row.scope_value,
                "period": row.period,
                "amount_cents": row.amount_cents,
                "currency": row.currency,
                "active": row.active,
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ],
        "count": len(rows),
    }


def create_budget_rule(
    session: Session,
    *,
    user_id: str,
    scope_type: str,
    scope_value: str,
    period: str,
    amount_cents: int,
    currency: str = "EUR",
    active: bool = True,
) -> dict[str, Any]:
    if scope_type not in {"category", "source_kind"}:
        raise ValueError("scope_type must be one of: category, source_kind")
    if period not in {"monthly", "annual"}:
        raise ValueError("period must be one of: monthly, annual")
    rule = BudgetRule(
        user_id=user_id,
        scope_type=scope_type,
        scope_value=scope_value.strip(),
        period=period,
        amount_cents=int(amount_cents),
        currency=currency.strip() or "EUR",
        active=active,
    )
    session.add(rule)
    session.flush()
    return {
        "rule_id": rule.rule_id,
        "user_id": rule.user_id,
        "scope_type": rule.scope_type,
        "scope_value": rule.scope_value,
        "period": rule.period,
        "amount_cents": rule.amount_cents,
        "currency": rule.currency,
        "active": rule.active,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def budget_utilization(
    session: Session,
    *,
    year: int | None = None,
    month: int | None = None,
    visibility: VisibilityContext | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    today = _today()
    target_year = year or today.year
    target_month = month or today.month

    rules_stmt = select(BudgetRule).where(BudgetRule.active.is_(True))
    if user_id is not None:
        rules_stmt = rules_stmt.where(BudgetRule.user_id == user_id)
    rules = session.execute(rules_stmt.order_by(BudgetRule.scope_type.asc())).scalars().all()
    rows: list[dict[str, Any]] = []
    for rule in rules:
        if rule.period == "annual":
            period_start = date(target_year, 1, 1)
            period_end = date(target_year + 1, 1, 1)
        else:
            period_start, period_end = _month_bounds(target_year, target_month)
        period_days = (period_end - period_start).days
        elapsed_days = min(max((today - period_start).days + 1, 1), period_days)

        if rule.scope_type == "category":
            spent_stmt = select(func.coalesce(func.sum(ItemObservation.line_total_net_cents), 0)).where(
                ItemObservation.date >= period_start.isoformat(),
                ItemObservation.date < period_end.isoformat(),
                func.lower(func.coalesce(ItemObservation.category, "")) == rule.scope_value.lower(),
            )
            if visibility is not None:
                spent_stmt = spent_stmt.where(observation_visibility_filter(visibility))
            spent = session.execute(spent_stmt).scalar_one()
        else:
            spent_stmt = select(func.coalesce(func.sum(ItemObservation.line_total_net_cents), 0)).where(
                ItemObservation.date >= period_start.isoformat(),
                ItemObservation.date < period_end.isoformat(),
                ItemObservation.source_kind == rule.scope_value,
            )
            if visibility is not None:
                spent_stmt = spent_stmt.where(observation_visibility_filter(visibility))
            spent = session.execute(spent_stmt).scalar_one()
        spent_cents = int(spent or 0)
        projected = int(round((spent_cents / elapsed_days) * period_days))
        utilization = round(spent_cents / rule.amount_cents, 6) if rule.amount_cents > 0 else 0.0
        projected_utilization = (
            round(projected / rule.amount_cents, 6) if rule.amount_cents > 0 else 0.0
        )
        rows.append(
            {
                "rule_id": rule.rule_id,
                "scope_type": rule.scope_type,
                "scope_value": rule.scope_value,
                "period": rule.period,
                "budget_cents": rule.amount_cents,
                "spent_cents": spent_cents,
                "remaining_cents": rule.amount_cents - spent_cents,
                "utilization": utilization,
                "projected_spent_cents": projected,
                "projected_utilization": projected_utilization,
                "over_budget": spent_cents > rule.amount_cents,
                "projected_over_budget": projected > rule.amount_cents,
            }
        )
    return {
        "period": {"year": target_year, "month": target_month},
        "rows": rows,
        "count": len(rows),
    }


def patterns_summary(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _date_window(date_from, date_to, default_days=365)

    tx_stmt = (
        select(
            Transaction.purchased_at,
            Transaction.source_id,
            Transaction.total_gross_cents,
            Transaction.discount_total_cents,
        )
        .where(
            Transaction.purchased_at >= datetime.combine(start, datetime.min.time(), tzinfo=UTC),
            Transaction.purchased_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
        )
        .order_by(Transaction.purchased_at.asc())
    )
    if visibility is not None:
        tx_stmt = tx_stmt.where(Transaction.id.in_(visible_transaction_ids_subquery(visibility)))
    tx_rows = session.execute(tx_stmt).all()
    per_source_dates: dict[str, list[date]] = defaultdict(list)
    basket_totals: list[int] = []
    per_day_spend: dict[str, int] = defaultdict(int)
    for purchased_at, source_id, gross, discount in tx_rows:
        purchased_date = purchased_at.astimezone(UTC).date()
        per_source_dates[str(source_id)].append(purchased_date)
        net_total = int(gross or 0) - int(discount or 0)
        basket_totals.append(net_total)
        per_day_spend[purchased_date.isoformat()] += net_total

    shopping_frequency: list[dict[str, Any]] = []
    for source_id, days in per_source_dates.items():
        sorted_days = sorted(days)
        if len(sorted_days) < 2:
            avg_days = None
        else:
            gaps = [
                (sorted_days[index] - sorted_days[index - 1]).days
                for index in range(1, len(sorted_days))
            ]
            avg_days = round(sum(gaps) / len(gaps), 2) if gaps else None
        shopping_frequency.append(
            {
                "source_id": source_id,
                "purchase_count": len(sorted_days),
                "avg_days_between_shops": avg_days,
            }
        )
    shopping_frequency.sort(key=lambda row: row["purchase_count"], reverse=True)

    bins: list[dict[str, Any]] = [
        {"min": 0, "max": 1000},
        {"min": 1000, "max": 2500},
        {"min": 2500, "max": 5000},
        {"min": 5000, "max": 10000},
        {"min": 10000, "max": None},
    ]
    basket_distribution: list[dict[str, Any]] = []
    for bucket in bins:
        count = 0
        for total in basket_totals:
            if total < bucket["min"]:
                continue
            if bucket["max"] is not None and total >= bucket["max"]:
                continue
            count += 1
        basket_distribution.append(
            {
                "min_cents": bucket["min"],
                "max_cents": bucket["max"],
                "count": count,
            }
        )

    item_counts_stmt = (
        select(
            func.lower(ItemObservation.raw_item_name),
            func.count(),
        )
        .where(
            ItemObservation.date >= start.isoformat(),
            ItemObservation.date <= end.isoformat(),
        )
        .group_by(func.lower(ItemObservation.raw_item_name))
    )
    if visibility is not None:
        item_counts_stmt = item_counts_stmt.where(observation_visibility_filter(visibility))
    item_counts = session.execute(item_counts_stmt).all()
    one_time_items = sum(1 for _, count in item_counts if int(count or 0) == 1)
    unique_items = len(item_counts)

    today_date = _today()
    velocity_points: list[dict[str, Any]] = []
    for offset in range(29, -1, -1):
        day = today_date - timedelta(days=offset)
        rolling7 = sum(
            per_day_spend.get((day - timedelta(days=inner)).isoformat(), 0)
            for inner in range(0, 7)
        )
        rolling30 = sum(
            per_day_spend.get((day - timedelta(days=inner)).isoformat(), 0)
            for inner in range(0, 30)
        )
        velocity_points.append(
            {
                "date": day.isoformat(),
                "rolling_7d_cents": rolling7,
                "rolling_30d_cents": rolling30,
            }
        )

    seasonal_stmt = (
        select(
            func.substr(ItemObservation.date, 6, 2).label("month"),
            func.avg(ItemObservation.line_total_net_cents),
            func.sum(ItemObservation.line_total_net_cents),
        )
        .where(
            ItemObservation.date >= start.isoformat(),
            ItemObservation.date <= end.isoformat(),
        )
        .group_by(func.substr(ItemObservation.date, 6, 2))
        .order_by(func.substr(ItemObservation.date, 6, 2).asc())
    )
    if visibility is not None:
        seasonal_stmt = seasonal_stmt.where(observation_visibility_filter(visibility))
    seasonal_rows = session.execute(seasonal_stmt).all()
    seasonal = [
        {
            "month": int(str(month)),
            "avg_spend_cents": int(avg_spend or 0),
            "total_spend_cents": int(total_spend or 0),
        }
        for month, avg_spend, total_spend in seasonal_rows
    ]

    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "shopping_frequency": shopping_frequency,
        "basket_size_distribution": basket_distribution,
        "impulse_indicator": {
            "one_time_items": one_time_items,
            "unique_items": unique_items,
            "one_time_share": round(one_time_items / unique_items, 6) if unique_items else 0.0,
        },
        "spend_velocity": velocity_points,
        "seasonal_patterns": seasonal,
    }


def deposit_analytics(
    session: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    """Return deposit (Pfand) totals: paid, returned, net outstanding, and monthly breakdown."""
    start, end = _date_window(date_from, date_to, default_days=365 * 5)

    vis_ids = visible_transaction_ids_subquery(visibility) if visibility is not None else None

    stmt = (
        select(
            func.substr(Transaction.purchased_at, 1, 7).label("month"),
            func.coalesce(
                func.sum(
                    case(
                        (TransactionItem.line_total_cents > 0, TransactionItem.line_total_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("paid_cents"),
            func.coalesce(
                func.sum(
                    case(
                        (TransactionItem.line_total_cents < 0, TransactionItem.line_total_cents),
                        else_=0,
                    )
                ),
                0,
            ).label("returned_cents"),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            TransactionItem.is_deposit.is_(True),
            Transaction.purchased_at >= start.isoformat(),
            Transaction.purchased_at <= end.isoformat(),
        )
        .group_by(func.substr(Transaction.purchased_at, 1, 7))
        .order_by(func.substr(Transaction.purchased_at, 1, 7))
    )
    if vis_ids is not None:
        stmt = stmt.where(Transaction.id.in_(vis_ids))

    rows = session.execute(stmt).all()

    total_paid = 0
    total_returned = 0
    monthly: list[dict[str, Any]] = []
    for month, paid, returned in rows:
        total_paid += int(paid)
        total_returned += int(returned)
        monthly.append(
            {
                "month": str(month),
                "paid_cents": int(paid),
                "returned_cents": int(returned),
                "net_cents": int(paid) + int(returned),
            }
        )

    return {
        "date_from": start.isoformat(),
        "date_to": end.isoformat(),
        "total_paid_cents": total_paid,
        "total_returned_cents": total_returned,
        "net_outstanding_cents": total_paid + total_returned,
        "monthly": monthly,
    }
