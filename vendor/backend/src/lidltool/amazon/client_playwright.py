from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext, sync_playwright

from lidltool.amazon.auth_state import classify_amazon_auth_state, describe_auth_failure
from lidltool.amazon.profiles import (
    GERMANY_PROFILE,
    AmazonCountryProfile,
    get_country_profile,
)
from lidltool.amazon.session import default_amazon_profile_dir


class AmazonClientError(RuntimeError):
    pass


class AmazonReauthRequiredError(AmazonClientError):
    def __init__(self, message: str, *, auth_state: str | None = None) -> None:
        super().__init__(message)
        self.auth_state = auth_state


def _normalize_item_urls(
    items: list[dict[str, Any]],
    *,
    profile: AmazonCountryProfile,
) -> None:
    for item in items:
        if not isinstance(item, dict):
            continue
        asin = str(item.get("asin") or "").strip().upper()
        if asin:
            item["itemUrl"] = profile.item_url(asin)


def _looks_like_profile_in_use_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "processsingleton" in message
        or "singletonlock" in message
        or "user data directory is already in use" in message
        or "browsercontext.new_page" in message and "closed" in message
    )


_PROMO_RE = re.compile(
    r"(?i)(rabatt|nachlass|ersparnis|savings?|discount|coupon|gutschein)[^\n]{0,120}?"
    r"([0-9]+[.,][0-9]{2})"
)

_SPLIT_LINES_RE = re.compile(r"\s*\n+\s*")
_ITEM_QTY_PATTERNS = (
    re.compile(r"(?i)(?:menge|qty|anzahl)\s*[:x]?\s*(\d+)"),
    re.compile(r"(?i)\b(\d+)\s*[x×]\b"),
    re.compile(r"(?i)\b(\d+)\s*(?:stück|stk|pcs|pack)\b"),
)
_ITEM_DISCOUNT_RE = re.compile(
    r"(?i)(?:spar(?:en|abo)?|rabatt|discount|coupon|gutschein|nachlass|ersparnis)"
    r"[^\n]{0,100}?([0-9]+[.,][0-9]{2})"
)

_DE_MONTH_MAP: dict[str, int] = {
    "januar": 1, "jan": 1, "january": 1,
    "februar": 2, "feb": 2, "february": 2,
    "märz": 3, "mär": 3, "maerz": 3, "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "mai": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10, "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12, "december": 12, "dec": 12,
}
_INVOICE_URL_MARKERS = (
    "invoice",
    "tax-invoice",
    "taxinvoice",
    "pdf",
    "popover",
    "print",
    "download",
)
_PAYMENT_ADJUSTMENT_MARKERS = (
    "gift card",
    "giftcard",
    "gift-card",
    "refund summary",
    "refund",
    "payment adjustment",
    "payment summary",
    "balance",
    "reimbursement",
)


def _parse_amazon_de_date(text: str) -> datetime | None:
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), tzinfo=UTC)
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜß]+\.?)\s+(\d{4})", text)
    if m:
        month = _DE_MONTH_MAP.get(m.group(2).lower().rstrip("."))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=UTC)
            except ValueError:
                pass
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        month = _DE_MONTH_MAP.get(m.group(1).lower().rstrip("."))
        if month:
            try:
                return datetime(int(m.group(3)), month, int(m.group(2)), tzinfo=UTC)
            except ValueError:
                pass
    return None


def _parse_de_amount(text: str) -> float:
    cleaned = re.sub(r"(\d)\.(\d{3})", r"\1\2", text).replace(",", ".")
    m = re.search(r"(\d+\.?\d*)", cleaned)
    return float(m.group(1)) if m else 0.0


def _is_invoice_or_payment_route(href: str) -> bool:
    lowered = href.lower()
    return any(marker in lowered for marker in _INVOICE_URL_MARKERS)


def _is_order_details_href(href: str) -> bool:
    lowered = href.lower()
    return (
        ("order-details" in lowered or "orderid=" in lowered)
        and not _is_invoice_or_payment_route(lowered)
    )


def _looks_like_payment_adjustment_line(text: str) -> bool:
    lowered = _normalize_text(text).lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in _PAYMENT_ADJUSTMENT_MARKERS)


def _extract_asin_from_url(url: str) -> str:
    m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$|\?)", url, re.IGNORECASE)
    return m.group(1).upper() if m else ""


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _title_key(value: Any) -> str:
    return _normalize_text(str(value or "")).lower()


def _to_positive_int(value: Any, *, default: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _parse_qty_from_text(text: str) -> int:
    for pattern in _ITEM_QTY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        qty = _to_positive_int(match.group(1), default=0)
        if qty > 0:
            return qty
    return 1


def _parse_item_discount_from_text(text: str) -> float:
    match = _ITEM_DISCOUNT_RE.search(text)
    if not match:
        return 0.0
    amount = _parse_de_amount(match.group(1))
    return amount if amount > 0 else 0.0


def _collapse_detail_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collapsed: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, float, str], dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        asin = str(raw.get("asin") or "").strip().upper()
        title = _normalize_text(str(raw.get("title") or ""))
        seller = _normalize_text(str(raw.get("seller") or ""))
        price = float(raw.get("price") or 0)
        discount = float(raw.get("discount") or 0)
        qty = _to_positive_int(raw.get("qty"), default=1)
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


def _detail_to_order_item(detail: dict[str, Any]) -> dict[str, Any]:
    return _detail_to_order_item_for_profile(detail, profile=GERMANY_PROFILE)


def _detail_to_order_item_for_profile(
    detail: dict[str, Any],
    *,
    profile: AmazonCountryProfile,
) -> dict[str, Any]:
    asin = str(detail.get("asin") or "").strip().upper()
    title = _normalize_text(str(detail.get("title") or "")) or f"Amazon item {asin}"
    quantity = _to_positive_int(detail.get("qty", detail.get("quantity", 1)), default=1)
    price = float(detail.get("price") or 0)
    discount = float(detail.get("discount") or 0)
    item_url = profile.item_url(asin) if asin else ""
    out: dict[str, Any] = {
        "title": title,
        "asin": asin,
        "quantity": quantity,
        "price": price,
        "discount": discount,
        "itemUrl": item_url,
    }
    seller = _normalize_text(str(detail.get("seller") or ""))
    if seller:
        out["seller"] = seller
    return out


def _parse_order_detail_html(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict[str, Any]] = []
    promotions: list[dict[str, Any]] = []
    shipping = 0.0
    gift_wrap = 0.0

    shipment_selectors = [
        ".a-box.shipment",
        "[data-component='shipmentCard']",
        ".shipment",
        ".od-shipment",
    ]
    shipment_boxes: list[Tag] = []
    for sel in shipment_selectors:
        shipment_boxes = soup.select(sel)
        if shipment_boxes:
            break

    if not shipment_boxes:
        shipment_boxes = soup.select(".a-box-group")

    for box in shipment_boxes:
        item_rows = box.select(".a-fixed-left-grid-inner, .a-row.item-row, .yohtmlc-item")
        if not item_rows:
            item_rows = box.select("[class*='item']")

        for row in item_rows:
            if not isinstance(row, Tag):
                continue
            title = ""
            asin = ""
            price = 0.0
            qty = 1
            seller = ""
            discount = 0.0

            link = row.select_one("a[href*='/dp/'], a[href*='/gp/product/']")
            if link:
                href = link.get("href", "")
                if isinstance(href, list):
                    href = href[0] if href else ""
                asin = _extract_asin_from_url(href)
                title = (
                    link.get_text(strip=True)
                    or str(link.get("title", ""))
                    or str(link.get("aria-label", ""))
                )

            if not title:
                title_el = row.select_one(".a-link-normal, .a-text-bold, .yohtmlc-product-title")
                if title_el:
                    title = title_el.get_text(strip=True)

            price_el = row.select_one(".a-color-price, .a-price .a-offscreen, [class*='price']")
            if price_el:
                price = _parse_de_amount(price_el.get_text(strip=True))

            row_text = row.get_text(" ", strip=True)
            qty = _parse_qty_from_text(row_text)
            discount = _parse_item_discount_from_text(row_text)

            seller_el = row.select_one("[class*='seller'], .a-size-small")
            if seller_el:
                seller_text = seller_el.get_text(strip=True)
                if "verkauft" in seller_text.lower() or "sold" in seller_text.lower():
                    seller = seller_text

            if title or asin:
                items.append(
                    {
                        "title": _normalize_text(title) or f"Amazon item {asin}",
                        "asin": asin,
                        "price": price,
                        "qty": qty,
                        "seller": _normalize_text(seller),
                        "discount": discount,
                    }
                )

    subtotal_tables = soup.select(
        "#subtotals-marketplace-table, .a-spacing-mini.a-spacing-top-mini"
    )
    for table in subtotal_tables:
        rows = table.select("tr, .a-row")
        for row in rows:
            if not isinstance(row, Tag):
                continue
            text = row.get_text(" ", strip=True).lower()
            amount_el = row.select_one(".a-color-price, .a-text-right, td:last-child")
            if not amount_el:
                continue
            amount = _parse_de_amount(amount_el.get_text(strip=True))
            if _looks_like_payment_adjustment_line(text):
                continue
            if any(kw in text for kw in ["versand", "shipping", "lieferung", "delivery"]):
                shipping = amount
            elif any(kw in text for kw in ["geschenkverpackung", "gift wrap"]):
                gift_wrap = amount
            elif any(
                kw in text
                for kw in [
                    "rabatt",
                    "nachlass",
                    "ersparnis",
                    "discount",
                    "coupon",
                    "gutschein",
                    "savings",
                ]
            ):
                if amount > 0:
                    promotions.append({"description": text[:120], "amount": amount})

    if not promotions:
        promotions = _parse_promotions_from_details_html(html)

    return {
        "items": _collapse_detail_items(items),
        "promotions": promotions,
        "shipping": shipping,
        "gift_wrap": gift_wrap,
    }


def _merge_item_details(
    list_items: list[dict[str, Any]],
    detail_items: list[dict[str, Any]],
    *,
    profile: AmazonCountryProfile = GERMANY_PROFILE,
) -> list[dict[str, Any]]:
    if not detail_items:
        return list_items
    detail_rows = [
        _detail_to_order_item_for_profile(d, profile=profile)
        for d in _collapse_detail_items(detail_items)
    ]
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
        title_key = _title_key(raw.get("title"))
        if title_key:
            by_title.setdefault(title_key, []).append(idx)

    matched_indexes: set[int] = set()
    merged: list[dict[str, Any]] = []

    def _find_match(row: dict[str, Any]) -> int | None:
        asin = str(row.get("asin") or "").strip().upper()
        for idx in by_asin.get(asin, []):
            if idx not in matched_indexes:
                return idx
        title_key = _title_key(row.get("title"))
        for idx in by_title.get(title_key, []):
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
            merged_item["quantity"] = _to_positive_int(base.get("quantity"), default=1)
        if float(detail.get("discount") or 0) <= 0 and isinstance(base.get("discount"), (int, float)):
            merged_item["discount"] = float(base["discount"])
        if not merged_item.get("itemUrl") and isinstance(base.get("itemUrl"), str):
            merged_item["itemUrl"] = base["itemUrl"]
        merged.append(merged_item)

    seen_keys = {
        (str(row.get("asin") or "").strip().upper(), _title_key(row.get("title"))) for row in merged
    }
    for idx, raw in enumerate(list_items):
        if idx in matched_indexes or not isinstance(raw, dict):
            continue
        key = (str(raw.get("asin") or "").strip().upper(), _title_key(raw.get("title")))
        if key in seen_keys:
            continue
        merged.append(raw)

    return merged


_SCRAPE_ORDERS_SCRIPT = r"""
() => {
  const toAmountCurrency = (text) => {
    const cleaned = text.replace(/(\d)\.(\d{3})/g, '$1$2').replace(',', '.');
    const patterns = [
      /([0-9]+\.?[0-9]*)\s*(EUR|€)/i,
      /(EUR|€)\s*([0-9]+\.?[0-9]*)/i,
      /([0-9]+\.[0-9]{2})/
    ];
    for (const p of patterns) {
      const m = cleaned.match(p);
      if (m) {
        const amountRaw = (m[1] && /[0-9]/.test(m[1])) ? m[1] : (m[2] || "0");
        const currencyRaw = (m[2] && /[A-Z€]/i.test(m[2])) ? m[2] : (m[1] || "EUR");
        const amount = Number(amountRaw);
        const currency = (currencyRaw === "€") ? "EUR" : currencyRaw.toUpperCase();
        if (Number.isFinite(amount)) {
          return { amount, currency };
        }
      }
    }
    return { amount: 0, currency: "EUR" };
  };

  const extractOrderId = (text) => {
    const m = text.match(/\d{3}-\d{7}-\d{7}/);
    return m ? m[0] : "";
  };

  const extractOrderIdFromUrl = (url) => {
    const m = url.match(/orderI[Dd]=(\d{3}-\d{7}-\d{7})/);
    return m ? m[1] : "";
  };

  const extractAsin = (url) => {
    const m = url.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:\/|$|\?)/i);
    return m ? m[1].toUpperCase() : "";
  };

  const orderSelectors = [
    ".order-card",
    ".order",
    "[data-component='orderCard']",
    ".a-box-group.order",
    ".your-orders-content-container .a-box-group",
    "#ordersContainer .order-card",
    ".js-order-card",
    "[class*='order-card']"
  ];

  let orderNodes = [];
  for (const selector of orderSelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    if (nodes.length > 0) {
      orderNodes = nodes;
      break;
    }
  }

  if (orderNodes.length === 0) {
    const orderIdPattern = /\d{3}-\d{7}-\d{7}/;
    const candidates = new Set();
    for (const el of Array.from(document.querySelectorAll("*"))) {
      const txt = el.textContent || "";
      if (!orderIdPattern.test(txt)) {
        continue;
      }
      let parent = el;
      for (let i = 0; i < 10 && parent && parent.parentElement; i++) {
        parent = parent.parentElement;
        if (
          parent.classList.contains("a-box") ||
          parent.classList.contains("a-box-group") ||
          (parent.tagName === "DIV" && parent.children.length > 3)
        ) {
          candidates.add(parent);
          break;
        }
      }
    }
    orderNodes = Array.from(candidates);
  }

  const out = [];
  for (const orderEl of orderNodes) {
    const text = (orderEl.textContent || "").replace(/\s+/g, " ").trim();
    let orderId = extractOrderId(text);
    let detailsUrl = "";

    const detailsLink = Array.from(orderEl.querySelectorAll("a[href]")).find((link) => {
      const href = link.href || "";
      return href && /order-details|orderid=/i.test(href) && !/invoice|tax-invoice|taxinvoice|pdf|popover|print|download/i.test(href);
    });
    if (detailsLink && detailsLink.href) {
      detailsUrl = detailsLink.href;
      if (!orderId) {
        orderId = extractOrderIdFromUrl(detailsUrl);
      }
    }

    if (!orderId) {
      continue;
    }

    let orderDate = "";
    const datePatterns = [
      /(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\s*[A-Za-zäöüÄÖÜß]+\.?\s+\d{4})/i,
      /(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\d{1,2}\.\d{4})/i,
      /(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\s*[A-Za-zäöüÄÖÜß]+\.?)/i,
      /(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\d{1,2}\.)/i,
      /(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i,
      /(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?)/i
    ];
    for (const p of datePatterns) {
      const m = text.match(p);
      if (m && m[1]) {
        orderDate = m[1];
        break;
      }
    }

    const amt = toAmountCurrency(text);
    let status = "";
    const statusPatterns = [
      /(?:Zugestellt|Geliefert)\s*(?:am)?\s*[\d.\s\w]*/i,
      /(?:Delivered|Arriving|Shipped)\s*[\w\s,\d]*/i,
      /(?:Storniert|Cancelled|Returned|Refunded)/i
    ];
    for (const p of statusPatterns) {
      const m = text.match(p);
      if (m && m[0]) {
        status = m[0].trim().slice(0, 60);
        break;
      }
    }

    const items = [];
    const seenAsins = new Set();
    const productLinks = orderEl.querySelectorAll("a[href*='/dp/'], a[href*='/gp/product/']");
    for (const link of productLinks) {
      const href = link.getAttribute("href") || link.href || "";
      const asin = extractAsin(href);
      if (!asin || seenAsins.has(asin)) {
        continue;
      }
      seenAsins.add(asin);
      const title = (
        (link.textContent || "").trim() ||
        (link.getAttribute("title") || "") ||
        (link.getAttribute("aria-label") || "")
      ).replace(/\s+/g, " ").trim();
      items.push({
        title: title || `Amazon item ${asin}`,
        asin,
        quantity: 1,
        price: 0,
        discount: 0,
        itemUrl: `https://www.amazon.de/dp/${asin}`
      });
    }

    out.push({
      orderId,
      orderDate,
      totalAmount: amt.amount,
      currency: amt.currency || "EUR",
      items,
      orderStatus: status,
      detailsUrl,
      promotions: [],
      totalSavings: 0
    });
  }
  return out;
}
"""

_HAS_NEXT_PAGE_SCRIPT = r"""
() => {
  const selectors = [
    ".a-pagination .a-last:not(.a-disabled) a",
    "a[aria-label*='Nächste']",
    "a[aria-label*='Next']",
    ".a-pagination li:last-child:not(.a-disabled) a",
    "a.a-last:not(.a-disabled)"
  ];
  return selectors.some((s) => document.querySelector(s) !== null);
}
"""


class AmazonPlaywrightClient:
    def __init__(
        self,
        *,
        state_file: Path,
        domain: str = "amazon.de",
        source_id: str = "amazon_de",
        profile_dir: Path | None = None,
        headless: bool = True,
        page_delay_ms: int = 800,
        dump_html_dir: Path | None = None,
        auth_interaction_timeout_s: int = 600,
    ) -> None:
        self._state_file = state_file.expanduser().resolve()
        self._profile = get_country_profile(
            source_id=source_id.strip() or None,
            domain=domain,
        )
        self._source_id = self._profile.source_id
        self._domain = self._profile.normalized_domain()
        self._profile_dir = (
            profile_dir.expanduser().resolve()
            if profile_dir is not None
            else default_amazon_profile_dir(source_id=self._source_id)
        )
        self._headless = headless
        self._page_delay_ms = page_delay_ms
        self._dump_html_dir = dump_html_dir.expanduser().resolve() if dump_html_dir else None
        self._auth_interaction_timeout_s = max(30, int(auth_interaction_timeout_s))

    @property
    def profile(self) -> AmazonCountryProfile:
        return self._profile

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def domain(self) -> str:
        return self._domain

    def fetch_orders(
        self,
        *,
        years: int = 2,
        max_pages_per_year: int = 8,
        max_pages: int | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        return list(
            self.iter_orders(
                years=years,
                max_pages_per_year=max_pages_per_year,
                max_pages=max_pages,
                progress_cb=progress_cb,
            )
        )

    def iter_orders(
        self,
        *,
        years: int = 2,
        max_pages_per_year: int = 8,
        max_pages: int | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
        ) -> Iterator[dict[str, Any]]:
        if not self._session_artifact_exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                f"Run 'lidltool connectors auth bootstrap --source-id {self._source_id}' first.",
                auth_state="expired_session",
            )

        seen_order_ids: set[str] = set()
        current_year = datetime.now().year
        pages_visited = 0

        with sync_playwright() as playwright:
            context, browser = self._open_authenticated_context(playwright=playwright)
            page = self._open_work_page(context)

            try:
                for offset in range(max(1, years)):
                    year = current_year - offset
                    year_any = False
                    page_idx = 0
                    last_page_marker: tuple[str, tuple[str, ...]] | None = None

                    while True:
                        if max_pages is not None and pages_visited >= max(1, max_pages):
                            return
                        if max_pages_per_year is not None and page_idx >= max(1, max_pages_per_year):
                            break

                        start_idx = page_idx * 10
                        html = self._load_authenticated_html(
                            page=page,
                            context=context,
                            url=self._order_history_url(year=year, start_index=start_idx),
                        )
                        self._maybe_dump_html(html, f"order_list_y{year}_p{page_idx}.html")

                        page_orders = page.evaluate(_SCRAPE_ORDERS_SCRIPT)
                        if not isinstance(page_orders, list):
                            page_orders = []
                        for row in page_orders:
                            if isinstance(row, dict):
                                row.setdefault("sourceYear", year)

                        page_signature = tuple(
                            str(row.get("orderId") or "").strip()
                            for row in page_orders
                            if isinstance(row, dict) and str(row.get("orderId") or "").strip()
                        )
                        page_marker = (str(page.url), page_signature)
                        if page_signature and page_marker == last_page_marker:
                            break
                        last_page_marker = page_marker
                        pages_visited += 1
                        self._emit_progress(
                            progress_cb,
                            {
                                "pages": pages_visited,
                                "discovered_receipts": len(seen_order_ids),
                                "current_year": year,
                                "current_page": page_idx + 1,
                            },
                        )

                        if len(page_orders) == 0:
                            break

                        page_new = 0
                        for row in page_orders:
                            if not isinstance(row, dict):
                                continue
                            order_id = row.get("orderId")
                            if not isinstance(order_id, str) or not order_id:
                                continue
                            if order_id in seen_order_ids:
                                continue
                            if isinstance(row.get("items"), list):
                                _normalize_item_urls(row["items"], profile=self._profile)
                            seen_order_ids.add(order_id)
                            self._enrich_order_from_details(context, row)
                            self._emit_progress(
                                progress_cb,
                                {
                                    "pages": pages_visited,
                                    "discovered_receipts": len(seen_order_ids),
                                    "current_year": year,
                                    "current_page": page_idx + 1,
                                    "current_record_ref": order_id,
                                },
                            )
                            yield row
                            page_new += 1

                        if page_new == 0:
                            break

                        if page_new > 0:
                            year_any = True
                        has_next = bool(page.evaluate(_HAS_NEXT_PAGE_SCRIPT))
                        if not has_next:
                            break
                        page_idx += 1

                    if not year_any and offset > 0:
                        continue
            finally:
                context.close()
                if browser is not None:
                    browser.close()

    def validate_session(self) -> None:
        if not self._session_artifact_exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                f"Run 'lidltool connectors auth bootstrap --source-id {self._source_id}' first.",
                auth_state="expired_session",
            )

        with sync_playwright() as playwright:
            context, browser = self._open_authenticated_context(playwright=playwright)
            page = self._open_work_page(context)
            try:
                self._load_authenticated_html(
                    page=page,
                    context=context,
                    url=self._order_history_url(),
                )
            finally:
                context.close()
                if browser is not None:
                    browser.close()

    def _session_artifact_exists(self) -> bool:
        if self._profile_dir is not None and self._profile_dir.exists():
            try:
                next(self._profile_dir.iterdir())
            except StopIteration:
                pass
            else:
                return True
        return self._state_file.exists()

    def _open_authenticated_context(self, *, playwright: Any) -> tuple[Any, Any | None]:
        from lidltool.connectors.auth.browser_runtime import (
            launch_playwright_chromium,
            launch_playwright_chromium_persistent_context,
        )

        if self._profile_dir is not None and self._profile_dir.exists():
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=self._profile_dir,
                    headless=self._headless,
                )
                return context, None
            except Exception as exc:  # noqa: BLE001
                if not _looks_like_profile_in_use_error(exc) or not self._state_file.exists():
                    raise
                browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
                context = browser.new_context(storage_state=str(self._state_file))
                return context, browser

        browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
        context = browser.new_context(storage_state=str(self._state_file))
        return context, browser

    def _open_work_page(self, context: BrowserContext) -> Any:
        restored_pages = list(getattr(context, "pages", ()) or ())
        page = context.new_page()
        for restored_page in restored_pages:
            if restored_page is page:
                continue
            with suppress(Exception):
                restored_page.close()
        return page

    def _supports_interactive_auth_recovery(self) -> bool:
        return not self._headless and self._profile_dir is not None

    def _ensure_logged_in(self, page: Any) -> None:
        self._ensure_logged_in_html(
            url=str(getattr(page, "url", "")),
            html=self._page_content(page),
        )

    def _ensure_logged_in_html(self, *, url: str, html: str) -> None:
        classification = classify_amazon_auth_state(
            url=url,
            html=html,
            profile=self._profile,
            expect_authenticated_session=True,
        )
        if classification.authenticated:
            return
        raise AmazonReauthRequiredError(
            describe_auth_failure(source_id=self._source_id, classification=classification),
            auth_state=classification.state.value,
        )

    def _load_authenticated_html(
        self,
        *,
        page: Any,
        context: BrowserContext,
        url: str,
        retries: int = 1,
    ) -> str:
        last_error: AmazonReauthRequiredError | None = None
        for attempt in range(max(0, retries) + 1):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(self._page_delay_ms)
            html = self._page_content(page)
            try:
                self._ensure_logged_in_html(url=str(getattr(page, "url", url)), html=html)
            except AmazonReauthRequiredError as exc:
                last_error = exc
                if self._supports_interactive_auth_recovery():
                    return self._await_interactive_auth_resolution(
                        page=page,
                        context=context,
                        target_url=url,
                        original_error=exc,
                    )
                if attempt >= max(0, retries):
                    raise
                page.wait_for_timeout(self._page_delay_ms * 2)
                continue
            self._persist_storage_state(context)
            return html
        if last_error is not None:
            raise last_error
        raise AmazonClientError("failed to load authenticated Amazon page")

    def _await_interactive_auth_resolution(
        self,
        *,
        page: Any,
        context: BrowserContext,
        target_url: str,
        original_error: AmazonReauthRequiredError,
    ) -> str:
        print(
            "Amazon needs attention in the browser window. Complete sign-in, MFA, CAPTCHA, or any challenge to continue the import.",
            flush=True,
        )
        attempts = max(1, int((self._auth_interaction_timeout_s * 1000) / max(250, self._page_delay_ms)))
        last_html = ""
        for _ in range(attempts):
            page.wait_for_timeout(max(250, self._page_delay_ms))
            last_html = self._page_content(page)
            try:
                self._ensure_logged_in_html(url=str(getattr(page, "url", "")), html=last_html)
            except AmazonReauthRequiredError:
                continue
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(self._page_delay_ms)
            recovered_html = self._page_content(page)
            self._ensure_logged_in_html(url=str(getattr(page, "url", target_url)), html=recovered_html)
            self._persist_storage_state(context)
            print("Amazon challenge resolved. Continuing import.", flush=True)
            return recovered_html
        if last_html:
            self._maybe_dump_html(last_html, "session_probe_auth_attention_timeout.html")
        raise original_error

    def _enrich_order_from_details(self, context: BrowserContext, order: dict[str, Any]) -> None:
        details_url = order.get("detailsUrl")
        if not isinstance(details_url, str) or not details_url:
            self._mark_partial_order(order, "missing_details_url")
            return

        warnings: list[str] = []
        html: str | None = None
        try:
            response = context.request.get(details_url)
        except Exception:
            warnings.append("detail_request_failed")
        else:
            if getattr(response, "ok", False):
                try:
                    html = self._validated_detail_html(
                        url=str(getattr(response, "url", details_url) or details_url),
                        html=response.text(),
                    )
                except AmazonReauthRequiredError:
                    warnings.append("detail_request_auth_failed")
            else:
                warnings.append("detail_response_not_ok")

        if html is None:
            try:
                html = self._fetch_detail_html_via_page(context=context, details_url=details_url)
            except AmazonReauthRequiredError:
                warnings.append("detail_page_auth_failed")
            except Exception:
                warnings.append("detail_page_failed")

        if html is None:
            self._mark_partial_order(order, *warnings)
            return

        order_id = str(order.get("orderId", "unknown"))
        self._maybe_dump_html(html, f"order_detail_{order_id}.html")

        detail = _parse_order_detail_html(html)
        if detail["items"]:
            order["items"] = _merge_item_details(
                order.get("items") or [],
                detail["items"],
                profile=self._profile,
            )
        if detail["promotions"]:
            order["promotions"] = detail["promotions"]
            order["totalSavings"] = round(sum(float(p["amount"]) for p in detail["promotions"]), 2)
        if detail["shipping"] > 0:
            order["shipping"] = detail["shipping"]
        if detail["gift_wrap"] > 0:
            order["gift_wrap"] = detail["gift_wrap"]
        self._merge_parse_warnings(order, *warnings)

    def _validated_detail_html(self, *, url: str, html: str) -> str:
        self._ensure_logged_in_html(url=url, html=html)
        return html

    def _fetch_detail_html_via_page(self, *, context: BrowserContext, details_url: str) -> str:
        page = context.new_page()
        try:
            return self._load_authenticated_html(page=page, context=context, url=details_url)
        finally:
            with suppress(Exception):
                page.close()

    def _persist_storage_state(self, context: BrowserContext) -> None:
        storage_state = getattr(context, "storage_state", None)
        if not callable(storage_state):
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            storage_state(path=str(self._state_file))
        except Exception:
            return

    def _order_history_url(self, *, year: int | None = None, start_index: int = 0) -> str:
        return self._profile.order_history_url(year=year, start_index=start_index)

    def _page_content(self, page: Any) -> str:
        try:
            return str(page.content())
        except Exception:
            return ""

    def _maybe_dump_html(self, html: str, filename: str) -> None:
        if self._dump_html_dir is None:
            return
        self._dump_html_dir.mkdir(parents=True, exist_ok=True)
        (self._dump_html_dir / filename).write_text(html, encoding="utf-8")

    def _merge_parse_warnings(self, order: dict[str, Any], *warnings: str) -> None:
        existing = []
        for item in order.get("parseWarnings") or []:
            text = str(item).strip()
            if text:
                existing.append(text)
        merged: list[str] = []
        seen: set[str] = set()
        for value in (*existing, *warnings):
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
        if merged:
            order["parseWarnings"] = merged
            order["parseStatus"] = "partial"
        elif "parseWarnings" in order:
            order["parseWarnings"] = []

    def _mark_partial_order(self, order: dict[str, Any], *warnings: str) -> None:
        self._merge_parse_warnings(order, *warnings)
        if "parseStatus" not in order:
            order["parseStatus"] = "partial"

    def _emit_progress(self, progress_cb: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
        if progress_cb is None:
            return
        progress_cb(payload)


def _parse_promotions_from_details_html(html: str) -> list[dict[str, Any]]:
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain)
    candidate_lines = _SPLIT_LINES_RE.split(plain)

    promotions: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for line in candidate_lines:
        if not line:
            continue
        if _looks_like_payment_adjustment_line(line):
            continue
        for match in _PROMO_RE.finditer(line):
            amount_raw = match.group(2).replace(",", ".")
            try:
                amount = round(float(amount_raw), 2)
            except ValueError:
                continue
            if amount <= 0:
                continue
            desc = line.strip()
            key = (desc, amount)
            if key in seen:
                continue
            seen.add(key)
            promotions.append({"description": desc[:120], "amount": amount})
    return promotions
