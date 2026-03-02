from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from lidltool.connectors.base import BaseConnectorAdapter
from lidltool.ingest.dedupe import compute_fingerprint
from lidltool.ingest.normalizer import normalize_receipt
from lidltool.rossmann.client_playwright import (
    RossmannClientError,
    RossmannPlaywrightClient,
    parse_rossmann_date,
)


@dataclass(slots=True)
class _OrderCache:
    by_order_id: dict[str, dict[str, Any]]
    fetched_at: datetime


def _to_int_cents(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        raw = value.replace("€", "").replace("EUR", "").replace(" ", "").replace(",", ".")
        if not raw:
            return 0
        try:
            return int(round(float(raw) * 100))
        except ValueError:
            return 0
    return 0


def _to_discount_cents(value: Any) -> int:
    cents = _to_int_cents(value)
    if cents == 0:
        return 0
    return cents if cents < 0 else -cents


def _to_quantity(value: Any) -> float:
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric > 0 else 1.0
    if isinstance(value, str):
        raw = value.strip().replace(",", ".")
        if not raw:
            return 1.0
        try:
            parsed = float(raw)
            return parsed if parsed > 0 else 1.0
        except ValueError:
            return 1.0
    return 1.0


def _discount_subkind(label: str) -> str | None:
    lowered = label.lower()
    if "coupon" in lowered or "gutschein" in lowered:
        return "coupon"
    if "bonus" in lowered or "app" in lowered:
        return "loyalty"
    if "rabatt" in lowered or "aktion" in lowered or "promotion" in lowered:
        return "promotion"
    return None


class RossmannConnectorAdapter(BaseConnectorAdapter):
    required_scope_map = {
        "authenticate": ("auth.session",),
        "refresh_auth": ("auth.session",),
        "healthcheck": ("read.health",),
        "discover_new_records": ("read.receipts",),
        "fetch_record_detail": ("read.receipt_detail",),
        "normalize": ("transform.normalize",),
        "extract_discounts": ("transform.discounts",),
    }

    def __init__(
        self,
        *,
        client: RossmannPlaywrightClient,
        source: str = "rossmann_de",
        store_name: str = "Rossmann",
    ) -> None:
        self._client = client
        self._source = source
        self._store_name = store_name
        self._cache: _OrderCache | None = None

    def authenticate(self) -> dict[str, Any]:
        self._ensure_cache()
        return {"authenticated": True}

    def refresh_auth(self) -> dict[str, Any]:
        self._cache = None
        self._ensure_cache()
        return {"refreshed": True}

    def healthcheck(self) -> dict[str, Any]:
        try:
            cache = self._ensure_cache()
        except RossmannClientError as exc:
            return {"healthy": False, "error": str(exc)}
        return {"healthy": True, "sample_size": len(cache.by_order_id)}

    def discover_new_records(self) -> list[str]:
        cache = self._ensure_cache()
        return list(cache.by_order_id.keys())

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        cache = self._ensure_cache()
        order = cache.by_order_id.get(record_ref)
        if order is None:
            raise RossmannClientError(f"order not found for record_ref={record_ref}")
        return self._map_order_to_receipt_payload(order)

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_receipt(record_detail)
        return {
            "id": normalized.id,
            "purchased_at": normalized.purchased_at.isoformat(),
            "store_id": normalized.store_id,
            "store_name": normalized.store_name,
            "store_address": normalized.store_address,
            "total_gross_cents": normalized.total_gross,
            "currency": normalized.currency,
            "discount_total_cents": normalized.discount_total,
            "fingerprint": normalized.fingerprint,
            "items": [
                {
                    "line_no": item.line_no,
                    "source_item_id": f"{normalized.id}:{item.line_no}",
                    "name": item.name,
                    "qty": str(item.qty),
                    "unit": item.unit,
                    "unit_price_cents": item.unit_price,
                    "line_total_cents": item.line_total,
                    "vat_rate": str(item.vat_rate) if item.vat_rate is not None else None,
                    "category": item.category,
                    "discounts": item.discounts,
                }
                for item in normalized.items
            ],
            "raw_json": normalized.raw_json,
        }

    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        discounts: list[dict[str, Any]] = []
        raw_items = record_detail.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        for idx, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            raw_discounts = item.get("discounts")
            item_discounts = raw_discounts if isinstance(raw_discounts, list) else []
            for raw_discount in item_discounts:
                if not isinstance(raw_discount, dict):
                    continue
                amount_cents = abs(int(raw_discount.get("amount_cents", 0) or 0))
                if amount_cents <= 0:
                    continue
                discount_type = str(raw_discount.get("type") or "unknown")
                source_code = raw_discount.get("promotion_id")
                source_label = str(raw_discount.get("label") or discount_type)
                raw_scope = str(raw_discount.get("scope") or "item")
                scope = "transaction" if raw_scope in {"basket", "transaction"} else "item"
                discounts.append(
                    {
                        "line_no": idx if scope == "item" else None,
                        "type": discount_type,
                        "promotion_id": str(source_code) if source_code is not None else None,
                        "amount_cents": amount_cents,
                        "label": source_label,
                        "scope": scope,
                        "subkind": _discount_subkind(source_label),
                        "funded_by": "retailer",
                    }
                )
        return discounts

    def _ensure_cache(self) -> _OrderCache:
        if self._cache is not None:
            return self._cache
        orders = self._client.fetch_receipts()
        by_order_id: dict[str, dict[str, Any]] = {}
        for raw in orders:
            if not isinstance(raw, dict):
                continue
            order_id = str(raw.get("orderId") or "").strip()
            if order_id:
                by_order_id[order_id] = raw
        self._cache = _OrderCache(by_order_id=by_order_id, fetched_at=datetime.now(tz=UTC))
        return self._cache

    def _map_order_to_receipt_payload(self, order: dict[str, Any]) -> dict[str, Any]:
        order_id = str(order.get("orderId") or "").strip()
        purchased_at = parse_rossmann_date(str(order.get("orderDate") or ""))
        currency = str(order.get("currency") or "EUR")
        store_id = self._source

        mapped_items: list[dict[str, Any]] = []
        line_total_sum = 0
        item_discount_total = 0

        raw_items = order.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        for idx, raw_item in enumerate(items, start=1):
            if not isinstance(raw_item, dict):
                continue
            qty = _to_quantity(raw_item.get("quantity"))
            unit_price_cents = _to_int_cents(raw_item.get("price"))
            item_discount_cents = _to_discount_cents(raw_item.get("discount"))
            item_discount_total += item_discount_cents

            line_total_cents = int(round(qty * unit_price_cents)) + item_discount_cents
            line_total_cents = max(0, line_total_cents)
            line_total_sum += line_total_cents

            discounts: list[dict[str, Any]] = []
            if item_discount_cents != 0:
                discounts.append(
                    {
                        "type": "item_discount",
                        "promotion_id": str(raw_item.get("sku") or "rossmann_item_discount"),
                        "amount_cents": item_discount_cents,
                        "label": "Rossmann item discount",
                        "scope": "item",
                    }
                )

            mapped_items.append(
                {
                    "name": str(raw_item.get("title") or f"Rossmann item {idx}"),
                    "qty": qty,
                    "unit": "pcs",
                    "unitPrice": unit_price_cents / 100.0 if unit_price_cents else 0.0,
                    "lineTotal": line_total_cents / 100.0,
                    "discounts": discounts,
                }
            )

        promo_discount_total = 0
        promotions_in = order.get("promotions")
        promotions = promotions_in if isinstance(promotions_in, list) else []
        promo_discounts: list[dict[str, Any]] = []
        for promotion in promotions:
            if not isinstance(promotion, dict):
                continue
            discount_cents = _to_discount_cents(promotion.get("amount"))
            if discount_cents == 0:
                continue
            promo_discount_total += discount_cents
            promo_discounts.append(
                {
                    "type": "promotion",
                    "promotion_id": "rossmann_promotion",
                    "amount_cents": discount_cents,
                    "label": str(promotion.get("description") or "Rossmann promotion"),
                    "scope": "transaction",
                }
            )

        if promo_discounts:
            if not mapped_items:
                mapped_items.append(
                    {
                        "name": "Rossmann order",
                        "qty": 1,
                        "unit": "order",
                        "unitPrice": 0,
                        "lineTotal": 0,
                        "discounts": promo_discounts,
                    }
                )
            else:
                first_discounts = mapped_items[0].get("discounts")
                if isinstance(first_discounts, list):
                    first_discounts.extend(promo_discounts)

        total_gross_cents = _to_int_cents(order.get("totalAmount"))
        if total_gross_cents <= 0:
            total_gross_cents = line_total_sum

        total_savings_cents = _to_int_cents(order.get("totalSavings"))
        if total_savings_cents <= 0:
            total_savings_cents = abs(item_discount_total) + abs(promo_discount_total)
        discount_total = total_savings_cents if total_savings_cents > 0 else None

        fp = compute_fingerprint(
            purchased_at=purchased_at,
            total_cents=total_gross_cents,
            item_names=[str(it.get("name") or "") for it in mapped_items],
        )

        return {
            "id": f"rossmann-{order_id}" if order_id else f"rossmann-fp-{fp[:20]}",
            "purchasedAt": purchased_at,
            "storeId": store_id,
            "storeName": self._store_name,
            "storeAddress": "rossmann.de",
            "totalGross": total_gross_cents / 100.0,
            "currency": currency,
            "discountTotal": (discount_total / 100.0) if discount_total is not None else None,
            "items": mapped_items,
            "source": self._source,
            "rawOrderId": order_id or None,
            "detailsUrl": order.get("detailsUrl"),
            "orderStatus": order.get("orderStatus"),
            "originalOrder": order,
        }
