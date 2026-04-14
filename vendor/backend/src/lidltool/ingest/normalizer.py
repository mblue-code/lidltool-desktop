from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from dateutil import parser as date_parser

from lidltool.analytics.categorization import CompiledRule, categorize_name
from lidltool.ingest.dedupe import compute_fingerprint


@dataclass(slots=True)
class NormalizedReceiptItem:
    line_no: int
    name: str
    qty: Decimal
    unit: str | None
    unit_price: int | None
    line_total: int
    vat_rate: Decimal | None
    category: str | None
    discounts: list[dict[str, Any]]


@dataclass(slots=True)
class NormalizedReceipt:
    id: str
    purchased_at: datetime
    store_id: str | None
    store_name: str | None
    store_address: str | None
    total_gross: int
    currency: str
    discount_total: int | None
    fingerprint: str
    items: list[NormalizedReceiptItem]
    raw_json: dict[str, Any]


def _first_present(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        if value > 1_000_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str) and value.strip():
        parsed = date_parser.parse(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(tz=UTC)


def to_cents(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, Decimal):
        return int((value * Decimal("100")).quantize(Decimal("1")))
    if isinstance(value, str):
        normalized = (
            value.replace("€", "")
            .replace("EUR", "")
            .replace("£", "")
            .replace("GBP", "")
            .replace(" ", "")
        )
        normalized = normalized.replace(",", ".")
        if normalized == "":
            return default
        try:
            decimal_value = Decimal(normalized)
            return int((decimal_value * Decimal("100")).quantize(Decimal("1")))
        except InvalidOperation:
            return default
    return default


def to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        normalized = value.replace(",", ".").strip()
        if normalized == "":
            return default
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return default
    return default


def _normalize_store_field(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _fallback_store_id(*, store_id: Any, store_name: Any, store_address: Any) -> str | None:
    explicit = _normalize_store_field(store_id)
    if explicit is not None:
        return explicit
    parts = [part for part in (_normalize_store_field(store_name), _normalize_store_field(store_address)) if part]
    if not parts:
        return None
    digest = hashlib.sha1("::".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"store:{digest}"


def normalize_receipt(
    receipt_detail: dict[str, Any],
    summary: dict[str, Any] | None = None,
    category_rules: list[CompiledRule] | None = None,
) -> NormalizedReceipt:
    payload = dict(receipt_detail)
    if summary:
        for key, value in summary.items():
            payload.setdefault(key, value)

    rid = str(_first_present(payload, ["id", "receiptId", "ticketId", "uuid"]) or "")
    purchased_at = parse_datetime(
        _first_present(payload, ["purchasedAt", "createdAt", "date", "timestamp"])
    )

    store_payload = _first_present(payload, ["store", "shop", "market"]) or {}
    if not isinstance(store_payload, dict):
        store_payload = {}
    store_id = _first_present(payload, ["storeId"]) or _first_present(
        store_payload, ["id", "storeId"]
    )
    store_name = _first_present(payload, ["storeName"]) or _first_present(
        store_payload, ["name", "title"]
    )
    store_address = _first_present(payload, ["storeAddress"]) or _first_present(
        store_payload, ["address", "street"]
    )

    total_gross = to_cents(
        _first_present(payload, ["totalGross", "total", "amountTotal", "totalAmount"])
    )
    discount_total_value = _first_present(payload, ["discountTotal", "discount", "savingsTotal"])
    discount_total = to_cents(discount_total_value) if discount_total_value is not None else None
    currency = str(_first_present(payload, ["currency"]) or "EUR")

    raw_items = _first_present(payload, ["items", "lineItems", "positions", "products"]) or []
    if not isinstance(raw_items, list):
        raw_items = []

    normalized_items: list[NormalizedReceiptItem] = []
    for idx, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            continue
        name = str(
            _first_present(raw_item, ["name", "description", "title", "text"]) or f"item_{idx}"
        )
        qty = to_decimal(
            _first_present(raw_item, ["qty", "quantity", "amount"]) or Decimal("1"), Decimal("1")
        )
        unit = _first_present(raw_item, ["unit", "unitName"])
        unit_price_raw = _first_present(raw_item, ["unitPrice", "pricePerUnit", "price"])
        unit_price = to_cents(unit_price_raw) if unit_price_raw is not None else None
        line_total_raw = _first_present(raw_item, ["lineTotal", "total", "sum", "amount"])
        line_total = to_cents(line_total_raw)
        if line_total == 0 and unit_price is not None:
            line_total = int((Decimal(unit_price) * qty).quantize(Decimal("1")))
        vat_rate_raw = _first_present(raw_item, ["vatRate", "taxRate"])
        vat_rate = to_decimal(vat_rate_raw) if vat_rate_raw is not None else None

        raw_discounts = raw_item.get("discounts")
        discounts: list[dict[str, Any]] = raw_discounts if isinstance(raw_discounts, list) else []

        source_category = _first_present(
            raw_item,
            ["category", "department", "group", "itemCategory", "section"],
        )
        category = (
            str(source_category)
            if source_category is not None and str(source_category).strip()
            else categorize_name(name, category_rules or [])
        )
        normalized_items.append(
            NormalizedReceiptItem(
                line_no=idx,
                name=name,
                qty=qty,
                unit=str(unit) if unit is not None else None,
                unit_price=unit_price,
                line_total=line_total,
                vat_rate=vat_rate,
                category=category,
                discounts=discounts,
            )
        )

    if not rid:
        rid = f"fp-{compute_fingerprint(purchased_at=purchased_at.isoformat(), total_cents=total_gross, item_names=[i.name for i in normalized_items])[:20]}"

    fingerprint = compute_fingerprint(
        purchased_at=purchased_at.isoformat(),
        total_cents=total_gross,
        item_names=[item.name for item in normalized_items],
    )

    normalized_store_name = _normalize_store_field(store_name)
    normalized_store_address = _normalize_store_field(store_address)
    normalized_store_id = _fallback_store_id(
        store_id=store_id,
        store_name=normalized_store_name,
        store_address=normalized_store_address,
    )

    return NormalizedReceipt(
        id=rid,
        purchased_at=purchased_at,
        store_id=normalized_store_id,
        store_name=normalized_store_name,
        store_address=normalized_store_address,
        total_gross=total_gross,
        currency=currency,
        discount_total=discount_total,
        fingerprint=fingerprint,
        items=normalized_items,
        raw_json=receipt_detail,
    )
