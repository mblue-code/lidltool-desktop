from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Integer, and_, cast, exists, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from lidltool.analytics.scope import (
    VisibilityContext,
    visible_transaction_ids_subquery,
)
from lidltool.db.models import (
    DiscountEvent,
    Document,
    RecurringBillMatch,
    Source,
    Transaction,
    TransactionItem,
)


def _period_bounds(year: int, month: int | None = None) -> tuple[datetime, datetime]:
    if month is None:
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC)
        return start, end

    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )
    return start, end


def cents_to_currency(value: int) -> Decimal:
    return (Decimal(value) / Decimal("100")).quantize(Decimal("0.01"))


_NORMALIZED_DISCOUNT_TYPE_MAP: dict[str, str] = {
    "promotion": "promotion",
    "coupon": "coupon",
    "voucher": "coupon",
    "lidl_plus": "loyalty",
    "loyalty": "loyalty",
    "points": "loyalty",
    "mhd": "markdown",
    "markdown": "markdown",
    "cashback": "cashback",
}


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _exclusive_window_end(value: datetime) -> datetime:
    return value + timedelta(days=1)


SHOPPING_MANUAL_CATEGORY_PREFIXES = ("groceries", "shopping")
SHOPPING_MANUAL_CATEGORIES = {
    "bakery",
    "beverages",
    "deposit",
    "drugstore",
    "fish",
    "food",
    "frozen",
    "groceries",
    "household",
    "meat",
    "pantry",
    "personal_care",
    "produce",
    "snacks",
    "supermarket",
}


def _shopping_purchase_filter():
    category_item = aliased(TransactionItem)
    normalized_category = func.lower(func.trim(func.coalesce(category_item.category, "")))
    has_shopping_manual_category = exists(
        select(category_item.id).select_from(category_item).where(
            category_item.transaction_id == Transaction.id,
            or_(
                *[
                    normalized_category.like(f"{prefix}%")
                    for prefix in SHOPPING_MANUAL_CATEGORY_PREFIXES
                ],
                normalized_category.in_(SHOPPING_MANUAL_CATEGORIES),
            ),
        ).correlate(Transaction)
    )
    has_recurring_match = exists(
        select(RecurringBillMatch.id).select_from(RecurringBillMatch).where(
            RecurringBillMatch.transaction_id == Transaction.id
        ).correlate(Transaction)
    )
    return and_(
        ~has_recurring_match,
        or_(
            Source.kind.in_(("connector", "ocr")),
            and_(Source.kind == "manual", has_shopping_manual_category),
        ),
    )


def _shopping_window_transactions(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext,
    limit: int,
) -> list[dict[str, Any]]:
    end = _exclusive_window_end(to_date)
    stmt = (
        select(Transaction)
        .join(Source, Source.id == Transaction.source_id)
        .where(
            Transaction.purchased_at >= from_date,
            Transaction.purchased_at < end,
            Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
            _shopping_purchase_filter(),
        )
        .order_by(Transaction.purchased_at.desc(), Transaction.created_at.desc())
        .limit(limit)
    )
    transactions = session.execute(stmt).scalars().all()
    return [
        {
            "id": transaction.id,
            "purchased_at": transaction.purchased_at.isoformat(),
            "source_id": transaction.source_id,
            "user_id": transaction.user_id,
            "shared_group_id": transaction.shared_group_id,
            "store_name": transaction.merchant_name,
            "total_gross_cents": transaction.total_gross_cents,
            "currency": transaction.currency,
            "discount_total_cents": transaction.discount_total_cents or 0,
            "source_transaction_id": transaction.source_transaction_id,
        }
        for transaction in transactions
    ]


def _to_int(value: object) -> int:
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
            return 0
    return 0


def _month_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _normalize_discount_type(kind: str | None) -> str:
    value = (kind or "unknown").strip().lower()
    return _NORMALIZED_DISCOUNT_TYPE_MAP.get(value, "other")


def dashboard_available_years(
    session: Session,
    *,
    source_ids: list[str] | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    normalized_source_ids = _normalize_source_ids(source_ids)
    year_expr = func.strftime("%Y", Transaction.purchased_at)
    stmt = (
        select(year_expr)
        .where(Transaction.purchased_at.is_not(None))
        .group_by(year_expr)
        .order_by(year_expr.asc())
    )
    stmt = _apply_source_filter(stmt, normalized_source_ids)
    stmt = _apply_transaction_visibility(stmt, visibility)

    years = [
        int(raw_year)
        for (raw_year,) in session.execute(stmt).all()
        if raw_year is not None and str(raw_year).isdigit()
    ]
    return {
        "years": years,
        "min_year": years[0] if years else None,
        "max_year": years[-1] if years else None,
        "latest_year": years[-1] if years else None,
    }


def _apply_transaction_visibility(stmt: Any, visibility: VisibilityContext | None) -> Any:
    if visibility is None:
        return stmt
    return stmt.where(Transaction.id.in_(visible_transaction_ids_subquery(visibility)))


def _workspace_owner_payload(
    *,
    user_id: str | None,
    shared_group_id: str | None,
) -> dict[str, Any]:
    return {
        "workspace_kind": "shared_group" if shared_group_id else "personal",
        "shared_group_id": shared_group_id,
        "user_id": user_id,
    }


def _transaction_allocation_mode(
    transaction: Transaction,
    *,
    items: list[TransactionItem] | None = None,
) -> str:
    if transaction.shared_group_id:
        return "shared_receipt"
    if items is None:
        return "personal"
    if any(item.shared_group_id for item in items):
        return "split_items"
    return "personal"


def _normalize_source_ids(source_ids: list[str] | None) -> list[str] | None:
    if source_ids is None:
        return None
    normalized = sorted({source_id.strip() for source_id in source_ids if source_id.strip()})
    return normalized or None


def _apply_source_filter(stmt: Any, source_ids: list[str] | None) -> Any:
    if source_ids is None:
        return stmt
    return stmt.where(Transaction.source_id.in_(source_ids))


def _apply_household_spend_filter(stmt: Any) -> Any:
    return stmt.where(
        Transaction.direction == "outflow",
        Transaction.ledger_scope == "household",
        Transaction.dashboard_include.is_(True),
    )


def display_merchant_name(source_id: str | None, merchant_name: str | None) -> str:
    raw_name = (merchant_name or "").strip()
    raw_source = (source_id or "").strip()
    if raw_source.startswith("lidl_plus") and raw_name and not raw_name.lower().startswith("lidl"):
        return f"Lidl {raw_name}"
    return raw_name or raw_source or "Unknown"


def _shifted_datetime_expr(timestamp_expr: Any, tz_offset_minutes: int) -> Any:
    if tz_offset_minutes == 0:
        return timestamp_expr
    return func.datetime(timestamp_expr, f"{tz_offset_minutes:+d} minutes")


def _timing_hour_expr(shifted_datetime_expr: Any) -> Any:
    return cast(func.strftime("%H", shifted_datetime_expr), Integer)


def _timing_weekday_expr(shifted_datetime_expr: Any) -> Any:
    return (cast(func.strftime("%w", shifted_datetime_expr), Integer) + 6) % 7


def _timing_window_utc_bounds(
    *,
    purchased_from: datetime | None,
    purchased_to: datetime | None,
    tz_offset_minutes: int,
) -> tuple[datetime | None, datetime | None]:
    if purchased_from is None and purchased_to is None:
        return purchased_from, purchased_to
    offset = timedelta(minutes=tz_offset_minutes)
    return (
        purchased_from - offset if purchased_from is not None else None,
        purchased_to - offset if purchased_to is not None else None,
    )


def _is_owner(
    user_id: str | None,
    shared_group_id: str | None,
    visibility: VisibilityContext | None,
) -> bool | None:
    if visibility is None:
        return None
    if visibility.workspace_kind == "shared_group" and visibility.shared_group_id is not None:
        return shared_group_id == visibility.shared_group_id
    if visibility.is_service:
        return user_id in {None, visibility.user_id}
    return user_id == visibility.user_id


def month_stats(
    session: Session,
    year: int,
    month: int | None = None,
    *,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)

    total_stmt = select(func.coalesce(func.sum(Transaction.total_gross_cents), 0)).where(
        Transaction.purchased_at >= start,
        Transaction.purchased_at < end,
    )
    total_stmt = _apply_transaction_visibility(total_stmt, visibility)
    total_cents = session.execute(total_stmt).scalar_one()
    receipt_count_stmt = select(func.count(Transaction.id)).where(
        Transaction.purchased_at >= start, Transaction.purchased_at < end
    )
    receipt_count_stmt = _apply_transaction_visibility(receipt_count_stmt, visibility)
    receipt_count = session.execute(receipt_count_stmt).scalar_one()

    store_stmt = (
        select(
            func.coalesce(Transaction.merchant_name, "Unknown"),
            func.sum(Transaction.total_gross_cents),
            func.count(Transaction.id),
        )
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(func.coalesce(Transaction.merchant_name, "Unknown"))
        .order_by(func.sum(Transaction.total_gross_cents).desc())
        .limit(10)
    )
    store_stmt = _apply_transaction_visibility(store_stmt, visibility)
    store_rows = session.execute(store_stmt).all()

    category_stmt = (
        select(
            func.coalesce(TransactionItem.category, "uncategorized"),
            func.sum(TransactionItem.line_total_cents),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(func.coalesce(TransactionItem.category, "uncategorized"))
        .order_by(func.sum(TransactionItem.line_total_cents).desc())
        .limit(20)
    )
    category_stmt = _apply_transaction_visibility(category_stmt, visibility)
    category_rows = session.execute(category_stmt).all()

    top_item_stmt = (
        select(
            TransactionItem.name,
            func.sum(TransactionItem.line_total_cents),
            func.sum(TransactionItem.qty),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(TransactionItem.name)
        .order_by(func.sum(TransactionItem.line_total_cents).desc())
        .limit(20)
    )
    top_item_stmt = _apply_transaction_visibility(top_item_stmt, visibility)
    top_item_rows = session.execute(top_item_stmt).all()

    price_stmt = (
        select(
            TransactionItem.name,
            func.min(TransactionItem.unit_price_cents),
            func.max(TransactionItem.unit_price_cents),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(
            TransactionItem.unit_price_cents.is_not(None),
            Transaction.purchased_at >= start,
            Transaction.purchased_at < end,
        )
        .group_by(TransactionItem.name)
        .having(
            func.min(TransactionItem.unit_price_cents) != func.max(TransactionItem.unit_price_cents)
        )
        .order_by(
            (
                func.max(TransactionItem.unit_price_cents)
                - func.min(TransactionItem.unit_price_cents)
            ).desc()
        )
        .limit(20)
    )
    price_stmt = _apply_transaction_visibility(price_stmt, visibility)
    price_rows = session.execute(price_stmt).all()

    return {
        "period": {
            "year": year,
            "month": month,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "totals": {
            "receipt_count": int(receipt_count),
            "total_cents": int(total_cents),
            "total_currency": str(cents_to_currency(int(total_cents))),
        },
        "stores": [
            {
                "store_name": str(name),
                "total_cents": int(total or 0),
                "total_currency": str(cents_to_currency(int(total or 0))),
                "receipts": int(count),
            }
            for name, total, count in store_rows
        ],
        "categories": [
            {
                "category": str(category),
                "total_cents": int(total or 0),
                "total_currency": str(cents_to_currency(int(total or 0))),
            }
            for category, total in category_rows
        ],
        "top_items": [
            {
                "name": str(name),
                "total_cents": int(total or 0),
                "total_currency": str(cents_to_currency(int(total or 0))),
                "qty": float(qty or 0),
            }
            for name, total, qty in top_item_rows
        ],
        "price_changes": [
            {
                "name": str(name),
                "min_unit_price_cents": int(min_price),
                "max_unit_price_cents": int(max_price),
            }
            for name, min_price, max_price in price_rows
        ],
    }


def export_receipts(
    session: Session, *, visibility: VisibilityContext | None = None
) -> list[dict[str, Any]]:
    stmt = (
        select(Transaction)
        .options(selectinload(Transaction.items))
        .order_by(Transaction.purchased_at.desc())
    )
    stmt = _apply_transaction_visibility(stmt, visibility)
    receipts = session.execute(stmt).scalars().all()
    out: list[dict[str, Any]] = []
    for receipt in receipts:
        out.append(
            {
                "id": receipt.id,
                "shared_group_id": receipt.shared_group_id,
                "purchased_at": receipt.purchased_at.isoformat(),
                "store_id": receipt.source_id,
                "store_name": receipt.merchant_name,
                "store_address": None,
                "total_gross_cents": receipt.total_gross_cents,
                "currency": receipt.currency,
                "discount_total_cents": receipt.discount_total_cents,
                "items": [
                    {
                        "id": item.id,
                        "shared_group_id": item.shared_group_id,
                        "line_no": item.line_no,
                        "name": item.name,
                        "qty": float(item.qty),
                        "unit": item.unit,
                        "unit_price_cents": item.unit_price_cents,
                        "line_total_cents": item.line_total_cents,
                        "vat_rate": None,
                        "category": item.category,
                    }
                    for item in receipt.items
                ],
            }
        )
    return out


def savings_breakdown(
    session: Session,
    year: int | None = None,
    month: int | None = None,
    *,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start: datetime | None = None
    end: datetime | None = None
    if year is not None:
        start, end = _period_bounds(year, month)
    elif month is not None:
        raise ValueError("month requires year")

    stmt = select(
        func.coalesce(DiscountEvent.kind, "unknown"),
        func.count(DiscountEvent.id),
        func.coalesce(func.sum(DiscountEvent.amount_cents), 0),
    ).join(Transaction, Transaction.id == DiscountEvent.transaction_id)
    if start is not None and end is not None:
        stmt = stmt.where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
    stmt = _apply_transaction_visibility(stmt, visibility)
    stmt = stmt.group_by(func.coalesce(DiscountEvent.kind, "unknown"))

    rows = session.execute(stmt).all()
    total_events = sum(int(count) for _, count, _ in rows)
    total_saved_cents = sum(int(total or 0) for _, _, total in rows)
    ranked = sorted(rows, key=lambda item: int(item[2] or 0), reverse=True)

    return {
        "period": {"year": year, "month": month},
        "totals": {
            "discount_events": total_events,
            "saved_cents": total_saved_cents,
            "saved_currency": str(cents_to_currency(total_saved_cents)),
        },
        "by_type": [
            {
                "type": str(name),
                "discount_events": int(count),
                "saved_cents": int(saved or 0),
                "saved_currency": str(cents_to_currency(int(saved or 0))),
            }
            for name, count, saved in ranked
        ],
    }


def dashboard_totals(
    session: Session,
    year: int,
    month: int | None = None,
    *,
    source_ids: list[str] | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    normalized_source_ids = _normalize_source_ids(source_ids)
    gross_stmt = select(func.coalesce(func.sum(Transaction.total_gross_cents), 0)).where(
        Transaction.purchased_at >= start,
        Transaction.purchased_at < end,
    )
    gross_stmt = _apply_household_spend_filter(gross_stmt)
    gross_stmt = _apply_source_filter(gross_stmt, normalized_source_ids)
    gross_stmt = _apply_transaction_visibility(gross_stmt, visibility)
    gross_cents = int(session.execute(gross_stmt).scalar_one())
    discount_stmt = (
        select(func.coalesce(func.sum(DiscountEvent.amount_cents), 0))
        .join(Transaction, Transaction.id == DiscountEvent.transaction_id)
        .where(
            Transaction.purchased_at >= start,
            Transaction.purchased_at < end,
        )
    )
    discount_stmt = _apply_household_spend_filter(discount_stmt)
    discount_stmt = _apply_source_filter(discount_stmt, normalized_source_ids)
    discount_stmt = _apply_transaction_visibility(discount_stmt, visibility)
    discount_total_cents = int(session.execute(discount_stmt).scalar_one())
    receipt_count_stmt = select(func.count(Transaction.id)).where(
        Transaction.purchased_at >= start,
        Transaction.purchased_at < end,
    )
    receipt_count_stmt = _apply_household_spend_filter(receipt_count_stmt)
    receipt_count_stmt = _apply_source_filter(receipt_count_stmt, normalized_source_ids)
    receipt_count_stmt = _apply_transaction_visibility(receipt_count_stmt, visibility)
    receipt_count = int(session.execute(receipt_count_stmt).scalar_one())
    net_cents = gross_cents - discount_total_cents
    savings_rate = _safe_ratio(discount_total_cents, gross_cents)
    return {
        "period": {
            "year": year,
            "month": month,
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "totals": {
            "receipt_count": receipt_count,
            "gross_cents": gross_cents,
            "gross_currency": str(cents_to_currency(gross_cents)),
            "net_cents": net_cents,
            "net_currency": str(cents_to_currency(net_cents)),
            "discount_total_cents": discount_total_cents,
            "discount_total_currency": str(cents_to_currency(discount_total_cents)),
            "paid_cents": net_cents,
            "paid_currency": str(cents_to_currency(net_cents)),
            "saved_cents": discount_total_cents,
            "saved_currency": str(cents_to_currency(discount_total_cents)),
            "savings_rate": savings_rate,
        },
    }


def dashboard_trends(
    session: Session,
    *,
    year: int,
    months_back: int = 6,
    end_month: int = 12,
    source_ids: list[str] | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    if months_back < 1:
        raise ValueError("months_back must be >= 1")
    if not 1 <= end_month <= 12:
        raise ValueError("end_month must be between 1 and 12")

    start_month = max(1, end_month - months_back + 1)
    start, end = _period_bounds(year, start_month)
    _, series_end = _period_bounds(year, end_month)
    normalized_source_ids = _normalize_source_ids(source_ids)
    gross_stmt = (
        select(
            func.strftime("%Y", Transaction.purchased_at),
            func.strftime("%m", Transaction.purchased_at),
            func.coalesce(func.sum(Transaction.total_gross_cents), 0),
        )
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < series_end)
        .group_by(
            func.strftime("%Y", Transaction.purchased_at),
            func.strftime("%m", Transaction.purchased_at),
        )
    )
    gross_stmt = _apply_household_spend_filter(gross_stmt)
    gross_stmt = _apply_source_filter(gross_stmt, normalized_source_ids)
    gross_stmt = _apply_transaction_visibility(gross_stmt, visibility)
    saved_stmt = (
        select(
            func.strftime("%Y", Transaction.purchased_at),
            func.strftime("%m", Transaction.purchased_at),
            func.coalesce(func.sum(DiscountEvent.amount_cents), 0),
        )
        .join(Transaction, Transaction.id == DiscountEvent.transaction_id)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < series_end)
        .group_by(
            func.strftime("%Y", Transaction.purchased_at),
            func.strftime("%m", Transaction.purchased_at),
        )
    )
    saved_stmt = _apply_household_spend_filter(saved_stmt)
    saved_stmt = _apply_source_filter(saved_stmt, normalized_source_ids)
    saved_stmt = _apply_transaction_visibility(saved_stmt, visibility)
    gross_rows = session.execute(gross_stmt).all()
    saved_rows = session.execute(saved_stmt).all()

    gross_map: dict[str, int] = {}
    for year_s, month_s, total in gross_rows:
        if year_s is None or month_s is None:
            continue
        gross_map[f"{year_s}-{month_s}"] = int(total or 0)
    saved_map: dict[str, int] = {}
    for year_s, month_s, total in saved_rows:
        if year_s is None or month_s is None:
            continue
        saved_map[f"{year_s}-{month_s}"] = int(total or 0)

    points: list[dict[str, Any]] = []
    for month in range(start_month, end_month + 1):
        key = _month_key(year, month)
        gross_cents = gross_map.get(key, 0)
        discount_total_cents = saved_map.get(key, 0)
        net_cents = gross_cents - discount_total_cents
        points.append(
            {
                "year": year,
                "month": month,
                "period_key": key,
                "gross_cents": gross_cents,
                "gross_currency": str(cents_to_currency(gross_cents)),
                "net_cents": net_cents,
                "net_currency": str(cents_to_currency(net_cents)),
                "discount_total_cents": discount_total_cents,
                "discount_total_currency": str(cents_to_currency(discount_total_cents)),
                "paid_cents": net_cents,
                "saved_cents": discount_total_cents,
                "paid_currency": str(cents_to_currency(net_cents)),
                "saved_currency": str(cents_to_currency(discount_total_cents)),
                "savings_rate": _safe_ratio(discount_total_cents, gross_cents),
            }
        )
    return {
        "period": {
            "year": year,
            "start_month": start_month,
            "end_month": end_month,
            "months_back": months_back,
        },
        "points": points,
    }


def dashboard_savings_breakdown(
    session: Session,
    *,
    year: int,
    month: int | None = None,
    view: str = "native",
    source_ids: list[str] | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    normalized_source_ids = _normalize_source_ids(source_ids)
    stmt = (
        select(
            func.coalesce(DiscountEvent.kind, "unknown"),
            func.count(DiscountEvent.id),
            func.coalesce(func.sum(DiscountEvent.amount_cents), 0),
        )
        .join(Transaction, Transaction.id == DiscountEvent.transaction_id)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(func.coalesce(DiscountEvent.kind, "unknown"))
    )
    stmt = _apply_source_filter(stmt, normalized_source_ids)
    stmt = _apply_transaction_visibility(stmt, visibility)
    rows = session.execute(stmt).all()

    if view not in {"native", "normalized"}:
        raise ValueError("view must be one of: native, normalized")

    grouped: dict[str, dict[str, int]] = {}
    for kind, count, saved in rows:
        native_kind = str(kind)
        bucket = native_kind if view == "native" else _normalize_discount_type(native_kind)
        row = grouped.setdefault(bucket, {"discount_events": 0, "saved_cents": 0})
        row["discount_events"] += int(count or 0)
        row["saved_cents"] += int(saved or 0)

    by_type = sorted(grouped.items(), key=lambda item: item[1]["saved_cents"], reverse=True)
    total_events = sum(data["discount_events"] for _, data in by_type)
    total_saved_cents = sum(data["saved_cents"] for _, data in by_type)
    return {
        "period": {"year": year, "month": month},
        "view": view,
        "totals": {
            "discount_events": total_events,
            "saved_cents": total_saved_cents,
            "saved_currency": str(cents_to_currency(total_saved_cents)),
        },
        "by_type": [
            {
                "type": kind,
                "discount_events": data["discount_events"],
                "saved_cents": data["saved_cents"],
                "saved_currency": str(cents_to_currency(data["saved_cents"])),
            }
            for kind, data in by_type
        ],
    }


def dashboard_retailer_composition(
    session: Session,
    *,
    year: int,
    month: int | None = None,
    source_ids: list[str] | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    normalized_source_ids = _normalize_source_ids(source_ids)
    gross_stmt = (
        select(
            Transaction.source_id,
            func.coalesce(Source.display_name, Transaction.merchant_name, Transaction.source_id),
            func.coalesce(func.sum(Transaction.total_gross_cents), 0),
            func.count(Transaction.id),
        )
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id, isouter=True)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(
            Transaction.source_id,
            func.coalesce(Source.display_name, Transaction.merchant_name, Transaction.source_id),
        )
    )
    gross_stmt = _apply_household_spend_filter(gross_stmt)
    gross_stmt = _apply_source_filter(gross_stmt, normalized_source_ids)
    gross_stmt = _apply_transaction_visibility(gross_stmt, visibility)
    gross_rows = session.execute(gross_stmt).all()
    saved_stmt = (
        select(Transaction.source_id, func.coalesce(func.sum(DiscountEvent.amount_cents), 0))
        .join(Transaction, Transaction.id == DiscountEvent.transaction_id)
        .where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
        .group_by(Transaction.source_id)
    )
    saved_stmt = _apply_household_spend_filter(saved_stmt)
    saved_stmt = _apply_source_filter(saved_stmt, normalized_source_ids)
    saved_stmt = _apply_transaction_visibility(saved_stmt, visibility)
    saved_rows = session.execute(saved_stmt).all()

    gross_map = {str(source_id): int(total or 0) for source_id, _, total, _ in gross_rows}
    saved_map = {str(source_id): int(total or 0) for source_id, total in saved_rows}
    count_map = {str(source_id): int(count or 0) for source_id, _, _, count in gross_rows}
    name_map = {str(source_id): str(name) for source_id, name, _, _ in gross_rows}
    source_ids = sorted(set(gross_map.keys()) | set(saved_map.keys()))

    gross_total = sum(gross_map.get(source_id, 0) for source_id in source_ids)
    discount_total = sum(saved_map.get(source_id, 0) for source_id in source_ids)
    net_total = gross_total - discount_total

    retailers = sorted(
        [
            {
                "source_id": source_id,
                "retailer": name_map.get(source_id, source_id),
                "receipt_count": count_map.get(source_id, 0),
                "gross_cents": gross_map.get(source_id, 0),
                "gross_currency": str(cents_to_currency(gross_map.get(source_id, 0))),
                "net_cents": gross_map.get(source_id, 0) - saved_map.get(source_id, 0),
                "net_currency": str(
                    cents_to_currency(gross_map.get(source_id, 0) - saved_map.get(source_id, 0))
                ),
                "discount_total_cents": saved_map.get(source_id, 0),
                "discount_total_currency": str(cents_to_currency(saved_map.get(source_id, 0))),
                "paid_cents": gross_map.get(source_id, 0) - saved_map.get(source_id, 0),
                "saved_cents": saved_map.get(source_id, 0),
                "paid_currency": str(
                    cents_to_currency(gross_map.get(source_id, 0) - saved_map.get(source_id, 0))
                ),
                "saved_currency": str(cents_to_currency(saved_map.get(source_id, 0))),
                "gross_share": _safe_ratio(gross_map.get(source_id, 0), gross_total),
                "net_share": _safe_ratio(
                    gross_map.get(source_id, 0) - saved_map.get(source_id, 0),
                    net_total,
                ),
                "paid_share": _safe_ratio(
                    gross_map.get(source_id, 0) - saved_map.get(source_id, 0),
                    net_total,
                ),
                "saved_share": _safe_ratio(saved_map.get(source_id, 0), discount_total),
                "savings_rate": _safe_ratio(
                    saved_map.get(source_id, 0),
                    gross_map.get(source_id, 0),
                ),
            }
            for source_id in source_ids
        ],
        key=lambda row: _to_int(row["saved_cents"]),
        reverse=True,
    )

    return {
        "period": {"year": year, "month": month},
        "totals": {
            "gross_cents": gross_total,
            "gross_currency": str(cents_to_currency(gross_total)),
            "net_cents": net_total,
            "net_currency": str(cents_to_currency(net_total)),
            "discount_total_cents": discount_total,
            "discount_total_currency": str(cents_to_currency(discount_total)),
            "paid_cents": net_total,
            "saved_cents": discount_total,
            "paid_currency": str(cents_to_currency(net_total)),
            "saved_currency": str(cents_to_currency(discount_total)),
            "savings_rate": _safe_ratio(discount_total, gross_total),
        },
        "retailers": retailers,
    }


def dashboard_window_totals(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext | None = None,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    end = _exclusive_window_end(to_date)
    normalized_source_ids = _normalize_source_ids(source_ids)
    stmt = select(
        func.count(Transaction.id),
        func.coalesce(func.sum(Transaction.total_gross_cents), 0),
        func.coalesce(func.sum(Transaction.discount_total_cents), 0),
    ).where(
        Transaction.purchased_at >= from_date,
        Transaction.purchased_at < end,
    )
    stmt = _apply_household_spend_filter(stmt)
    stmt = _apply_source_filter(stmt, normalized_source_ids)
    stmt = _apply_transaction_visibility(stmt, visibility)
    receipt_count, gross_cents, discount_cents = session.execute(stmt).one()
    net_cents = int(gross_cents or 0) - int(discount_cents or 0)
    return {
        "receipt_count": int(receipt_count or 0),
        "gross_cents": int(gross_cents or 0),
        "discount_total_cents": int(discount_cents or 0),
        "net_cents": net_cents,
    }


def dashboard_category_spend_summary(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext | None = None,
    source_ids: list[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    end = _exclusive_window_end(to_date)
    normalized_source_ids = _normalize_source_ids(source_ids)
    stmt = (
        select(
            func.coalesce(TransactionItem.category, "uncategorized"),
            func.coalesce(func.sum(TransactionItem.line_total_cents), 0),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .where(Transaction.purchased_at >= from_date, Transaction.purchased_at < end)
        .group_by(func.coalesce(TransactionItem.category, "uncategorized"))
        .order_by(func.coalesce(func.sum(TransactionItem.line_total_cents), 0).desc())
        .limit(limit)
    )
    stmt = _apply_household_spend_filter(stmt)
    stmt = _apply_source_filter(stmt, normalized_source_ids)
    stmt = _apply_transaction_visibility(stmt, visibility)
    rows = session.execute(stmt).all()
    total_cents = sum(int(amount or 0) for _, amount in rows)
    return [
        {
            "category": str(category or "uncategorized"),
            "amount_cents": int(amount or 0),
            "share": _safe_ratio(int(amount or 0), total_cents),
        }
        for category, amount in rows
    ]


def dashboard_window_transactions(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    result = search_transactions(
        session,
        purchased_from=from_date,
        purchased_to=_exclusive_window_end(to_date),
        limit=limit,
        offset=0,
        visibility=visibility,
    )
    return result["transactions"]


def dashboard_merchant_summary(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext | None = None,
    source_ids: list[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    end = _exclusive_window_end(to_date)
    normalized_source_ids = _normalize_source_ids(source_ids)
    stmt = (
        select(
            Transaction.source_id,
            func.coalesce(Transaction.merchant_name, Source.display_name, Transaction.source_id),
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.total_gross_cents), 0),
            func.max(Transaction.purchased_at),
        )
        .select_from(Transaction)
        .join(Source, Source.id == Transaction.source_id, isouter=True)
        .where(Transaction.purchased_at >= from_date, Transaction.purchased_at < end)
        .group_by(Transaction.source_id, func.coalesce(Transaction.merchant_name, Source.display_name, Transaction.source_id))
        .order_by(func.coalesce(func.sum(Transaction.total_gross_cents), 0).desc())
        .limit(limit)
    )
    stmt = _apply_household_spend_filter(stmt)
    stmt = _apply_source_filter(stmt, normalized_source_ids)
    stmt = _apply_transaction_visibility(stmt, visibility)
    rows = session.execute(stmt).all()
    return [
        {
            "source_id": str(source_id or ""),
            "merchant": display_merchant_name(str(source_id or ""), str(name or "")),
            "receipt_count": int(count or 0),
            "spend_cents": int(spend or 0),
            "last_purchased_at": last_purchased_at.isoformat() if last_purchased_at else None,
        }
        for source_id, name, count, spend, last_purchased_at in rows
    ]


def grocery_workspace_summary(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext,
    limit: int = 12,
) -> dict[str, Any]:
    end = _exclusive_window_end(to_date)
    totals_stmt = select(
        func.count(Transaction.id),
        func.coalesce(func.sum(Transaction.total_gross_cents), 0),
        func.count(func.distinct(func.coalesce(Transaction.merchant_name, Transaction.source_id))),
    ).join(Source, Source.id == Transaction.source_id).where(
        Transaction.purchased_at >= from_date,
        Transaction.purchased_at < end,
        _shopping_purchase_filter(),
    )
    totals_stmt = _apply_transaction_visibility(totals_stmt, visibility)
    receipt_count, total_cents, merchant_count = session.execute(totals_stmt).one()

    transactions = _shopping_window_transactions(
        session,
        from_date=from_date,
        to_date=to_date,
        visibility=visibility,
        limit=limit,
    )
    total_cents = int(total_cents or 0)
    receipt_count = int(receipt_count or 0)
    merchant_count = int(merchant_count or 0)
    category_rows = (
        session.execute(
            select(
                func.coalesce(TransactionItem.category, "uncategorized"),
                func.coalesce(func.sum(TransactionItem.line_total_cents), 0),
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .join(Source, Source.id == Transaction.source_id)
            .where(
                Transaction.purchased_at >= from_date,
                Transaction.purchased_at < end,
                Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
                _shopping_purchase_filter(),
            )
            .group_by(func.coalesce(TransactionItem.category, "uncategorized"))
            .order_by(func.sum(TransactionItem.line_total_cents).desc())
            .limit(8)
        )
        .all()
    )
    return {
        "period": {
            "from_date": from_date.date().isoformat(),
            "to_date": to_date.date().isoformat(),
        },
        "totals": {
            "spend_cents": total_cents,
            "receipt_count": receipt_count,
            "average_basket_cents": round(total_cents / receipt_count) if receipt_count else 0,
            "merchant_count": merchant_count,
        },
        "category_breakdown": [
            {"category": str(category), "amount_cents": int(amount_cents or 0)}
            for category, amount_cents in category_rows
        ],
        "recent_transactions": transactions,
    }


def merchant_workspace_summary(
    session: Session,
    *,
    from_date: datetime,
    to_date: datetime,
    visibility: VisibilityContext,
    search: str | None = None,
    limit: int = 40,
) -> dict[str, Any]:
    end = _exclusive_window_end(to_date)
    merchant_filter = (search or "").strip().lower()
    merchant_buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "merchant": "Unknown",
            "receipt_count": 0,
            "spend_cents": 0,
            "last_purchased_at": None,
            "source_ids": set(),
        }
    )
    rows = (
        session.execute(
            select(Transaction)
            .where(
                Transaction.purchased_at >= from_date,
                Transaction.purchased_at < end,
                Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
            )
            .order_by(Transaction.purchased_at.desc())
        )
        .scalars()
        .all()
    )
    for tx in rows:
        merchant_name = (tx.merchant_name or tx.source_id or "Unknown").strip() or "Unknown"
        if merchant_filter and merchant_filter not in merchant_name.lower():
            continue
        bucket = merchant_buckets[merchant_name]
        bucket["merchant"] = merchant_name
        bucket["receipt_count"] += 1
        bucket["spend_cents"] += tx.total_gross_cents
        bucket["source_ids"].add(tx.source_id)
        if bucket["last_purchased_at"] is None or tx.purchased_at > bucket["last_purchased_at"]:
            bucket["last_purchased_at"] = tx.purchased_at

    dominant_category_rows = (
        session.execute(
            select(
                func.coalesce(Transaction.merchant_name, Transaction.source_id, "Unknown"),
                func.coalesce(TransactionItem.category, "uncategorized"),
                func.coalesce(func.sum(TransactionItem.line_total_cents), 0),
            )
            .join(Transaction, Transaction.id == TransactionItem.transaction_id)
            .where(
                Transaction.purchased_at >= from_date,
                Transaction.purchased_at < end,
                Transaction.id.in_(visible_transaction_ids_subquery(visibility)),
            )
            .group_by(
                func.coalesce(Transaction.merchant_name, Transaction.source_id, "Unknown"),
                func.coalesce(TransactionItem.category, "uncategorized"),
            )
            .order_by(
                func.coalesce(Transaction.merchant_name, Transaction.source_id, "Unknown").asc(),
                func.sum(TransactionItem.line_total_cents).desc(),
            )
        )
        .all()
    )
    dominant_categories: dict[str, str] = {}
    for merchant_name, category, _amount_cents in dominant_category_rows:
        merchant_key = str(merchant_name or "Unknown")
        if merchant_key not in dominant_categories:
            dominant_categories[merchant_key] = str(category)

    items = sorted(
        (
            {
                "merchant": bucket["merchant"],
                "receipt_count": bucket["receipt_count"],
                "spend_cents": bucket["spend_cents"],
                "last_purchased_at": bucket["last_purchased_at"].isoformat()
                if bucket["last_purchased_at"] is not None
                else None,
                "source_ids": sorted(bucket["source_ids"]),
                "dominant_category": dominant_categories.get(bucket["merchant"]),
            }
            for bucket in merchant_buckets.values()
        ),
        key=lambda item: (-item["spend_cents"], item["merchant"].lower()),
    )[:limit]
    return {
        "period": {
            "from_date": from_date.date().isoformat(),
            "to_date": to_date.date().isoformat(),
        },
        "count": len(items),
        "items": items,
    }


def search_transactions(
    session: Session,
    *,
    query: str | None = None,
    year: int | None = None,
    month: int | None = None,
    source_id: str | None = None,
    source_kind: str | None = None,
    weekday: int | None = None,
    hour: int | None = None,
    tz_offset_minutes: int = 0,
    merchant_name: str | None = None,
    min_total_cents: int | None = None,
    max_total_cents: int | None = None,
    purchased_from: datetime | None = None,
    purchased_to: datetime | None = None,
    sort_by: Literal[
        "purchased_at", "merchant_name", "source_id", "total_gross_cents", "discount_total_cents"
    ] = "purchased_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    limit: int = 50,
    offset: int = 0,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    if month is not None and year is None:
        raise ValueError("month requires year")
    if not -840 <= tz_offset_minutes <= 840:
        raise ValueError("tz_offset_minutes must be between -840 and 840")
    if weekday is not None and not 0 <= weekday <= 6:
        raise ValueError("weekday must be between 0 and 6")
    if hour is not None and not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")

    start: datetime | None = None
    end: datetime | None = None
    if year is not None:
        start, end = _period_bounds(year, month)

    stmt = select(Transaction).options(
        selectinload(Transaction.source),
        selectinload(Transaction.user),
    )
    stmt = _apply_transaction_visibility(stmt, visibility)
    if start is not None and end is not None:
        stmt = stmt.where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
    timing_filters_enabled = weekday is not None or hour is not None
    purchased_from_utc = purchased_from
    purchased_to_utc = purchased_to
    if timing_filters_enabled:
        purchased_from_utc, purchased_to_utc = _timing_window_utc_bounds(
            purchased_from=purchased_from,
            purchased_to=purchased_to,
            tz_offset_minutes=tz_offset_minutes,
        )

    if purchased_from_utc is not None:
        stmt = stmt.where(Transaction.purchased_at >= purchased_from_utc)
    if purchased_to_utc is not None:
        stmt = stmt.where(Transaction.purchased_at < purchased_to_utc)
    if source_id:
        stmt = stmt.where(Transaction.source_id == source_id)
    if source_kind:
        stmt = stmt.where(Transaction.source.has(Source.kind == source_kind))
    if timing_filters_enabled:
        shifted_purchased_at = _shifted_datetime_expr(Transaction.purchased_at, tz_offset_minutes)
        if weekday is not None:
            stmt = stmt.where(_timing_weekday_expr(shifted_purchased_at) == weekday)
        if hour is not None:
            stmt = stmt.where(_timing_hour_expr(shifted_purchased_at) == hour)
    if merchant_name:
        merchant_query = f"%{merchant_name.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(Transaction.merchant_name, "")).like(merchant_query)
        )
    if min_total_cents is not None:
        stmt = stmt.where(Transaction.total_gross_cents >= min_total_cents)
    if max_total_cents is not None:
        stmt = stmt.where(Transaction.total_gross_cents <= max_total_cents)
    if query:
        q = f"%{query.lower()}%"
        stmt = stmt.where(
            func.lower(func.coalesce(Transaction.merchant_name, "")).like(q)
            | Transaction.items.any(func.lower(TransactionItem.name).like(q))
        )

    allowed_sort_by = {
        "purchased_at",
        "merchant_name",
        "source_id",
        "total_gross_cents",
        "discount_total_cents",
    }
    if sort_by not in allowed_sort_by:
        raise ValueError(
            "sort_by must be one of: purchased_at, merchant_name, source_id, total_gross_cents, discount_total_cents"
        )
    if sort_dir not in {"asc", "desc"}:
        raise ValueError("sort_dir must be one of: asc, desc")

    sort_expr_map = {
        "purchased_at": Transaction.purchased_at,
        "merchant_name": func.lower(func.coalesce(Transaction.merchant_name, "")),
        "source_id": func.lower(Transaction.source_id),
        "total_gross_cents": Transaction.total_gross_cents,
        "discount_total_cents": func.coalesce(Transaction.discount_total_cents, 0),
    }
    sort_expr = sort_expr_map[sort_by]
    tie_breaker = Transaction.id.asc() if sort_dir == "asc" else Transaction.id.desc()
    ordered_stmt = stmt.order_by(
        sort_expr.asc() if sort_dir == "asc" else sort_expr.desc(),
        tie_breaker,
    )

    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(ordered_stmt.offset(offset).limit(limit)).scalars().all()

    items = [
        {
            "id": receipt.id,
            "purchased_at": receipt.purchased_at.isoformat(),
            "source_id": receipt.source_id,
            "user_id": receipt.user_id,
            "shared_group_id": receipt.shared_group_id,
            "store_name": receipt.merchant_name,
            "total_gross_cents": receipt.total_gross_cents,
            "direction": receipt.direction,
            "ledger_scope": receipt.ledger_scope,
            "dashboard_include": receipt.dashboard_include,
            "currency": receipt.currency,
            "discount_total_cents": receipt.discount_total_cents,
            "source_transaction_id": receipt.source_transaction_id,
            "allocation_mode": "shared_receipt" if receipt.shared_group_id else "personal",
            "owner_username": receipt.user.username if receipt.user is not None else None,
            "owner_display_name": (
                receipt.user.display_name if receipt.user is not None else None
            ),
            "workspace_kind": "shared_group" if receipt.shared_group_id else "personal",
            "is_owner": _is_owner(receipt.user_id, receipt.shared_group_id, visibility),
        }
        for receipt in rows
    ]
    return {
        "query": query,
        "filters": {
            "year": year,
            "month": month,
            "source_id": source_id,
            "source_kind": source_kind,
            "weekday": weekday,
            "hour": hour,
            "tz_offset_minutes": tz_offset_minutes,
            "merchant_name": merchant_name,
            "min_total_cents": min_total_cents,
            "max_total_cents": max_total_cents,
            "purchased_from": purchased_from.isoformat() if purchased_from is not None else None,
            "purchased_to": purchased_to.isoformat() if purchased_to is not None else None,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        },
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "total": int(total),
        "items": items,
        "transactions": items,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "total": int(total),
        },
    }


def transaction_detail(
    session: Session,
    *,
    transaction_id: str,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any] | None:
    tx_stmt = (
        select(Transaction)
        .options(
            selectinload(Transaction.source),
            selectinload(Transaction.user),
        )
        .where(Transaction.id == transaction_id)
    )
    tx_stmt = _apply_transaction_visibility(tx_stmt, visibility)
    transaction = session.execute(tx_stmt.limit(1)).scalar_one_or_none()
    if transaction is None:
        return None
    is_owner = _is_owner(transaction.user_id, transaction.shared_group_id, visibility)
    items_stmt = (
        select(TransactionItem)
        .where(TransactionItem.transaction_id == transaction.id)
        .order_by(TransactionItem.line_no.asc(), TransactionItem.id.asc())
    )
    if (
        visibility is not None
        and visibility.workspace_kind == "shared_group"
        and visibility.shared_group_id is not None
        and transaction.shared_group_id != visibility.shared_group_id
        and (transaction.source is None or transaction.source.shared_group_id != visibility.shared_group_id)
    ):
        items_stmt = items_stmt.where(TransactionItem.shared_group_id == visibility.shared_group_id)
    items = session.execute(items_stmt).scalars().all()
    discounts_stmt = (
        select(DiscountEvent)
        .where(DiscountEvent.transaction_id == transaction.id)
        .order_by(DiscountEvent.scope.asc(), DiscountEvent.id.asc())
    )
    if visibility is not None and visibility.workspace_kind == "shared_group" and visibility.shared_group_id is not None:
        if transaction.shared_group_id != visibility.shared_group_id and (
            transaction.source is None or transaction.source.shared_group_id != visibility.shared_group_id
        ):
            discounts_stmt = discounts_stmt.where(
                DiscountEvent.transaction_item_id.in_(
                    select(TransactionItem.id).where(
                        TransactionItem.transaction_id == transaction.id,
                        TransactionItem.shared_group_id == visibility.shared_group_id,
                    )
                )
            )
    discounts = session.execute(discounts_stmt).scalars().all()
    documents = (
        session.execute(
            select(Document)
            .where(Document.transaction_id == transaction.id)
            .order_by(Document.created_at.desc(), Document.id.desc())
        )
        .scalars()
        .all()
    )
    return {
        "transaction": {
            "id": transaction.id,
            "source_id": transaction.source_id,
            "user_id": transaction.user_id,
            "shared_group_id": transaction.shared_group_id,
            "source_account_id": transaction.source_account_id,
            "source_transaction_id": transaction.source_transaction_id,
            "purchased_at": transaction.purchased_at.isoformat(),
            "merchant_name": transaction.merchant_name,
            "total_gross_cents": transaction.total_gross_cents,
            "direction": transaction.direction,
            "ledger_scope": transaction.ledger_scope,
            "dashboard_include": transaction.dashboard_include,
            "currency": transaction.currency,
            "discount_total_cents": transaction.discount_total_cents,
            "allocation_mode": _transaction_allocation_mode(transaction, items=items),
            "owner_username": transaction.user.username if transaction.user is not None else None,
            "owner_display_name": (
                transaction.user.display_name if transaction.user is not None else None
            ),
            "workspace_kind": "shared_group" if transaction.shared_group_id else "personal",
            "is_owner": is_owner,
            "confidence": (
                float(transaction.confidence) if transaction.confidence is not None else None
            ),
            "raw_payload": transaction.raw_payload,
        },
        "items": [
            {
                "id": item.id,
                "shared_group_id": item.shared_group_id,
                "source_item_id": item.source_item_id,
                "line_no": item.line_no,
                "name": item.name,
                "qty": float(item.qty),
                "unit": item.unit,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": item.line_total_cents,
                "category": item.category,
                "category_id": item.category_id,
                "category_method": item.category_method,
                "category_confidence": (
                    float(item.category_confidence)
                    if item.category_confidence is not None
                    else None
                ),
                "category_source_value": item.category_source_value,
                "category_version": item.category_version,
                "is_shared_allocation": item.shared_group_id is not None,
                "confidence": float(item.confidence) if item.confidence is not None else None,
                "raw_payload": item.raw_payload,
            }
            for item in items
        ],
        "discounts": [
            {
                "id": discount.id,
                "transaction_item_id": discount.transaction_item_id,
                "source": discount.source,
                "source_discount_code": discount.source_discount_code,
                "source_label": discount.source_label,
                "scope": discount.scope,
                "amount_cents": discount.amount_cents,
                "currency": discount.currency,
                "kind": discount.kind,
                "subkind": discount.subkind,
                "funded_by": discount.funded_by,
                "is_loyalty_program": discount.is_loyalty_program,
                "confidence": (
                    float(discount.confidence) if discount.confidence is not None else None
                ),
                "raw_payload": discount.raw_payload,
            }
            for discount in discounts
        ],
        "documents": [
            {
                "id": document.id,
                "source_id": document.source_id,
                "shared_group_id": document.shared_group_id,
                "storage_uri": document.storage_uri,
                "mime_type": document.mime_type,
                "file_name": document.file_name,
                "ocr_status": document.ocr_status,
                "review_status": document.review_status,
                "ocr_confidence": (
                    float(document.ocr_confidence) if document.ocr_confidence is not None else None
                ),
                "created_at": document.created_at.isoformat(),
            }
            for document in documents
        ],
    }


def review_queue(
    session: Session,
    *,
    threshold: float,
    limit: int = 50,
    offset: int = 0,
    status: str = "needs_review",
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = (
        select(Document, Transaction)
        .join(Transaction, Document.transaction_id == Transaction.id)
        .where(Document.review_status == status)
        .where(
            (Transaction.confidence.is_(None))
            | (Transaction.confidence < Decimal(f"{threshold:.3f}"))
        )
    )
    stmt = _apply_transaction_visibility(stmt, visibility)
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(
        stmt.order_by(Document.created_at.desc(), Document.id.desc()).offset(offset).limit(limit)
    ).all()
    items = [
        {
            "document_id": document.id,
            "transaction_id": transaction.id,
            "source_id": document.source_id,
            "shared_group_id": document.shared_group_id,
            "review_status": document.review_status,
            "ocr_status": document.ocr_status,
            "merchant_name": transaction.merchant_name,
            "purchased_at": transaction.purchased_at.isoformat(),
            "total_gross_cents": transaction.total_gross_cents,
            "currency": transaction.currency,
            "transaction_confidence": (
                float(transaction.confidence) if transaction.confidence is not None else None
            ),
            "ocr_confidence": (
                float(document.ocr_confidence) if document.ocr_confidence is not None else None
            ),
            "created_at": document.created_at.isoformat(),
        }
        for document, transaction in rows
    ]
    return {
        "limit": limit,
        "offset": offset,
        "count": len(items),
        "total": int(total),
        "items": items,
    }


def review_queue_detail(
    session: Session,
    *,
    document_id: str,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any] | None:
    document = session.get(Document, document_id)
    if document is None or document.transaction_id is None:
        return None
    tx_stmt = select(Transaction).where(Transaction.id == document.transaction_id)
    tx_stmt = _apply_transaction_visibility(tx_stmt, visibility)
    transaction = session.execute(tx_stmt.limit(1)).scalar_one_or_none()
    if transaction is None:
        return None
    items = (
        session.execute(
            select(TransactionItem)
            .where(TransactionItem.transaction_id == transaction.id)
            .order_by(TransactionItem.line_no.asc(), TransactionItem.id.asc())
        )
        .scalars()
        .all()
    )
    confidence_meta: dict[str, Any] = {}
    if isinstance(document.metadata_json, dict):
        raw_conf = document.metadata_json.get("confidence")
        if isinstance(raw_conf, dict):
            confidence_meta = raw_conf

    return {
        "document": {
            "id": document.id,
            "transaction_id": transaction.id,
            "source_id": document.source_id,
            "review_status": document.review_status,
            "ocr_status": document.ocr_status,
            "file_name": document.file_name,
            "mime_type": document.mime_type,
            "storage_uri": document.storage_uri,
            "ocr_provider": document.ocr_provider,
            "ocr_confidence": (
                float(document.ocr_confidence) if document.ocr_confidence is not None else None
            ),
            "ocr_fallback_used": document.ocr_fallback_used,
            "ocr_latency_ms": document.ocr_latency_ms,
            "ocr_text": document.ocr_text,
            "created_at": document.created_at.isoformat(),
            "processed_at": (
                document.ocr_processed_at.isoformat()
                if document.ocr_processed_at is not None
                else None
            ),
        },
        "transaction": {
            "id": transaction.id,
            "source_id": transaction.source_id,
            "shared_group_id": transaction.shared_group_id,
            "source_transaction_id": transaction.source_transaction_id,
            "purchased_at": transaction.purchased_at.isoformat(),
            "merchant_name": transaction.merchant_name,
            "total_gross_cents": transaction.total_gross_cents,
            "currency": transaction.currency,
            "discount_total_cents": transaction.discount_total_cents,
            "confidence": (
                float(transaction.confidence) if transaction.confidence is not None else None
            ),
            "raw_payload": transaction.raw_payload,
        },
        "items": [
            {
                "id": item.id,
                "line_no": item.line_no,
                "name": item.name,
                "qty": float(item.qty),
                "unit": item.unit,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": item.line_total_cents,
                "category": item.category,
                "confidence": float(item.confidence) if item.confidence is not None else None,
                "raw_payload": item.raw_payload,
            }
            for item in items
        ],
        "confidence": confidence_meta,
    }
