from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session, selectinload

from lidltool.analytics.product_matcher import create_manual_product_alias
from lidltool.analytics.query_engine import run_query
from lidltool.analytics.scope import (
    VisibilityContext,
    observation_visibility_filter,
    personal_source_filter,
    visible_transaction_ids_subquery,
)
from lidltool.db.models import (
    ComparisonGroup,
    ComparisonGroupMember,
    Document,
    ItemObservation,
    Product,
    ProductAlias,
    SavedQuery,
    Source,
    Transaction,
    TransactionItem,
)


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _preset_saved_queries() -> list[dict[str, Any]]:
    return [
        {
            "query_id": "preset-total-spend-all-time",
            "name": "Total spend all time",
            "description": "Monthly net spend across all available data.",
            "query_json": {
                "metrics": ["net_total"],
                "dimensions": ["month"],
                "filters": {},
                "time_grain": "month",
                "sort_by": "month",
                "sort_dir": "asc",
            },
        },
        {
            "query_id": "preset-groceries-last-90d-by-source",
            "name": "Groceries last 90 days by source",
            "description": "Net spend by source over the last 90 days.",
            "query_json": {
                "metrics": ["net_total"],
                "dimensions": ["source_kind"],
                "filters": {"date_preset": "last90d"},
                "sort_by": "net_total",
                "sort_dir": "desc",
            },
        },
        {
            "query_id": "preset-top-20-items-ytd",
            "name": "Top 20 items by spend this year",
            "description": "Top products by net spend year-to-date.",
            "query_json": {
                "metrics": ["net_total"],
                "dimensions": ["product"],
                "filters": {"date_preset": "ytd"},
                "sort_by": "net_total",
                "sort_dir": "desc",
                "limit": 20,
            },
        },
        {
            "query_id": "preset-discount-attribution-ytd",
            "name": "Discount attribution this year",
            "description": "Total discounts year-to-date by source.",
            "query_json": {
                "metrics": ["discount_total"],
                "dimensions": ["source_kind"],
                "filters": {"date_preset": "ytd"},
                "sort_by": "discount_total",
                "sort_dir": "desc",
            },
        },
        {
            "query_id": "preset-monthly-basket-count-by-source",
            "name": "Monthly basket count by source",
            "description": "Receipt count trend by source.",
            "query_json": {
                "metrics": ["purchase_count"],
                "dimensions": ["month", "source_kind"],
                "filters": {},
                "sort_by": "month",
                "sort_dir": "asc",
            },
        },
    ]


def ensure_saved_query_presets(session: Session) -> None:
    existing_ids = {
        str(query_id)
        for query_id in session.execute(select(SavedQuery.query_id).where(SavedQuery.is_preset.is_(True))).scalars().all()
    }
    inserted = 0
    for preset in _preset_saved_queries():
        if preset["query_id"] in existing_ids:
            continue
        session.add(
            SavedQuery(
                query_id=str(preset["query_id"]),
                name=str(preset["name"]),
                description=str(preset["description"]),
                query_json=dict(preset["query_json"]),
                is_preset=True,
            )
        )
        inserted += 1
    if inserted > 0:
        session.flush()


def list_sources(
    session: Session, *, visibility: VisibilityContext | None = None
) -> dict[str, Any]:
    stmt = select(Source).options(selectinload(Source.user)).order_by(Source.display_name.asc())
    if visibility is not None:
        stmt = stmt.where(personal_source_filter(visibility))
    rows = session.execute(stmt).scalars().all()
    return {
        "sources": [
            {
                "id": source.id,
                "user_id": source.user_id,
                "owner_username": source.user.username if source.user is not None else None,
                "owner_display_name": source.user.display_name if source.user is not None else None,
                "kind": source.kind,
                "display_name": source.display_name,
                "status": source.status,
                "enabled": source.enabled,
                "family_share_mode": source.family_share_mode,
            }
            for source in rows
        ]
    }


def run_workbench_query(
    session: Session,
    query_payload: dict[str, Any],
    *,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    return run_query(session, query_payload, visibility=visibility)


def list_saved_queries(session: Session) -> dict[str, Any]:
    ensure_saved_query_presets(session)
    rows = session.execute(
        select(SavedQuery).order_by(SavedQuery.is_preset.desc(), SavedQuery.name.asc())
    ).scalars().all()
    return {
        "items": [
            {
                "query_id": row.query_id,
                "name": row.name,
                "description": row.description,
                "query_json": row.query_json,
                "is_preset": row.is_preset,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "count": len(rows),
    }


def create_saved_query(
    session: Session,
    *,
    name: str,
    description: str | None,
    query_json: dict[str, Any],
) -> dict[str, Any]:
    row = SavedQuery(
        name=name.strip(),
        description=description.strip() if isinstance(description, str) else None,
        query_json=query_json,
        is_preset=False,
    )
    session.add(row)
    session.flush()
    return {
        "query_id": row.query_id,
        "name": row.name,
        "description": row.description,
        "query_json": row.query_json,
        "is_preset": row.is_preset,
        "created_at": row.created_at.isoformat(),
    }


def get_saved_query(session: Session, *, query_id: str) -> dict[str, Any] | None:
    row = session.get(SavedQuery, query_id)
    if row is None:
        return None
    return {
        "query_id": row.query_id,
        "name": row.name,
        "description": row.description,
        "query_json": row.query_json,
        "is_preset": row.is_preset,
        "created_at": row.created_at.isoformat(),
    }


def delete_saved_query(session: Session, *, query_id: str) -> bool:
    row = session.get(SavedQuery, query_id)
    if row is None:
        return False
    if row.is_preset:
        raise ValueError("preset queries cannot be deleted")
    session.delete(row)
    return True


def search_products(
    session: Session,
    *,
    search: str | None = None,
    source_kind: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Product).options(selectinload(Product.aliases))
    normalized_search = (search or "").strip()

    def _like_filter(search_term: str) -> Any:
        like_query = f"%{search_term.lower()}%"
        alias_subquery = select(ProductAlias.product_id).where(
            func.lower(ProductAlias.raw_name).like(like_query)
        )
        if source_kind:
            alias_subquery = alias_subquery.where(
                (ProductAlias.source_kind == source_kind) | ProductAlias.source_kind.is_(None)
            )
        return func.lower(Product.canonical_name).like(like_query) | Product.product_id.in_(
            alias_subquery
        )

    if normalized_search:
        if len(normalized_search) == 1:
            stmt = stmt.where(_like_filter(normalized_search))
        else:
            tokens = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", normalized_search.lower())
            fts_query = " ".join(f"{token}*" for token in tokens)
            if not fts_query:
                stmt = stmt.where(_like_filter(normalized_search))
            else:
                product_ids: set[str] = set()
                try:
                    direct_rows = session.execute(
                        text(
                            "SELECT DISTINCT product_id "
                            "FROM products_fts "
                            "WHERE products_fts MATCH :search"
                        ),
                        {"search": fts_query},
                    ).all()
                    for (product_id,) in direct_rows:
                        if product_id:
                            product_ids.add(str(product_id))

                    alias_sql = (
                        "SELECT DISTINCT pa.product_id "
                        "FROM product_aliases_fts "
                        "JOIN product_aliases pa ON pa.rowid = product_aliases_fts.rowid "
                        "WHERE product_aliases_fts MATCH :search"
                    )
                    params: dict[str, Any] = {"search": fts_query}
                    if source_kind:
                        alias_sql += " AND (pa.source_kind = :source_kind OR pa.source_kind IS NULL)"
                        params["source_kind"] = source_kind
                    alias_rows = session.execute(text(alias_sql), params).all()
                    for (product_id,) in alias_rows:
                        if product_id:
                            product_ids.add(str(product_id))
                except Exception:
                    stmt = stmt.where(_like_filter(normalized_search))
                else:
                    if not product_ids:
                        return {"items": [], "count": 0}
                    stmt = stmt.where(Product.product_id.in_(sorted(product_ids)))

    rows = session.execute(stmt.order_by(Product.canonical_name.asc()).limit(min(max(limit, 1), 200))).scalars().all()
    return {
        "items": [
            {
                "product_id": row.product_id,
                "canonical_name": row.canonical_name,
                "brand": row.brand,
                "default_unit": row.default_unit,
                "category_id": row.category_id,
                "gtin_ean": row.gtin_ean,
                "alias_count": len(row.aliases),
            }
            for row in rows
        ],
        "count": len(rows),
    }


def create_product(
    session: Session,
    *,
    canonical_name: str,
    brand: str | None = None,
    default_unit: str | None = None,
    gtin_ean: str | None = None,
    is_ai_generated: bool = False,
    cluster_confidence: float | None = None,
) -> dict[str, Any]:
    normalized_name = canonical_name.strip()
    if not normalized_name:
        raise ValueError("canonical_name is required")

    product = Product(
        canonical_name=normalized_name,
        brand=brand.strip() if isinstance(brand, str) and brand.strip() else None,
        default_unit=(
            default_unit.strip()
            if isinstance(default_unit, str) and default_unit.strip()
            else None
        ),
        gtin_ean=gtin_ean.strip() if isinstance(gtin_ean, str) and gtin_ean.strip() else None,
        is_ai_generated=is_ai_generated,
        cluster_confidence=cluster_confidence,
    )
    session.add(product)
    session.flush()
    return {
        "product_id": product.product_id,
        "canonical_name": product.canonical_name,
        "brand": product.brand,
        "default_unit": product.default_unit,
        "category_id": product.category_id,
        "gtin_ean": product.gtin_ean,
        "is_ai_generated": product.is_ai_generated,
        "cluster_confidence": product.cluster_confidence,
        "created_at": product.created_at.isoformat(),
    }


def seed_products_from_items(session: Session) -> dict[str, Any]:
    distinct_names = sorted(
        {
            str(name).strip()
            for name in session.execute(select(TransactionItem.name).distinct()).scalars().all()
            if isinstance(name, str) and name.strip()
        }
    )
    existing_alias_names = {
        str(raw_name).strip().lower()
        for raw_name in session.execute(select(ProductAlias.raw_name).distinct()).scalars().all()
        if isinstance(raw_name, str) and raw_name.strip()
    }

    created = 0
    skipped = 0

    for raw_name in distinct_names:
        normalized = raw_name.lower()
        if normalized in existing_alias_names:
            skipped += 1
            continue

        product = Product(canonical_name=raw_name, is_ai_generated=False)
        session.add(product)
        session.flush()

        session.add(
            ProductAlias(
                product_id=product.product_id,
                source_kind=None,
                raw_name=raw_name,
                raw_sku=None,
                match_confidence=Decimal("1.000"),
                match_method="exact",
            )
        )

        session.execute(
            update(TransactionItem)
            .where(func.lower(TransactionItem.name) == normalized)
            .values(product_id=product.product_id)
        )
        session.execute(
            update(ItemObservation)
            .where(func.lower(ItemObservation.raw_item_name) == normalized)
            .values(product_id=product.product_id)
        )

        existing_alias_names.add(normalized)
        created += 1

    total_products = session.execute(select(func.count()).select_from(Product)).scalar_one()
    return {
        "created": created,
        "skipped": skipped,
        "total_products": int(total_products),
    }


def merge_products(
    session: Session,
    *,
    target_product_id: str,
    source_product_ids: list[str],
) -> dict[str, Any]:
    target = session.get(Product, target_product_id)
    if target is None:
        raise ValueError("unknown target product_id")

    source_ids = sorted({product_id for product_id in source_product_ids if product_id and product_id != target_product_id})
    if not source_ids:
        raise ValueError("source_product_ids must contain at least one id different from target")

    source_products = session.execute(
        select(Product).where(Product.product_id.in_(source_ids))
    ).scalars().all()
    found_ids = {row.product_id for row in source_products}
    missing_ids = [product_id for product_id in source_ids if product_id not in found_ids]
    if missing_ids:
        raise ValueError(f"unknown source product_id(s): {', '.join(missing_ids)}")

    moved_aliases = int(
        session.execute(
            select(func.count())
            .select_from(ProductAlias)
            .where(ProductAlias.product_id.in_(source_ids))
        ).scalar_one()
    )
    moved_items = int(
        session.execute(
            select(func.count())
            .select_from(TransactionItem)
            .where(TransactionItem.product_id.in_(source_ids))
        ).scalar_one()
    )

    session.execute(
        update(ProductAlias)
        .where(ProductAlias.product_id.in_(source_ids))
        .values(product_id=target_product_id)
    )
    session.execute(
        update(TransactionItem)
        .where(TransactionItem.product_id.in_(source_ids))
        .values(product_id=target_product_id)
    )
    session.execute(
        update(ItemObservation)
        .where(ItemObservation.product_id.in_(source_ids))
        .values(product_id=target_product_id)
    )

    for source_product in source_products:
        session.delete(source_product)

    return {
        "target_product_id": target_product_id,
        "merged_products": len(source_ids),
        "moved_aliases": moved_aliases,
        "moved_items": moved_items,
    }


def get_product_detail(session: Session, *, product_id: str) -> dict[str, Any] | None:
    product = session.execute(
        select(Product).where(Product.product_id == product_id).options(selectinload(Product.aliases))
    ).scalar_one_or_none()
    if product is None:
        return None
    aliases = sorted(
        product.aliases,
        key=lambda item: (item.source_kind or "", item.raw_name.lower()),
    )
    return {
        "product": {
            "product_id": product.product_id,
            "canonical_name": product.canonical_name,
            "brand": product.brand,
            "default_unit": product.default_unit,
            "category_id": product.category_id,
            "gtin_ean": product.gtin_ean,
            "created_at": product.created_at.isoformat(),
        },
        "aliases": [
            {
                "alias_id": alias.alias_id,
                "source_kind": alias.source_kind,
                "raw_name": alias.raw_name,
                "raw_sku": alias.raw_sku,
                "match_confidence": _to_float(alias.match_confidence),
                "match_method": alias.match_method,
                "created_at": alias.created_at.isoformat(),
            }
            for alias in aliases
        ],
    }


def _grain_expr(grain: str) -> Any:
    if grain == "month":
        return func.substr(ItemObservation.date, 1, 7)
    if grain == "year":
        return func.substr(ItemObservation.date, 1, 4)
    return ItemObservation.date


def product_price_series(
    session: Session,
    *,
    product_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    grain: str = "day",
    net: bool = True,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    if grain not in {"day", "month", "year"}:
        raise ValueError("grain must be one of: day, month, year")
    period = _grain_expr(grain).label("period")
    price_expr = (
        func.avg(ItemObservation.unit_price_net_cents)
        if net
        else func.avg(ItemObservation.unit_price_gross_cents)
    )
    stmt = (
        select(
            period,
            ItemObservation.source_kind,
            func.coalesce(price_expr, 0),
            func.count(),
            func.min(
                ItemObservation.unit_price_net_cents
                if net
                else ItemObservation.unit_price_gross_cents
            ),
            func.max(
                ItemObservation.unit_price_net_cents
                if net
                else ItemObservation.unit_price_gross_cents
            ),
        )
        .where(ItemObservation.product_id == product_id)
        .group_by(period, ItemObservation.source_kind)
        .order_by(period.asc(), ItemObservation.source_kind.asc())
    )
    if visibility is not None:
        stmt = stmt.where(observation_visibility_filter(visibility))
    if date_from is not None:
        stmt = stmt.where(ItemObservation.date >= date_from.isoformat())
    if date_to is not None:
        stmt = stmt.where(ItemObservation.date <= date_to.isoformat())
    rows = session.execute(stmt).all()
    return {
        "product_id": product_id,
        "net": net,
        "grain": grain,
        "points": [
            {
                "period": str(period_key),
                "source_kind": source_kind,
                "unit_price_cents": int(avg_price or 0),
                "purchase_count": int(count or 0),
                "min_unit_price_cents": int(min_price or 0),
                "max_unit_price_cents": int(max_price or 0),
            }
            for period_key, source_kind, avg_price, count, min_price, max_price in rows
        ],
    }


def product_purchases(
    session: Session,
    *,
    product_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = (
        select(ItemObservation)
        .where(ItemObservation.product_id == product_id)
        .order_by(ItemObservation.date.desc(), ItemObservation.transaction_id.desc())
    )
    if visibility is not None:
        stmt = stmt.where(observation_visibility_filter(visibility))
    if date_from is not None:
        stmt = stmt.where(ItemObservation.date >= date_from.isoformat())
    if date_to is not None:
        stmt = stmt.where(ItemObservation.date <= date_to.isoformat())
    rows = session.execute(stmt.limit(1000)).scalars().all()
    return {
        "product_id": product_id,
        "count": len(rows),
        "items": [
            {
                "transaction_id": row.transaction_id,
                "date": row.date,
                "source_id": row.source_id,
                "source_kind": row.source_kind,
                "merchant_name": row.merchant_name,
                "raw_item_name": row.raw_item_name,
                "quantity_value": _to_float(row.quantity_value),
                "quantity_unit": row.quantity_unit,
                "unit_price_gross_cents": row.unit_price_gross_cents,
                "unit_price_net_cents": row.unit_price_net_cents,
                "line_total_gross_cents": row.line_total_gross_cents,
                "line_total_net_cents": row.line_total_net_cents,
            }
            for row in rows
        ],
    }


def manual_product_match(
    session: Session,
    *,
    product_id: str,
    raw_name: str,
    source_kind: str | None = None,
    raw_sku: str | None = None,
) -> dict[str, Any]:
    product = session.get(Product, product_id)
    if product is None:
        raise ValueError("unknown product_id")
    alias = create_manual_product_alias(
        session,
        product_id=product_id,
        raw_name=raw_name,
        source_kind=source_kind,
        raw_sku=raw_sku,
    )

    stmt = (
        select(TransactionItem.id, TransactionItem.transaction_id)
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .join(Source, Source.id == Transaction.source_id)
        .where(func.lower(TransactionItem.name) == raw_name.lower())
    )
    if source_kind:
        stmt = stmt.where(Source.kind == source_kind)
    matched_rows = session.execute(stmt).all()
    matched_item_ids = [item_id for item_id, _ in matched_rows]
    matched_transaction_ids = sorted({transaction_id for _, transaction_id in matched_rows})
    if matched_item_ids:
        session.execute(
            update(TransactionItem)
            .where(TransactionItem.id.in_(matched_item_ids))
            .values(product_id=product_id)
        )
        obs_update = (
            update(ItemObservation)
            .where(func.lower(ItemObservation.raw_item_name) == raw_name.lower())
            .values(product_id=product_id)
        )
        if source_kind:
            obs_update = obs_update.where(ItemObservation.source_kind == source_kind)
        session.execute(obs_update)

    return {
        "product_id": product_id,
        "raw_name": raw_name,
        "source_kind": source_kind,
        "alias_id": alias.alias_id,
        "matched_item_count": len(matched_item_ids),
        "matched_transaction_count": len(matched_transaction_ids),
    }


def list_comparison_groups(session: Session) -> dict[str, Any]:
    rows = session.execute(select(ComparisonGroup).order_by(ComparisonGroup.name.asc())).scalars().all()
    items: list[dict[str, Any]] = []
    for group in rows:
        count = session.execute(
            select(func.count()).select_from(ComparisonGroupMember).where(
                ComparisonGroupMember.group_id == group.group_id
            )
        ).scalar_one()
        items.append(
            {
                "group_id": group.group_id,
                "name": group.name,
                "unit_standard": group.unit_standard,
                "notes": group.notes,
                "member_count": int(count),
                "created_at": group.created_at.isoformat(),
            }
        )
    return {"items": items, "count": len(items)}


def create_comparison_group(
    session: Session,
    *,
    name: str,
    unit_standard: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    row = ComparisonGroup(
        name=name.strip(),
        unit_standard=unit_standard.strip() if isinstance(unit_standard, str) else None,
        notes=notes.strip() if isinstance(notes, str) else None,
    )
    session.add(row)
    session.flush()
    return {
        "group_id": row.group_id,
        "name": row.name,
        "unit_standard": row.unit_standard,
        "notes": row.notes,
        "created_at": row.created_at.isoformat(),
    }


def add_comparison_group_member(
    session: Session,
    *,
    group_id: str,
    product_id: str,
    weight: float = 1.0,
) -> dict[str, Any]:
    group = session.get(ComparisonGroup, group_id)
    if group is None:
        raise ValueError("unknown group_id")
    product = session.get(Product, product_id)
    if product is None:
        raise ValueError("unknown product_id")
    existing = session.get(ComparisonGroupMember, {"group_id": group_id, "product_id": product_id})
    if existing is None:
        existing = ComparisonGroupMember(
            group_id=group_id,
            product_id=product_id,
            weight=Decimal(f"{weight:.3f}"),
        )
        session.add(existing)
    else:
        existing.weight = Decimal(f"{weight:.3f}")
    return {
        "group_id": group_id,
        "product_id": product_id,
        "weight": _to_float(existing.weight),
    }


def comparison_group_series(
    session: Session,
    *,
    group_id: str,
    date_from: date | None = None,
    date_to: date | None = None,
    grain: str = "month",
    net: bool = True,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    group = session.get(ComparisonGroup, group_id)
    if group is None:
        raise ValueError("unknown group_id")
    period = _grain_expr(grain if grain in {"day", "month", "year"} else "month").label("period")
    price_expr = (
        func.avg(ItemObservation.unit_price_net_cents)
        if net
        else func.avg(ItemObservation.unit_price_gross_cents)
    )
    stmt = (
        select(
            period,
            ItemObservation.source_kind,
            ItemObservation.product_id,
            func.coalesce(price_expr, 0),
            func.count(),
        )
        .join(
            ComparisonGroupMember,
            ComparisonGroupMember.product_id == ItemObservation.product_id,
        )
        .where(ComparisonGroupMember.group_id == group_id)
        .group_by(period, ItemObservation.source_kind, ItemObservation.product_id)
        .order_by(period.asc(), ItemObservation.source_kind.asc())
    )
    if visibility is not None:
        stmt = stmt.where(observation_visibility_filter(visibility))
    if date_from is not None:
        stmt = stmt.where(ItemObservation.date >= date_from.isoformat())
    if date_to is not None:
        stmt = stmt.where(ItemObservation.date <= date_to.isoformat())
    rows = session.execute(stmt).all()
    # Build product_id -> canonical_name map for display
    product_ids = {row[2] for row in rows if row[2]}
    product_names: dict[str, str] = {}
    if product_ids:
        products = session.execute(
            select(Product.product_id, Product.canonical_name).where(
                Product.product_id.in_(list(product_ids))
            )
        ).all()
        product_names = {pid: name for pid, name in products}
    return {
        "group": {
            "group_id": group.group_id,
            "name": group.name,
            "unit_standard": group.unit_standard,
        },
        "net": net,
        "grain": grain,
        "points": [
            {
                "period": str(period_key),
                "source_kind": source_kind,
                "product_id": product_id,
                "product_name": product_names.get(product_id) if product_id else None,
                "unit_price_cents": int(avg_price or 0),
                "purchase_count": int(count or 0),
            }
            for period_key, source_kind, product_id, avg_price, count in rows
        ],
    }


def unmatched_items_quality(
    session: Session,
    *,
    limit: int = 200,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = (
        select(
            TransactionItem.name,
            Source.kind,
            func.count(TransactionItem.id),
            func.coalesce(func.sum(TransactionItem.line_total_cents), 0),
            func.max(Transaction.purchased_at),
        )
        .join(Transaction, Transaction.id == TransactionItem.transaction_id)
        .join(Source, Source.id == Transaction.source_id)
        .where(TransactionItem.product_id.is_(None))
        .group_by(TransactionItem.name, Source.kind)
        .order_by(func.coalesce(func.sum(TransactionItem.line_total_cents), 0).desc())
        .limit(min(max(limit, 1), 1000))
    )
    if visibility is not None:
        stmt = stmt.where(Transaction.id.in_(visible_transaction_ids_subquery(visibility)))
    rows = session.execute(stmt).all()
    return {
        "items": [
            {
                "raw_name": str(raw_name),
                "source_kind": str(source_kind),
                "purchase_count": int(count or 0),
                "total_spend_cents": int(total_spend or 0),
                "last_seen_at": (
                    last_seen.astimezone(UTC).isoformat()
                    if isinstance(last_seen, datetime)
                    else None
                ),
            }
            for raw_name, source_kind, count, total_spend, last_seen in rows
        ],
        "count": len(rows),
    }


def low_confidence_ocr_quality(
    session: Session,
    *,
    threshold: float = 0.85,
    limit: int = 200,
    visibility: VisibilityContext | None = None,
) -> dict[str, Any]:
    stmt = (
        select(Document)
        .where(Document.ocr_confidence.is_not(None), Document.ocr_confidence < Decimal(f"{threshold:.3f}"))
        .order_by(Document.created_at.desc())
        .limit(min(max(limit, 1), 1000))
    )
    if visibility is not None:
        stmt = stmt.where(
            Document.transaction_id.in_(visible_transaction_ids_subquery(visibility))
        )
    rows = session.execute(stmt).scalars().all()
    return {
        "items": [
            {
                "document_id": row.id,
                "transaction_id": row.transaction_id,
                "source_id": row.source_id,
                "file_name": row.file_name,
                "review_status": row.review_status,
                "ocr_status": row.ocr_status,
                "ocr_confidence": _to_float(row.ocr_confidence),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        "count": len(rows),
        "threshold": threshold,
    }
