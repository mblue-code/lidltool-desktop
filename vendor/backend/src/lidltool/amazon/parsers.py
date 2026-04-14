from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from lidltool.amazon.profiles import AmazonCountryProfile

AmazonParseStatus = Literal["complete", "partial", "unsupported"]

_SPLIT_LINES_RE = re.compile(r"\s*\n+\s*")
_ORDER_ID_RE = re.compile(r"\d{3}-\d{7}-\d{7}")
_ORDER_ID_FROM_URL_RE = re.compile(r"orderI[Dd]=(\d{3}-\d{7}-\d{7})")
_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$|\?)", re.IGNORECASE)
_ITEM_QTY_PATTERNS = (
    re.compile(r"(?i)(?:menge|qty|anzahl|quantit[ée])\s*[:x]?\s*(\d+)"),
    re.compile(r"(?i)\b(\d+)\s*[x×]\b"),
    re.compile(r"(?i)\b(\d+)\s*(?:stück|stk|pcs|pack|article|articles)\b"),
)
_ITEM_DISCOUNT_PATTERNS = (
    re.compile(r"(?i)(?:spar(?:en|abo)?|rabatt|discount|coupon|gutschein|nachlass|ersparnis)[^\n]{0,100}?([0-9]+[.,][0-9]{2})"),
    re.compile(r"(?i)(?:r[ée]duction|remise|coupon|[ée]conomie)[^\n]{0,100}?([0-9]+[.,][0-9]{2})"),
)


@dataclass(frozen=True, slots=True)
class AmazonParseResult:
    data: dict[str, Any]
    parse_status: AmazonParseStatus
    parse_warnings: tuple[str, ...]
    unsupported_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AmazonOrderListPageParseResult:
    orders: list[dict[str, Any]]
    has_next_page: bool


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def title_key(value: Any) -> str:
    return normalize_text(str(value or "")).lower()


def extract_asin_from_url(url: str) -> str:
    match = _ASIN_RE.search(url)
    return match.group(1).upper() if match else ""


def parse_order_list_html(
    html: str,
    *,
    profile: AmazonCountryProfile,
    page_url: str,
) -> AmazonOrderListPageParseResult:
    soup = BeautifulSoup(html, "lxml")
    order_nodes = _find_order_nodes(soup=soup, profile=profile)
    orders: list[dict[str, Any]] = []

    for order_el in order_nodes:
        text = normalize_text(order_el.get_text(" ", strip=True))
        if not text:
            continue

        details_url = _extract_detail_url(order_el=order_el, profile=profile, page_url=page_url)
        order_id = _extract_order_id(text) or _extract_order_id_from_url(details_url)
        if not order_id:
            continue

        warnings: list[str] = []
        order_date = _extract_order_date(text=text, profile=profile)
        if not order_date:
            warnings.append("missing_order_date")

        total_amount, currency = _extract_total_amount(text=text, profile=profile)
        if total_amount <= 0:
            warnings.append("missing_total_amount")

        order_status = _extract_order_status(text=text, profile=profile)
        if not details_url:
            warnings.append("missing_details_url")

        items = _extract_list_items(order_el=order_el, profile=profile)
        if not items:
            warnings.append("missing_list_items")

        unsupported_reason = classify_unsupported_order(
            text=text,
            status=order_status,
            items=items,
            profile=profile,
        )
        parse_status: AmazonParseStatus = (
            "unsupported" if unsupported_reason else "partial" if warnings else "complete"
        )

        orders.append(
            {
                "orderId": order_id,
                "orderDate": order_date,
                "totalAmount": total_amount,
                "currency": currency or profile.currency,
                "items": items,
                "orderStatus": order_status,
                "detailsUrl": details_url,
                "promotions": [],
                "totalSavings": 0,
                "parseStatus": parse_status,
                "parseWarnings": warnings,
                "unsupportedReason": unsupported_reason,
            }
        )

    has_next_page = any(
        soup.select_one(selector) is not None
        for selector in profile.selector_bundle.pagination.next_page_selectors
    )
    return AmazonOrderListPageParseResult(orders=orders, has_next_page=has_next_page)


def parse_order_detail_html(html: str, *, profile: AmazonCountryProfile) -> AmazonParseResult:
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []
    items: list[dict[str, Any]] = []

    shipment_boxes = _select_first_nonempty(
        soup=soup,
        selectors=profile.selector_bundle.detail.shipment_selectors,
    )
    if not shipment_boxes:
        shipment_boxes = _select_first_nonempty(
            soup=soup,
            selectors=profile.selector_bundle.detail.fallback_shipment_selectors,
        )

    for box in shipment_boxes:
        row_nodes = _select_first_nonempty_within(
            container=box,
            selectors=profile.selector_bundle.detail.item_row_selectors,
        )
        for row in row_nodes:
            row_item = _parse_detail_item(row=row, profile=profile)
            if row_item is not None:
                items.append(row_item)

    collapsed_items = collapse_detail_items(items)
    if not collapsed_items:
        warnings.append("missing_detail_items")

    subtotal_entries = parse_subtotal_entries(soup=soup, profile=profile)
    promotions = [
        {
            "description": entry["label"],
            "amount": abs(float(entry["amount"])),
            "category": entry["category"],
        }
        for entry in subtotal_entries
        if entry["category"]
        not in {"shipping", "gift_wrap", "free_shipping"}
        and float(entry["amount"]) != 0
    ]

    if not promotions:
        promotions = parse_promotions_from_details_html(html, profile=profile)

    shipping = sum(
        abs(float(entry["amount"]))
        for entry in subtotal_entries
        if entry["category"] == "shipping" and float(entry["amount"]) != 0
    )
    gift_wrap = sum(
        abs(float(entry["amount"]))
        for entry in subtotal_entries
        if entry["category"] == "gift_wrap" and float(entry["amount"]) != 0
    )

    text = normalize_text(soup.get_text(" ", strip=True))
    unsupported_reason = classify_unsupported_order(
        text=text,
        status=text,
        items=collapsed_items,
        profile=profile,
    )
    parse_status: AmazonParseStatus = (
        "unsupported" if unsupported_reason else "partial" if warnings else "complete"
    )

    return AmazonParseResult(
        data={
            "items": collapsed_items,
            "promotions": promotions,
            "shipping": round(shipping, 2),
            "gift_wrap": round(gift_wrap, 2),
            "subtotals": subtotal_entries,
        },
        parse_status=parse_status,
        parse_warnings=tuple(warnings),
        unsupported_reason=unsupported_reason,
    )


def parse_promotions_from_details_html(
    html: str,
    *,
    profile: AmazonCountryProfile,
) -> list[dict[str, Any]]:
    plain = BeautifulSoup(html, "lxml").get_text("\n", strip=True)
    candidate_lines = _SPLIT_LINES_RE.split(plain)

    promotions: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for line in candidate_lines:
        lowered = line.lower()
        if not any(keyword in lowered for keyword in profile.promotion_keywords):
            continue
        amount = abs(parse_signed_amount(line, profile=profile))
        if amount <= 0:
            continue
        desc = normalize_text(line)[:120]
        key = (desc, amount)
        if key in seen:
            continue
        seen.add(key)
        promotions.append({"description": desc, "amount": round(amount, 2), "category": "promotion"})
    return promotions


def parse_subtotal_entries(
    *,
    soup: BeautifulSoup,
    profile: AmazonCountryProfile,
) -> list[dict[str, Any]]:
    containers = _select_first_nonempty(
        soup=soup,
        selectors=profile.selector_bundle.detail.subtotal_container_selectors,
    )
    subtotals: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()

    for container in containers:
        rows = _select_first_nonempty_within(
            container=container,
            selectors=profile.selector_bundle.detail.subtotal_row_selectors,
        )
        for row in rows:
            text = normalize_text(row.get_text(" ", strip=True))
            if not text:
                continue
            amount_node = _select_one_within(
                container=row,
                selectors=profile.selector_bundle.detail.subtotal_amount_selectors,
            )
            if amount_node is None:
                continue
            amount = parse_signed_amount(amount_node.get_text(strip=True), profile=profile)
            if amount == 0:
                continue
            category = classify_subtotal_label(text=text, profile=profile)
            key = (text.lower(), round(amount, 2))
            if key in seen:
                continue
            seen.add(key)
            subtotals.append(
                {
                    "label": text[:120],
                    "amount": round(amount, 2),
                    "category": category,
                }
            )
    return subtotals


def collapse_detail_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, float, str], dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        asin = str(raw.get("asin") or "").strip().upper()
        title = normalize_text(str(raw.get("title") or ""))
        seller = normalize_text(str(raw.get("seller") or ""))
        price = float(raw.get("price") or 0)
        discount = float(raw.get("discount") or 0)
        qty = to_positive_int(raw.get("qty"), default=1)
        key = (asin, title.lower(), round(price, 2), seller.lower())
        existing = by_key.get(key)
        if existing is not None:
            existing["qty"] = int(existing.get("qty", 1)) + qty
            existing["discount"] = float(existing.get("discount", 0)) + discount
            continue
        row = {
            "title": title or f"Amazon item {asin}",
            "asin": asin,
            "price": price,
            "qty": qty,
            "seller": seller,
            "discount": discount,
        }
        by_key[key] = row
        collapsed.append(row)
    return collapsed


def detail_to_order_item(
    detail: dict[str, Any],
    *,
    profile: AmazonCountryProfile,
) -> dict[str, Any]:
    asin = str(detail.get("asin") or "").strip().upper()
    title = normalize_text(str(detail.get("title") or "")) or f"Amazon item {asin}"
    quantity = to_positive_int(detail.get("qty", detail.get("quantity", 1)), default=1)
    price = float(detail.get("price") or 0)
    discount = float(detail.get("discount") or 0)
    out: dict[str, Any] = {
        "title": title,
        "asin": asin,
        "quantity": quantity,
        "price": price,
        "discount": discount,
        "itemUrl": profile.item_url(asin),
    }
    seller = normalize_text(str(detail.get("seller") or ""))
    if seller:
        out["seller"] = seller
    return out


def merge_item_details(
    list_items: list[dict[str, Any]],
    detail_items: list[dict[str, Any]],
    *,
    profile: AmazonCountryProfile,
) -> list[dict[str, Any]]:
    if not detail_items:
        return list_items
    detail_rows = [detail_to_order_item(item, profile=profile) for item in collapse_detail_items(detail_items)]
    if not list_items:
        return detail_rows

    by_asin: dict[str, list[int]] = {}
    by_title: dict[str, list[int]] = {}
    for idx, raw in enumerate(list_items):
        if not isinstance(raw, dict):
            continue
        asin = str(raw.get("asin") or "").strip().upper()
        if asin:
            by_asin.setdefault(asin, []).append(idx)
        key = title_key(raw.get("title"))
        if key:
            by_title.setdefault(key, []).append(idx)

    matched_indexes: set[int] = set()
    merged: list[dict[str, Any]] = []

    def _find_match(row: dict[str, Any]) -> int | None:
        asin = str(row.get("asin") or "").strip().upper()
        for idx in by_asin.get(asin, []):
            if idx not in matched_indexes:
                return idx
        key = title_key(row.get("title"))
        for idx in by_title.get(key, []):
            if idx not in matched_indexes:
                return idx
        return None

    for detail in detail_rows:
        match_idx = _find_match(detail)
        base: dict[str, Any] = {}
        if match_idx is not None and isinstance(list_items[match_idx], dict):
            base = dict(list_items[match_idx])
            matched_indexes.add(match_idx)
        merged_item = {**base, **detail}
        if float(detail.get("price") or 0) <= 0 and isinstance(base.get("price"), (int, float)):
            merged_item["price"] = float(base["price"])
        if int(detail.get("quantity") or 1) <= 1 and isinstance(base.get("quantity"), (int, float)):
            merged_item["quantity"] = to_positive_int(base.get("quantity"), default=1)
        if float(detail.get("discount") or 0) <= 0 and isinstance(base.get("discount"), (int, float)):
            merged_item["discount"] = float(base["discount"])
        if not merged_item.get("itemUrl") and isinstance(base.get("itemUrl"), str):
            merged_item["itemUrl"] = base["itemUrl"]
        merged.append(merged_item)

    seen_keys = {
        (str(row.get("asin") or "").strip().upper(), title_key(row.get("title")))
        for row in merged
    }
    for idx, raw in enumerate(list_items):
        if idx in matched_indexes or not isinstance(raw, dict):
            continue
        key = (str(raw.get("asin") or "").strip().upper(), title_key(raw.get("title")))
        if key in seen_keys:
            continue
        merged.append(raw)

    return merged


def parse_signed_amount(text: str, *, profile: AmazonCountryProfile) -> float:
    amount = profile.amount_parser(text)
    if amount == 0:
        return 0.0
    normalized = normalize_text(text).lower()
    negative = normalized.startswith("-") or " -" in normalized or normalized.startswith("(") or "−" in normalized
    return -abs(amount) if negative else abs(amount)


def classify_subtotal_label(text: str, *, profile: AmazonCountryProfile) -> str:
    lowered = text.lower()
    for marker, category in profile.subtotal_label_map:
        if marker in lowered:
            return category
    return "promotion"


def classify_unsupported_order(
    *,
    text: str,
    status: str,
    items: list[dict[str, Any]],
    profile: AmazonCountryProfile,
) -> str | None:
    lowered = f"{text} {status}".lower()
    for rule in profile.unsupported_order_rules:
        if any(marker in lowered for marker in rule.markers):
            if rule.reason == "canceled_only" and items:
                continue
            return rule.reason
    return None


def to_positive_int(value: Any, *, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def parse_qty_from_text(text: str) -> int:
    for pattern in _ITEM_QTY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        qty = to_positive_int(match.group(1), default=0)
        if qty > 0:
            return qty
    return 1


def parse_item_discount_from_text(text: str, *, profile: AmazonCountryProfile) -> float:
    for pattern in _ITEM_DISCOUNT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        amount = abs(profile.amount_parser(match.group(1)))
        if amount > 0:
            return amount
    return 0.0


def _find_order_nodes(
    *,
    soup: BeautifulSoup,
    profile: AmazonCountryProfile,
) -> list[Tag]:
    selector_nodes = _select_first_nonempty(
        soup=soup,
        selectors=profile.selector_bundle.order_list.order_card_selectors,
    )
    if selector_nodes:
        return selector_nodes

    candidates: list[Tag] = []
    seen_ids: set[int] = set()
    for text_node in soup.find_all(string=_ORDER_ID_RE):
        if not isinstance(text_node, NavigableString):
            continue
        parent = text_node.parent
        for _ in range(10):
            if not isinstance(parent, Tag):
                break
            classes = set(parent.get("class", []))
            if {"a-box", "a-box-group"} & classes or (parent.name == "div" and len(parent.find_all(recursive=False)) > 3):
                node_id = id(parent)
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    candidates.append(parent)
                break
            parent = parent.parent
    return candidates


def _extract_order_id(text: str) -> str:
    match = _ORDER_ID_RE.search(text)
    return match.group(0) if match else ""


def _extract_order_id_from_url(url: str) -> str:
    match = _ORDER_ID_FROM_URL_RE.search(url)
    return match.group(1) if match else ""


def _extract_detail_url(
    *,
    order_el: Tag,
    profile: AmazonCountryProfile,
    page_url: str,
) -> str:
    for selector in profile.selector_bundle.order_list.detail_link_selectors:
        link = order_el.select_one(selector)
        if link is None:
            continue
        href = str(link.get("href", "") or getattr(link, "href", "") or "")
        if not href:
            continue
        return urljoin(page_url or f"https://www.{profile.normalized_domain()}/", href)
    return ""


def _extract_order_date(*, text: str, profile: AmazonCountryProfile) -> str:
    for pattern in profile.list_date_patterns:
        match = pattern.search(text)
        if match and match.group(1):
            return normalize_text(match.group(1))
    return ""


def _extract_order_status(*, text: str, profile: AmazonCountryProfile) -> str:
    for pattern in profile.list_status_patterns:
        match = pattern.search(text)
        if match and match.group(0):
            return normalize_text(match.group(0))[:60]
    return ""


def _extract_total_amount(*, text: str, profile: AmazonCountryProfile) -> tuple[float, str]:
    for pattern in profile.order_total_label_patterns:
        match = pattern.search(text)
        if match and match.group(1):
            amount = abs(profile.amount_parser(match.group(1)))
            if amount > 0:
                return round(amount, 2), profile.currency
    amount = abs(profile.amount_parser(text))
    return round(amount, 2), profile.currency if amount > 0 else ""


def _extract_list_items(
    *,
    order_el: Tag,
    profile: AmazonCountryProfile,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_asins: set[str] = set()
    selectors = profile.selector_bundle.order_list.product_link_selectors
    title_selectors = profile.selector_bundle.order_list.product_title_selectors
    for selector in selectors:
        for link in order_el.select(selector):
            href = str(link.get("href", "") or "")
            asin = extract_asin_from_url(href)
            if not asin or asin in seen_asins:
                continue
            seen_asins.add(asin)
            title = normalize_text(link.get_text(strip=True))
            if not title:
                for title_selector in title_selectors:
                    title_el = link.select_one(title_selector)
                    if title_el is not None:
                        title = normalize_text(title_el.get_text(strip=True))
                        if title:
                            break
            items.append(
                {
                    "title": title or f"Amazon item {asin}",
                    "asin": asin,
                    "quantity": 1,
                    "price": 0,
                    "discount": 0,
                    "itemUrl": profile.item_url(asin),
                }
            )
    return items


def _parse_detail_item(
    *,
    row: Tag,
    profile: AmazonCountryProfile,
) -> dict[str, Any] | None:
    title = ""
    asin = ""
    price = 0.0
    qty = 1
    seller = ""
    discount = 0.0

    link = _select_one_within(container=row, selectors=profile.selector_bundle.detail.title_link_selectors)
    if link is not None:
        href = str(link.get("href", "") or "")
        asin = extract_asin_from_url(href)
        title = (
            normalize_text(link.get_text(strip=True))
            or str(link.get("title", ""))
            or str(link.get("aria-label", ""))
        )

    if not title:
        fallback = _select_one_within(
            container=row,
            selectors=profile.selector_bundle.detail.title_fallback_selectors,
        )
        if fallback is not None:
            title = normalize_text(fallback.get_text(strip=True))

    price_el = _select_one_within(container=row, selectors=profile.selector_bundle.detail.price_selectors)
    if price_el is not None:
        price = abs(profile.amount_parser(price_el.get_text(strip=True)))

    row_text = normalize_text(row.get_text(" ", strip=True))
    qty = parse_qty_from_text(row_text)
    discount = parse_item_discount_from_text(row_text, profile=profile)

    seller_el = _select_one_within(container=row, selectors=profile.selector_bundle.detail.seller_selectors)
    if seller_el is not None:
        seller_text = normalize_text(seller_el.get_text(strip=True))
        seller = seller_text if any(marker in seller_text.lower() for marker in ("verkauft", "sold", "vendu")) else ""

    if not title and not asin:
        return None

    return {
        "title": title or f"Amazon item {asin}",
        "asin": asin,
        "price": price,
        "qty": qty,
        "seller": seller,
        "discount": discount,
    }


def _select_first_nonempty(*, soup: BeautifulSoup, selectors: tuple[str, ...]) -> list[Tag]:
    for selector in selectors:
        nodes = [node for node in soup.select(selector) if isinstance(node, Tag)]
        if nodes:
            return nodes
    return []


def _select_first_nonempty_within(*, container: Tag, selectors: tuple[str, ...]) -> list[Tag]:
    for selector in selectors:
        nodes = [node for node in container.select(selector) if isinstance(node, Tag)]
        if nodes:
            return nodes
    return []


def _select_one_within(*, container: Tag, selectors: tuple[str, ...]) -> Tag | None:
    for selector in selectors:
        node = container.select_one(selector)
        if isinstance(node, Tag):
            return node
    return None
