from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import BrowserContext, sync_playwright


class AmazonClientError(RuntimeError):
    pass


class AmazonReauthRequiredError(AmazonClientError):
    pass


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

REAUTH_URL_PATTERNS = ["/ap/signin", "authportal", "/ap/cvf/", "/ap/mfa"]
REAUTH_HTML_MARKERS = ['id="auth-supertask-header"', 'name="signIn"']


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
    asin = str(detail.get("asin") or "").strip().upper()
    title = _normalize_text(str(detail.get("title") or "")) or f"Amazon item {asin}"
    quantity = _to_positive_int(detail.get("qty", detail.get("quantity", 1)), default=1)
    price = float(detail.get("price") or 0)
    discount = float(detail.get("discount") or 0)
    item_url = f"https://www.amazon.de/dp/{asin}" if asin else ""
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
) -> list[dict[str, Any]]:
    if not detail_items:
        return list_items
    detail_rows = [_detail_to_order_item(d) for d in _collapse_detail_items(detail_items)]
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

    const detailsLink = orderEl.querySelector(
      "a[href*='order-details'], a[href*='orderID='], a[href*='orderId=']"
    );
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
      /(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})/i
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
        headless: bool = True,
        page_delay_ms: int = 800,
        dump_html_dir: Path | None = None,
    ) -> None:
        self._state_file = state_file
        self._domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
        self._headless = headless
        self._page_delay_ms = page_delay_ms
        self._dump_html_dir = dump_html_dir

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int = 8) -> list[dict[str, Any]]:
        if not self._state_file.exists():
            raise AmazonReauthRequiredError(
                f"Amazon session state missing: {self._state_file}. "
                "Run 'lidltool amazon auth bootstrap' first."
            )

        seen_order_ids: set[str] = set()
        out: list[dict[str, Any]] = []
        current_year = datetime.now().year

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self._headless)
            context = browser.new_context(storage_state=str(self._state_file))
            page = context.new_page()
            self._ensure_logged_in(page)

            for offset in range(max(1, years)):
                year = current_year - offset
                year_any = False
                for page_idx in range(max(1, max_pages_per_year)):
                    start_idx = page_idx * 10
                    url = (
                        f"https://www.{self._domain}/gp/your-account/order-history"
                        f"?timeFilter=year-{year}"
                    )
                    if start_idx:
                        url += f"&startIndex={start_idx}"
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_timeout(self._page_delay_ms)
                    self._ensure_logged_in(page)

                    if self._dump_html_dir is not None:
                        self._dump_html_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"order_list_y{year}_p{page_idx}.html"
                        (self._dump_html_dir / fname).write_text(
                            page.content(), encoding="utf-8"
                        )

                    page_orders = page.evaluate(_SCRAPE_ORDERS_SCRIPT)
                    if not isinstance(page_orders, list):
                        page_orders = []

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
                        seen_order_ids.add(order_id)
                        self._enrich_order_from_details(context, row)
                        out.append(row)
                        page_new += 1

                    if page_new == 0:
                        break

                    if page_new > 0:
                        year_any = True
                    has_next = bool(page.evaluate(_HAS_NEXT_PAGE_SCRIPT))
                    if not has_next:
                        break
                if not year_any and offset > 0:
                    continue

            context.close()
            browser.close()

        return out

    def _ensure_logged_in(self, page: Any) -> None:
        url = str(page.url)
        if any(p in url for p in REAUTH_URL_PATTERNS):
            raise AmazonReauthRequiredError(
                "Amazon session expired or invalid. Run 'lidltool amazon auth bootstrap' again."
            )
        try:
            content = page.content()
        except Exception:
            return
        if any(m in content for m in REAUTH_HTML_MARKERS):
            raise AmazonReauthRequiredError(
                "Amazon session expired (auth wall detected). "
                "Run 'lidltool amazon auth bootstrap' again."
            )

    def _enrich_order_from_details(self, context: BrowserContext, order: dict[str, Any]) -> None:
        details_url = order.get("detailsUrl")
        if not isinstance(details_url, str) or not details_url:
            return
        try:
            response = context.request.get(details_url)
        except Exception:
            return
        if not response.ok:
            return
        html = response.text()
        if "/ap/signin" in html:
            return

        if self._dump_html_dir is not None:
            order_id = str(order.get("orderId", "unknown"))
            self._dump_html_dir.mkdir(parents=True, exist_ok=True)
            (self._dump_html_dir / f"order_detail_{order_id}.html").write_text(
                html, encoding="utf-8"
            )

        detail = _parse_order_detail_html(html)
        if detail["items"]:
            order["items"] = _merge_item_details(order.get("items") or [], detail["items"])
        if detail["promotions"]:
            order["promotions"] = detail["promotions"]
            order["totalSavings"] = round(
                sum(float(p["amount"]) for p in detail["promotions"]), 2
            )
        if detail["shipping"] > 0:
            order["shipping"] = detail["shipping"]
        if detail["gift_wrap"] > 0:
            order["gift_wrap"] = detail["gift_wrap"]


def _parse_promotions_from_details_html(html: str) -> list[dict[str, Any]]:
    plain = re.sub(r"<[^>]+>", " ", html)
    plain = re.sub(r"\s+", " ", plain)
    candidate_lines = _SPLIT_LINES_RE.split(plain)

    promotions: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for line in candidate_lines:
        if not line:
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
