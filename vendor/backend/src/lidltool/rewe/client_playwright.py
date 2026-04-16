from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright
from lidltool.connectors.auth.browser_runtime import (
    launch_playwright_chromium,
    wait_for_page_network_idle,
)


class ReweClientError(RuntimeError):
    pass


class ReweReauthRequiredError(ReweClientError):
    pass


_SCRAPE_ORDERS_SCRIPT = r"""
() => {
  const toAmount = (text) => {
    const patterns = [
      /([0-9]+[.,][0-9]{2})\s*(EUR|€)/i,
      /(EUR|€)\s*([0-9]+[.,][0-9]{2})/i,
      /([0-9]+[.,][0-9]{2})/
    ];
    for (const p of patterns) {
      const m = text.match(p);
      if (!m) {
        continue;
      }
      const raw = (m[1] && /[0-9]/.test(m[1])) ? m[1] : (m[2] || "0");
      const amount = Number(raw.replace(",", "."));
      if (Number.isFinite(amount)) {
        return amount;
      }
    }
    return 0;
  };

  const orderCards = Array.from(
    document.querySelectorAll(
      "[data-testid*='order'], [class*='order-card'], [class*='orderCard'], article, section"
    )
  );

  const rows = [];
  for (const card of orderCards) {
    const text = (card.textContent || "").replace(/\s+/g, " ").trim();
    if (!text) {
      continue;
    }
    if (!/bestellung|order|beleg|kauf/i.test(text)) {
      continue;
    }

    let orderId = "";
    const attrOrderId =
      card.getAttribute("data-order-id") ||
      card.getAttribute("data-orderid") ||
      card.getAttribute("data-testid");
    if (attrOrderId && /[A-Za-z0-9-]{8,}/.test(attrOrderId)) {
      orderId = attrOrderId.match(/[A-Za-z0-9-]{8,}/)[0];
    }
    if (!orderId) {
      const idMatch = text.match(/(?:Bestell(?:ung)?(?:snummer)?|Order(?:\\s*ID)?)[:#\\s-]*([A-Za-z0-9-]{8,})/i);
      if (idMatch && idMatch[1]) {
        orderId = idMatch[1];
      }
    }
    if (!orderId) {
      continue;
    }

    let orderDate = "";
    const dateEl = card.querySelector("time");
    if (dateEl) {
      orderDate = dateEl.getAttribute("datetime") || dateEl.textContent || "";
    }
    if (!orderDate) {
      const dateMatch = text.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})/);
      if (dateMatch && dateMatch[1]) {
        orderDate = dateMatch[1];
      }
    }

    let totalAmount = 0;
    const amountNode = card.querySelector("[data-testid*='total'], [class*='total']");
    if (amountNode && amountNode.textContent) {
      totalAmount = toAmount(amountNode.textContent);
    }
    if (!totalAmount) {
      totalAmount = toAmount(text);
    }

    const itemNodes = Array.from(
      card.querySelectorAll(
        "[data-testid*='item-name'], [class*='item-name'], [class*='product-name'], li, [class*='line-item']"
      )
    );
    const items = [];
    const seenNames = new Set();
    for (const node of itemNodes) {
      const name = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (!name || name.length < 2 || name.length > 120) {
        continue;
      }
      if (seenNames.has(name)) {
        continue;
      }
      seenNames.add(name);
      items.push({ title: name, quantity: 1, price: 0, discount: 0 });
      if (items.length >= 30) {
        break;
      }
    }

    const promotions = [];
    const promoRegex = /((?:rabatt|coupon|gutschein|bonus|vorteil)[^0-9-]{0,80})(-?[0-9]+[.,][0-9]{2})/ig;
    let promoMatch = promoRegex.exec(text);
    while (promoMatch) {
      const description = (promoMatch[1] || "REWE promotion").trim();
      const rawAmount = Number((promoMatch[2] || "0").replace(",", "."));
      if (Number.isFinite(rawAmount) && rawAmount !== 0) {
        promotions.push({ description, amount: Math.abs(rawAmount) });
      }
      promoMatch = promoRegex.exec(text);
    }
    const totalSavings = promotions.reduce((acc, promo) => acc + (promo.amount || 0), 0);

    rows.push({
      orderId,
      orderDate,
      totalAmount,
      currency: "EUR",
      orderStatus: "",
      detailsUrl: "",
      items,
      promotions,
      totalSavings
    });
  }

  return rows;
}
"""


class RewePlaywrightClient:
    def __init__(
        self,
        *,
        state_file: Path,
        domain: str = "shop.rewe.de",
        headless: bool = True,
        max_pages: int = 10,
    ) -> None:
        self._state_file = state_file
        self._domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
        self._headless = headless
        self._max_pages = max(1, max_pages)

    def fetch_receipts(self) -> list[dict[str, Any]]:
        if not self._state_file.exists():
            raise ReweReauthRequiredError(
                f"REWE session state missing: {self._state_file}. "
                "Run 'lidltool connectors auth bootstrap --source-id rewe_de' first."
            )

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        with sync_playwright() as playwright:
            browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
            context = browser.new_context(storage_state=str(self._state_file))
            page = context.new_page()
            self._ensure_logged_in(page)

            for page_idx in range(1, self._max_pages + 1):
                orders_url = f"https://{self._domain}/account/orders?page={page_idx}"
                page.goto(orders_url, wait_until="domcontentloaded")
                wait_for_page_network_idle(page, timeout_ms=1000)
                self._ensure_logged_in(page)
                rows = page.evaluate(_SCRAPE_ORDERS_SCRIPT)
                if not isinstance(rows, list) or not rows:
                    break

                added = 0
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    order_id_raw = row.get("orderId")
                    if not isinstance(order_id_raw, str):
                        continue
                    order_id = order_id_raw.strip()
                    if not order_id or order_id in seen:
                        continue
                    row["orderId"] = order_id
                    if not row.get("orderDate"):
                        row["orderDate"] = datetime.now(tz=UTC).isoformat()
                    if row.get("currency") is None:
                        row["currency"] = "EUR"
                    out.append(row)
                    seen.add(order_id)
                    added += 1
                if added == 0:
                    break

            try:
                context.close()
            finally:
                browser.close()

        return out

    def _ensure_logged_in(self, page: Any) -> None:
        url = str(page.url).lower()
        if "/auth/login" in url or "/login" in url:
            raise ReweReauthRequiredError(
                "REWE session expired or invalid. Run 'lidltool connectors auth bootstrap --source-id rewe_de' again."
            )


def parse_rewe_date(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return datetime.now(tz=UTC).isoformat()
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue
    return cleaned


_PROMOTION_RE = re.compile(
    r"(?i)(?:rabatt|coupon|gutschein|bonus|vorteil)[^0-9-]{0,80}(-?[0-9]+[.,][0-9]{2})"
)


def parse_rewe_promotions(text: str) -> list[dict[str, Any]]:
    promotions: list[dict[str, Any]] = []
    for match in _PROMOTION_RE.finditer(text):
        raw = match.group(1).replace(",", ".")
        try:
            amount = abs(float(raw))
        except ValueError:
            continue
        if amount <= 0:
            continue
        promotions.append({"description": "REWE promotion", "amount": round(amount, 2)})
    return promotions
