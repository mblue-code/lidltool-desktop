from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from lidltool.analytics.categorization import load_compiled_rules
from lidltool.db.engine import session_scope
from lidltool.db.models import Receipt, ReceiptItem, Store
from lidltool.ingest.dedupe import fingerprint_exists, receipt_exists
from lidltool.ingest.normalizer import normalize_receipt, to_cents
from lidltool.amazon.client_playwright import _parse_amazon_de_date


@dataclass(slots=True)
class AmazonImportResult:
    ok: bool
    records_seen: int
    new_receipts: int
    new_items: int
    skipped_existing: int
    warnings: list[str] = field(default_factory=list)


class AmazonImportError(RuntimeError):
    pass


class AmazonImportService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        source: str = "amazon_de",
        store_name: str = "Amazon",
    ) -> None:
        self._session_factory = session_factory
        self._source = source
        self._store_name = store_name

    def import_file(self, input_file: Path) -> AmazonImportResult:
        if not input_file.exists():
            raise AmazonImportError(f"input file does not exist: {input_file}")

        payload = _load_json(input_file)
        orders = _extract_orders(payload)
        return self.import_orders(orders)

    def import_orders(self, orders: list[Any]) -> AmazonImportResult:
        progress = AmazonImportResult(
            ok=True, records_seen=0, new_receipts=0, new_items=0, skipped_existing=0
        )

        with session_scope(self._session_factory) as session:
            rules = load_compiled_rules(session)
            for idx, order in enumerate(orders, start=1):
                progress.records_seen += 1
                if not isinstance(order, dict):
                    progress.warnings.append(f"Skipping non-object order record at index={idx}")
                    continue

                mapped = _map_order_to_receipt_payload(
                    order=order,
                    source=self._source,
                    default_store_name=self._store_name,
                )
                normalized = normalize_receipt(mapped, category_rules=rules)

                if receipt_exists(session, normalized.id):
                    progress.skipped_existing += 1
                    continue

                if fingerprint_exists(session, normalized.fingerprint):
                    progress.skipped_existing += 1
                    continue

                _upsert_store(
                    session, normalized.store_id, normalized.store_name, normalized.store_address
                )
                session.add(
                    Receipt(
                        id=normalized.id,
                        purchased_at=normalized.purchased_at,
                        store_id=normalized.store_id,
                        store_name=normalized.store_name,
                        store_address=normalized.store_address,
                        total_gross=normalized.total_gross,
                        currency=normalized.currency,
                        discount_total=normalized.discount_total,
                        fingerprint=normalized.fingerprint,
                        raw_json=normalized.raw_json,
                    )
                )
                session.flush()

                for item in normalized.items:
                    session.add(
                        ReceiptItem(
                            receipt_id=normalized.id,
                            line_no=item.line_no,
                            name=item.name,
                            qty=item.qty,
                            unit=item.unit,
                            unit_price=item.unit_price,
                            line_total=item.line_total,
                            vat_rate=item.vat_rate,
                            category=item.category,
                            discounts=item.discounts,
                        )
                    )

                progress.new_receipts += 1
                progress.new_items += len(normalized.items)

        return progress


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AmazonImportError(f"invalid JSON in {path}: {exc}") from exc


def _extract_orders(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        orders = payload.get("orders")
        if isinstance(orders, list):
            return orders
    raise AmazonImportError("expected JSON array of orders or object with an 'orders' array")


def _to_negative_discount_cents(value: Any) -> int:
    cents = int(to_cents(value, default=0))
    if cents == 0:
        return 0
    return cents if cents < 0 else -cents


def _to_positive_discount_total_cents(
    order_total_savings: Any, item_discounts: int, basket_discounts: int
) -> int | None:
    inferred = abs(item_discounts) + abs(basket_discounts)
    return inferred if inferred > 0 else None


def _parse_order_purchased_at(order: dict[str, Any]) -> Any:
    raw_date = order.get("orderDate")
    source_year = order.get("sourceYear")
    if isinstance(raw_date, str):
        parsed = _parse_amazon_de_date(raw_date)
        if parsed is None and isinstance(source_year, (int, str)):
            source_year_text = str(source_year).strip()
            if source_year_text.isdigit() and not re.search(r"\b\d{4}\b", raw_date):
                parsed = _parse_amazon_de_date(f"{raw_date.strip()} {source_year_text}")
        if parsed is not None:
            return parsed.isoformat()
    return raw_date


def _map_order_to_receipt_payload(
    *,
    order: dict[str, Any],
    source: str,
    default_store_name: str,
) -> dict[str, Any]:
    order_id = str(order.get("orderId") or "").strip()
    details_url = str(order.get("detailsUrl") or "").strip()
    currency = str(order.get("currency") or "EUR")
    store_address = _extract_host(details_url)
    store_id = f"{source}:{store_address}" if store_address else source

    items_in = order.get("items")
    source_items = items_in if isinstance(items_in, list) else []
    mapped_items: list[dict[str, Any]] = []
    item_discounts_total = 0
    line_total_sum = 0

    for idx, raw_item in enumerate(source_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        qty = _to_quantity(raw_item.get("quantity"))
        unit_price = to_cents(raw_item.get("price"), default=0)
        item_discount = _to_negative_discount_cents(raw_item.get("discount"))
        item_discounts_total += item_discount

        line_total = int(round(qty * unit_price)) + item_discount
        line_total = max(0, line_total)
        line_total_sum += line_total

        discounts: list[dict[str, Any]] = []
        if item_discount != 0:
            discounts.append(
                {
                    "type": "item_discount",
                    "promotion_id": str(raw_item.get("asin") or "amazon_item_discount"),
                    "amount_cents": item_discount,
                    "label": "Amazon item discount",
                    "scope": "item",
                }
            )

        mapped_items.append(
            {
                "name": str(raw_item.get("title") or f"Amazon item {idx}"),
                "qty": qty,
                "unit": "pcs",
                "unitPrice": unit_price / 100.0 if unit_price else 0,
                "lineTotal": line_total / 100.0,
                "discounts": discounts,
            }
        )

    promotions_in = order.get("promotions")
    source_promotions = promotions_in if isinstance(promotions_in, list) else []
    basket_discounts_total = 0
    basket_discounts: list[dict[str, Any]] = []
    for promo in source_promotions:
        if not isinstance(promo, dict):
            continue
        amount = _to_negative_discount_cents(promo.get("amount"))
        if amount == 0:
            continue
        basket_discounts_total += amount
        basket_discounts.append(
            {
                "type": "promotion",
                "promotion_id": "amazon_promotion",
                "amount_cents": amount,
                "label": str(promo.get("description") or "Amazon promotion"),
                "scope": "basket",
            }
        )

    if basket_discounts:
        if not mapped_items:
            mapped_items.append(
                {
                    "name": "Amazon order",
                    "qty": 1,
                    "unit": "order",
                    "unitPrice": 0,
                    "lineTotal": 0,
                    "discounts": basket_discounts,
                }
            )
        else:
            mapped_items[0].setdefault("discounts", [])
            first_discounts = mapped_items[0]["discounts"]
            if isinstance(first_discounts, list):
                first_discounts.extend(basket_discounts)

    total_amount_cents = to_cents(order.get("totalAmount"), default=0)
    if total_amount_cents <= 0:
        total_amount_cents = line_total_sum

    discount_total = _to_positive_discount_total_cents(
        order_total_savings=order.get("totalSavings"),
        item_discounts=item_discounts_total,
        basket_discounts=basket_discounts_total,
    )

    rid = f"amazon-{order_id}" if order_id else ""
    return {
        "id": rid,
        "purchasedAt": _parse_order_purchased_at(order),
        "storeId": store_id,
        "storeName": default_store_name,
        "storeAddress": store_address,
        "totalGross": total_amount_cents / 100.0,
        "currency": currency,
        "discountTotal": discount_total / 100.0 if discount_total is not None else None,
        "items": mapped_items,
        "source": source,
        "rawOrderId": order_id or None,
        "detailsUrl": details_url or None,
        "orderStatus": order.get("orderStatus"),
        "originalOrder": order,
    }


def _extract_host(url: str) -> str | None:
    if "://" not in url:
        return None
    after_scheme = url.split("://", 1)[1]
    host = after_scheme.split("/", 1)[0].strip()
    return host or None


def _to_quantity(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value) if float(value) > 0 else 1.0
    if isinstance(value, str):
        try:
            parsed = float(value.strip().replace(",", "."))
            return parsed if parsed > 0 else 1.0
        except ValueError:
            return 1.0
    return 1.0


def _upsert_store(
    session: Session, store_id: str | None, name: str | None, address: str | None
) -> None:
    if not store_id:
        return
    existing = session.get(Store, store_id)
    if existing is None:
        session.add(Store(id=store_id, name=name, address=address))
        return
    if name and existing.name != name:
        existing.name = name
    if address and existing.address != address:
        existing.address = address
