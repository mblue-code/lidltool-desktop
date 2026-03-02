from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select

from lidltool.analytics.scope import VisibilityContext, observation_visibility_filter
from lidltool.db.models import ComparisonGroupMember, ItemObservation

ALLOWED_METRICS = {
    "net_total",
    "gross_total",
    "discount_total",
    "purchase_count",
    "avg_unit_price",
}
ALLOWED_DIMENSIONS = {"month", "date", "source_kind", "category", "product"}
ALLOWED_TIME_GRAINS = {"day", "week", "month", "quarter", "year"}


def _to_jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def encode_drilldown_token(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_drilldown_token(token: str) -> dict[str, Any]:
    pad = "=" * ((4 - len(token) % 4) % 4)
    decoded = base64.urlsafe_b64decode(f"{token}{pad}".encode("ascii"))
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid drilldown token")
    return payload


def _metric_expressions() -> dict[str, Any]:
    basket_discount = func.coalesce(ItemObservation.basket_discount_alloc_cents, 0)
    effective_line_net = ItemObservation.line_total_net_cents - basket_discount
    return {
        "net_total": func.coalesce(func.sum(effective_line_net), 0),
        "gross_total": func.coalesce(func.sum(ItemObservation.line_total_gross_cents), 0),
        "discount_total": func.coalesce(
            func.sum(ItemObservation.line_total_gross_cents - effective_line_net), 0
        ),
        "purchase_count": func.count(func.distinct(ItemObservation.transaction_id)),
        "avg_unit_price": func.coalesce(func.avg(ItemObservation.unit_price_net_cents), 0),
    }


def _dimension_expressions() -> dict[str, Any]:
    return {
        "month": func.substr(ItemObservation.date, 1, 7),
        "date": ItemObservation.date,
        "source_kind": ItemObservation.source_kind,
        "category": func.coalesce(ItemObservation.category, "uncategorized"),
        "product": func.coalesce(ItemObservation.product_id, ItemObservation.raw_item_name),
    }


def _normalize_filter_dates(filters: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(filters)
    preset = normalized.get("date_preset")
    if not isinstance(preset, str):
        return normalized
    today = datetime.now(tz=UTC).date()
    if preset == "last90d":
        normalized["date_from"] = (today - timedelta(days=90)).isoformat()
        normalized["date_to"] = today.isoformat()
    elif preset == "ytd":
        normalized["date_from"] = today.replace(month=1, day=1).isoformat()
        normalized["date_to"] = today.isoformat()
    return normalized


def _apply_filters(stmt: Select[Any], filters: dict[str, Any]) -> Select[Any]:
    normalized = _normalize_filter_dates(filters)
    date_from = normalized.get("date_from")
    date_to = normalized.get("date_to")
    if isinstance(date_from, str) and date_from:
        stmt = stmt.where(ItemObservation.date >= date_from)
    if isinstance(date_to, str) and date_to:
        stmt = stmt.where(ItemObservation.date <= date_to)

    source_kinds = normalized.get("source_kinds")
    if isinstance(source_kinds, list):
        values = [str(value) for value in source_kinds if str(value).strip()]
        if values:
            stmt = stmt.where(ItemObservation.source_kind.in_(values))

    categories = normalized.get("categories")
    if isinstance(categories, list):
        values = [str(value) for value in categories if str(value).strip()]
        if values:
            stmt = stmt.where(func.coalesce(ItemObservation.category, "uncategorized").in_(values))

    products = normalized.get("products")
    if isinstance(products, list):
        values = [str(value) for value in products if str(value).strip()]
        if values:
            stmt = stmt.where(ItemObservation.product_id.in_(values))

    comparison_group = normalized.get("comparison_group")
    if isinstance(comparison_group, str) and comparison_group:
        member_subquery = select(ComparisonGroupMember.product_id).where(
            ComparisonGroupMember.group_id == comparison_group
        )
        stmt = stmt.where(ItemObservation.product_id.in_(member_subquery))

    only_discounted = normalized.get("only_discounted")
    if isinstance(only_discounted, bool) and only_discounted:
        stmt = stmt.where(ItemObservation.line_total_net_cents < ItemObservation.line_total_gross_cents)

    only_loyalty = normalized.get("only_loyalty")
    if isinstance(only_loyalty, bool) and only_loyalty:
        raise ValueError("only_loyalty filter is not yet supported")

    min_spend = normalized.get("min_spend_cents")
    if min_spend is not None:
        stmt = stmt.where(ItemObservation.line_total_net_cents >= int(min_spend))
    max_spend = normalized.get("max_spend_cents")
    if max_spend is not None:
        stmt = stmt.where(ItemObservation.line_total_net_cents <= int(max_spend))
    return stmt


def run_query(
    session: Session,
    query: dict[str, Any],
    *,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    metrics = query.get("metrics")
    dimensions = query.get("dimensions")
    filters = query.get("filters")
    sort_by = query.get("sort_by")
    sort_dir = str(query.get("sort_dir", "desc")).lower()
    limit = query.get("limit")
    time_grain = query.get("time_grain")

    if not isinstance(metrics, list) or not metrics:
        raise ValueError("metrics must be a non-empty list")
    if not isinstance(dimensions, list):
        dimensions = []
    if not isinstance(filters, dict):
        filters = {}
    if sort_dir not in {"asc", "desc"}:
        raise ValueError("sort_dir must be one of: asc, desc")
    if time_grain is not None and str(time_grain) not in ALLOWED_TIME_GRAINS:
        raise ValueError("time_grain must be one of: day, week, month, quarter, year")

    metric_expr_map = _metric_expressions()
    dim_expr_map = _dimension_expressions()
    for metric in metrics:
        if metric not in ALLOWED_METRICS:
            raise ValueError(
                "unsupported metric: "
                + str(metric)
                + "; allowed: "
                + ", ".join(sorted(ALLOWED_METRICS))
            )
    for dimension in dimensions:
        if dimension not in ALLOWED_DIMENSIONS:
            raise ValueError(
                "unsupported dimension: "
                + str(dimension)
                + "; allowed: "
                + ", ".join(sorted(ALLOWED_DIMENSIONS))
            )

    selected_dims = [dim_expr_map[dim].label(dim) for dim in dimensions]
    selected_metrics = [metric_expr_map[metric].label(metric) for metric in metrics]
    stmt = select(*selected_dims, *selected_metrics).select_from(ItemObservation)
    stmt = _apply_filters(stmt, filters)
    if visibility is not None:
        stmt = stmt.where(observation_visibility_filter(visibility))
    if selected_dims:
        stmt = stmt.group_by(*selected_dims)

    selectable_map = {column.key: column for column in [*selected_dims, *selected_metrics]}
    sort_key = str(sort_by) if sort_by is not None else metrics[0]
    if sort_key not in selectable_map:
        raise ValueError(f"sort_by must be one of: {', '.join(selectable_map.keys())}")
    sort_expr = selectable_map[sort_key]
    stmt = stmt.order_by(sort_expr.asc() if sort_dir == "asc" else sort_expr.desc())

    if limit is not None:
        stmt = stmt.limit(min(max(int(limit), 1), 5000))

    rows = session.execute(stmt).all()
    totals_stmt = select(*selected_metrics).select_from(ItemObservation)
    totals_stmt = _apply_filters(totals_stmt, filters)
    if visibility is not None:
        totals_stmt = totals_stmt.where(observation_visibility_filter(visibility))
    totals_row = session.execute(totals_stmt).one()
    totals = {metrics[index]: _to_jsonable(totals_row[index]) for index in range(len(metrics))}

    response_rows: list[list[object]] = []
    for row in rows:
        response_rows.append([_to_jsonable(value) for value in row])

    bind = session.get_bind()
    explain_sql = str(
        stmt.compile(
            dialect=bind.dialect,
            compile_kwargs={"literal_binds": True},
        )
    )
    normalized_filters = _normalize_filter_dates(filters)
    drilldown_token = encode_drilldown_token(
        {
            "filters": normalized_filters,
            "dimensions": dimensions,
            "metrics": metrics,
        }
    )
    return {
        "columns": [*dimensions, *metrics],
        "rows": response_rows,
        "totals": totals,
        "drilldown_token": drilldown_token,
        "explain": explain_sql,
    }
