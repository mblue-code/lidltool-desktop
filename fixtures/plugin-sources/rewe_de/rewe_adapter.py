from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from rewe_client import ReweClientError, RewePlaywrightClient, classify_rewe_discount

from lidltool.connectors.base import BaseConnectorAdapter
from lidltool.ingest.normalizer import normalize_receipt


@dataclass(slots=True)
class _RecordCache:
    by_record_ref: dict[str, dict[str, Any]]
    fetched_at: datetime


class ReweConnectorAdapter(BaseConnectorAdapter):
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
        client: RewePlaywrightClient,
        source: str = "rewe_de",
        store_name: str = "REWE",
    ) -> None:
        self._client = client
        self._source = source
        self._store_name = store_name
        self._cache: _RecordCache | None = None
        self._legacy_records_by_ref: dict[str, dict[str, Any]] = {}

    def authenticate(self) -> dict[str, Any]:
        self._ensure_cache()
        return {"authenticated": True}

    def refresh_auth(self) -> dict[str, Any]:
        self._cache = None
        self._legacy_records_by_ref = {}
        self._ensure_cache()
        return {"refreshed": True}

    def healthcheck(self) -> dict[str, Any]:
        try:
            cache = self._ensure_cache()
        except ReweClientError as exc:
            return {"healthy": False, "error": str(exc)}
        return {"healthy": True, "sample_size": len(cache.by_record_ref)}

    def discover_new_records(self) -> list[str]:
        cache = self._ensure_cache()
        return list(cache.by_record_ref.keys())

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        cache = self._ensure_cache()
        summary = cache.by_record_ref.get(record_ref)
        if summary is None:
            raise ReweClientError(f"record not found for record_ref={record_ref}")
        if hasattr(self._client, "fetch_record_detail"):
            try:
                return self._client.fetch_record_detail(record_ref, summary=summary)  # type: ignore[misc]
            except TypeError:
                return self._client.fetch_record_detail(record_ref)  # type: ignore[misc]
        raw = self._legacy_records_by_ref.get(record_ref)
        if raw is None:
            raise ReweClientError(f"record detail not found for record_ref={record_ref}")
        return self._map_legacy_order_to_receipt_payload(raw, record_ref=record_ref)

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
                normalized = self._normalize_discount_row(raw_discount, scope_default="item")
                if normalized is None:
                    continue
                normalized["line_no"] = idx
                discounts.append(normalized)

        transaction_discounts_raw = record_detail.get("transactionDiscounts")
        transaction_discounts = (
            transaction_discounts_raw if isinstance(transaction_discounts_raw, list) else []
        )
        for raw_discount in transaction_discounts:
            normalized = self._normalize_discount_row(raw_discount, scope_default="transaction")
            if normalized is None:
                continue
            normalized["line_no"] = None
            discounts.append(normalized)
        return discounts

    def _normalize_discount_row(
        self,
        raw_discount: Any,
        *,
        scope_default: str,
    ) -> dict[str, Any] | None:
        if not isinstance(raw_discount, dict):
            return None
        amount_cents = int(raw_discount.get("amount_cents", 0) or 0)
        if amount_cents == 0:
            amount_cents = int(round(float(raw_discount.get("amount", 0.0) or 0.0) * 100))
        amount_cents = abs(amount_cents)
        if amount_cents <= 0:
            return None
        label = str(raw_discount.get("label") or raw_discount.get("name") or "REWE discount")
        type_value = str(raw_discount.get("type") or "").strip()
        subkind = raw_discount.get("subkind")
        if not type_value:
            classified = classify_rewe_discount(label)
            type_value = str(classified["type"] or "discount")
            if subkind is None:
                subkind = classified["subkind"]
        return {
            "type": type_value,
            "promotion_id": (
                str(raw_discount.get("promotion_id") or raw_discount.get("promotionId") or "").strip()
                or None
            ),
            "amount_cents": amount_cents,
            "label": label,
            "scope": "transaction"
            if str(raw_discount.get("scope") or scope_default) == "transaction"
            else "item",
            "subkind": str(subkind) if subkind is not None else None,
            "funded_by": str(raw_discount.get("funded_by") or "retailer"),
        }

    def _ensure_cache(self) -> _RecordCache:
        if self._cache is not None:
            return self._cache
        if hasattr(self._client, "fetch_records"):
            raw_records = self._client.fetch_records()  # type: ignore[misc]
            by_record_ref = {
                str(record.get("recordRef") or ""): record
                for record in raw_records
                if isinstance(record, dict) and str(record.get("recordRef") or "").strip()
            }
        else:
            legacy_orders = self._client.fetch_receipts()  # type: ignore[misc]
            by_record_ref = {}
            for raw in legacy_orders:
                if not isinstance(raw, dict):
                    continue
                order_id = str(raw.get("orderId") or "").strip()
                if not order_id:
                    continue
                record_ref = f"online:{order_id}"
                by_record_ref[record_ref] = {
                    "recordRef": record_ref,
                    "channel": "online",
                    "orderId": order_id,
                    "purchasedAt": str(raw.get("orderDate") or ""),
                    "totalAmount": raw.get("totalAmount"),
                    "currency": str(raw.get("currency") or "EUR"),
                    "detailsUrl": str(raw.get("detailsUrl") or ""),
                    "raw": raw,
                }
                self._legacy_records_by_ref[record_ref] = raw
        self._cache = _RecordCache(
            by_record_ref=by_record_ref,
            fetched_at=datetime.now(tz=UTC),
        )
        return self._cache

    def _map_legacy_order_to_receipt_payload(
        self,
        order: dict[str, Any],
        *,
        record_ref: str,
    ) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for raw_item in order.get("items") or []:
            if not isinstance(raw_item, dict):
                continue
            qty = float(raw_item.get("quantity") or 1.0)
            price = float(raw_item.get("price") or 0.0)
            discount = float(raw_item.get("discount") or 0.0)
            line_total = max(round((qty * price) - abs(discount), 2), 0.0)
            item_discounts = []
            if discount:
                item_discounts.append(
                    {
                        "type": "promotion",
                        "amount_cents": -abs(int(round(discount * 100))),
                        "label": "REWE legacy item discount",
                        "scope": "item",
                    }
                )
            items.append(
                {
                    "name": str(raw_item.get("title") or "REWE item"),
                    "qty": qty,
                    "unit": "pcs",
                    "unitPrice": price,
                    "lineTotal": line_total,
                    "discounts": item_discounts,
                }
            )
        transaction_discounts = []
        for promotion in order.get("promotions") or []:
            if not isinstance(promotion, dict):
                continue
            amount_cents = abs(int(round(float(promotion.get("amount") or 0.0) * 100)))
            if amount_cents <= 0:
                continue
            transaction_discounts.append(
                {
                    "type": "promotion",
                    "subkind": "promotion",
                    "amount_cents": -amount_cents,
                    "label": str(promotion.get("description") or "REWE promotion"),
                    "scope": "transaction",
                }
            )
        return {
            "id": str(order.get("orderId") or record_ref),
            "orderId": str(order.get("orderId") or ""),
            "channel": "online",
            "kind": "online_order_receipt",
            "purchasedAt": str(order.get("orderDate") or datetime.now(tz=UTC).isoformat()),
            "storeName": self._store_name,
            "storeAddress": None,
            "totalGross": float(order.get("totalAmount") or 0.0),
            "currency": str(order.get("currency") or "EUR"),
            "discountTotal": float(order.get("totalSavings") or 0.0),
            "items": items
            or [
                {
                    "name": "REWE Online Bestellung",
                    "qty": 1,
                    "unit": "order",
                    "unitPrice": float(order.get("totalAmount") or 0.0),
                    "lineTotal": float(order.get("totalAmount") or 0.0),
                    "discounts": [],
                }
            ],
            "transactionDiscounts": transaction_discounts,
            "bonus": {"earned": [], "redeemed": [], "matched_transactions": []},
            "source_record_detail": {"legacy_order": order},
            "raw_json": {"legacy_order": order},
        }
