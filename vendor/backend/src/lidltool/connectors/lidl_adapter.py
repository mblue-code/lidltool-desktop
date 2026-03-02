from __future__ import annotations

from typing import Any

from lidltool.connectors.base import BaseConnectorAdapter
from lidltool.ingest.normalizer import normalize_receipt
from lidltool.lidl.client import LidlClient, LidlClientError


class LidlConnectorAdapter(BaseConnectorAdapter):
    required_scope_map = {
        "authenticate": ("auth.session",),
        "refresh_auth": ("auth.session",),
        "healthcheck": ("read.health",),
        "discover_new_records": ("read.receipts",),
        "fetch_record_detail": ("read.receipt_detail",),
        "normalize": ("transform.normalize",),
        "extract_discounts": ("transform.discounts",),
    }

    def __init__(self, client: LidlClient, page_size: int = 50) -> None:
        self._client = client
        self._page_size = page_size
        self._summary_cache: dict[str, dict[str, Any]] = {}

    def authenticate(self) -> dict[str, Any]:
        # List call forces token validity checks in the Lidl client implementations.
        self._client.list_receipts(page_size=1)
        return {"authenticated": True}

    def refresh_auth(self) -> dict[str, Any]:
        # Current Lidl clients auto-refresh internally on demand.
        self._client.list_receipts(page_size=1)
        return {"refreshed": True}

    def healthcheck(self) -> dict[str, Any]:
        try:
            page = self._client.list_receipts(page_size=1)
        except LidlClientError as exc:
            return {"healthy": False, "error": str(exc)}
        return {"healthy": True, "sample_size": len(page.receipts)}

    def discover_new_records(self) -> list[str]:
        refs: list[str] = []
        self._summary_cache = {}
        page_token: str | None = None
        while True:
            page = self._client.list_receipts(page_token=page_token, page_size=self._page_size)
            for summary in page.receipts:
                ref = summary.get("id")
                if isinstance(ref, str) and ref:
                    refs.append(ref)
                    self._summary_cache[ref] = summary
            page_token = page.next_page_token
            if not page_token:
                break
        return refs

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        return self._client.get_receipt(record_ref)

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        summary = self._summary_cache.get(str(record_detail.get("id", ""))) or None
        normalized = normalize_receipt(record_detail, summary=summary)
        items = [
            {
                "line_no": item.line_no,
                "name": item.name,
                "qty": str(item.qty),
                "unit": item.unit,
                "unit_price_cents": item.unit_price,
                "line_total_cents": item.line_total,
                "is_deposit": bool("pfand" in item.name.lower()),
                "vat_rate": str(item.vat_rate) if item.vat_rate is not None else None,
                "category": item.category,
                "discounts": item.discounts,
            }
            for item in normalized.items
        ]
        deposit_cents = 0
        for _item in items:
            if _item.get("is_deposit"):
                raw = _item.get("line_total_cents")
                # Only subtract positive deposits paid; returns (negative) stay in totalAmount
                if isinstance(raw, int) and raw > 0:
                    deposit_cents += raw
        return {
            "id": normalized.id,
            "purchased_at": normalized.purchased_at.isoformat(),
            "store_id": normalized.store_id,
            "store_name": normalized.store_name,
            "store_address": normalized.store_address,
            "total_gross_cents": normalized.total_gross - deposit_cents,
            "currency": normalized.currency,
            "discount_total_cents": normalized.discount_total,
            "fingerprint": normalized.fingerprint,
            "items": items,
            "raw_json": normalized.raw_json,
        }

    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        discounts: list[dict[str, Any]] = []
        items = record_detail.get("items")
        if not isinstance(items, list):
            return discounts
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            item_discounts = item.get("discounts")
            if not isinstance(item_discounts, list):
                continue
            for raw_discount in item_discounts:
                if not isinstance(raw_discount, dict):
                    continue
                discounts.append(
                    {
                        "line_no": index,
                        "type": str(raw_discount.get("type", "unknown")),
                        "promotion_id": raw_discount.get("promotion_id"),
                        "amount_cents": int(raw_discount.get("amount_cents", 0)),
                        "label": str(raw_discount.get("label", "")),
                    }
                )
        return discounts
