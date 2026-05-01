from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from collections.abc import Callable, Iterator
from typing import Any

from lidltool.amazon.client_playwright import (
    AmazonClientError,
    AmazonPlaywrightClient,
)
from lidltool.amazon.order_money import (
    amazon_financials_payload,
    normalize_order_financials,
    payment_adjustment_subkind,
    resolve_discount_total_cents,
    resolve_total_gross_cents,
    to_int_cents,
)
from lidltool.amazon.profiles import AmazonCountryProfile, get_country_profile
from lidltool.connectors.base import BaseConnectorAdapter
from lidltool.ingest.dedupe import compute_fingerprint
from lidltool.ingest.normalizer import normalize_receipt, parse_datetime


@dataclass(slots=True)
class _OrderCache:
    by_order_id: dict[str, dict[str, Any]]
    fetched_at: datetime


def _to_int_cents(value: Any) -> int:
    return to_int_cents(value)


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


def _extract_host(url: str) -> str | None:
    if "://" not in url:
        return None
    after_scheme = url.split("://", 1)[1]
    host = after_scheme.split("/", 1)[0].strip()
    return host or None


def _discount_subkind(label: str) -> str | None:
    payment_subkind = payment_adjustment_subkind(label)
    if payment_subkind is not None:
        return payment_subkind
    lowered = label.lower()
    if "subscribe" in lowered or "spar-abo" in lowered or "abonnez-vous" in lowered:
        return "subscribe_and_save"
    if "coupon" in lowered or "bon de réduction" in lowered:
        return "coupon"
    if "rabatt" in lowered or "discount" in lowered or "réduction" in lowered or "reduction" in lowered:
        return "promotion"
    return None


def _resolve_order_purchase_datetime(
    order: dict[str, Any],
    *,
    profile: AmazonCountryProfile,
) -> tuple[datetime, str]:
    raw_date = order.get("orderDate")
    if isinstance(raw_date, str) and raw_date.strip():
        parsed = profile.date_parser(raw_date)
        if parsed is not None:
            return parsed, "explicit_order_date"
        return parse_datetime(raw_date), "explicit_order_date"
    if raw_date is not None and not (isinstance(raw_date, str) and not raw_date.strip()):
        return parse_datetime(raw_date), "explicit_order_date"

    page_year = order.get("pageYear")
    try:
        parsed_year = int(page_year)
    except (TypeError, ValueError):
        parsed_year = 0
    if parsed_year >= 1995:
        return datetime(parsed_year, 1, 1, tzinfo=UTC), "page_year"

    return datetime.now(tz=UTC), "fallback_now"


def _reallocate_single_item_total(
    *,
    mapped_items: list[dict[str, Any]],
    total_gross_cents: int,
    shipping_cents: int,
    gift_wrap_cents: int,
    promo_discount_total: int,
    payment_adjustment_total: int,
) -> None:
    if (
        total_gross_cents <= 0
        or shipping_cents > 0
        or gift_wrap_cents > 0
        or promo_discount_total != 0
        or payment_adjustment_total != 0
    ):
        return

    deposit_total_cents = sum(
        _to_int_cents(item.get("lineTotal"))
        for item in mapped_items
        if bool(item.get("is_deposit"))
    )
    product_items = [
        item
        for item in mapped_items
        if not bool(item.get("is_deposit"))
        and str(item.get("category") or "").strip().lower() not in {"shipping", "fees"}
    ]
    if len(product_items) != 1:
        return

    item = product_items[0]
    qty = _to_quantity(item.get("qty"))
    allocatable_cents = total_gross_cents - shipping_cents - gift_wrap_cents - deposit_total_cents
    if allocatable_cents <= 0:
        return

    current_line_total_cents = _to_int_cents(item.get("lineTotal"))
    if abs(current_line_total_cents - allocatable_cents) <= 1:
        return

    unit_price_cents = int(round(allocatable_cents / qty)) if qty > 0 else allocatable_cents
    item["unitPrice"] = unit_price_cents / 100.0
    item["lineTotal"] = allocatable_cents / 100.0

class AmazonConnectorAdapter(BaseConnectorAdapter):
    dedupe_by_source_transaction_id = True

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
        client: AmazonPlaywrightClient,
        source: str = "amazon_de",
        store_name: str = "Amazon",
        years: int = 2,
        max_pages_per_year: int | None = None,
    ) -> None:
        self._client = client
        self._source = source
        self._store_name = store_name
        self._years = years
        self._max_pages_per_year = max_pages_per_year
        self._cache: _OrderCache | None = None
        self._session_validated = False
        self._profile: AmazonCountryProfile = getattr(
            client,
            "profile",
            get_country_profile(source_id=source),
        )

    def authenticate(self) -> dict[str, Any]:
        self._ensure_valid_session()
        return {"authenticated": True}

    def refresh_auth(self) -> dict[str, Any]:
        self._cache = None
        self._ensure_valid_session()
        return {"refreshed": True}

    def healthcheck(self) -> dict[str, Any]:
        try:
            self._ensure_valid_session()
            cache = self._cache
        except AmazonClientError as exc:
            return {"healthy": False, "error": str(exc)}
        sample_size = len(cache.by_order_id) if cache is not None else 0
        return {"healthy": True, "sample_size": sample_size}

    def discover_new_records(self) -> list[str]:
        cache = self._ensure_cache()
        return list(cache.by_order_id.keys())

    def stream_record_details_with_progress(
        self,
        *,
        max_pages: int | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        iter_orders = getattr(self._client, "iter_orders", None)
        if callable(iter_orders):
            for order in iter_orders(
                years=max(1, self._years),
                max_pages_per_year=(
                    max(1, self._max_pages_per_year)
                    if self._max_pages_per_year is not None
                    else None
                ),
                max_pages=max_pages,
                progress_cb=progress_cb,
            ):
                order_id = str(order.get("orderId") or "").strip()
                if not order_id:
                    continue
                yield order_id, self._map_order_to_receipt_payload(order)
            return

        cache = self._ensure_cache()
        for index, order_id in enumerate(cache.by_order_id.keys(), start=1):
            order = cache.by_order_id[order_id]
            if progress_cb is not None:
                progress_cb(
                    {
                        "pages": 1,
                        "discovered_receipts": index,
                    }
                )
            yield order_id, self._map_order_to_receipt_payload(order)

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        cache = self._ensure_cache()
        order = cache.by_order_id.get(record_ref)
        if order is None:
            raise AmazonClientError(f"order not found for record_ref={record_ref}")
        return self._map_order_to_receipt_payload(order)

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        if str(record_detail.get("parseStatus") or "").strip().lower() == "unsupported":
            reason = str(record_detail.get("unsupportedReason") or "unsupported_order")
            raise AmazonClientError(f"unsupported Amazon order skipped: {reason}")

        normalized = normalize_receipt(record_detail)
        raw_items = record_detail.get("items")
        source_items = raw_items if isinstance(raw_items, list) else []
        normalized_items: list[dict[str, Any]] = []
        for item in normalized.items:
            source_item = (
                source_items[item.line_no - 1]
                if 0 <= item.line_no - 1 < len(source_items)
                and isinstance(source_items[item.line_no - 1], dict)
                else {}
            )
            normalized_items.append(
                {
                    "line_no": item.line_no,
                    "source_item_id": f"{normalized.id}:{item.line_no}",
                    "name": item.name,
                    "qty": str(item.qty),
                    "unit": item.unit,
                    "unit_price_cents": item.unit_price,
                    "line_total_cents": item.line_total,
                    "is_deposit": bool(source_item.get("is_deposit")),
                    "category": item.category,
                    "discounts": item.discounts,
                }
            )
        return {
            "id": normalized.id,
            "purchased_at": normalized.purchased_at.isoformat(),
            "date_source": record_detail.get("dateSource"),
            "page_year": record_detail.get("pageYear"),
            "store_id": normalized.store_id,
            "store_name": normalized.store_name,
            "store_address": normalized.store_address,
            "total_gross_cents": normalized.total_gross,
            "currency": normalized.currency,
            "discount_total_cents": normalized.discount_total,
            "fingerprint": normalized.fingerprint,
            "items": normalized_items,
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
                funded_by = "amazon" if scope == "transaction" else "retailer"
                discounts.append(
                    {
                        "line_no": idx if scope == "item" else None,
                        "type": discount_type,
                        "promotion_id": str(source_code) if source_code is not None else None,
                        "amount_cents": amount_cents,
                        "label": source_label,
                        "scope": scope,
                        "subkind": _discount_subkind(source_label),
                        "funded_by": funded_by,
                    }
                )
        return discounts

    def _ensure_cache(self) -> _OrderCache:
        if self._cache is not None:
            return self._cache
        iter_orders = getattr(self._client, "iter_orders", None)
        if callable(iter_orders):
            orders = list(
                iter_orders(
                    years=max(1, self._years),
                    max_pages_per_year=(
                        max(1, self._max_pages_per_year)
                        if self._max_pages_per_year is not None
                        else None
                    ),
                )
            )
        else:
            orders = self._client.fetch_orders(
                years=max(1, self._years),
                max_pages_per_year=(
                    max(1, self._max_pages_per_year)
                    if self._max_pages_per_year is not None
                    else None
                ),
            )
        by_order_id: dict[str, dict[str, Any]] = {}
        for raw in orders:
            if not isinstance(raw, dict):
                continue
            order_id = str(raw.get("orderId") or "").strip()
            if order_id:
                by_order_id[order_id] = raw
        self._cache = _OrderCache(by_order_id=by_order_id, fetched_at=datetime.now(tz=UTC))
        return self._cache

    def _ensure_valid_session(self) -> None:
        if self._session_validated:
            return
        validate_session = getattr(self._client, "validate_session", None)
        if callable(validate_session):
            validate_session()
        else:
            # Fallback for test doubles that only implement fetch_orders.
            self._ensure_cache()
        self._session_validated = True

    def _map_order_to_receipt_payload(self, order: dict[str, Any]) -> dict[str, Any]:
        order_id = str(order.get("orderId") or "").strip()
        details_url = str(order.get("detailsUrl") or "").strip()
        currency = str(order.get("currency") or "EUR")
        host = _extract_host(details_url)
        store_id = f"{self._source}:{host}" if host else self._source

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
            is_deposit = bool(
                raw_item.get("isDeposit")
                or raw_item.get("is_deposit")
                or str(raw_item.get("category") or "").strip().lower() == "deposit"
            )
            item_discount_total += item_discount_cents

            line_total_cents = int(round(qty * unit_price_cents)) + item_discount_cents
            line_total_cents = max(0, line_total_cents)
            line_total_sum += line_total_cents

            discounts: list[dict[str, Any]] = []
            if item_discount_cents != 0:
                discounts.append(
                    {
                        "type": "item_discount",
                        "promotion_id": str(raw_item.get("asin") or "amazon_item_discount"),
                        "amount_cents": item_discount_cents,
                        "label": "Amazon item discount",
                        "scope": "item",
                    }
                )

            mapped_items.append(
                {
                    "name": str(raw_item.get("title") or f"Amazon item {idx}"),
                    "qty": qty,
                    "unit": "deposit" if is_deposit else "pcs",
                    "unitPrice": unit_price_cents / 100.0 if unit_price_cents else 0.0,
                    "lineTotal": line_total_cents / 100.0,
                    "discounts": discounts,
                    "is_deposit": is_deposit,
                    "category": str(raw_item.get("category") or "").strip() or None,
                }
            )

        promo_discount_total = 0
        payment_adjustment_total = 0
        promotions_in = order.get("promotions")
        promotions = promotions_in if isinstance(promotions_in, list) else []
        promo_discounts: list[dict[str, Any]] = []
        payment_adjustments: list[dict[str, Any]] = []
        seen_payment_adjustments: set[tuple[str, int, str]] = set()
        for promotion in promotions:
            if not isinstance(promotion, dict):
                continue
            discount_cents = _to_discount_cents(promotion.get("amount"))
            if discount_cents == 0:
                continue
            label = str(promotion.get("description") or "Amazon promotion")
            payment_subkind = payment_adjustment_subkind(label)
            if payment_subkind is not None:
                payment_adjustment_total += abs(discount_cents)
                key = (payment_subkind, abs(discount_cents), label)
                if key not in seen_payment_adjustments:
                    payment_adjustments.append(
                        {
                            "type": "payment_adjustment",
                            "subkind": payment_subkind,
                            "amount_cents": abs(discount_cents),
                            "label": label,
                        }
                    )
                    seen_payment_adjustments.add(key)
                continue
            promo_discount_total += discount_cents
            promo_discounts.append(
                {
                    "type": "promotion",
                    "promotion_id": "amazon_promotion",
                    "amount_cents": discount_cents,
                    "label": label,
                    "scope": "basket",
                }
            )
        raw_payment_adjustments = order.get("paymentAdjustments")
        if isinstance(raw_payment_adjustments, list):
            for adjustment in raw_payment_adjustments:
                if not isinstance(adjustment, dict):
                    continue
                subkind = str(adjustment.get("subkind") or "").strip()
                if not subkind:
                    subkind = payment_adjustment_subkind(adjustment.get("label"))
                if not subkind:
                    continue
                amount_cents = abs(
                    int(
                        adjustment.get("amount_cents")
                        if adjustment.get("amount_cents") is not None
                        else _to_int_cents(adjustment.get("amount"))
                    )
                )
                if amount_cents <= 0:
                    continue
                label = str(adjustment.get("label") or "Amazon payment adjustment")
                key = (subkind, amount_cents, label)
                if key in seen_payment_adjustments:
                    continue
                payment_adjustment_total += amount_cents
                payment_adjustments.append(
                    {
                        "type": "payment_adjustment",
                        "subkind": subkind,
                        "amount_cents": amount_cents,
                        "label": label,
                    }
                )
                seen_payment_adjustments.add(key)
        if promo_discounts:
            if not mapped_items:
                mapped_items.append(
                    {
                        "name": "Amazon order",
                        "qty": 1,
                        "unit": "order",
                        "unitPrice": 0,
                        "lineTotal": 0,
                        "discounts": promo_discounts,
                    }
                )
            else:
                mapped_items[0].setdefault("discounts", [])
                first_discounts = mapped_items[0]["discounts"]
                if isinstance(first_discounts, list):
                    first_discounts.extend(promo_discounts)

        shipping_cents = _to_int_cents(order.get("shipping"))
        if shipping_cents > 0:
            line_total_sum += shipping_cents
            mapped_items.append(
                {
                    "name": self._profile.shipping_line_name,
                    "qty": 1,
                    "unit": "order",
                    "unitPrice": shipping_cents / 100.0,
                    "lineTotal": shipping_cents / 100.0,
                    "discounts": [],
                    "is_deposit": False,
                    "category": "shipping",
                }
            )

        gift_wrap_cents = _to_int_cents(order.get("gift_wrap"))
        if gift_wrap_cents > 0:
            line_total_sum += gift_wrap_cents
            mapped_items.append(
                {
                    "name": self._profile.gift_wrap_line_name,
                    "qty": 1,
                    "unit": "order",
                    "unitPrice": gift_wrap_cents / 100.0,
                    "lineTotal": gift_wrap_cents / 100.0,
                    "discounts": [],
                    "is_deposit": False,
                    "category": "fees",
                }
            )

        raw_total_amount = order.get("totalAmount")
        total_is_explicit = not (
            raw_total_amount is None or (isinstance(raw_total_amount, str) and not raw_total_amount.strip())
        )
        explicit_total_cents = _to_int_cents(raw_total_amount)
        total_gross_cents = resolve_total_gross_cents(
            order=order,
            explicit_total_cents=explicit_total_cents,
            total_is_explicit=total_is_explicit,
            line_total_sum=line_total_sum,
            basket_discount_total_cents=promo_discount_total,
            payment_adjustment_total_cents=payment_adjustment_total,
        )
        financials = normalize_order_financials(
            order,
            gross_total_cents=total_gross_cents,
            payment_adjustment_total_cents=payment_adjustment_total,
        )
        _reallocate_single_item_total(
            mapped_items=mapped_items,
            total_gross_cents=total_gross_cents,
            shipping_cents=shipping_cents,
            gift_wrap_cents=gift_wrap_cents,
            promo_discount_total=promo_discount_total,
            payment_adjustment_total=payment_adjustment_total,
        )

        if not mapped_items:
            mapped_items.append(
                {
                    "name": "Amazon order",
                    "qty": 1,
                    "unit": "order",
                    "unitPrice": total_gross_cents / 100.0 if total_gross_cents > 0 else 0.0,
                    "lineTotal": total_gross_cents / 100.0 if total_gross_cents > 0 else 0.0,
                    "discounts": [],
                    "is_deposit": False,
                    "category": "other",
                }
            )

        discount_total = resolve_discount_total_cents(
            order=order,
            item_discount_total_cents=item_discount_total,
            basket_discount_total_cents=promo_discount_total,
            payment_adjustment_total_cents=payment_adjustment_total,
        )

        purchased, date_source = _resolve_order_purchase_datetime(order, profile=self._profile)
        fp = compute_fingerprint(
            purchased_at=purchased.isoformat(),
            total_cents=financials.net_spending_total_cents,
            item_names=[str(it.get("name") or "") for it in mapped_items],
        )

        return {
            "id": f"amazon-{order_id}" if order_id else f"amazon-fp-{fp[:20]}",
            "purchasedAt": purchased.isoformat(),
            "dateSource": date_source,
            "pageYear": order.get("pageYear"),
            "pageIndex": order.get("pageIndex"),
            "pageStartIndex": order.get("pageStartIndex"),
            "storeId": store_id,
            "storeName": self._store_name,
            "storeAddress": host,
            "totalGross": financials.net_spending_total_cents / 100.0,
            "currency": currency,
            "discountTotal": (discount_total / 100.0) if discount_total is not None else None,
            "items": mapped_items,
            "source": self._source,
            "rawOrderId": order_id or None,
            "detailsUrl": details_url or None,
            "orderStatus": order.get("orderStatus"),
            "parseStatus": order.get("parseStatus"),
            "parseWarnings": order.get("parseWarnings"),
            "unsupportedReason": order.get("unsupportedReason"),
            "subtotals": order.get("subtotals"),
            "amazonFinancials": amazon_financials_payload(financials),
            "paymentAdjustments": payment_adjustments,
            "originalOrder": order,
        }
