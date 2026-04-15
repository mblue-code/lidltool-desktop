from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from lidltool.amazon.profiles import AmazonCountryProfile

AmazonParseStatus = Literal["complete", "partial", "unsupported"]

_SPLIT_LINES_RE = re.compile(r"\s*\n+\s*")
_ORDER_ID_RE = re.compile(r"[A-Z0-9]{3}-\d{7}-\d{7}", re.IGNORECASE)
_ORDER_ID_FROM_URL_RE = re.compile(r"orderI[Dd]=([A-Z0-9]{3}-\d{7}-\d{7})", re.IGNORECASE)
_ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$|\?)", re.IGNORECASE)
_ITEM_QTY_PATTERNS = (
    re.compile(r"(?i)(?:menge|qty|quantity|anzahl|quantit[ée])\s*[:x]?\s*(\d+)"),
)
_ITEM_DISCOUNT_PATTERNS = (
    re.compile(r"(?i)(?:spar(?:en|abo)?|rabatt|discount|coupon|gutschein|nachlass|ersparnis)[^\n]{0,100}?([0-9]+[.,][0-9]{2})"),
    re.compile(r"(?i)(?:r[ée]duction|remise|coupon|[ée]conomie)[^\n]{0,100}?([0-9]+[.,][0-9]{2})"),
)
_PACK_COUNT_PATTERNS = (
    re.compile(r"(?i)\b(\d+)\s*[x×]\s*\d+(?:[.,]\d+)?\s*(?:ml|cl|l)\b"),
    re.compile(r"(?i)\b(\d+)\s*[x×]\b"),
)
_DEPOSIT_CONTAINER_MARKERS = (
    "dose",
    "dosen",
    "can",
    "cans",
    "flasche",
    "flaschen",
    "bottle",
    "bottles",
)
_DETAIL_QTY_SELECTORS = (
    ".od-item-view-qty span",
    "[class*='item-view-qty'] span",
)
_DETAIL_SUMMARY_TITLE_MARKERS = (
    "summe der erstattung",
    "erstattung für artikel",
    "erstattung",
    "steuererstattung",
    "refund total",
    "refund for item",
    "refund",
    "tax refund",
    "total du remboursement",
    "remboursement",
)
_REFUND_SUBTOTAL_TITLE_MARKERS = (
    "summe der erstattung",
    "erstattung für artikel",
    "steuererstattung",
    "refund total",
    "refund for item",
    "tax refund",
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
            allowed_reasons=("canceled_only",),
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
    order_date = _extract_detail_order_date(soup=soup, profile=profile)
    promotions = [
        {
            "description": entry["label"],
            "amount": abs(float(entry["amount"])),
            "category": entry["category"],
        }
        for entry in subtotal_entries
        if entry["category"]
        not in {
            "shipping",
            "gift_wrap",
            "free_shipping",
            "subtotal",
            "pre_tax_total",
            "tax",
            "order_total",
            "refund_info",
        }
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
    inferred_deposit = _infer_hidden_deposit_item(
        items=collapsed_items,
        subtotal_entries=subtotal_entries,
        shipping=shipping,
        gift_wrap=gift_wrap,
        profile=profile,
    )
    if inferred_deposit is not None:
        collapsed_items.append(inferred_deposit)
    order_total = _detail_order_total(subtotal_entries)

    detail_text = normalize_text(
        " ".join(
            part
            for part in [
                *(box.get_text(" ", strip=True) for box in shipment_boxes),
                *(str(entry.get("label") or "") for entry in subtotal_entries),
            ]
            if part
        )
    )
    text = detail_text or normalize_text(soup.get_text(" ", strip=True))
    unsupported_reason = classify_unsupported_order(
        text=text,
        status=text,
        items=collapsed_items,
        profile=profile,
        allowed_reasons=("canceled_only",),
    )
    parse_status: AmazonParseStatus = (
        "unsupported" if unsupported_reason else "partial" if warnings else "complete"
    )

    return AmazonParseResult(
        data={
            "items": collapsed_items,
            "orderDate": order_date,
            "promotions": promotions,
            "shipping": round(shipping, 2),
            "gift_wrap": round(gift_wrap, 2),
            "totalAmount": order_total,
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
        if any(marker in lowered for marker in _REFUND_SUBTOTAL_TITLE_MARKERS):
            continue
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

    rows: list[Tag] = []
    for container in containers:
        rows.extend(
            _select_first_nonempty_within(
                container=container,
                selectors=profile.selector_bundle.detail.subtotal_row_selectors,
            )
        )
    if not rows:
        rows = [node for node in soup.select(".od-line-item-row") if isinstance(node, Tag)]

    for row in rows:
        label_text = _subtotal_label_text(row)
        amount_node = _subtotal_amount_node(row=row, profile=profile)
        if amount_node is None:
            continue
        amount = parse_signed_amount(amount_node.get_text(" ", strip=True), profile=profile)
        category = _classify_detail_summary_kind(text=label_text, profile=profile)
        if amount == 0 and category not in {"shipping", "gift_wrap", "free_shipping", "order_total"}:
            continue
        key = (label_text.lower(), round(amount, 2), category)
        if key in seen:
            continue
        seen.add(key)
        subtotals.append(
            {
                "label": label_text[:120],
                "amount": round(amount, 2),
                "category": category,
            }
        )
    return subtotals


def collapse_detail_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, float, str, bool], dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        asin = str(raw.get("asin") or "").strip().upper()
        title = normalize_text(str(raw.get("title") or ""))
        seller = normalize_text(str(raw.get("seller") or ""))
        price = float(raw.get("price") or 0)
        discount = float(raw.get("discount") or 0)
        qty = to_positive_int(raw.get("qty"), default=1)
        is_deposit = bool(raw.get("isDeposit") or raw.get("is_deposit"))
        category = normalize_text(str(raw.get("category") or ""))
        key = (asin, title.lower(), round(price, 2), seller.lower(), is_deposit)
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
        if is_deposit:
            row["isDeposit"] = True
        if category:
            row["category"] = category
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
    if bool(detail.get("isDeposit")):
        out["isDeposit"] = True
    category = normalize_text(str(detail.get("category") or ""))
    if category:
        out["category"] = category
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
        if not merged_item.get("category") and isinstance(base.get("category"), str):
            merged_item["category"] = base["category"]
        if not merged_item.get("isDeposit") and bool(base.get("isDeposit")):
            merged_item["isDeposit"] = True
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
    if any(marker in lowered for marker in _REFUND_SUBTOTAL_TITLE_MARKERS):
        return "refund_info"
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
    allowed_reasons: tuple[str, ...] | None = None,
) -> str | None:
    lowered = f"{text} {status}".lower()
    allowed = set(allowed_reasons) if allowed_reasons is not None else None
    for rule in profile.unsupported_order_rules:
        if allowed is not None and rule.reason not in allowed:
            continue
        if any(marker in lowered for marker in rule.markers):
            if rule.reason == "canceled_only" and items:
                if any(
                    marker in lowered
                    for marker in (
                        "nicht in rechnung gestellt",
                        "not billed",
                        "not charged",
                        "pas été facturée",
                        "pas ete facturee",
                    )
                ):
                    return rule.reason
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


def _extract_pack_count(text: str) -> int:
    normalized = normalize_text(text)
    for pattern in _PACK_COUNT_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        return to_positive_int(match.group(1), default=0)
    return 0


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


def _extract_detail_order_date(*, soup: BeautifulSoup, profile: AmazonCountryProfile) -> str:
    text = normalize_text(soup.get_text(" ", strip=True))
    for pattern in profile.detail_date_patterns:
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
    lowered = text.lower()
    if not any(marker in lowered for marker in ("€", "eur", "£", "gbp")):
        return 0.0, ""
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
    row_classes = set(row.get("class", []))
    if {"od-line-item-row-content", "od-line-item-row-label"} & row_classes:
        return None

    title = ""
    asin = ""
    price = 0.0
    qty = 1
    seller = ""
    discount = 0.0

    asin, title = _extract_detail_link_data(row=row, profile=profile)

    if not title:
        title = _extract_detail_fallback_title(row=row, profile=profile)

    price_el = _select_one_within(container=row, selectors=profile.selector_bundle.detail.price_selectors)
    if price_el is not None:
        price = abs(profile.amount_parser(price_el.get_text(strip=True)))

    row_text = normalize_text(row.get_text(" ", strip=True))
    title_text = normalize_text(title)
    qty_text = row_text
    if title_text:
        qty_text = normalize_text(qty_text.replace(title_text, " "))
    qty = _extract_detail_qty(row=row) or parse_qty_from_text(qty_text)
    discount = parse_item_discount_from_text(row_text, profile=profile)

    seller_el = _select_one_within(container=row, selectors=profile.selector_bundle.detail.seller_selectors)
    if seller_el is not None:
        seller_text = normalize_text(seller_el.get_text(strip=True))
        seller = seller_text if any(marker in seller_text.lower() for marker in ("verkauft", "sold", "vendu")) else ""

    if not title and not asin:
        return None
    if _looks_like_detail_summary_row(title=title_text, asin=asin, row_text=row_text, profile=profile):
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


def _extract_detail_qty(*, row: Tag) -> int | None:
    for selector in _DETAIL_QTY_SELECTORS:
        node = row.select_one(selector)
        if not isinstance(node, Tag):
            continue
        qty = to_positive_int(normalize_text(node.get_text(" ", strip=True)), default=0)
        if qty > 0:
            return qty
    return None


def _extract_detail_link_data(
    *,
    row: Tag,
    profile: AmazonCountryProfile,
) -> tuple[str, str]:
    best_asin = ""
    best_title = ""
    best_score = (-1, -1)
    for selector in profile.selector_bundle.detail.title_link_selectors:
        links = [node for node in row.select(selector) if isinstance(node, Tag)]
        if not links:
            continue
        for link in links:
            href = str(link.get("href", "") or "")
            candidate_asin = extract_asin_from_url(href)
            candidate_title = _extract_detail_link_title(link)
            score = (1 if candidate_asin else 0, len(candidate_title))
            if score > best_score:
                best_asin = candidate_asin
                best_title = candidate_title
                best_score = score
        if best_score[0] > 0 and best_score[1] > 0:
            break
    return best_asin, best_title


def _extract_detail_link_title(link: Tag) -> str:
    text = normalize_text(link.get_text(" ", strip=True))
    if text:
        return text
    for attr in ("title", "aria-label"):
        value = normalize_text(str(link.get(attr, "") or ""))
        if value:
            return value
    image = link.find("img")
    if isinstance(image, Tag):
        alt = normalize_text(str(image.get("alt", "") or ""))
        if alt:
            return alt
    return ""


def _extract_detail_fallback_title(
    *,
    row: Tag,
    profile: AmazonCountryProfile,
) -> str:
    best_title = ""
    for selector in profile.selector_bundle.detail.title_fallback_selectors:
        nodes = [node for node in row.select(selector) if isinstance(node, Tag)]
        if not nodes:
            continue
        for node in nodes:
            candidate = _extract_detail_link_title(node)
            if not candidate:
                candidate = normalize_text(node.get_text(" ", strip=True))
            if len(candidate) > len(best_title):
                best_title = candidate
        if best_title:
            break
    return best_title


def _detail_order_totals(subtotal_entries: list[dict[str, Any]]) -> list[float]:
    totals: list[float] = []
    for entry in subtotal_entries:
        if entry.get("category") != "order_total":
            continue
        try:
            amount = float(entry.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if amount > 0:
            totals.append(round(amount, 2))
    return totals


def _deposit_line_title(profile: AmazonCountryProfile) -> str:
    if profile.country_code == "DE":
        return "Einwegpfand"
    if profile.country_code == "FR":
        return "Consigne"
    return "Deposit"


def _infer_hidden_deposit_item(
    *,
    items: list[dict[str, Any]],
    subtotal_entries: list[dict[str, Any]],
    shipping: float,
    gift_wrap: float,
    profile: AmazonCountryProfile,
) -> dict[str, Any] | None:
    order_totals = _detail_order_totals(subtotal_entries)
    if not items or not order_totals:
        return None

    pre_discount_total_cents = int(round(max(order_totals) * 100))
    visible_item_total_cents = 0
    inferred_deposit_cents = 0
    for item in items:
        if bool(item.get("isDeposit")):
            continue
        qty = to_positive_int(item.get("qty"), default=1)
        price_cents = int(round(float(item.get("price") or 0) * 100))
        discount_cents = int(round(float(item.get("discount") or 0) * 100))
        visible_item_total_cents += max(0, price_cents * qty - discount_cents)

        title = normalize_text(str(item.get("title") or "")).lower()
        pack_count = _extract_pack_count(title)
        if pack_count <= 0:
            continue
        if not any(marker in title for marker in _DEPOSIT_CONTAINER_MARKERS):
            continue
        inferred_deposit_cents += 25 * pack_count * qty

    hidden_charge_cents = pre_discount_total_cents - visible_item_total_cents
    hidden_charge_cents -= int(round(shipping * 100))
    hidden_charge_cents -= int(round(gift_wrap * 100))
    if hidden_charge_cents <= 0 or inferred_deposit_cents <= 0:
        return None
    if abs(hidden_charge_cents - inferred_deposit_cents) > 1:
        return None

    return {
        "title": _deposit_line_title(profile),
        "asin": "",
        "price": round(hidden_charge_cents / 100.0, 2),
        "qty": 1,
        "seller": "",
        "discount": 0.0,
        "isDeposit": True,
        "category": "deposit",
    }


def _looks_like_detail_summary_row(
    *,
    title: str,
    asin: str,
    row_text: str,
    profile: AmazonCountryProfile,
) -> bool:
    normalized_title = normalize_text(title)
    if not normalized_title or asin:
        return False
    lowered = normalized_title.lower().rstrip(":")
    if any(marker in lowered for marker in _DETAIL_SUMMARY_TITLE_MARKERS):
        return True
    if lowered in {
        "gesamtsumme",
        "summe",
        "gesamt vor ust.",
        "gesamt vor ust",
        "zwischensumme",
        "total",
        "subtotal",
        "sous-total",
        "total de la commande",
    }:
        return True
    normalized_row = normalize_text(row_text).lower()
    if normalized_row.startswith(f"{lowered}:"):
        return True
    if any(marker in lowered for marker, _ in profile.subtotal_label_map) and len(normalized_title) <= 40:
        return True
    amount = abs(profile.amount_parser(normalized_title))
    if amount > 0 and normalized_title.replace("\xa0", " ").strip().endswith(("€", "£", "eur", "gbp")):
        return True
    return False


def _subtotal_label_text(row: Tag) -> str:
    label_container = row.select_one(".od-line-item-row-label")
    if isinstance(label_container, Tag):
        return normalize_text(label_container.get_text(" ", strip=True))
    return normalize_text(row.get_text(" ", strip=True))


def _subtotal_amount_node(*, row: Tag, profile: AmazonCountryProfile) -> Tag | None:
    content = row.select_one(".od-line-item-row-content")
    if isinstance(content, Tag):
        candidates = [
            node
            for node in content.find_all(["span", "div"], recursive=True)
            if isinstance(node, Tag) and profile.amount_parser(node.get_text(" ", strip=True)) != 0
        ]
        if candidates:
            return candidates[-1]
        if profile.amount_parser(content.get_text(" ", strip=True)) == 0:
            zero_candidates = [
                node
                for node in content.find_all(["span", "div"], recursive=True)
                if isinstance(node, Tag)
                and normalize_text(node.get_text(" ", strip=True)).replace("\xa0", " ").strip().endswith(("€", "£"))
            ]
            if zero_candidates:
                return zero_candidates[-1]
        return content

    return _select_one_within(container=row, selectors=profile.selector_bundle.detail.subtotal_amount_selectors)


def _classify_detail_summary_kind(*, text: str, profile: AmazonCountryProfile) -> str:
    lowered = normalize_text(text).lower().rstrip(":")
    if lowered in {
        "gesamtsumme",
        "summe",
        "gesamtbetrag für diese bestellung",
        "total",
        "total de la commande",
    }:
        return "order_total"
    if lowered in {"zwischensumme", "artikel-zwischensumme", "artikel zwischensumme", "subtotal", "sous-total"}:
        return "subtotal"
    if lowered in {
        "gesamt vor ust.",
        "gesamt vor ust",
        "summe ohne mwst.",
        "summe ohne mwst",
        "gesamtbetrag vor steuern",
        "total avant tva",
        "total before vat",
    }:
        return "pre_tax_total"
    if lowered in {"anzurechnende mwst.", "anzurechnende mwst", "geschätzte ust.", "estimated vat"}:
        return "tax"
    if "ust" in lowered or "mwst" in lowered or lowered == "vat":
        return "tax"
    return classify_subtotal_label(text=text, profile=profile)


def _detail_order_total(entries: list[dict[str, Any]]) -> float | None:
    for entry in reversed(entries):
        if entry.get("category") == "order_total":
            return abs(float(entry.get("amount") or 0))
    return None
