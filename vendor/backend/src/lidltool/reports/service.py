from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from math import floor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.analytics.advanced import budget_utilization
from lidltool.analytics.queries import (
    dashboard_category_spend_summary,
    dashboard_merchant_summary,
    dashboard_window_totals,
    grocery_workspace_summary,
    search_transactions,
)
from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import CashflowEntry, RecurringBill, RecurringBillOccurrence, Source, TransactionItem
from lidltool.goals.service import goals_summary
from lidltool.shared_groups.ownership import ownership_filter

OUTFLOW_ONLY_MODE = "outflow_only"
COMBINED_MODE = "combined"
MERCHANT_BREAKDOWN = "merchant"
SUBCATEGORY_BREAKDOWN = "subcategory"
SUBCATEGORY_SOURCE_BREAKDOWN = "subcategory_source"
SOURCE_BREAKDOWN = "source"
SUBCATEGORY_ONLY_BREAKDOWN = "subcategory_only"
OTHER_INFLOW_BUCKET_ID = "inflow:__other__"
OTHER_OUTFLOW_CATEGORY_ID = "category:__other__"
OTHER_MERCHANT_ID = "merchant:__other__"
OTHER_SOURCE_ID = "source:__other__"
OTHER_SUBCATEGORY_PREFIX = "subcategory:__other__:"
DIRECT_SUBCATEGORY_PREFIX = "subcategory:__direct__:"
SYNTHETIC_INFLOW_BUCKET_ID = "inflow:__synthetic__"
DIRECT_SUBCATEGORY_TOKEN = "__direct__"
GROCERY_DETAIL_LEAF_KEYS = {
    "bakery",
    "baking",
    "beverages",
    "dairy",
    "fish",
    "frozen",
    "household",
    "meat",
    "pantry",
    "produce",
    "snacks",
}


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
                RecurringBillOccurrence.due_date >= from_date,
                RecurringBillOccurrence.due_date <= to_date,
                ownership_filter(RecurringBill, visibility=visibility),
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


def _normalized_bucket_value(value: str | None, fallback: str = "uncategorized") -> str:
    normalized = (value or "").strip()
    return normalized or fallback


def _top_keys_by_total(totals: dict[str, int], limit: int) -> set[str]:
    if limit <= 0 or len(totals) <= limit:
        return set(totals)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return {key for key, _ in ranked[:limit]}


def _allocate_proportional(total: int, weights: list[int]) -> list[int]:
    if total <= 0 or not weights:
        return [0 for _ in weights]
    weight_sum = sum(max(weight, 0) for weight in weights)
    if weight_sum <= 0:
        return [0 for _ in weights]

    raw_values = [total * max(weight, 0) / weight_sum for weight in weights]
    allocations = [floor(value) for value in raw_values]
    remainder = total - sum(allocations)
    if remainder <= 0:
        return allocations

    remainders = sorted(
        range(len(weights)),
        key=lambda index: (raw_values[index] - allocations[index], weights[index], index),
        reverse=True,
    )
    for index in remainders[:remainder]:
        allocations[index] += 1
    return allocations


def _empty_report_sankey(
    *,
    from_date: date,
    to_date: date,
    mode: str,
    breakdown: str,
    flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "period": {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
        "mode": mode,
        "breakdown": breakdown,
        "model": {
            "kind": _report_sankey_model_kind(mode, breakdown),
            "transaction_provenance_supported": False,
        },
        "flags": {
            "aggregated_inflows": False,
            "aggregated_categories": False,
            "aggregated_merchants": False,
            "aggregated_subcategories": False,
            "aggregated_sources": False,
            "manual_inflows_excluded_by_source_filter": False,
            "synthetic_inflow_bucket": False,
            **(flags or {}),
        },
        "summary": {
            "total_outflow_cents": 0,
            "total_inflow_basis_cents": 0,
            "node_count": 0,
            "link_count": 0,
        },
        "nodes": [],
        "links": [],
    }


def _report_sankey_model_kind(mode: str, breakdown: str) -> str:
    if breakdown == SUBCATEGORY_ONLY_BREAKDOWN:
        return (
            "period_proportional_inflow_to_outflow_category_subcategory"
            if mode == COMBINED_MODE
            else "outflow_category_to_subcategory"
        )
    if breakdown == SUBCATEGORY_BREAKDOWN:
        return (
            "period_proportional_inflow_to_outflow_category_subcategory_merchant"
            if mode == COMBINED_MODE
            else "outflow_category_to_subcategory_merchant"
        )
    if breakdown == SUBCATEGORY_SOURCE_BREAKDOWN:
        return (
            "period_proportional_inflow_to_outflow_category_subcategory_source"
            if mode == COMBINED_MODE
            else "outflow_category_to_subcategory_source"
        )
    if breakdown == SOURCE_BREAKDOWN:
        return (
            "period_proportional_inflow_to_outflow_category_source"
            if mode == COMBINED_MODE
            else "outflow_category_to_source"
        )
    return (
        "period_proportional_inflow_to_outflow_category_merchant"
        if mode == COMBINED_MODE
        else "outflow_category_to_merchant"
    )


def _subcategory_node_id(parent_key: str, subcategory_key: str) -> str:
    if subcategory_key == DIRECT_SUBCATEGORY_TOKEN:
        return f"{DIRECT_SUBCATEGORY_PREFIX}{parent_key}"
    return f"subcategory:{subcategory_key}"


def _other_subcategory_node_id(parent_node_id: str) -> str:
    parent_bucket = parent_node_id.removeprefix("category:")
    return f"{OTHER_SUBCATEGORY_PREFIX}{parent_bucket}"


def _normalize_detail_category(parent_category_key: str, raw_detail_value: str | None) -> str:
    normalized = (raw_detail_value or "").strip().lower()
    if not normalized or normalized in {"uncategorized", "other", parent_category_key}:
        return DIRECT_SUBCATEGORY_TOKEN
    if parent_category_key == "groceries" and ":" not in normalized and normalized in GROCERY_DETAIL_LEAF_KEYS:
        return f"groceries:{normalized}"
    return normalized


def _transaction_detail_splits(
    *,
    transaction_id: str,
    parent_category_key: str,
    raw_category_id: str,
    amount_cents: int,
    item_rows_by_transaction_id: dict[str, list[tuple[str | None, str | None, int]]],
) -> list[tuple[str, int]]:
    if parent_category_key == "groceries":
        detail_weights: dict[str, int] = defaultdict(int)
        for category_id, category_value, line_total_cents in item_rows_by_transaction_id.get(transaction_id, []):
            line_total = int(line_total_cents or 0)
            if line_total <= 0:
                continue
            detail_key = _normalize_detail_category(parent_category_key, category_id or category_value)
            detail_weights[detail_key] += line_total
        if detail_weights:
            detail_keys = sorted(detail_weights, key=lambda key: (-detail_weights[key], key))
            allocations = _allocate_proportional(
                amount_cents,
                [detail_weights[key] for key in detail_keys],
            )
            return [
                (detail_keys[index], allocation)
                for index, allocation in enumerate(allocations)
                if allocation > 0
            ]

    if raw_category_id != parent_category_key:
        return [(raw_category_id, amount_cents)]
    return [(DIRECT_SUBCATEGORY_TOKEN, amount_cents)]


def build_report_sankey(
    session: Session,
    *,
    user_id: str,
    visibility: VisibilityContext,
    from_date: date,
    to_date: date,
    merchant_names: list[str] | None = None,
    finance_category_id: str | None = None,
    direction: str | None = None,
    source_id: str | None = None,
    source_ids: list[str] | None = None,
    mode: str = COMBINED_MODE,
    breakdown: str = MERCHANT_BREAKDOWN,
    top_n: int = 8,
) -> dict[str, Any]:
    normalized_mode = (mode or COMBINED_MODE).strip().lower()
    if normalized_mode not in {COMBINED_MODE, OUTFLOW_ONLY_MODE}:
        raise ValueError("mode must be one of: combined, outflow_only")
    normalized_breakdown = (breakdown or MERCHANT_BREAKDOWN).strip().lower()
    if normalized_breakdown not in {
        MERCHANT_BREAKDOWN,
        SUBCATEGORY_BREAKDOWN,
        SUBCATEGORY_ONLY_BREAKDOWN,
        SUBCATEGORY_SOURCE_BREAKDOWN,
        SOURCE_BREAKDOWN,
    }:
        raise ValueError("breakdown must be one of: merchant, subcategory, subcategory_only, subcategory_source, source")

    normalized_source_ids = sorted(
        {
            candidate.strip()
            for candidate in [*(source_ids or []), *([source_id] if source_id else [])]
            if candidate and candidate.strip()
        }
    )
    if direction is not None and direction != "outflow":
        return _empty_report_sankey(
            from_date=from_date,
            to_date=to_date,
            mode=normalized_mode,
            breakdown=normalized_breakdown,
            flags={
                "manual_inflows_excluded_by_source_filter": bool(normalized_source_ids),
            },
        )

    from_dt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    to_dt = datetime.combine(to_date, datetime.max.time(), tzinfo=UTC)
    outflow_result = search_transactions(
        session,
        purchased_from=from_dt,
        purchased_to=to_dt,
        merchant_name=merchant_names[0] if merchant_names and len(merchant_names) == 1 else None,
        finance_category_id=finance_category_id,
        direction="outflow",
        source_id=source_id,
        source_ids=normalized_source_ids or None,
        limit=10_000,
        offset=0,
        visibility=visibility,
    )
    outflow_items = outflow_result["items"]
    if merchant_names and len(merchant_names) > 1:
        wanted_merchants = {name.casefold() for name in merchant_names}
        outflow_items = [
            item
            for item in outflow_items
            if str(item.get("store_name") or "").casefold() in wanted_merchants
        ]

    if not outflow_items:
        return _empty_report_sankey(
            from_date=from_date,
            to_date=to_date,
            mode=normalized_mode,
            breakdown=normalized_breakdown,
            flags={
                "manual_inflows_excluded_by_source_filter": bool(normalized_source_ids),
            },
        )

    source_ids_in_items = sorted(
        {
            str(item.get("source_id") or "").strip()
            for item in outflow_items
            if str(item.get("source_id") or "").strip()
        }
    )
    source_label_map: dict[str, str] = {}
    if source_ids_in_items:
        source_rows = (
            session.execute(
                select(Source.id, Source.display_name)
                .where(Source.id.in_(source_ids_in_items))
                .order_by(Source.id.asc())
            )
            .all()
        )
        source_label_map = {
            str(source_id_value): str(display_name or source_id_value)
            for source_id_value, display_name in source_rows
        }

    item_rows_by_transaction_id: dict[str, list[tuple[str | None, str | None, int]]] = defaultdict(list)
    if normalized_breakdown in {SUBCATEGORY_BREAKDOWN, SUBCATEGORY_ONLY_BREAKDOWN, SUBCATEGORY_SOURCE_BREAKDOWN}:
        outflow_transaction_ids = [
            str(item.get("id") or "").strip()
            for item in outflow_items
            if str(item.get("id") or "").strip()
        ]
        if outflow_transaction_ids:
            item_rows = (
                session.execute(
                    select(
                        TransactionItem.transaction_id,
                        TransactionItem.category_id,
                        TransactionItem.category,
                        TransactionItem.line_total_cents,
                    )
                    .where(TransactionItem.transaction_id.in_(outflow_transaction_ids))
                    .order_by(TransactionItem.transaction_id.asc(), TransactionItem.line_no.asc(), TransactionItem.id.asc())
                )
                .all()
            )
            for transaction_id, category_id, category_value, line_total_cents in item_rows:
                item_rows_by_transaction_id[str(transaction_id)].append(
                    (category_id, category_value, int(line_total_cents or 0))
                )

    category_totals: dict[str, int] = defaultdict(int)
    category_labels: dict[str, str] = {}
    merchant_totals: dict[str, int] = defaultdict(int)
    merchant_labels: dict[str, str] = {}
    source_totals: dict[str, int] = defaultdict(int)
    source_labels: dict[str, str] = {}
    subcategory_totals: dict[tuple[str, str], int] = defaultdict(int)
    subcategory_labels: dict[tuple[str, str], str] = {}
    raw_category_merchant_totals: dict[tuple[str, str], int] = defaultdict(int)
    raw_category_source_totals: dict[tuple[str, str], int] = defaultdict(int)
    raw_subcategory_merchant_totals: dict[tuple[str, str, str], int] = defaultdict(int)
    raw_subcategory_source_totals: dict[tuple[str, str, str], int] = defaultdict(int)

    for item in outflow_items:
        transaction_id = str(item.get("id") or "").strip()
        amount_cents = int(item.get("total_gross_cents") or 0)
        if amount_cents <= 0:
            continue
        raw_category_id = _normalized_bucket_value(str(item.get("finance_category_id") or ""))
        category_key = _normalized_bucket_value(
            str(item.get("finance_category_parent_id") or raw_category_id)
        )
        raw_subcategory_key = (
            raw_category_id
            if raw_category_id != category_key
            else DIRECT_SUBCATEGORY_TOKEN
        )
        source_key = _normalized_bucket_value(str(item.get("source_id") or "unknown"), "unknown")
        merchant_key = _normalized_bucket_value(
            str(item.get("store_name") or source_label_map.get(source_key) or source_key or "Unknown"),
            "Unknown",
        )
        category_totals[category_key] += amount_cents
        category_labels[category_key] = category_key
        merchant_totals[merchant_key] += amount_cents
        merchant_labels[merchant_key] = merchant_key
        source_totals[source_key] += amount_cents
        source_labels[source_key] = source_label_map.get(source_key, source_key)
        raw_category_merchant_totals[(category_key, merchant_key)] += amount_cents
        raw_category_source_totals[(category_key, source_key)] += amount_cents
        detail_splits = _transaction_detail_splits(
            transaction_id=transaction_id,
            parent_category_key=category_key,
            raw_category_id=raw_category_id,
            amount_cents=amount_cents,
            item_rows_by_transaction_id=item_rows_by_transaction_id,
        )
        for detail_key, detail_amount_cents in detail_splits:
            subcategory_key = (category_key, detail_key)
            subcategory_totals[subcategory_key] += detail_amount_cents
            subcategory_labels[subcategory_key] = (
                "General" if detail_key == DIRECT_SUBCATEGORY_TOKEN else detail_key
            )
            raw_subcategory_merchant_totals[(category_key, detail_key, merchant_key)] += detail_amount_cents
            raw_subcategory_source_totals[(category_key, detail_key, source_key)] += detail_amount_cents

    total_outflow_cents = sum(category_totals.values())
    if total_outflow_cents <= 0:
        return _empty_report_sankey(
            from_date=from_date,
            to_date=to_date,
            mode=normalized_mode,
            breakdown=normalized_breakdown,
            flags={
                "manual_inflows_excluded_by_source_filter": bool(normalized_source_ids),
            },
        )

    category_limit = max(4, min(top_n, 10))
    kept_categories = _top_keys_by_total(category_totals, category_limit)
    aggregated_categories = len(kept_categories) < len(category_totals)
    grouped_category_totals: dict[str, int] = defaultdict(int)
    grouped_category_labels: dict[str, str] = {}
    grouped_category_node_ids: dict[str, str] = {}
    for raw_category_key, amount_cents in category_totals.items():
        category_node_id = (
            f"category:{raw_category_key}"
            if raw_category_key in kept_categories
            else OTHER_OUTFLOW_CATEGORY_ID
        )
        grouped_category_node_ids[raw_category_key] = category_node_id
        grouped_category_totals[category_node_id] += amount_cents
        grouped_category_labels[category_node_id] = (
            category_labels.get(raw_category_key, raw_category_key)
            if raw_category_key in kept_categories
            else "Other categories"
        )

    flags: dict[str, Any] = {
        "aggregated_inflows": False,
        "aggregated_categories": aggregated_categories,
        "aggregated_merchants": False,
        "aggregated_subcategories": False,
        "aggregated_sources": False,
        "manual_inflows_excluded_by_source_filter": bool(normalized_source_ids),
        "synthetic_inflow_bucket": False,
    }
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    if normalized_mode == COMBINED_MODE:
        inflow_totals: dict[str, int] = defaultdict(int)
        inflow_labels: dict[str, str] = {}

        if not normalized_source_ids:
            cashflow_entries = (
                session.execute(
                    select(CashflowEntry)
                    .where(
                        CashflowEntry.effective_date >= from_date,
                        CashflowEntry.effective_date <= to_date,
                        CashflowEntry.direction == "inflow",
                        CashflowEntry.linked_transaction_id.is_(None),
                        ownership_filter(CashflowEntry, visibility=visibility),
                    )
                    .order_by(CashflowEntry.effective_date.asc(), CashflowEntry.created_at.asc())
                )
                .scalars()
                .all()
            )
            for entry in cashflow_entries:
                bucket_value = _normalized_bucket_value(entry.category, "other")
                bucket_key = f"inflow:{bucket_value}"
                inflow_totals[bucket_key] += int(entry.amount_cents or 0)
                inflow_labels[bucket_key] = bucket_value

        inflow_result = search_transactions(
            session,
            purchased_from=from_dt,
            purchased_to=to_dt,
            direction="inflow",
            source_id=source_id,
            source_ids=normalized_source_ids or None,
            limit=10_000,
            offset=0,
            visibility=visibility,
        )
        for item in inflow_result["items"]:
            amount_cents = int(item.get("total_gross_cents") or 0)
            if amount_cents <= 0:
                continue
            raw_bucket_label = _normalized_bucket_value(
                str(item.get("finance_category_id") or item.get("source_id") or "uncategorized")
            )
            bucket_key = f"inflow:{raw_bucket_label}"
            inflow_totals[bucket_key] += amount_cents
            inflow_labels[bucket_key] = raw_bucket_label

        total_inflow_basis_cents = sum(inflow_totals.values())
        if total_inflow_basis_cents <= 0:
            flags["synthetic_inflow_bucket"] = True
            inflow_totals = {SYNTHETIC_INFLOW_BUCKET_ID: total_outflow_cents}
            inflow_labels = {SYNTHETIC_INFLOW_BUCKET_ID: "Unattributed period inflow"}
            total_inflow_basis_cents = 0

        inflow_limit = max(3, min(top_n, 6))
        kept_inflows = _top_keys_by_total(inflow_totals, inflow_limit)
        grouped_inflow_basis_totals: dict[str, int] = defaultdict(int)
        grouped_inflow_labels: dict[str, str] = {}
        for inflow_key, amount_cents in inflow_totals.items():
            grouped_key = inflow_key if inflow_key in kept_inflows else OTHER_INFLOW_BUCKET_ID
            grouped_inflow_basis_totals[grouped_key] += amount_cents
            grouped_inflow_labels[grouped_key] = (
                inflow_labels.get(inflow_key, inflow_key)
                if inflow_key in kept_inflows
                else "Other inflows"
            )
        flags["aggregated_inflows"] = len(grouped_inflow_basis_totals) < len(inflow_totals)

        inflow_node_ids = sorted(
            grouped_inflow_basis_totals,
            key=lambda key: (-grouped_inflow_basis_totals[key], grouped_inflow_labels[key]),
        )
        inflow_weights = [grouped_inflow_basis_totals[key] for key in inflow_node_ids]
        scaled_inflow_totals: dict[str, int] = defaultdict(int)

        for category_key, category_total in grouped_category_totals.items():
            allocations = _allocate_proportional(category_total, inflow_weights)
            for index, amount_cents in enumerate(allocations):
                if amount_cents <= 0:
                    continue
                inflow_key = inflow_node_ids[index]
                scaled_inflow_totals[inflow_key] += amount_cents
                links.append(
                    {
                        "source": inflow_key,
                        "target": category_key,
                        "value_cents": amount_cents,
                        "kind": "period_proportional_attribution",
                    }
                )

        for inflow_key in inflow_node_ids:
            nodes.append(
                {
                    "id": inflow_key,
                    "label": grouped_inflow_labels[inflow_key],
                    "kind": "inflow",
                    "layer": 0,
                    "amount_cents": scaled_inflow_totals[inflow_key],
                    "basis_amount_cents": grouped_inflow_basis_totals[inflow_key],
                }
            )
    else:
        total_inflow_basis_cents = 0

    category_layer = 1 if normalized_mode == COMBINED_MODE else 0
    subcategory_layer = category_layer + 1
    source_layer = category_layer + (
        2 if normalized_breakdown == SUBCATEGORY_SOURCE_BREAKDOWN else 1
    )
    merchant_layer = category_layer + (
        2 if normalized_breakdown == SUBCATEGORY_BREAKDOWN else 1
    )

    for category_key in sorted(
        grouped_category_totals,
        key=lambda key: (-grouped_category_totals[key], grouped_category_labels[key]),
    ):
        raw_category_id = category_key.removeprefix("category:") if category_key.startswith("category:") else None
        nodes.append(
            {
                "id": category_key,
                "label": grouped_category_labels[category_key],
                "kind": "outflow_category",
                "layer": category_layer,
                "amount_cents": grouped_category_totals[category_key],
                "category_id": raw_category_id if category_key != OTHER_OUTFLOW_CATEGORY_ID else None,
            }
        )

    if normalized_breakdown == SOURCE_BREAKDOWN:
        source_limit = max(5, min(top_n * 2, 16))
        kept_sources = _top_keys_by_total(source_totals, source_limit)
        flags["aggregated_sources"] = len(kept_sources) < len(source_totals)
        grouped_source_totals: dict[str, int] = defaultdict(int)
        grouped_source_labels: dict[str, str] = {}
        category_source_totals: dict[tuple[str, str], int] = defaultdict(int)

        for (raw_category_key, raw_source_key), amount_cents in raw_category_source_totals.items():
            category_node_id = grouped_category_node_ids[raw_category_key]
            source_node_id = (
                f"source:{raw_source_key}"
                if raw_source_key in kept_sources
                else OTHER_SOURCE_ID
            )
            grouped_source_totals[source_node_id] += amount_cents
            grouped_source_labels[source_node_id] = (
                source_labels.get(raw_source_key, raw_source_key)
                if raw_source_key in kept_sources
                else "Other sources"
            )
            category_source_totals[(category_node_id, source_node_id)] += amount_cents

        for source_key in sorted(
            grouped_source_totals,
            key=lambda key: (-grouped_source_totals[key], grouped_source_labels[key]),
        ):
            nodes.append(
                {
                    "id": source_key,
                    "label": grouped_source_labels[source_key],
                    "kind": "source",
                    "layer": source_layer,
                    "amount_cents": grouped_source_totals[source_key],
                    "source_id": source_key.removeprefix("source:") if source_key != OTHER_SOURCE_ID else None,
                }
            )

        for (category_key, source_key), amount_cents in sorted(
            category_source_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": category_key,
                    "target": source_key,
                    "value_cents": amount_cents,
                    "kind": "category_to_source",
                }
            )
    elif normalized_breakdown == SUBCATEGORY_ONLY_BREAKDOWN:
        subcategory_limit = max(6, min(top_n * 2, 18))
        kept_subcategories = _top_keys_by_total(
            {
                f"{parent_key}|{subcategory_key}": amount_cents
                for (parent_key, subcategory_key), amount_cents in subcategory_totals.items()
            },
            subcategory_limit,
        )
        flags["aggregated_subcategories"] = len(kept_subcategories) < len(subcategory_totals)
        grouped_subcategory_totals: dict[str, int] = defaultdict(int)
        grouped_subcategory_labels: dict[str, str] = {}
        category_subcategory_totals: dict[tuple[str, str], int] = defaultdict(int)

        for (raw_category_key, raw_subcategory_key), amount_cents in subcategory_totals.items():
            category_node_id = grouped_category_node_ids[raw_category_key]
            subcategory_composite_key = f"{raw_category_key}|{raw_subcategory_key}"
            subcategory_node_id = (
                _subcategory_node_id(raw_category_key, raw_subcategory_key)
                if subcategory_composite_key in kept_subcategories and raw_category_key in kept_categories
                else _other_subcategory_node_id(category_node_id)
            )
            grouped_subcategory_totals[subcategory_node_id] += amount_cents
            grouped_subcategory_labels[subcategory_node_id] = (
                subcategory_labels.get((raw_category_key, raw_subcategory_key), raw_subcategory_key)
                if subcategory_node_id.startswith("subcategory:")
                and not subcategory_node_id.startswith(OTHER_SUBCATEGORY_PREFIX)
                else "Other subcategories"
            )
            category_subcategory_totals[(category_node_id, subcategory_node_id)] += amount_cents

        for subcategory_key in sorted(
            grouped_subcategory_totals,
            key=lambda key: (-grouped_subcategory_totals[key], grouped_subcategory_labels[key]),
        ):
            category_id = None
            if (
                subcategory_key.startswith("subcategory:")
                and not subcategory_key.startswith(OTHER_SUBCATEGORY_PREFIX)
                and not subcategory_key.startswith(DIRECT_SUBCATEGORY_PREFIX)
            ):
                category_id = subcategory_key.removeprefix("subcategory:")
            nodes.append(
                {
                    "id": subcategory_key,
                    "label": grouped_subcategory_labels[subcategory_key],
                    "kind": "subcategory",
                    "layer": subcategory_layer,
                    "amount_cents": grouped_subcategory_totals[subcategory_key],
                    "category_id": category_id,
                }
            )

        for (category_key, subcategory_key), amount_cents in sorted(
            category_subcategory_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": category_key,
                    "target": subcategory_key,
                    "value_cents": amount_cents,
                    "kind": "category_to_subcategory",
                }
            )
    elif normalized_breakdown == SUBCATEGORY_BREAKDOWN:
        merchant_limit = max(6, min(top_n * 2, 16))
        subcategory_limit = max(6, min(top_n * 2, 18))
        kept_merchants = _top_keys_by_total(merchant_totals, merchant_limit)
        kept_subcategories = _top_keys_by_total(
            {
                f"{parent_key}|{subcategory_key}": amount_cents
                for (parent_key, subcategory_key), amount_cents in subcategory_totals.items()
            },
            subcategory_limit,
        )
        flags["aggregated_merchants"] = len(kept_merchants) < len(merchant_totals)
        flags["aggregated_subcategories"] = len(kept_subcategories) < len(subcategory_totals)
        grouped_subcategory_totals: dict[str, int] = defaultdict(int)
        grouped_subcategory_labels: dict[str, str] = {}
        grouped_merchant_totals: dict[str, int] = defaultdict(int)
        grouped_merchant_labels: dict[str, str] = {}
        category_subcategory_totals: dict[tuple[str, str], int] = defaultdict(int)
        subcategory_merchant_totals: dict[tuple[str, str], int] = defaultdict(int)

        for (raw_category_key, raw_subcategory_key, raw_merchant_key), amount_cents in raw_subcategory_merchant_totals.items():
            category_node_id = grouped_category_node_ids[raw_category_key]
            subcategory_composite_key = f"{raw_category_key}|{raw_subcategory_key}"
            subcategory_node_id = (
                _subcategory_node_id(raw_category_key, raw_subcategory_key)
                if subcategory_composite_key in kept_subcategories and raw_category_key in kept_categories
                else _other_subcategory_node_id(category_node_id)
            )
            merchant_node_id = (
                f"merchant:{raw_merchant_key}"
                if raw_merchant_key in kept_merchants
                else OTHER_MERCHANT_ID
            )
            grouped_subcategory_totals[subcategory_node_id] += amount_cents
            grouped_subcategory_labels[subcategory_node_id] = (
                subcategory_labels.get((raw_category_key, raw_subcategory_key), raw_subcategory_key)
                if subcategory_node_id.startswith("subcategory:")
                and not subcategory_node_id.startswith(OTHER_SUBCATEGORY_PREFIX)
                else "Other subcategories"
            )
            grouped_merchant_totals[merchant_node_id] += amount_cents
            grouped_merchant_labels[merchant_node_id] = (
                merchant_labels.get(raw_merchant_key, raw_merchant_key)
                if raw_merchant_key in kept_merchants
                else "Other merchants"
            )
            category_subcategory_totals[(category_node_id, subcategory_node_id)] += amount_cents
            subcategory_merchant_totals[(subcategory_node_id, merchant_node_id)] += amount_cents

        for subcategory_key in sorted(
            grouped_subcategory_totals,
            key=lambda key: (-grouped_subcategory_totals[key], grouped_subcategory_labels[key]),
        ):
            category_id = None
            if (
                subcategory_key.startswith("subcategory:")
                and not subcategory_key.startswith(OTHER_SUBCATEGORY_PREFIX)
                and not subcategory_key.startswith(DIRECT_SUBCATEGORY_PREFIX)
            ):
                category_id = subcategory_key.removeprefix("subcategory:")
            nodes.append(
                {
                    "id": subcategory_key,
                    "label": grouped_subcategory_labels[subcategory_key],
                    "kind": "subcategory",
                    "layer": subcategory_layer,
                    "amount_cents": grouped_subcategory_totals[subcategory_key],
                    "category_id": category_id,
                }
            )

        for merchant_key in sorted(
            grouped_merchant_totals,
            key=lambda key: (-grouped_merchant_totals[key], grouped_merchant_labels[key]),
        ):
            nodes.append(
                {
                    "id": merchant_key,
                    "label": grouped_merchant_labels[merchant_key],
                    "kind": "merchant",
                    "layer": merchant_layer,
                    "amount_cents": grouped_merchant_totals[merchant_key],
                    "merchant_name": grouped_merchant_labels[merchant_key],
                }
            )

        for (category_key, subcategory_key), amount_cents in sorted(
            category_subcategory_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": category_key,
                    "target": subcategory_key,
                    "value_cents": amount_cents,
                    "kind": "category_to_subcategory",
                }
            )
        for (subcategory_key, merchant_key), amount_cents in sorted(
            subcategory_merchant_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": subcategory_key,
                    "target": merchant_key,
                    "value_cents": amount_cents,
                    "kind": "subcategory_to_merchant",
                }
            )
    elif normalized_breakdown == SUBCATEGORY_SOURCE_BREAKDOWN:
        source_limit = max(5, min(top_n * 2, 16))
        subcategory_limit = max(6, min(top_n * 2, 18))
        kept_sources = _top_keys_by_total(source_totals, source_limit)
        kept_subcategories = _top_keys_by_total(
            {
                f"{parent_key}|{subcategory_key}": amount_cents
                for (parent_key, subcategory_key), amount_cents in subcategory_totals.items()
            },
            subcategory_limit,
        )
        flags["aggregated_sources"] = len(kept_sources) < len(source_totals)
        flags["aggregated_subcategories"] = len(kept_subcategories) < len(subcategory_totals)
        grouped_subcategory_totals: dict[str, int] = defaultdict(int)
        grouped_subcategory_labels: dict[str, str] = {}
        grouped_source_totals: dict[str, int] = defaultdict(int)
        grouped_source_labels: dict[str, str] = {}
        category_subcategory_totals: dict[tuple[str, str], int] = defaultdict(int)
        subcategory_source_totals: dict[tuple[str, str], int] = defaultdict(int)

        for (raw_category_key, raw_subcategory_key, raw_source_key), amount_cents in raw_subcategory_source_totals.items():
            category_node_id = grouped_category_node_ids[raw_category_key]
            subcategory_composite_key = f"{raw_category_key}|{raw_subcategory_key}"
            subcategory_node_id = (
                _subcategory_node_id(raw_category_key, raw_subcategory_key)
                if subcategory_composite_key in kept_subcategories and raw_category_key in kept_categories
                else _other_subcategory_node_id(category_node_id)
            )
            source_node_id = (
                f"source:{raw_source_key}"
                if raw_source_key in kept_sources
                else OTHER_SOURCE_ID
            )
            grouped_subcategory_totals[subcategory_node_id] += amount_cents
            grouped_subcategory_labels[subcategory_node_id] = (
                subcategory_labels.get((raw_category_key, raw_subcategory_key), raw_subcategory_key)
                if subcategory_node_id.startswith("subcategory:")
                and not subcategory_node_id.startswith(OTHER_SUBCATEGORY_PREFIX)
                else "Other subcategories"
            )
            grouped_source_totals[source_node_id] += amount_cents
            grouped_source_labels[source_node_id] = (
                source_labels.get(raw_source_key, raw_source_key)
                if raw_source_key in kept_sources
                else "Other sources"
            )
            category_subcategory_totals[(category_node_id, subcategory_node_id)] += amount_cents
            subcategory_source_totals[(subcategory_node_id, source_node_id)] += amount_cents

        for subcategory_key in sorted(
            grouped_subcategory_totals,
            key=lambda key: (-grouped_subcategory_totals[key], grouped_subcategory_labels[key]),
        ):
            category_id = None
            if (
                subcategory_key.startswith("subcategory:")
                and not subcategory_key.startswith(OTHER_SUBCATEGORY_PREFIX)
                and not subcategory_key.startswith(DIRECT_SUBCATEGORY_PREFIX)
            ):
                category_id = subcategory_key.removeprefix("subcategory:")
            nodes.append(
                {
                    "id": subcategory_key,
                    "label": grouped_subcategory_labels[subcategory_key],
                    "kind": "subcategory",
                    "layer": subcategory_layer,
                    "amount_cents": grouped_subcategory_totals[subcategory_key],
                    "category_id": category_id,
                }
            )

        for source_key in sorted(
            grouped_source_totals,
            key=lambda key: (-grouped_source_totals[key], grouped_source_labels[key]),
        ):
            nodes.append(
                {
                    "id": source_key,
                    "label": grouped_source_labels[source_key],
                    "kind": "source",
                    "layer": source_layer,
                    "amount_cents": grouped_source_totals[source_key],
                    "source_id": source_key.removeprefix("source:") if source_key != OTHER_SOURCE_ID else None,
                }
            )

        for (category_key, subcategory_key), amount_cents in sorted(
            category_subcategory_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": category_key,
                    "target": subcategory_key,
                    "value_cents": amount_cents,
                    "kind": "category_to_subcategory",
                }
            )
        for (subcategory_key, source_key), amount_cents in sorted(
            subcategory_source_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": subcategory_key,
                    "target": source_key,
                    "value_cents": amount_cents,
                    "kind": "subcategory_to_source",
                }
            )
    else:
        merchant_limit = max(6, min(top_n * 2, 16))
        kept_merchants = _top_keys_by_total(merchant_totals, merchant_limit)
        flags["aggregated_merchants"] = len(kept_merchants) < len(merchant_totals)
        grouped_merchant_totals: dict[str, int] = defaultdict(int)
        grouped_merchant_labels: dict[str, str] = {}
        category_merchant_totals: dict[tuple[str, str], int] = defaultdict(int)

        for (raw_category_key, raw_merchant_key), amount_cents in raw_category_merchant_totals.items():
            category_node_id = grouped_category_node_ids[raw_category_key]
            merchant_node_id = (
                f"merchant:{raw_merchant_key}"
                if raw_merchant_key in kept_merchants
                else OTHER_MERCHANT_ID
            )
            grouped_merchant_totals[merchant_node_id] += amount_cents
            grouped_merchant_labels[merchant_node_id] = (
                merchant_labels.get(raw_merchant_key, raw_merchant_key)
                if raw_merchant_key in kept_merchants
                else "Other merchants"
            )
            category_merchant_totals[(category_node_id, merchant_node_id)] += amount_cents

        for merchant_key in sorted(
            grouped_merchant_totals,
            key=lambda key: (-grouped_merchant_totals[key], grouped_merchant_labels[key]),
        ):
            nodes.append(
                {
                    "id": merchant_key,
                    "label": grouped_merchant_labels[merchant_key],
                    "kind": "merchant",
                    "layer": merchant_layer,
                    "amount_cents": grouped_merchant_totals[merchant_key],
                    "merchant_name": grouped_merchant_labels[merchant_key],
                }
            )

        for (category_key, merchant_key), amount_cents in sorted(
            category_merchant_totals.items(),
            key=lambda item: (-item[1], item[0][0], item[0][1]),
        ):
            links.append(
                {
                    "source": category_key,
                    "target": merchant_key,
                    "value_cents": amount_cents,
                    "kind": "category_to_merchant",
                }
            )

    return {
        "period": {"from_date": from_date.isoformat(), "to_date": to_date.isoformat()},
        "mode": normalized_mode,
        "breakdown": normalized_breakdown,
        "model": {
            "kind": _report_sankey_model_kind(normalized_mode, normalized_breakdown),
            "transaction_provenance_supported": False,
        },
        "flags": flags,
        "summary": {
            "total_outflow_cents": total_outflow_cents,
            "total_inflow_basis_cents": total_inflow_basis_cents,
            "node_count": len(nodes),
            "link_count": len(links),
        },
        "nodes": nodes,
        "links": links,
    }
