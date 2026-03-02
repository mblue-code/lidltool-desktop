from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from lidltool.db.models import (
    AnalyticsMetadata,
    Category,
    ItemObservation,
    Transaction,
)


def _to_decimal_qty(value: Decimal | None) -> Decimal:
    if value is None or value <= 0:
        return Decimal("1.000")
    return value


def _to_int_unit_price(line_total_cents: int, qty: Decimal, fallback: int | None) -> int:
    if fallback is not None:
        return int(fallback)
    if qty <= 0:
        return int(line_total_cents)
    return int(Decimal(line_total_cents) / qty)


def rebuild_item_observations(session: Session) -> int:
    session.flush()
    session.execute(delete(ItemObservation))

    category_map = {
        (row.name or "").strip().lower(): row.category_id
        for row in session.execute(select(Category)).scalars().all()
    }

    transactions = (
        session.execute(
            select(Transaction)
            .options(
                selectinload(Transaction.source),
                selectinload(Transaction.items),
                selectinload(Transaction.discount_events),
            )
            .order_by(Transaction.purchased_at.asc())
        )
        .scalars()
        .all()
    )

    inserted = 0
    for transaction in transactions:
        source_kind = transaction.source.kind if transaction.source is not None else transaction.source_id
        tx_date = transaction.purchased_at.astimezone(UTC).date().isoformat()

        item_discounts: dict[str, int] = {}
        basket_discount_total = 0
        for event in transaction.discount_events:
            if event.scope == "item" and event.transaction_item_id is not None:
                item_discounts[event.transaction_item_id] = (
                    item_discounts.get(event.transaction_item_id, 0) + int(event.amount_cents or 0)
                )
            elif event.scope == "basket":
                basket_discount_total += int(event.amount_cents or 0)

        total_line_gross = sum(int(item.line_total_cents or 0) for item in transaction.items)
        remaining_basket_discount = basket_discount_total

        for index, item in enumerate(transaction.items):
            qty = _to_decimal_qty(item.qty)
            quantity_value = qty
            quantity_unit = item.unit or "pcs"
            line_total_gross = int(item.line_total_cents or 0)
            item_discount = int(item_discounts.get(item.id, 0))
            line_total_net = line_total_gross - item_discount
            unit_price_gross = _to_int_unit_price(line_total_gross, qty, item.unit_price_cents)
            unit_price_net = int(Decimal(line_total_net) / qty) if qty > 0 else line_total_net

            if total_line_gross > 0:
                if index == len(transaction.items) - 1:
                    basket_alloc = remaining_basket_discount
                else:
                    basket_alloc = int(round((line_total_gross / total_line_gross) * basket_discount_total))
                    remaining_basket_discount -= basket_alloc
            else:
                basket_alloc = 0

            normalized_category = (item.category or "").strip().lower()
            category_id = category_map.get(normalized_category)

            session.add(
                ItemObservation(
                    observation_id=str(uuid4()),
                    transaction_id=transaction.id,
                    date=tx_date,
                    source_id=transaction.source_id,
                    source_kind=source_kind,
                    product_id=item.product_id,
                    raw_item_name=item.name,
                    quantity_value=quantity_value,
                    quantity_unit=quantity_unit,
                    unit_price_gross_cents=unit_price_gross,
                    unit_price_net_cents=unit_price_net,
                    line_total_gross_cents=line_total_gross,
                    line_total_net_cents=line_total_net,
                    basket_discount_alloc_cents=basket_alloc,
                    category=item.category,
                    category_id=category_id,
                    merchant_name=transaction.merchant_name,
                )
            )
            inserted += 1

    metadata = session.get(AnalyticsMetadata, "item_observations_last_rebuilt_at")
    payload = {"rebuilt_at": datetime.now(tz=UTC).isoformat(), "rows": inserted}
    if metadata is None:
        metadata = AnalyticsMetadata(key="item_observations_last_rebuilt_at", value_json=payload)
        session.add(metadata)
    else:
        metadata.value_json = payload

    return inserted


def refresh_observations_for_transaction(
    session: Session,
    *,
    transaction_id: str,
) -> int:
    session.flush()
    session.execute(
        delete(ItemObservation).where(ItemObservation.transaction_id == transaction_id)
    )
    transaction = session.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id)
        .options(
            selectinload(Transaction.source),
            selectinload(Transaction.items),
            selectinload(Transaction.discount_events),
        )
    ).scalar_one_or_none()
    if transaction is None:
        return 0

    category_map = {
        (row.name or "").strip().lower(): row.category_id
        for row in session.execute(select(Category)).scalars().all()
    }
    source_kind = transaction.source.kind if transaction.source is not None else transaction.source_id
    tx_date = transaction.purchased_at.astimezone(UTC).date().isoformat()
    item_discounts: dict[str, int] = {}
    basket_discount_total = 0
    for event in transaction.discount_events:
        if event.scope == "item" and event.transaction_item_id is not None:
            item_discounts[event.transaction_item_id] = (
                item_discounts.get(event.transaction_item_id, 0) + int(event.amount_cents or 0)
            )
        elif event.scope == "basket":
            basket_discount_total += int(event.amount_cents or 0)

    total_line_gross = sum(int(item.line_total_cents or 0) for item in transaction.items)
    remaining_basket_discount = basket_discount_total
    inserted = 0
    for index, item in enumerate(transaction.items):
        qty = _to_decimal_qty(item.qty)
        line_total_gross = int(item.line_total_cents or 0)
        line_total_net = line_total_gross - int(item_discounts.get(item.id, 0))
        if total_line_gross > 0:
            if index == len(transaction.items) - 1:
                basket_alloc = remaining_basket_discount
            else:
                basket_alloc = int(round((line_total_gross / total_line_gross) * basket_discount_total))
                remaining_basket_discount -= basket_alloc
        else:
            basket_alloc = 0
        session.add(
            ItemObservation(
                observation_id=str(uuid4()),
                transaction_id=transaction.id,
                date=tx_date,
                source_id=transaction.source_id,
                source_kind=source_kind,
                product_id=item.product_id,
                raw_item_name=item.name,
                quantity_value=qty,
                quantity_unit=item.unit or "pcs",
                unit_price_gross_cents=_to_int_unit_price(line_total_gross, qty, item.unit_price_cents),
                unit_price_net_cents=int(Decimal(line_total_net) / qty) if qty > 0 else line_total_net,
                line_total_gross_cents=line_total_gross,
                line_total_net_cents=line_total_net,
                basket_discount_alloc_cents=basket_alloc,
                category=item.category,
                category_id=category_map.get((item.category or "").strip().lower()),
                merchant_name=transaction.merchant_name,
            )
        )
        inserted += 1
    return inserted
