from __future__ import annotations

import base64
import csv
import io
import json
import re
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

REWE_BASE_URL = "https://www.rewe.de"
REWE_ACCOUNT_ROOT_URL = f"{REWE_BASE_URL}/shop/mydata"
REWE_PURCHASES_URL = f"{REWE_ACCOUNT_ROOT_URL}/meine-einkaeufe"
REWE_ONLINE_PURCHASES_URL = f"{REWE_PURCHASES_URL}/onlineshop"
REWE_MARKET_PURCHASES_URL = f"{REWE_PURCHASES_URL}/im-markt"
REWE_BONUS_URL = f"{REWE_ACCOUNT_ROOT_URL}/rewe-bonus"
REWE_BONUS_TRANSACTIONS_URL = f"{REWE_BASE_URL}/api/loyalty-balance/me/transactions"
REWE_BONUS_ACCOUNT_URL = f"{REWE_BASE_URL}/api/rewe/loyalty-accounts/me"
REWE_LOYALTY_BALANCE_URL = f"{REWE_BASE_URL}/api/loyalty-balance/me"
DEFAULT_REWE_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)
_APPLE_EVENTS_DISABLED_MARKER = "JavaScript über AppleScript ist deaktiviert"
_APPLE_EVENTS_DISABLED_MARKER_ALT = "JavaScript from Apple Events"
_LIVE_CHROME_TAB_NOT_FOUND = "No REWE tab open in Google Chrome. Open REWE account/receipts in normal Chrome first."

_AMOUNT_RE = re.compile(r"-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2}))")
_DATE_TIME_RE = re.compile(
    r"(?P<date>\d{1,2}\.\d{1,2}\.\d{2,4})(?:,\s*(?P<time>\d{1,2}:\d{2})\s*Uhr)?",
    re.IGNORECASE,
)
_RECEIPT_ID_RE = re.compile(r"/api/receipts/([0-9a-fA-F-]{8,})/")
_NON_ITEM_PREFIXES = (
    "summe",
    "gesamt",
    "zu zahlen",
    "zahlbetrag",
    "mwst",
    "steuer",
    "bar",
    "ec",
    "visa",
    "mastercard",
    "kartenzahlung",
    "bonus-guthaben",
    "bonus guthaben",
)

_BOT_CHALLENGE_MARKERS = (
    "just a moment",
    "zeig uns, dass du ein mensch bist",
    "waf challenge",
    "bot protection",
    "verify you are human",
    "attention required",
)

_MARKET_LIST_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();

  const parseAmount = (value) => {
    const text = normalize(value);
    const match = text.match(/-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2}))/);
    if (!match) {
      return 0;
    }
    let raw = match[0];
    let sign = 1;
    if (raw.startsWith("-")) {
      sign = -1;
      raw = raw.slice(1);
    }
    raw = raw.replace(/(\d)[.\s](\d{3})(?=[,.]|$)/g, "$1$2");
    raw = raw.replace(/\s+/g, "").replace(",", ".");
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? sign * parsed : 0;
  };

  const extractReceiptId = (url) => {
    if (!url) {
      return "";
    }
    const match = url.match(/\/api\/receipts\/([0-9a-fA-F-]{8,})\//);
    return match ? match[1] : "";
  };

  const parseDateTime = (text) => {
    const match = text.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})(?:,\s*(\d{1,2}:\d{2})\s*Uhr)?/i);
    if (!match) {
      return { date: "", time: "" };
    }
    return {
      date: match[1] || "",
      time: match[2] || "",
    };
  };

  const groups = new Map();
  const anchors = Array.from(document.querySelectorAll("a[href*='/api/receipts/']"));
  for (const anchor of anchors) {
    const href = anchor.href || anchor.getAttribute("href") || "";
    const receiptId = extractReceiptId(href);
    if (!receiptId) {
      continue;
    }
    const card =
      anchor.closest("article, li, section, [role='listitem'], [class*='receipt'], [class*='card'], div") ||
      anchor.parentElement;
    const group = groups.get(receiptId) || { receiptId, card, pdfUrl: "", csvUrl: "" };
    if (!group.card && card) {
      group.card = card;
    }
    if (/\/pdf(?:$|\?)/i.test(href)) {
      group.pdfUrl = href;
    }
    if (/\/csv(?:$|\?)/i.test(href)) {
      group.csvUrl = href;
    }
    groups.set(receiptId, group);
  }

  const records = [];
  for (const group of groups.values()) {
    const card = group.card;
    const text = normalize(card?.innerText || "");
    const lines = text.split(/\s{2,}|\n/).map((entry) => normalize(entry)).filter(Boolean);
    const heading = normalize(
      card?.querySelector("h1,h2,h3,h4,h5,strong,[class*='title'],[class*='market']")?.textContent || ""
    );
    const dateInfo = parseDateTime(text);
    let storeName = heading;
    if (!storeName && lines.length > 0) {
      storeName = lines[0];
    }
    const address = lines.find((line) => /\d{5}\s+[A-Za-zÄÖÜäöüß]/.test(line)) || "";
    records.push({
      recordRef: `market:${group.receiptId}`,
      channel: "market",
      receiptId: group.receiptId,
      purchasedAtText: dateInfo.date || "",
      purchasedTimeText: dateInfo.time || "",
      totalAmount: Math.abs(parseAmount(text)),
      currency: "EUR",
      storeName,
      storeAddress: address,
      pdfUrl: group.pdfUrl,
      csvUrl: group.csvUrl,
      rawText: text,
      rawLines: lines,
    });
  }

  return records;
}
"""

_ONLINE_LIST_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();

  const parseAmount = (value) => {
    const text = normalize(value);
    const match = text.match(/-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2}))/);
    if (!match) {
      return 0;
    }
    let raw = match[0];
    let sign = 1;
    if (raw.startsWith("-")) {
      sign = -1;
      raw = raw.slice(1);
    }
    raw = raw.replace(/(\d)[.\s](\d{3})(?=[,.]|$)/g, "$1$2");
    raw = raw.replace(/\s+/g, "").replace(",", ".");
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? sign * parsed : 0;
  };

  const parseOrderIdFromUrl = (url) => {
    if (!url) {
      return "";
    }
    try {
      const parsed = new URL(url, window.location.origin);
      const queryKeys = ["orderId", "orderID", "order_id", "bestellung", "bestellnummer", "id"];
      for (const key of queryKeys) {
        const value = parsed.searchParams.get(key);
        if (value && /^[A-Za-z0-9][A-Za-z0-9-]{5,}$/.test(value)) {
          return value;
        }
      }
      const segments = parsed.pathname.split("/").filter(Boolean).reverse();
      for (const segment of segments) {
        if (/^[A-Za-z0-9][A-Za-z0-9-]{5,}$/.test(segment)) {
          return segment;
        }
      }
    } catch (_err) {
      return "";
    }
    return "";
  };

  const parseOrderIdFromText = (text) => {
    const explicit = text.match(/(?:bestell(?:ung|nummer)?|auftragsnummer|order(?:\s*id)?|rechnung(?:snummer)?|beleg(?:nr|nummer)?)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9-]{5,})/i);
    if (explicit && explicit[1]) {
      return explicit[1];
    }
    const fallback = text.match(/\b([A-Z]{2,8}-[A-Z0-9-]{3,})\b/);
    return fallback ? fallback[1] : "";
  };

  const parseDateTime = (text) => {
    const match = text.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})(?:,\s*(\d{1,2}:\d{2})\s*Uhr)?/i);
    if (!match) {
      return { date: "", time: "" };
    }
    return {
      date: match[1] || "",
      time: match[2] || "",
    };
  };

  const cards = Array.from(document.querySelectorAll("article, li, section, [role='listitem'], div"));
  const seen = new Set();
  const records = [];

  for (const card of cards) {
    const text = normalize(card.innerText || "");
    if (!text) {
      continue;
    }
    if (!/(bestell|liefer|abhol|online|rechnung|invoice|auftrag)/i.test(text)) {
      continue;
    }
    const anchors = Array.from(card.querySelectorAll("a[href]"));
    const hrefs = anchors.map((anchor) => anchor.href || anchor.getAttribute("href") || "").filter(Boolean);
    const detailsUrl =
      hrefs.find((href) => !/\/pdf(?:$|\?)|\/csv(?:$|\?)|\.pdf(?:$|\?)/i.test(href) && /bestell|order|rechnung|invoice|details/i.test(href)) ||
      hrefs.find((href) => !/\/pdf(?:$|\?)|\/csv(?:$|\?)|\.pdf(?:$|\?)/i.test(href)) ||
      "";
    const orderId = parseOrderIdFromUrl(detailsUrl) || parseOrderIdFromText(text);
    if (!orderId || seen.has(orderId)) {
      continue;
    }
    seen.add(orderId);
    const dateInfo = parseDateTime(text);
    const pdfUrls = hrefs.filter((href) => /\/pdf(?:$|\?)|\.pdf(?:$|\?)|rechnung|invoice/i.test(href));
    const itemTexts = Array.from(card.querySelectorAll("li, tr, [class*='item'], [class*='product']"))
      .map((node) => normalize(node.innerText || node.textContent || ""))
      .filter((line) => line && line.length <= 240)
      .slice(0, 60);

    records.push({
      recordRef: `online:${orderId}`,
      channel: "online",
      orderId,
      purchasedAtText: dateInfo.date || "",
      purchasedTimeText: dateInfo.time || "",
      totalAmount: Math.abs(parseAmount(text)),
      currency: "EUR",
      statusText: text,
      detailsUrl,
      pdfUrls,
      rawText: text,
      itemTexts,
    });
  }

  return records;
}
"""

_ONLINE_DETAIL_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();

  const parseAmount = (value) => {
    const text = normalize(value);
    const match = text.match(/-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2}))/);
    if (!match) {
      return 0;
    }
    let raw = match[0];
    let sign = 1;
    if (raw.startsWith("-")) {
      sign = -1;
      raw = raw.slice(1);
    }
    raw = raw.replace(/(\d)[.\s](\d{3})(?=[,.]|$)/g, "$1$2");
    raw = raw.replace(/\s+/g, "").replace(",", ".");
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? sign * parsed : 0;
  };

  const rawText = normalize(document.body?.innerText || "");
  const itemTexts = Array.from(
    document.querySelectorAll("li, tr, [class*='item'], [class*='line'], [class*='product']")
  )
    .map((node) => normalize(node.innerText || node.textContent || ""))
    .filter((line) => line && line.length <= 240)
    .slice(0, 120);
  const hrefs = Array.from(document.querySelectorAll("a[href]"))
    .map((anchor) => anchor.href || anchor.getAttribute("href") || "")
    .filter(Boolean);
  const dateMatch = rawText.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})(?:,\s*(\d{1,2}:\d{2})\s*Uhr)?/i);
  return {
    rawText,
    itemTexts,
    hrefs,
    totalAmount: Math.abs(parseAmount(rawText)),
    purchasedAtText: dateMatch ? (dateMatch[1] || "") : "",
    purchasedTimeText: dateMatch ? (dateMatch[2] || "") : "",
  };
}
"""


def _run_jxa(source: str) -> str:
    result = subprocess.run(
        ["osascript", "-l", "JavaScript"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise ReweClientError(f"REWE live Chrome session failed to run osascript/JXA: {stderr}")
    return (result.stdout or result.stderr or "").strip()


def _json_literal(value: str | None) -> str:
    return json.dumps("" if value is None else value)


def _execute_javascript_in_rewe_chrome_tab(
    javascript: str,
    *,
    navigate_url: str | None = None,
    restore_original_url: bool = False,
    wait_after_navigation_seconds: float = 1.8,
) -> str:
    jxa_source = f"""
ObjC.import('Foundation');

function sleep(seconds) {{
  $.NSThread.sleepForTimeInterval(seconds);
}}

function emit(payload) {{
  console.log(JSON.stringify(payload));
}}

try {{
  const chrome = Application('Google Chrome');
  chrome.includeStandardAdditions = true;
  const windows = chrome.windows();
  let targetTab = null;
  let originalUrl = '';
  const navigateUrl = {_json_literal(navigate_url)};
  const shouldRestore = {str(restore_original_url).lower()};

  outer:
  for (let wi = 0; wi < windows.length; wi += 1) {{
    const tabs = windows[wi].tabs();
    for (let ti = 0; ti < tabs.length; ti += 1) {{
      const candidate = tabs[ti];
      const url = String(candidate.url() || '');
      if (url.includes('rewe.de')) {{
        targetTab = candidate;
        originalUrl = url;
        break outer;
      }}
    }}
  }}

  if (!targetTab) {{
    emit({{ ok: false, code: 'tab_not_found', error: {_json_literal(_LIVE_CHROME_TAB_NOT_FOUND)} }});
  }} else {{
    if (navigateUrl && originalUrl !== navigateUrl) {{
      targetTab.url = navigateUrl;
      sleep({wait_after_navigation_seconds});
      for (let i = 0; i < 20; i += 1) {{
        try {{
          const ready = String(targetTab.execute({{ javascript: 'document.readyState || ""' }}) || '');
          if (ready === 'interactive' || ready === 'complete') {{
            break;
          }}
        }} catch (_err) {{}}
        sleep(0.2);
      }}
    }}

    let rawResult = null;
    try {{
      rawResult = targetTab.execute({{ javascript: {_json_literal(javascript)} }});
    }} finally {{
      if (shouldRestore && originalUrl && String(targetTab.url() || '') !== originalUrl) {{
        targetTab.url = originalUrl;
      }}
    }}

    emit({{
      ok: true,
      result: rawResult,
      originalUrl,
      currentUrl: String(targetTab.url() || '')
    }});
  }}
}} catch (err) {{
  emit({{ ok: false, code: 'execution_failed', error: String(err) }});
}}
"""
    raw_output = _run_jxa(jxa_source)
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ReweClientError(f"REWE live Chrome session returned invalid JSON: {raw_output}") from exc
    if not isinstance(payload, dict):
        raise ReweClientError("REWE live Chrome session returned invalid payload")
    if payload.get("ok") is not True:
        error = str(payload.get("error") or "REWE live Chrome session failed")
        if (
            _APPLE_EVENTS_DISABLED_MARKER in error
            or _APPLE_EVENTS_DISABLED_MARKER_ALT in error
        ):
            raise ReweClientError(
                "REWE live Chrome session requires Chrome setting "
                "'Darstellung > Entwickler > JavaScript von Apple Events erlauben'."
            )
        raise ReweClientError(error)
    return str(payload.get("result") or "")


def _evaluate_rewe_chrome_json(
    javascript: str,
    *,
    navigate_url: str | None = None,
    restore_original_url: bool = False,
    wait_after_navigation_seconds: float = 1.8,
) -> Any:
    raw = _execute_javascript_in_rewe_chrome_tab(
        javascript,
        navigate_url=navigate_url,
        restore_original_url=restore_original_url,
        wait_after_navigation_seconds=wait_after_navigation_seconds,
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReweClientError(f"REWE live Chrome session returned invalid page JSON: {raw}") from exc


def _sync_xhr_json_script(url: str) -> str:
    return f"""
(() => {{
  const xhr = new XMLHttpRequest();
  xhr.open('GET', {json.dumps(url)}, false);
  xhr.withCredentials = true;
  xhr.send(null);
  const text = xhr.responseText || '';
  return JSON.stringify({{
    status: xhr.status,
    responseText: text
  }});
}})()
"""


def _sync_xhr_base64_script(url: str) -> str:
    return f"""
(() => {{
  const xhr = new XMLHttpRequest();
  xhr.open('GET', {json.dumps(url)}, false);
  xhr.responseType = 'arraybuffer';
  xhr.withCredentials = true;
  xhr.send(null);
  const bytes = new Uint8Array(xhr.response || new ArrayBuffer(0));
  let binary = '';
  for (const value of bytes) {{
    binary += String.fromCharCode(value);
  }}
  return JSON.stringify({{
    status: xhr.status,
    base64: btoa(binary)
  }});
}})()
"""


def probe_rewe_live_chrome_session() -> dict[str, str]:
    payload = _evaluate_rewe_chrome_json(
        "JSON.stringify({title: document.title || '', href: location.href || ''})",
        navigate_url=None,
        restore_original_url=False,
        wait_after_navigation_seconds=0.2,
    )
    if not isinstance(payload, dict):
        raise ReweClientError("REWE live Chrome session probe returned invalid payload")
    href = str(payload.get("href") or "")
    if "rewe.de" not in href:
        raise ReweClientError(_LIVE_CHROME_TAB_NOT_FOUND)
    return {
        "title": str(payload.get("title") or ""),
        "href": href,
    }


class ReweClientError(RuntimeError):
    pass


class ReweReauthRequiredError(ReweClientError):
    pass


def looks_like_rewe_bot_challenge(*, url: str, title: str, text: str) -> bool:
    lowered = " ".join(
        part.strip().lower()
        for part in (url, title, text)
        if isinstance(part, str) and part.strip()
    )
    return any(marker in lowered for marker in _BOT_CHALLENGE_MARKERS)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _parse_amount(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    match = _AMOUNT_RE.search(str(value).replace("\xa0", " "))
    if not match:
        return 0.0
    raw = match.group(0)
    sign = -1.0 if raw.startswith("-") else 1.0
    normalized = raw.replace("-", "")
    normalized = re.sub(r"(\d)[.\s](\d{3})(?=[,.]|$)", r"\1\2", normalized)
    normalized = normalized.replace(" ", "").replace(",", ".")
    try:
        return sign * float(normalized)
    except ValueError:
        return 0.0


def _to_cents(value: Any) -> int:
    return int(round(_parse_amount(value) * 100))


def _parse_quantity(value: Any) -> float:
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed > 0 else 1.0
    text = _normalize_text(str(value or ""))
    if not text:
        return 1.0
    text = text.replace(",", ".")
    try:
        parsed = float(text)
    except ValueError:
        return 1.0
    return parsed if parsed > 0 else 1.0


def _receipt_id_from_url(value: str) -> str | None:
    if not value:
        return None
    match = _RECEIPT_ID_RE.search(value)
    if match:
        return match.group(1)
    return None


def _parse_de_datetime(date_text: str, time_text: str = "") -> str | None:
    date_value = _normalize_text(date_text)
    if not date_value:
        return None
    time_value = _normalize_text(time_text).replace("Uhr", "").strip()
    formats = []
    if time_value:
        formats.extend(
            [
                ("%d.%m.%Y %H:%M", f"{date_value} {time_value}"),
                ("%d.%m.%y %H:%M", f"{date_value} {time_value}"),
            ]
        )
    formats.extend([("%d.%m.%Y", date_value), ("%d.%m.%y", date_value)])
    for fmt, value in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC).isoformat()
    return None


def classify_rewe_discount(label: str) -> dict[str, str | None]:
    lowered = _normalize_text(label).lower()
    if "bonus" in lowered or "guthaben" in lowered:
        if any(token in lowered for token in ("einlös", "eingeloes", "eingelös", "verrechnet", "abzug")):
            return {"type": "bonus_credit_redeemed", "subkind": "stored_value"}
        return {"type": "bonus_credit", "subkind": "loyalty"}
    if any(token in lowered for token in ("mhd", "mindestens haltbar", "frisch", "red", "abschrift")):
        return {"type": "low_freshness_reduction", "subkind": "markdown"}
    if re.search(r"\b\d+\s*(?:für|for)\b", lowered) or any(
        token in lowered for token in ("2+1", "3+1", "mehrfach", "multi", "gratis")
    ):
        return {"type": "multibuy_discount", "subkind": "promotion"}
    if "coupon" in lowered or "gutschein" in lowered:
        return {"type": "coupon", "subkind": "coupon"}
    if any(token in lowered for token in ("rabatt", "aktion", "vorteil", "spar", "%")):
        return {"type": "promotion", "subkind": "promotion"}
    return {"type": "discount", "subkind": None}


def _decode_csv_bytes(csv_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return csv_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return csv_bytes.decode("utf-8", errors="replace")


def _csv_header_map(header: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, raw in enumerate(header):
        key = _normalize_text(raw).lower()
        if not key:
            continue
        mapping[key] = idx
    return mapping


def _find_header_index(rows: list[list[str]]) -> int | None:
    keywords = ("artikel", "produkt", "bezeichnung", "menge", "einzelpreis", "gesamt", "rabatt")
    for idx, row in enumerate(rows[:8]):
        lowered = " | ".join(_normalize_text(cell).lower() for cell in row if _normalize_text(cell))
        if sum(1 for keyword in keywords if keyword in lowered) >= 2:
            return idx
    return None


def _select_first_column(header_map: dict[str, int], candidates: tuple[str, ...]) -> int | None:
    for candidate in candidates:
        for key, idx in header_map.items():
            if candidate in key:
                return idx
    return None


def _looks_like_market_summary_csv(rows: list[list[str]]) -> bool:
    if len(rows) < 2:
        return False
    header = [_normalize_text(cell).lower() for cell in rows[0] if _normalize_text(cell)]
    if not header:
        return False
    allowed = {"datum", "uhrzeit", "gesamtsumme", "summe"}
    return (
        any("summe" in cell for cell in header)
        and all(cell in allowed for cell in header)
        and len(header) <= 4
    )


def _transaction_discount_row(label: str, amount_cents: int) -> dict[str, Any]:
    semantics = classify_rewe_discount(label)
    return {
        "type": str(semantics["type"] or "discount"),
        "subkind": semantics["subkind"],
        "promotion_id": None,
        "amount_cents": -abs(amount_cents),
        "label": label,
        "scope": "transaction",
        "funded_by": "retailer",
    }


def _item_discount_row(label: str, amount_cents: int) -> dict[str, Any]:
    semantics = classify_rewe_discount(label)
    return {
        "type": str(semantics["type"] or "discount"),
        "subkind": semantics["subkind"],
        "promotion_id": None,
        "amount_cents": -abs(amount_cents),
        "label": label,
        "scope": "item",
    }


def parse_market_csv_payload(csv_bytes: bytes) -> dict[str, Any]:
    text = _decode_csv_bytes(csv_bytes)
    if not text.strip():
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": 0,
            "discount_total_cents": 0,
            "rows": [],
            "raw_text": text,
        }
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ";"
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [[_normalize_text(cell) for cell in row] for row in reader]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": 0,
            "discount_total_cents": 0,
            "rows": [],
            "raw_text": text,
        }
    if _looks_like_market_summary_csv(rows):
        total_gross_cents = abs(_to_cents(rows[-1][-1] if rows[-1] else ""))
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": total_gross_cents,
            "discount_total_cents": 0,
            "rows": rows,
            "raw_text": text,
        }

    header_index = _find_header_index(rows)
    header_map = _csv_header_map(rows[header_index]) if header_index is not None else {}
    data_rows = rows[header_index + 1 :] if header_index is not None else rows

    name_idx = _select_first_column(header_map, ("artikel", "produkt", "bezeichnung", "text", "name"))
    qty_idx = _select_first_column(header_map, ("menge", "anzahl", "qty"))
    unit_price_idx = _select_first_column(header_map, ("einzelpreis", "stückpreis", "stueckpreis", "preis"))
    total_idx = _select_first_column(header_map, ("gesamt", "betrag", "summe", "brutto"))
    discount_idx = _select_first_column(header_map, ("rabatt", "nachlass", "ersparnis"))

    items: list[dict[str, Any]] = []
    transaction_discounts: list[dict[str, Any]] = []
    bonus_earned: list[dict[str, Any]] = []
    discount_total_cents = 0
    total_gross_cents = 0

    for row in data_rows:
        combined = " | ".join(cell for cell in row if cell)
        lowered = combined.lower()
        if not combined:
            continue
        if any(token in lowered for token in ("summe", "zu zahlen", "gesamt")):
            amount = abs(_to_cents(combined))
            if amount > 0:
                total_gross_cents = max(total_gross_cents, amount)
            continue

        name = row[name_idx] if name_idx is not None and name_idx < len(row) else row[0]
        quantity = row[qty_idx] if qty_idx is not None and qty_idx < len(row) else "1"
        unit_price = row[unit_price_idx] if unit_price_idx is not None and unit_price_idx < len(row) else ""
        total = row[total_idx] if total_idx is not None and total_idx < len(row) else row[-1]
        discount = row[discount_idx] if discount_idx is not None and discount_idx < len(row) else ""

        amount_cents = _to_cents(total)
        if amount_cents == 0 and len(row) >= 2:
            amount_cents = _to_cents(row[-1])

        if "bonus" in lowered or "guthaben" in lowered:
            signed_amount = _to_cents(discount or total or combined)
            if signed_amount > 0 and not any(
                token in lowered for token in ("einlös", "eingeloes", "eingelös", "verrechnet", "abzug")
            ):
                bonus_earned.append(
                    {
                        "label": name or combined,
                        "amount_cents": signed_amount,
                        "source": "csv",
                    }
                )
                continue
            if signed_amount < 0 or any(
                token in lowered for token in ("einlös", "eingeloes", "eingelös", "verrechnet", "abzug")
            ):
                transaction_discounts.append(
                    _transaction_discount_row(name or combined, abs(signed_amount or amount_cents))
                )
                discount_total_cents += abs(signed_amount or amount_cents)
                continue

        if amount_cents < 0 or any(token in lowered for token in ("rabatt", "coupon", "gutschein", "mhd", "2 für")):
            transaction_discounts.append(_transaction_discount_row(name or combined, abs(amount_cents)))
            discount_total_cents += abs(amount_cents)
            continue

        qty = _parse_quantity(quantity)
        unit_price_cents = _to_cents(unit_price)
        if unit_price_cents <= 0 and amount_cents > 0 and qty > 0:
            unit_price_cents = int(round(amount_cents / qty))
        item_discounts: list[dict[str, Any]] = []
        discount_cents = abs(_to_cents(discount))
        if discount_cents > 0:
            item_discounts.append(_item_discount_row(f"{name} Rabatt", discount_cents))
            discount_total_cents += discount_cents
        items.append(
            {
                "name": name or "REWE Markt Artikel",
                "qty": qty,
                "unit": "pcs",
                "unitPrice": unit_price_cents / 100.0 if unit_price_cents else 0.0,
                "lineTotal": abs(amount_cents) / 100.0 if amount_cents else 0.0,
                "discounts": item_discounts,
            }
        )

    return {
        "items": items,
        "transaction_discounts": transaction_discounts,
        "bonus_earned": bonus_earned,
        "total_gross_cents": total_gross_cents,
        "discount_total_cents": discount_total_cents,
        "rows": rows,
        "raw_text": text,
    }


_PDF_ITEM_LINE_RE = re.compile(
    r"^(?P<label>.+?)\s+(?P<amount>-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})))\s+(?P<tax>[A-Z])(?:\s+\*)?$"
)
_PDF_SIMPLE_ITEM_LINE_RE = re.compile(
    r"^(?P<label>.+?)\s+(?P<amount>-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})))(?:\s+\*)?$"
)
_PDF_WEIGHT_CONTINUATION_RE = re.compile(
    r"^(?P<qty>\d+(?:[,.]\d+)?)\s*kg\s*x\s*(?P<unit_price>\d+(?:[,.]\d+)?)\s*EUR/kg$",
    re.IGNORECASE,
)
_PDF_PIECE_CONTINUATION_RE = re.compile(
    r"^(?P<qty>\d+(?:[,.]\d+)?)\s*(?:stk|st|pcs?)\s*x\s*(?P<unit_price>\d+(?:[,.]\d+)?)$",
    re.IGNORECASE,
)
_PDF_LABEL_AMOUNT_RE = re.compile(
    r"^(?P<label>.+?)\s+(?P<amount>-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})))(?:\s*EUR)?$",
    re.IGNORECASE,
)


def _parse_pdf_item_line(line: str) -> tuple[str, int] | None:
    match = _PDF_ITEM_LINE_RE.match(line)
    if match is not None:
        label = _normalize_text(match.group("label"))
        if not label:
            return None
        return label, _to_cents(match.group("amount"))
    fallback = _PDF_SIMPLE_ITEM_LINE_RE.match(line)
    if fallback is None:
        return None
    label = _normalize_text(fallback.group("label"))
    lowered = label.lower()
    if not label or (lowered.startswith(_NON_ITEM_PREFIXES) and "bonus" not in lowered and "guthaben" not in lowered) or lowered.endswith("eur"):
        return None
    return label, _to_cents(fallback.group("amount"))


def _apply_pdf_item_continuation(item: dict[str, Any], line: str) -> bool:
    for pattern, unit in (
        (_PDF_WEIGHT_CONTINUATION_RE, "kg"),
        (_PDF_PIECE_CONTINUATION_RE, "pcs"),
    ):
        match = pattern.match(line)
        if match is None:
            continue
        qty = _parse_quantity(match.group("qty"))
        unit_price_cents = abs(_to_cents(match.group("unit_price")))
        item["qty"] = qty
        item["unit"] = unit
        if unit_price_cents > 0:
            sign = -1.0 if float(item.get("lineTotal", 0.0) or 0.0) < 0 else 1.0
            item["unitPrice"] = sign * (unit_price_cents / 100.0)
        return True
    return False


def parse_rewe_pdf_text(text: str) -> dict[str, Any]:
    normalized_text = text.replace("\r", "\n")
    lines = [_normalize_text(line) for line in normalized_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": 0,
            "discount_total_cents": 0,
            "raw_text": text,
        }

    items: list[dict[str, Any]] = []
    transaction_discounts: list[dict[str, Any]] = []
    bonus_earned: list[dict[str, Any]] = []
    discount_total_cents = 0
    total_gross_cents = 0

    store_name = lines[0] if lines else ""
    purchased_at = ""
    store_address_parts: list[str] = []
    item_section_lines: list[tuple[int, str]] = []
    item_section_started = False

    for index, line in enumerate(lines):
        if _parse_pdf_item_line(line) is not None:
            item_section_started = True
        if item_section_started:
            lowered = line.lower()
            if lowered.startswith("summe"):
                break
            item_section_lines.append((index, line))
    item_section_indices = {index for index, _line in item_section_lines}

    for index, line in enumerate(lines):
        if not purchased_at:
            match = _DATE_TIME_RE.search(line)
            if match:
                purchased_at = _parse_de_datetime(match.group("date"), match.group("time") or "") or ""
        lowered = line.lower()
        if (
            index <= 4
            and not _DATE_TIME_RE.search(line)
            and not _AMOUNT_RE.search(line)
            and "uid nr" not in lowered
            and not re.fullmatch(r"\d{5,}", line.replace(" ", ""))
        ):
            if index > 0:
                store_address_parts.append(line)

        if index in item_section_indices:
            continue

        if lowered.startswith(_NON_ITEM_PREFIXES):
            maybe_total = abs(_to_cents(line))
            if maybe_total > 0:
                total_gross_cents = max(total_gross_cents, maybe_total)

        if lowered.startswith("mit diesem einkauf hast du"):
            amount_cents = _to_cents(line)
            nearby_text = " ".join(lines[index + 1 : index + 3]).lower()
            if amount_cents > 0 and "bonus" in nearby_text and "gesammelt" in nearby_text:
                bonus_earned.append(
                    {
                        "label": "REWE Bonus-Guthaben gesammelt",
                        "amount_cents": amount_cents,
                        "source": "pdf",
                    }
                )
            continue

        label_amount_match = _PDF_LABEL_AMOUNT_RE.match(line)
        if label_amount_match is None:
            continue
        label = _normalize_text(label_amount_match.group("label"))
        amount_cents = _to_cents(label_amount_match.group("amount"))
        lowered = label.lower()
        if amount_cents < 0 and any(
            token in lowered
            for token in ("rabatt", "coupon", "gutschein", "bonus", "guthaben", "mhd", "frisch", "2 für", "%")
        ):
            transaction_discounts.append(_transaction_discount_row(label, abs(amount_cents)))
            discount_total_cents += abs(amount_cents)
            continue
        if (
            amount_cents > 0
            and ("bonus" in lowered or "guthaben" in lowered)
            and "gesammelt" in lowered
            and "aktuelles" not in lowered
        ):
            bonus_earned.append({"label": label, "amount_cents": amount_cents, "source": "pdf"})

    current_item: dict[str, Any] | None = None
    for _index, line in item_section_lines:
        if set(line) <= {"-", "=", " "}:
            continue
        if current_item is not None and _apply_pdf_item_continuation(current_item, line):
            continue
        parsed_item = _parse_pdf_item_line(line)
        if parsed_item is None:
            continue
        label, amount_cents = parsed_item
        lowered = label.lower()
        if amount_cents > 0 and ("bonus" in lowered or "guthaben" in lowered):
            bonus_earned.append({"label": label, "amount_cents": amount_cents, "source": "pdf"})
            continue
        if amount_cents < 0 and any(
            token in lowered for token in ("rabatt", "coupon", "gutschein", "bonus", "guthaben", "mhd", "frisch", "2 für", "%")
        ):
            discount_row = _item_discount_row(label, abs(amount_cents))
            if current_item is not None and "bonus" not in lowered and "guthaben" not in lowered:
                current_item.setdefault("discounts", []).append(discount_row)
            else:
                transaction_discounts.append(_transaction_discount_row(label, abs(amount_cents)))
            discount_total_cents += abs(amount_cents)
            continue
        current_item = {
            "name": label,
            "qty": 1.0,
            "unit": "pcs",
            "unitPrice": amount_cents / 100.0,
            "lineTotal": amount_cents / 100.0,
            "discounts": [],
        }
        items.append(current_item)

    return {
        "store_name": store_name or None,
        "store_address": ", ".join(store_address_parts) or None,
        "purchased_at": purchased_at or None,
        "items": items,
        "transaction_discounts": transaction_discounts,
        "bonus_earned": bonus_earned,
        "total_gross_cents": total_gross_cents,
        "discount_total_cents": discount_total_cents,
        "raw_text": text,
    }


def parse_rewe_pdf_bytes(pdf_bytes: bytes) -> dict[str, Any]:
    if not pdf_bytes:
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": 0,
            "discount_total_cents": 0,
            "raw_text": "",
        }
    try:
        from pypdf import PdfReader
    except Exception:
        return {
            "items": [],
            "transaction_discounts": [],
            "bonus_earned": [],
            "total_gross_cents": 0,
            "discount_total_cents": 0,
            "raw_text": "",
        }
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        extracted = ""
    return parse_rewe_pdf_text(extracted)


def parse_bonus_transactions_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        for key in ("transactions", "items", "content", "data"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
        else:
            rows = []
    else:
        rows = []

    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        amount_cents = _to_cents(row.get("amount") or row.get("credit") or row.get("value"))
        if amount_cents == 0:
            continue
        details = row.get("details")
        parsed.append(
            {
                "transaction_id": str(row.get("id") or "").strip() or None,
                "source_id": str(row.get("sourceId") or row.get("source_id") or "").strip() or None,
                "type": str(row.get("type") or "").strip() or None,
                "text": str(row.get("text") or row.get("source") or row.get("description") or "").strip() or None,
                "source": str(row.get("source") or "").strip() or None,
                "amount_cents": amount_cents,
                "balance_cents": _to_cents(row.get("balance")),
                "date": str(row.get("date") or row.get("createdAt") or row.get("created_at") or "").strip()
                or None,
                "details": details if isinstance(details, dict) else {},
            }
        )
    return parsed


def match_bonus_transactions(
    *,
    record_ref: str,
    receipt_id: str | None,
    purchased_at: str | None,
    store_name: str | None,
    transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    matched: list[dict[str, Any]] = []
    exact_keys = {record_ref}
    if receipt_id:
        exact_keys.add(receipt_id)
    purchase_day = (purchased_at or "")[:10]
    normalized_store = _normalize_text(store_name or "").lower()
    for transaction in transactions:
        source_id = str(transaction.get("source_id") or "").strip()
        text = _normalize_text(str(transaction.get("text") or transaction.get("source") or "")).lower()
        tx_date = str(transaction.get("date") or "")[:10]
        if source_id and source_id in exact_keys:
            matched.append(transaction)
            continue
        if purchase_day and tx_date == purchase_day and normalized_store and normalized_store in text:
            matched.append(transaction)

    earned = [row for row in matched if int(row.get("amount_cents", 0) or 0) > 0]
    redeemed = [row for row in matched if int(row.get("amount_cents", 0) or 0) < 0]
    return {
        "matched": matched,
        "earned": earned,
        "redeemed": redeemed,
    }


def build_market_record_detail(
    *,
    summary: dict[str, Any],
    csv_payload: dict[str, Any] | None,
    pdf_payload: dict[str, Any] | None,
    bonus_match: dict[str, Any] | None,
) -> dict[str, Any]:
    csv_payload = csv_payload or {}
    pdf_payload = pdf_payload or {}
    bonus_match = bonus_match or {"matched": [], "earned": [], "redeemed": []}

    items = list(pdf_payload.get("items") or []) or list(csv_payload.get("items") or [])
    transaction_discounts = list(csv_payload.get("transaction_discounts") or [])
    transaction_discounts.extend(list(pdf_payload.get("transaction_discounts") or []))

    bonus_earned = list(csv_payload.get("bonus_earned") or [])
    bonus_earned.extend(list(pdf_payload.get("bonus_earned") or []))
    for entry in bonus_match.get("earned") or []:
        amount_cents = int(entry.get("amount_cents", 0) or 0)
        if amount_cents <= 0:
            continue
        bonus_earned.append(
            {
                "label": entry.get("text") or "REWE Bonus Guthaben gesammelt",
                "amount_cents": amount_cents,
                "transaction_id": entry.get("transaction_id"),
                "source": "bonus_api",
            }
        )

    for entry in bonus_match.get("redeemed") or []:
        amount_cents = abs(int(entry.get("amount_cents", 0) or 0))
        if amount_cents <= 0:
            continue
        transaction_discounts.append(
            _transaction_discount_row(
                str(entry.get("text") or "REWE Bonus Guthaben eingelöst"),
                amount_cents,
            )
        )

    purchased_at = (
        summary.get("purchasedAt")
        or pdf_payload.get("purchased_at")
        or _parse_de_datetime(str(summary.get("purchasedAtText") or ""), str(summary.get("purchasedTimeText") or ""))
        or datetime.now(tz=UTC).isoformat()
    )
    total_gross_cents = int(
        summary.get("totalGrossCents")
        or 0
        or csv_payload.get("total_gross_cents")
        or pdf_payload.get("total_gross_cents")
        or abs(_to_cents(summary.get("totalAmount")))
    )
    discount_total_cents = sum(
        abs(int(entry.get("amount_cents", 0) or 0))
        for entry in transaction_discounts
    ) + sum(
        abs(int(discount.get("amount_cents", 0) or 0))
        for item in items
        for discount in (item.get("discounts") or [])
        if isinstance(discount, dict)
    )

    if not items and total_gross_cents > 0:
        items = [
            {
                "name": "REWE Markt Einkauf",
                "qty": 1,
                "unit": "receipt",
                "unitPrice": total_gross_cents / 100.0,
                "lineTotal": total_gross_cents / 100.0,
                "discounts": [],
            }
        ]

    return {
        "id": summary.get("receiptId") or summary.get("recordRef"),
        "receiptId": summary.get("receiptId"),
        "channel": "market",
        "kind": "in_market_receipt",
        "purchasedAt": purchased_at,
        "storeName": summary.get("storeName") or pdf_payload.get("store_name") or "REWE Markt",
        "storeAddress": summary.get("storeAddress") or pdf_payload.get("store_address"),
        "totalGross": total_gross_cents / 100.0,
        "currency": summary.get("currency") or "EUR",
        "discountTotal": discount_total_cents / 100.0,
        "items": items,
        "transactionDiscounts": transaction_discounts,
        "bonus": {
            "earned": bonus_earned,
            "redeemed": bonus_match.get("redeemed") or [],
            "matched_transactions": bonus_match.get("matched") or [],
        },
        "downloads": {
            "pdf_url": summary.get("pdfUrl"),
            "csv_url": summary.get("csvUrl"),
        },
        "source_record_detail": {
            "summary": summary,
            "csv": csv_payload,
            "pdf": pdf_payload,
            "bonus_match": bonus_match,
        },
        "raw_json": {
            "summary": summary,
            "csv": csv_payload,
            "pdf": pdf_payload,
            "bonus_match": bonus_match,
        },
    }


def build_online_record_detail(
    *,
    summary: dict[str, Any],
    detail_payload: dict[str, Any] | None,
    bonus_match: dict[str, Any] | None,
) -> dict[str, Any]:
    detail_payload = detail_payload or {}
    bonus_match = bonus_match or {"matched": [], "earned": [], "redeemed": []}
    raw_text = _normalize_text(str(detail_payload.get("rawText") or summary.get("rawText") or ""))
    item_texts = detail_payload.get("itemTexts") or summary.get("itemTexts") or []
    items: list[dict[str, Any]] = []
    for line in item_texts:
        text = _normalize_text(str(line))
        if not text or len(text) > 240:
            continue
        if any(marker in text.lower() for marker in ("summe", "gesamt", "bestell", "rechnung")):
            continue
        amount = abs(_parse_amount(text))
        items.append(
            {
                "name": text,
                "qty": 1,
                "unit": "pcs",
                "unitPrice": amount if amount > 0 else 0.0,
                "lineTotal": amount if amount > 0 else 0.0,
                "discounts": [],
            }
        )
        if len(items) >= 50:
            break

    total_gross_cents = abs(
        _to_cents(detail_payload.get("totalAmount") or summary.get("totalAmount") or raw_text)
    )
    if not items and total_gross_cents > 0:
        items = [
            {
                "name": "REWE Online Bestellung",
                "qty": 1,
                "unit": "order",
                "unitPrice": total_gross_cents / 100.0,
                "lineTotal": total_gross_cents / 100.0,
                "discounts": [],
            }
        ]

    purchased_at = (
        _parse_de_datetime(
            str(detail_payload.get("purchasedAtText") or summary.get("purchasedAtText") or ""),
            str(detail_payload.get("purchasedTimeText") or summary.get("purchasedTimeText") or ""),
        )
        or summary.get("purchasedAt")
        or datetime.now(tz=UTC).isoformat()
    )

    bonus_earned = [
        {
            "label": row.get("text") or "REWE Bonus Guthaben gesammelt",
            "amount_cents": int(row.get("amount_cents", 0) or 0),
            "transaction_id": row.get("transaction_id"),
            "source": "bonus_api",
        }
        for row in bonus_match.get("earned") or []
        if int(row.get("amount_cents", 0) or 0) > 0
    ]
    transaction_discounts = [
        _transaction_discount_row(
            str(row.get("text") or "REWE Bonus Guthaben eingelöst"),
            abs(int(row.get("amount_cents", 0) or 0)),
        )
        for row in bonus_match.get("redeemed") or []
        if abs(int(row.get("amount_cents", 0) or 0)) > 0
    ]

    discount_total_cents = sum(abs(int(entry.get("amount_cents", 0) or 0)) for entry in transaction_discounts)

    return {
        "id": summary.get("orderId") or summary.get("recordRef"),
        "orderId": summary.get("orderId"),
        "channel": "online",
        "kind": "online_order_receipt",
        "purchasedAt": purchased_at,
        "storeName": "REWE Online",
        "storeAddress": None,
        "totalGross": total_gross_cents / 100.0,
        "currency": summary.get("currency") or "EUR",
        "discountTotal": discount_total_cents / 100.0,
        "items": items,
        "transactionDiscounts": transaction_discounts,
        "bonus": {
            "earned": bonus_earned,
            "redeemed": bonus_match.get("redeemed") or [],
            "matched_transactions": bonus_match.get("matched") or [],
        },
        "downloads": {
            "detail_url": summary.get("detailsUrl"),
            "pdf_urls": detail_payload.get("pdfUrls") or summary.get("pdfUrls") or [],
        },
        "source_record_detail": {
            "summary": summary,
            "detail": detail_payload,
            "bonus_match": bonus_match,
        },
        "raw_json": {
            "summary": summary,
            "detail": detail_payload,
            "bonus_match": bonus_match,
        },
    }


def _absolute_rewe_url(value: str, *, base_url: str = REWE_BASE_URL) -> str:
    return urljoin(base_url, value or "")


def _looks_like_login_or_auth_url(url: str) -> bool:
    lowered = str(url or "").lower()
    return "account.rewe.de" in lowered or "/login" in lowered or "/auth" in lowered


def _looks_like_rewe_cookie_domain(domain: str) -> bool:
    normalized = str(domain or "").strip().lstrip(".").lower()
    return normalized == "rewe.de" or normalized.endswith(".rewe.de")


def _parse_order_id_from_url(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except Exception:
        return ""
    path = parsed.path or ""
    query_pairs = re.findall(r"([^=&?#]+)=([^&?#]+)", parsed.query or "")
    for key, raw_value in query_pairs:
        if key.lower() in {"orderid", "order_id", "bestellung", "bestellnummer", "id"}:
            if re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{5,}$", raw_value):
                return raw_value
    reserved = {
        "account",
        "angebote",
        "details",
        "im-markt",
        "login",
        "meine-einkaeufe",
        "mydata",
        "online",
        "onlineshop",
        "personaldata",
        "rewe-bonus",
        "shop",
    }
    for segment in reversed([part for part in path.split("/") if part]):
        lowered = segment.lower()
        if lowered in reserved:
            continue
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{5,}$", segment) and re.search(r"\d", segment):
            return segment
    return ""


def _parse_order_id_from_text(text: str) -> str:
    explicit = re.search(
        r"(?:bestell(?:ung|nummer)?|auftragsnummer|order(?:\s*id)?|rechnung(?:snummer)?|beleg(?:nr|nummer)?)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9-]{5,})",
        text,
        re.IGNORECASE,
    )
    if explicit and explicit.group(1):
        return explicit.group(1)
    fallback = re.search(r"\b([A-Z]{2,8}-[A-Z0-9-]{3,})\b", text)
    return fallback.group(1) if fallback else ""


def _first_heading_text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    heading = tag.select_one("h1,h2,h3,h4,h5,strong,[class*='title'],[class*='market']")
    return _normalize_text(heading.get_text(" ", strip=True)) if heading is not None else ""


def _tag_text_lines(tag: Tag | None) -> list[str]:
    if tag is None:
        return []
    raw_text = tag.get_text("\n", strip=True)
    return [line for line in (_normalize_text(line) for line in raw_text.splitlines()) if line]


def _infer_total_amount(lines: list[str], fallback_text: str) -> float:
    normalized_lines: list[str] = []
    for index, line in enumerate(lines):
        if line == "€" and index > 0:
            normalized_lines[-1] = f"{normalized_lines[-1]} €"
            continue
        normalized_lines.append(line)
    for line in normalized_lines:
        lowered = line.lower()
        if any(token in lowered for token in ("summe", "gesamt", "zu zahlen", "zahlbetrag")):
            amount = abs(_parse_amount(line))
            if amount > 0:
                return amount
    for line in reversed(normalized_lines):
        if _DATE_TIME_RE.search(line) or "uhr" in line.lower():
            continue
        amount = abs(_parse_amount(line))
        if amount > 0 and ("," in line or "." in line or "€" in line):
            return amount
    return abs(_parse_amount(fallback_text))


def _nearest_receipt_card(anchor: Tag, receipt_id: str) -> Tag | None:
    best: Tag | None = None
    for parent in anchor.parents:
        if not isinstance(parent, Tag) or parent.name not in {"article", "li", "section", "div"}:
            continue
        href_ids = {
            extracted
            for extracted in (
                _receipt_id_from_url(_absolute_rewe_url(str(link.get("href") or "")))
                for link in parent.select("a[href*='/api/receipts/']")
            )
            if extracted
        }
        if receipt_id in href_ids and len(href_ids) == 1:
            best = parent
    if best is not None:
        return best
    return anchor.parent if isinstance(anchor.parent, Tag) else None


def parse_market_records_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    grouped: dict[str, dict[str, Any]] = {}
    for anchor in soup.select("a[href*='/api/receipts/']"):
        href = _absolute_rewe_url(str(anchor.get("href") or ""))
        receipt_id = _receipt_id_from_url(href)
        if not receipt_id:
            continue
        card = _nearest_receipt_card(anchor, receipt_id)
        group = grouped.setdefault(receipt_id, {"receiptId": receipt_id, "card": card, "pdfUrl": "", "csvUrl": ""})
        if group.get("card") is None and card is not None:
            group["card"] = card
        if href.lower().endswith("/pdf") or "/pdf?" in href.lower():
            group["pdfUrl"] = href
        if href.lower().endswith("/csv") or "/csv?" in href.lower():
            group["csvUrl"] = href

    records: list[dict[str, Any]] = []
    for receipt_id, group in grouped.items():
        card = group.get("card")
        lines = _tag_text_lines(card if isinstance(card, Tag) else None)
        text = _normalize_text(" ".join(lines))
        date_match = _DATE_TIME_RE.search(text)
        store_name = _first_heading_text(card if isinstance(card, Tag) else None) or (lines[0] if lines else "")
        store_address = ""
        for index, line in enumerate(lines):
            if re.search(r"\d{5}\s+[A-Za-zÄÖÜäöüß]", line):
                previous_line = lines[index - 1] if index > 0 else ""
                if index > 0 and not _DATE_TIME_RE.search(previous_line) and previous_line.lower() != "uhr":
                    store_address = f"{lines[index - 1]}, {line}"
                else:
                    store_address = line
                break
        records.append(
            {
                "recordRef": f"market:{receipt_id}",
                "channel": "market",
                "receiptId": receipt_id,
                "purchasedAtText": date_match.group("date") if date_match else "",
                "purchasedTimeText": date_match.group("time") if date_match else "",
                "totalAmount": _infer_total_amount(lines, text),
                "currency": "EUR",
                "storeName": store_name,
                "storeAddress": store_address,
                "pdfUrl": str(group.get("pdfUrl") or ""),
                "csvUrl": str(group.get("csvUrl") or ""),
                "rawText": text,
                "rawLines": lines,
            }
        )
    return records


def parse_online_records_html(html: str, *, page_url: str = REWE_ONLINE_PURCHASES_URL) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in soup.find_all(["article", "li", "section", "div"]):
        if not isinstance(card, Tag):
            continue
        text = _normalize_text(card.get_text(" ", strip=True))
        if not text or len(text) > 6000:
            continue
        if not re.search(r"(bestell|liefer|abhol|rechnung|invoice|auftrag)", text, re.IGNORECASE):
            continue
        hrefs = [
            _absolute_rewe_url(str(anchor.get("href") or ""), base_url=page_url)
            for anchor in card.select("a[href]")
            if str(anchor.get("href") or "").strip()
        ]
        details_url = next(
            (
                href
                for href in hrefs
                if not re.search(r"/pdf(?:$|\?)|/csv(?:$|\?)|\.pdf(?:$|\?)", href, re.IGNORECASE)
                and re.search(r"bestell|order|rechnung|invoice|details", href, re.IGNORECASE)
            ),
            "",
        )
        if not details_url:
            details_url = next(
                (
                    href
                    for href in hrefs
                    if not re.search(r"/pdf(?:$|\?)|/csv(?:$|\?)|\.pdf(?:$|\?)", href, re.IGNORECASE)
                    and _parse_order_id_from_url(href)
                ),
                "",
            )
        order_id = _parse_order_id_from_url(details_url) or _parse_order_id_from_text(text)
        if not order_id or order_id in seen:
            continue
        seen.add(order_id)
        date_match = _DATE_TIME_RE.search(text)
        item_texts = []
        for node in card.select("li, tr, [class*='item'], [class*='product']"):
            if not isinstance(node, Tag):
                continue
            line = _normalize_text(node.get_text(" ", strip=True))
            if line and len(line) <= 240:
                item_texts.append(line)
        records.append(
            {
                "recordRef": f"online:{order_id}",
                "channel": "online",
                "orderId": order_id,
                "purchasedAtText": date_match.group("date") if date_match else "",
                "purchasedTimeText": date_match.group("time") if date_match else "",
                "totalAmount": _infer_total_amount(_tag_text_lines(card), text),
                "currency": "EUR",
                "statusText": text,
                "detailsUrl": details_url,
                "pdfUrls": [
                    href
                    for href in hrefs
                    if re.search(r"/pdf(?:$|\?)|\.pdf(?:$|\?)|rechnung|invoice", href, re.IGNORECASE)
                ],
                "rawText": text,
                "itemTexts": item_texts[:60],
            }
        )
    return records


def parse_online_detail_html(html: str, *, details_url: str = "") -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    raw_text = _normalize_text(soup.get_text("\n", strip=True))
    body_like = soup.body if isinstance(soup.body, Tag) else None
    all_lines = _tag_text_lines(body_like)
    item_texts: list[str] = []
    for node in soup.select("li, tr, [class*='item'], [class*='line'], [class*='product']"):
        if not isinstance(node, Tag):
            continue
        line = _normalize_text(node.get_text(" ", strip=True))
        if line and len(line) <= 240:
            item_texts.append(line)
    hrefs = [
        _absolute_rewe_url(str(anchor.get("href") or ""), base_url=details_url or REWE_BASE_URL)
        for anchor in soup.select("a[href]")
        if str(anchor.get("href") or "").strip()
    ]
    date_match = _DATE_TIME_RE.search(raw_text)
    return {
        "rawText": raw_text,
        "itemTexts": item_texts[:120],
        "hrefs": hrefs,
        "pdfUrls": [href for href in hrefs if re.search(r"/pdf(?:$|\?)|\.pdf(?:$|\?)", href, re.IGNORECASE)],
        "totalAmount": _infer_total_amount(all_lines or item_texts, raw_text),
        "purchasedAtText": date_match.group("date") if date_match else "",
        "purchasedTimeText": date_match.group("time") if date_match else "",
    }


def _storage_state_to_httpx_cookies(storage_state: dict[str, Any]) -> httpx.Cookies:
    cookies = httpx.Cookies()
    for cookie in storage_state.get("cookies", []):
        if not isinstance(cookie, dict):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").strip() or None
        path = str(cookie.get("path") or "/")
        if not name:
            continue
        cookies.set(name, value, domain=domain, path=path)
    return cookies


def _storage_state_with_httpx_cookies(storage_state: dict[str, Any], cookie_jar: Any) -> dict[str, Any]:
    updated = dict(storage_state)
    cookies: list[dict[str, Any]] = []
    for cookie in getattr(cookie_jar, "jar", ()):
        domain = str(getattr(cookie, "domain", "") or "")
        if not _looks_like_rewe_cookie_domain(domain):
            continue
        name = str(getattr(cookie, "name", "") or "").strip()
        if not name:
            continue
        raw_rest = getattr(cookie, "_rest", {}) or {}
        http_only = any(str(key).lower() == "httponly" for key in raw_rest.keys())
        payload: dict[str, Any] = {
            "name": name,
            "value": str(getattr(cookie, "value", "") or ""),
            "domain": domain,
            "path": str(getattr(cookie, "path", "/") or "/"),
            "secure": bool(getattr(cookie, "secure", False)),
            "httpOnly": http_only,
            "expires": int(getattr(cookie, "expires", -1) or -1),
        }
        cookies.append(payload)
    if cookies:
        updated["cookies"] = cookies
    origins = updated.get("origins")
    if not isinstance(origins, list):
        updated["origins"] = []
    return updated


def _sec_ch_ua_from_user_agent(user_agent: str) -> str:
    match = re.search(r"Chrome/(\d+)", user_agent)
    major = match.group(1) if match else "123"
    return f'"Google Chrome";v="{major}", "Chromium";v="{major}", "Not=A?Brand";v="24"'


def _document_request_headers(
    user_agent: str,
    *,
    referer: str | None = None,
    sec_fetch_site: str = "none",
) -> dict[str, str]:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Cache-Control": "max-age=0",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": sec_fetch_site,
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": _sec_ch_ua_from_user_agent(user_agent),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _response_title_text_and_url(response: httpx.Response) -> tuple[str, str, str]:
    html = response.text
    soup = BeautifulSoup(html, "lxml")
    title = _normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    text = _normalize_text(soup.get_text(" ", strip=True))
    return title, text[:4000], str(response.url)


def _ensure_not_bot_challenged_response(response: httpx.Response) -> None:
    title, text, url = _response_title_text_and_url(response)
    if looks_like_rewe_bot_challenge(url=url, title=title, text=text):
        raise ReweClientError(
            "REWE bot protection blocked the current session while resolving the account page."
        )


def _continue_sso_if_needed(client: httpx.Client, response: httpx.Response, *, target_url: str) -> httpx.Response:
    _ensure_not_bot_challenged_response(response)
    current_url = str(response.url)
    if "account.rewe.de" not in current_url.lower():
        return response
    soup = BeautifulSoup(response.text, "lxml")
    page_text = _normalize_text(soup.get_text(" ", strip=True))
    form = soup.find("form")
    action = str(form.get("action") or "").strip() if isinstance(form, Tag) else ""
    if action and "Weiter mit diesem REWE Konto" in page_text:
        user_agent = str(client.headers.get("User-Agent") or DEFAULT_REWE_USER_AGENT)
        continued = client.post(
            _absolute_rewe_url(action, base_url=current_url),
            headers=_document_request_headers(
                user_agent,
                referer=current_url,
                sec_fetch_site="same-origin",
            ),
        )
        _ensure_not_bot_challenged_response(continued)
        if str(continued.url) != target_url:
            continued = client.get(target_url, headers=_document_request_headers(user_agent))
            _ensure_not_bot_challenged_response(continued)
        return continued
    return response


def verify_and_refresh_rewe_http_storage_state(
    storage_state: dict[str, Any],
    *,
    start_url: str = REWE_MARKET_PURCHASES_URL,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    client = httpx.Client(
        follow_redirects=True,
        timeout=max(5, timeout_seconds),
        cookies=_storage_state_to_httpx_cookies(storage_state),
        headers={
            "User-Agent": str(storage_state.get("user_agent") or DEFAULT_REWE_USER_AGENT),
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
        },
    )
    try:
        user_agent = str(storage_state.get("user_agent") or DEFAULT_REWE_USER_AGENT)
        response = client.get(start_url, headers=_document_request_headers(user_agent))
        response = _continue_sso_if_needed(client, response, target_url=start_url)
        _ensure_not_bot_challenged_response(response)
        if _looks_like_login_or_auth_url(str(response.url)):
            raise ReweReauthRequiredError(
                "REWE imported browser session did not reach the authenticated account area."
            )
        return _storage_state_with_httpx_cookies(storage_state, client.cookies)
    finally:
        client.close()


class RewePlaywrightClient:
    def __init__(
        self,
        *,
        state_file: Path,
        headless: bool = True,
        max_records: int = 250,
        detail_fetch_limit: int = 25,
        http_timeout_seconds: int = 30,
        persist_state_on_success: bool = True,
        dump_html_dir: Path | None = None,
    ) -> None:
        self._state_file = state_file
        self._headless = headless
        self._max_records = max(1, max_records)
        self._detail_fetch_limit = detail_fetch_limit
        self._http_timeout_seconds = max(5, http_timeout_seconds)
        self._persist_state_on_success = persist_state_on_success
        self._dump_html_dir = dump_html_dir

    def fetch_records(self) -> list[dict[str, Any]]:
        with self._authenticated_http_client() as client:
            records = []
            records.extend(self._collect_market_records(client))
            records.extend(self._collect_online_records(client))
        return records[: self._max_records]

    def fetch_record_detail(self, record_ref: str, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_summary = summary or self._find_record(record_ref)
        channel = str(resolved_summary.get("channel") or "")
        with self._authenticated_http_client() as client:
            bonus_transactions = self._fetch_bonus_transactions(client)
            bonus_match = match_bonus_transactions(
                record_ref=record_ref,
                receipt_id=str(
                    resolved_summary.get("receiptId")
                    or resolved_summary.get("orderId")
                    or resolved_summary.get("recordRef")
                    or ""
                )
                or None,
                purchased_at=str(resolved_summary.get("purchasedAt") or ""),
                store_name=str(resolved_summary.get("storeName") or ""),
                transactions=bonus_transactions,
            )
            if channel == "market":
                csv_payload = None
                pdf_payload = None
                csv_url = str(resolved_summary.get("csvUrl") or "")
                pdf_url = str(resolved_summary.get("pdfUrl") or "")
                if csv_url:
                    try:
                        csv_payload = parse_market_csv_payload(self._download_bytes(client, csv_url))
                    except Exception:
                        csv_payload = None
                if pdf_url:
                    try:
                        pdf_payload = parse_rewe_pdf_bytes(self._download_bytes(client, pdf_url))
                    except Exception:
                        pdf_payload = None
                return build_market_record_detail(
                    summary=resolved_summary,
                    csv_payload=csv_payload,
                    pdf_payload=pdf_payload,
                    bonus_match=bonus_match,
                )
            if channel == "online":
                detail_payload = self._fetch_online_detail(client, resolved_summary)
                return build_online_record_detail(
                    summary=resolved_summary,
                    detail_payload=detail_payload,
                    bonus_match=bonus_match,
                )
            raise ReweClientError(f"unsupported REWE record channel for {record_ref}")

    def fetch_receipts(self) -> list[dict[str, Any]]:
        """Legacy helper kept so older tests can still monkeypatch a simple fake client."""
        return list(self.fetch_records())

    def _find_record(self, record_ref: str) -> dict[str, Any]:
        for record in self.fetch_records():
            if str(record.get("recordRef") or "") == record_ref:
                return record
        raise ReweClientError(f"REWE record not found for record_ref={record_ref}")

    def _collect_market_records(self, client: httpx.Client) -> list[dict[str, Any]]:
        response = self._authenticated_get(client, REWE_MARKET_PURCHASES_URL)
        self._dump_html("market", response.text)
        raw_records = parse_market_records_html(response.text)
        records: list[dict[str, Any]] = []
        for raw in raw_records if isinstance(raw_records, list) else []:
            if not isinstance(raw, dict):
                continue
            purchased_at = _parse_de_datetime(
                str(raw.get("purchasedAtText") or ""),
                str(raw.get("purchasedTimeText") or ""),
            )
            normalized = dict(raw)
            normalized["purchasedAt"] = purchased_at
            normalized["totalGrossCents"] = abs(_to_cents(raw.get("totalAmount")))
            records.append(normalized)
        return records

    def _collect_online_records(self, client: httpx.Client) -> list[dict[str, Any]]:
        response = self._authenticated_get(client, REWE_ONLINE_PURCHASES_URL)
        self._dump_html("online", response.text)
        raw_records = parse_online_records_html(response.text, page_url=str(response.url))
        records: list[dict[str, Any]] = []
        for raw in raw_records if isinstance(raw_records, list) else []:
            if not isinstance(raw, dict):
                continue
            purchased_at = _parse_de_datetime(
                str(raw.get("purchasedAtText") or ""),
                str(raw.get("purchasedTimeText") or ""),
            )
            normalized = dict(raw)
            normalized["purchasedAt"] = purchased_at
            normalized["totalGrossCents"] = abs(_to_cents(raw.get("totalAmount")))
            records.append(normalized)
        return records

    def _fetch_online_detail(self, client: httpx.Client, summary: dict[str, Any]) -> dict[str, Any]:
        details_url = str(summary.get("detailsUrl") or "")
        if not details_url:
            return {}
        response = self._authenticated_get(client, details_url)
        self._dump_html("online-detail", response.text)
        payload = parse_online_detail_html(response.text, details_url=str(response.url))
        return payload if isinstance(payload, dict) else {}

    def _fetch_bonus_transactions(self, client: httpx.Client) -> list[dict[str, Any]]:
        try:
            response = self._authenticated_get(client, REWE_BONUS_TRANSACTIONS_URL)
            if response.status_code == 200:
                payload = response.json()
                return parse_bonus_transactions_payload(payload)
        except Exception:
            return []
        return []

    def _download_bytes(self, client: httpx.Client, url: str) -> bytes:
        response = self._authenticated_get(client, url)
        response.raise_for_status()
        return response.content

    def _load_storage_state(self) -> dict[str, Any]:
        if not self._state_file.exists():
            raise ReweReauthRequiredError(
                f"REWE session state missing: {self._state_file}. "
                "Run 'lidltool connectors auth bootstrap --source-id rewe_de' first."
            )
        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ReweReauthRequiredError(
                f"REWE session state is invalid JSON: {self._state_file}"
            ) from exc
        if not isinstance(payload, dict):
            raise ReweReauthRequiredError(
                f"REWE session state must be a JSON object: {self._state_file}"
            )
        cookies = payload.get("cookies")
        if not isinstance(cookies, list) or len(cookies) == 0:
            raise ReweReauthRequiredError(
                f"REWE session state contains no cookies: {self._state_file}"
            )
        return payload

    def _user_agent_for_storage_state(self, storage_state: dict[str, Any]) -> str:
        raw_value = storage_state.get("user_agent")
        if isinstance(raw_value, str) and raw_value.strip():
            return raw_value.strip()
        return DEFAULT_REWE_USER_AGENT

    @contextmanager
    def _authenticated_http_client(self) -> Iterator[httpx.Client]:
        storage_state = self._load_storage_state()
        client = httpx.Client(
            follow_redirects=True,
            timeout=self._http_timeout_seconds,
            cookies=_storage_state_to_httpx_cookies(storage_state),
            headers={
                "User-Agent": self._user_agent_for_storage_state(storage_state),
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )
        try:
            self._authenticated_get(client, REWE_MARKET_PURCHASES_URL)
            yield client
        finally:
            if self._persist_state_on_success:
                self._persist_http_storage_state(storage_state, client)
            client.close()

    def _persist_http_storage_state(self, storage_state: dict[str, Any], client: httpx.Client) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        refreshed = _storage_state_with_httpx_cookies(storage_state, client.cookies)
        self._state_file.write_text(
            json.dumps(refreshed, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _authenticated_get(self, client: httpx.Client, url: str) -> httpx.Response:
        user_agent = str(client.headers.get("User-Agent") or DEFAULT_REWE_USER_AGENT)
        request_headers = _document_request_headers(user_agent) if not re.search(r"/api/|\.pdf(?:$|\?)", url, re.IGNORECASE) else None
        response = client.get(url, headers=request_headers)
        response = _continue_sso_if_needed(client, response, target_url=url)
        _ensure_not_bot_challenged_response(response)
        if _looks_like_login_or_auth_url(str(response.url)):
            raise ReweReauthRequiredError(
                "REWE session expired or did not reach the authenticated account area. "
                "Run 'lidltool connectors auth bootstrap --source-id rewe_de' again."
            )
        return response

    def _dump_html(self, stem: str, html: str) -> None:
        if self._dump_html_dir is None:
            return
        self._dump_html_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        (self._dump_html_dir / f"{stem}-{timestamp}.html").write_text(str(html), encoding="utf-8")


class ReweChromeLiveTabClient:
    """Use the already-authenticated normal Chrome REWE tab directly via Apple Events."""

    def __init__(
        self,
        *,
        max_records: int = 250,
        detail_fetch_limit: int = 25,
    ) -> None:
        self._max_records = max(1, max_records)
        self._detail_fetch_limit = detail_fetch_limit

    def fetch_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        records.extend(self._collect_market_records())
        records.extend(self._collect_online_records())
        return records[: self._max_records]

    def fetch_record_detail(self, record_ref: str, *, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_summary = summary or self._find_record(record_ref)
        channel = str(resolved_summary.get("channel") or "")
        bonus_transactions = self._fetch_bonus_transactions()
        bonus_match = match_bonus_transactions(
            record_ref=record_ref,
            receipt_id=str(
                resolved_summary.get("receiptId")
                or resolved_summary.get("orderId")
                or resolved_summary.get("recordRef")
                or ""
            )
            or None,
            purchased_at=str(resolved_summary.get("purchasedAt") or ""),
            store_name=str(resolved_summary.get("storeName") or ""),
            transactions=bonus_transactions,
        )
        if channel == "market":
            csv_payload = None
            pdf_payload = None
            csv_url = str(resolved_summary.get("csvUrl") or "")
            pdf_url = str(resolved_summary.get("pdfUrl") or "")
            if csv_url:
                try:
                    csv_payload = parse_market_csv_payload(self._download_bytes(csv_url))
                except Exception:
                    csv_payload = None
            if pdf_url:
                try:
                    pdf_payload = parse_rewe_pdf_bytes(self._download_bytes(pdf_url))
                except Exception:
                    pdf_payload = None
            return build_market_record_detail(
                summary=resolved_summary,
                csv_payload=csv_payload,
                pdf_payload=pdf_payload,
                bonus_match=bonus_match,
            )
        if channel == "online":
            detail_payload = self._fetch_online_detail(resolved_summary)
            return build_online_record_detail(
                summary=resolved_summary,
                detail_payload=detail_payload,
                bonus_match=bonus_match,
            )
        raise ReweClientError(f"unsupported REWE record channel for {record_ref}")

    def fetch_receipts(self) -> list[dict[str, Any]]:
        return list(self.fetch_records())

    def _find_record(self, record_ref: str) -> dict[str, Any]:
        for record in self.fetch_records():
            if str(record.get("recordRef") or "") == record_ref:
                return record
        raise ReweClientError(f"REWE record not found for record_ref={record_ref}")

    def _collect_market_records(self) -> list[dict[str, Any]]:
        raw_records = _evaluate_rewe_chrome_json(
            f"JSON.stringify(({_MARKET_LIST_SCRIPT})())",
            navigate_url=REWE_MARKET_PURCHASES_URL,
            restore_original_url=True,
        )
        records: list[dict[str, Any]] = []
        for raw in raw_records if isinstance(raw_records, list) else []:
            if not isinstance(raw, dict):
                continue
            purchased_at = _parse_de_datetime(
                str(raw.get("purchasedAtText") or ""),
                str(raw.get("purchasedTimeText") or ""),
            )
            normalized = dict(raw)
            normalized["purchasedAt"] = purchased_at
            normalized["totalGrossCents"] = abs(_to_cents(raw.get("totalAmount")))
            records.append(normalized)
        return records

    def _collect_online_records(self) -> list[dict[str, Any]]:
        raw_records = _evaluate_rewe_chrome_json(
            f"JSON.stringify(({_ONLINE_LIST_SCRIPT})())",
            navigate_url=REWE_ONLINE_PURCHASES_URL,
            restore_original_url=True,
        )
        records: list[dict[str, Any]] = []
        for raw in raw_records if isinstance(raw_records, list) else []:
            if not isinstance(raw, dict):
                continue
            purchased_at = _parse_de_datetime(
                str(raw.get("purchasedAtText") or ""),
                str(raw.get("purchasedTimeText") or ""),
            )
            normalized = dict(raw)
            normalized["purchasedAt"] = purchased_at
            normalized["totalGrossCents"] = abs(_to_cents(raw.get("totalAmount")))
            records.append(normalized)
        return records

    def _fetch_online_detail(self, summary: dict[str, Any]) -> dict[str, Any]:
        details_url = str(summary.get("detailsUrl") or "")
        if not details_url:
            return {}
        payload = _evaluate_rewe_chrome_json(
            f"JSON.stringify(({_ONLINE_DETAIL_SCRIPT})())",
            navigate_url=details_url,
            restore_original_url=True,
            wait_after_navigation_seconds=2.0,
        )
        return payload if isinstance(payload, dict) else {}

    def _fetch_bonus_transactions(self) -> list[dict[str, Any]]:
        try:
            payload = _evaluate_rewe_chrome_json(
                _sync_xhr_json_script(REWE_BONUS_TRANSACTIONS_URL),
                navigate_url=REWE_MARKET_PURCHASES_URL,
                restore_original_url=False,
                wait_after_navigation_seconds=0.4,
            )
        except Exception:
            return []
        if not isinstance(payload, dict) or int(payload.get("status", 0) or 0) != 200:
            return []
        try:
            response_payload = json.loads(str(payload.get("responseText") or ""))
        except json.JSONDecodeError:
            return []
        return parse_bonus_transactions_payload(response_payload)

    def _download_bytes(self, url: str) -> bytes:
        payload = _evaluate_rewe_chrome_json(
            _sync_xhr_base64_script(url),
            navigate_url=REWE_MARKET_PURCHASES_URL,
            restore_original_url=False,
            wait_after_navigation_seconds=0.4,
        )
        if not isinstance(payload, dict):
            raise ReweClientError(f"REWE live Chrome download returned invalid payload for {url}")
        status = int(payload.get("status", 0) or 0)
        if status != 200:
            raise ReweClientError(f"REWE live Chrome download failed for {url} with status {status}")
        base64_payload = str(payload.get("base64") or "")
        if not base64_payload:
            return b""
        return base64.b64decode(base64_payload)
