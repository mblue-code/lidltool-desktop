from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, sync_playwright


class DmClientError(RuntimeError):
    pass


class DmReauthRequiredError(DmClientError):
    pass


_DE_MONTH_MAP: dict[str, int] = {
    "januar": 1,
    "jan": 1,
    "january": 1,
    "februar": 2,
    "feb": 2,
    "february": 2,
    "maerz": 3,
    "marz": 3,
    "mar": 3,
    "march": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "juni": 6,
    "jun": 6,
    "june": 6,
    "juli": 7,
    "jul": 7,
    "july": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "oct": 10,
    "october": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
    "dec": 12,
    "december": 12,
}

_PROMOTION_KEYWORDS = (
    "payback",
    "coupon",
    "gutschein",
    "rabatt",
    "bonus",
    "vorteil",
    "dm-app",
    "app-coupon",
    "app coupon",
    "punkte",
    "spar",
)

_PROMOTION_RE = re.compile(
    r"(?i)"
    r"((?:payback|coupon|gutschein|rabatt|bonus|vorteil|dm-app|app(?:-|\s)?coupon|punkte|spar"
    r")[^\n\r]{0,120}?)"
    r"\s*[:\-]?\s*"
    r"(-?(?:\d{1,3}(?:[\.\s]\d{3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})))"
)

_AMOUNT_RE = re.compile(r"-?(?:\d{1,3}(?:[\.\s]\d{3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2}))")
_QTY_X_RE = re.compile(r"(?i)(\d+(?:[\.,]\d+)?)\s*[x\u00d7]")
_QTY_WORD_RE = re.compile(r"(?i)(?:menge|anzahl|qty|stk|stueck|stuck|pcs)\s*[:\-]?\s*(\d+(?:[\.,]\d+)?)")
_DISCOUNT_RE = re.compile(
    r"(?i)(?:rabatt|coupon|gutschein|bonus|vorteil|payback|dm-app|punkte|spar)"
    r"[^\n\r]{0,120}?(-?(?:\d{1,3}(?:[\.\s]\d{3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})))"
)

_ORDER_ID_TEXT_RE = re.compile(
    r"(?i)(?:bestell(?:ung|nummer)?|auftragsnummer|order(?:\s*id)?|beleg(?:nr|nummer)?)"
    r"\s*[:#-]?\s*([a-z0-9][a-z0-9-]{5,})"
)
_ORDER_ID_FALLBACK_RE = re.compile(r"\b([A-Z]{2,8}-[A-Z0-9-]{3,})\b")

_NON_ITEM_MARKERS = (
    "bestell",
    "auftrag",
    "order",
    "liefer",
    "versand",
    "gesamtsumme",
    "summe",
    "gesamt",
    "zwischensumme",
    "status",
    "zahl",
    "adresse",
    "rechnung",
)

_REAUTH_URL_PATTERNS = (
    "signin.dm.de",
    "/authentication/web-login",
    "/service/login",
    "/login",
    "/anmeldung",
    "/auth",
)

_DM_ACCOUNT_PURCHASES_URL = "https://account.dm.de/purchases"
_DM_EBON_API_URL_TEMPLATE = "https://ebon-prod.services.dmtech.com/api/customer/ebons/{ebon_id}"
_EBON_ID_RE = re.compile(r"/ebons/([0-9a-fA-F-]{8,})")
_DM_DOWNLOAD_URL_TOKEN = "/api/customer/ebons/"

_RECEIPT_ITEM_RE = re.compile(
    r"^(?P<title>.+?)\s+(?P<amount>\d{1,3}(?:\.\d{3})*,\d{2})(?:\s+\d+)?$"
)
_RECEIPT_DISCOUNT_RE = re.compile(
    r"^(?P<description>.+?)\s+(?P<amount>-\d{1,3}(?:\.\d{3})*,\d{2})$"
)
_RECEIPT_TOTAL_RE = re.compile(r"(?i)^summe\s+eur\s+(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})$")
_RECEIPT_DATE_RE = re.compile(r"\b(?P<date>\d{2}\.\d{2}\.\d{4})\b")

_RECEIPT_NON_ITEM_PREFIXES = (
    "zwischensumme",
    "summe eur",
    "mastercard",
    "visa",
    "ec-karte",
    "kartenzahlung",
    "mwst-satz",
    "terminal-id",
    "ta-nr",
    "start:",
    "ende:",
    "sn-kasse",
    "sn-tse",
    "signaturzähler",
    "für diesen einkauf",
    "du sammelst",
    "öffnungszeiten",
    "steuer-nr",
    "fiskalinformationen",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _normalize_for_date(value: str) -> str:
    lowered = value.lower()
    lowered = lowered.replace("\u00e4", "ae").replace("\u00f6", "oe").replace("\u00fc", "ue")
    lowered = lowered.replace("\u00df", "ss")
    return lowered


def _parse_dm_amount(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    text = value.strip()
    if not text:
        return 0.0
    match = _AMOUNT_RE.search(text.replace("\xa0", " "))
    if not match:
        return 0.0
    raw = match.group(0)
    sign = -1.0 if raw.strip().startswith("-") else 1.0
    digits = raw.replace("-", "")
    digits = re.sub(r"(?<=\d)[\.\s](?=\d{3}(?:[\.,]|$))", "", digits)
    digits = digits.replace(" ", "").replace(",", ".")
    try:
        return sign * float(digits)
    except ValueError:
        return 0.0


def _extract_amounts(value: str) -> list[float]:
    amounts: list[float] = []
    for token in _AMOUNT_RE.findall(value):
        parsed = _parse_dm_amount(token)
        if parsed == 0.0:
            continue
        amounts.append(abs(parsed))
    return amounts


def _extract_quantity(value: str) -> float:
    for pattern in (_QTY_X_RE, _QTY_WORD_RE):
        match = pattern.search(value)
        if not match:
            continue
        raw = match.group(1).replace(",", ".")
        try:
            quantity = float(raw)
        except ValueError:
            continue
        if quantity > 0:
            return quantity
    return 1.0


def _extract_order_id_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("orderId", "orderID", "order_id", "bestellung", "bestellnummer", "id"):
        values = query.get(key)
        if not values:
            continue
        candidate = str(values[0]).strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{5,}", candidate):
            return candidate
    for segment in reversed([s for s in parsed.path.split("/") if s]):
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{5,}", segment):
            return segment
    return None


def _extract_order_id(text: str, details_url: str = "") -> str | None:
    url_candidate = _extract_order_id_from_url(details_url)
    if url_candidate:
        return url_candidate

    from_text = _ORDER_ID_TEXT_RE.search(text)
    if from_text:
        return from_text.group(1)

    fallback = _ORDER_ID_FALLBACK_RE.search(text)
    if fallback:
        return fallback.group(1)

    return None


def _extract_ebon_id(value: str) -> str | None:
    if not value:
        return None
    match = _EBON_ID_RE.search(value)
    if match:
        return match.group(1)
    if re.fullmatch(r"[0-9a-fA-F-]{8,}", value.strip()):
        return value.strip()
    return None


def _parse_api_amount(value: Any) -> float:
    if isinstance(value, int):
        return abs(float(value)) / 100.0
    if isinstance(value, float):
        if value.is_integer() and abs(value) >= 100:
            return abs(value) / 100.0
        return abs(value)
    return abs(_parse_dm_amount(value))


def _extract_discount_amount(text: str) -> float:
    match = _DISCOUNT_RE.search(text)
    if not match:
        return 0.0
    amount = abs(_parse_dm_amount(match.group(1)))
    return amount if amount > 0 else 0.0


def _cleanup_item_title(text: str) -> str:
    cleaned = _normalize_text(text)
    cleaned = re.sub(r"(?i)\b(?:menge|anzahl|qty|stk|stueck|stuck|pcs)\b", " ", cleaned)
    cleaned = re.sub(r"(?i)\d+(?:[\.,]\d+)?\s*[x\u00d7]", " ", cleaned)
    cleaned = re.sub(r"(?i)(?:EUR|\u20ac)", " ", cleaned)
    cleaned = _AMOUNT_RE.sub(" ", cleaned)
    cleaned = re.sub(
        r"(?i)\b(?:rabatt|coupon|gutschein|bonus|vorteil|payback|dm-app|app-coupon|punkte|spar(?:preis|angebot|en)?)\b",
        " ",
        cleaned,
    )
    cleaned = _normalize_text(cleaned)
    cleaned = cleaned.strip("-:|,")
    return cleaned


def _looks_like_non_item(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _NON_ITEM_MARKERS)


def _parse_dm_item_text(text: str) -> dict[str, Any] | None:
    normalized = _normalize_text(text)
    if not normalized or len(normalized) > 240:
        return None
    if _looks_like_non_item(normalized):
        return None

    quantity = _extract_quantity(normalized)
    amounts = _extract_amounts(normalized)
    discount = _extract_discount_amount(normalized)

    line_total = amounts[-1] if amounts else 0.0
    if discount > 0 and line_total >= discount and len(amounts) >= 2:
        line_total = amounts[-2]

    if quantity > 0 and line_total > 0:
        price = round(line_total / quantity, 2)
    elif amounts:
        price = amounts[0]
    else:
        price = 0.0

    title = _cleanup_item_title(normalized)
    if not title:
        return None

    return {
        "title": title,
        "quantity": quantity if quantity > 0 else 1.0,
        "price": round(max(price, 0.0), 2),
        "lineTotal": round(max(line_total, 0.0), 2) if line_total > 0 else 0.0,
        "discount": round(discount, 2) if discount > 0 else 0.0,
        "rawText": normalized,
    }


def _merge_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        title = _normalize_text(str(raw.get("title") or ""))
        if not title:
            continue
        quantity_raw = raw.get("quantity") or raw.get("qty") or "1"
        if isinstance(quantity_raw, (int, float)):
            quantity = float(quantity_raw)
        else:
            raw_quantity_text = str(quantity_raw).strip()
            try:
                quantity = float(raw_quantity_text.replace(",", "."))
            except ValueError:
                quantity = _extract_quantity(raw_quantity_text)
        if quantity <= 0:
            quantity = 1.0
        price = abs(_parse_dm_amount(str(raw.get("price") or "")))
        line_total = abs(_parse_dm_amount(str(raw.get("lineTotal") or "")))
        discount = abs(_parse_dm_amount(str(raw.get("discount") or "")))
        if line_total <= 0 and price > 0:
            line_total = round(price * quantity, 2)
        if price <= 0 and line_total > 0 and quantity > 0:
            price = round(line_total / quantity, 2)

        key = (title.lower(), int(round(price * 100)))
        existing = by_key.get(key)
        if existing is None:
            row = {
                "title": title,
                "quantity": quantity,
                "price": round(max(price, 0.0), 2),
                "lineTotal": round(max(line_total, 0.0), 2),
                "discount": round(max(discount, 0.0), 2),
            }
            by_key[key] = row
            merged.append(row)
            continue

        existing["quantity"] = round(float(existing.get("quantity", 1.0)) + quantity, 3)
        existing["lineTotal"] = round(float(existing.get("lineTotal", 0.0)) + line_total, 2)
        existing["discount"] = round(float(existing.get("discount", 0.0)) + discount, 2)
        if float(existing.get("price", 0.0)) <= 0 and price > 0:
            existing["price"] = round(price, 2)

    priced_titles: set[str] = set()
    for row in merged:
        title = str(row.get("title") or "").strip().lower()
        if not title:
            continue
        if float(row.get("price", 0.0) or 0.0) > 0 or float(row.get("lineTotal", 0.0) or 0.0) > 0:
            priced_titles.add(title)

    filtered: list[dict[str, Any]] = []
    for row in merged:
        title = str(row.get("title") or "").strip().lower()
        if title in priced_titles:
            if float(row.get("price", 0.0) or 0.0) <= 0 and float(row.get("lineTotal", 0.0) or 0.0) <= 0:
                continue
        filtered.append(row)
    return filtered


def _extract_total_amount(total_text: str, raw_text: str) -> float:
    for source_text in (_normalize_text(total_text), _normalize_text(raw_text)):
        if not source_text:
            continue
        for chunk in re.split(r"[|\n\r]+", source_text):
            lowered = chunk.lower()
            if not any(keyword in lowered for keyword in ("gesamt", "summe", "total", "betrag")):
                continue
            amounts = _extract_amounts(chunk)
            if amounts:
                return round(max(amounts), 2)

    raw_amounts = _extract_amounts(raw_text)
    if raw_amounts:
        return round(max(raw_amounts), 2)
    return 0.0


def _extract_order_status(text: str) -> str:
    lowered = text.lower()
    if "geliefert" in lowered or "delivered" in lowered:
        return "Delivered"
    if "versandt" in lowered or "shipped" in lowered:
        return "Shipped"
    if "storniert" in lowered or "cancel" in lowered:
        return "Canceled"
    if "in bearbeitung" in lowered or "processing" in lowered:
        return "Processing"
    return ""


def _normalize_scraped_order(raw: dict[str, Any]) -> dict[str, Any] | None:
    details_url = str(raw.get("detailsUrl") or "").strip()
    raw_text = _normalize_text(str(raw.get("rawText") or ""))
    total_text = _normalize_text(str(raw.get("totalText") or ""))

    order_id = str(raw.get("orderId") or "").strip() or (_extract_order_id(raw_text, details_url) or "")
    if not order_id:
        return None

    order_date = str(raw.get("orderDate") or "").strip()
    if not order_date:
        date_match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", raw_text)
        if date_match:
            order_date = date_match.group(1)

    total_amount_raw = _parse_dm_amount(raw.get("totalAmount") or "")
    total_amount = abs(total_amount_raw) if total_amount_raw != 0 else _extract_total_amount(total_text, raw_text)

    parsed_items: list[dict[str, Any]] = []
    incoming_items = raw.get("items")
    if isinstance(incoming_items, list):
        for entry in incoming_items:
            if not isinstance(entry, dict):
                continue
            title = _normalize_text(str(entry.get("title") or entry.get("name") or ""))
            if not title and isinstance(entry.get("rawText"), str):
                parsed = _parse_dm_item_text(str(entry.get("rawText") or ""))
                if parsed is not None:
                    parsed_items.append(parsed)
                continue
            parsed_items.append(
                {
                    "title": title,
                    "quantity": entry.get("quantity") or entry.get("qty") or 1,
                    "price": entry.get("price") or entry.get("unitPrice") or 0,
                    "lineTotal": entry.get("lineTotal") or entry.get("total") or 0,
                    "discount": entry.get("discount") or 0,
                }
            )

    item_texts = raw.get("itemTexts")
    if isinstance(item_texts, list):
        for item_text in item_texts:
            if not isinstance(item_text, str):
                continue
            parsed = _parse_dm_item_text(item_text)
            if parsed is not None:
                parsed_items.append(parsed)

    items = _merge_items(parsed_items)

    incoming_promotions = raw.get("promotions")
    promotions: list[dict[str, Any]] = []
    if isinstance(incoming_promotions, list):
        for promo in incoming_promotions:
            if not isinstance(promo, dict):
                continue
            description = _normalize_text(str(promo.get("description") or "dm promotion"))
            amount = abs(_parse_dm_amount(promo.get("amount") or ""))
            if amount <= 0:
                continue
            promotions.append({"description": description, "amount": round(amount, 2)})

    if not promotions:
        promotions = parse_dm_promotions("\n".join([raw_text, total_text]))

    total_savings_raw = abs(_parse_dm_amount(str(raw.get("totalSavings") or "")))
    if total_savings_raw > 0:
        total_savings = total_savings_raw
    else:
        total_savings = round(sum(float(p.get("amount", 0.0) or 0.0) for p in promotions), 2)

    status = _normalize_text(str(raw.get("orderStatus") or "")) or _extract_order_status(raw_text)

    return {
        "orderId": order_id,
        "orderDate": order_date,
        "totalAmount": round(max(total_amount, 0.0), 2),
        "currency": str(raw.get("currency") or "EUR"),
        "orderStatus": status,
        "detailsUrl": details_url,
        "items": items,
        "promotions": promotions,
        "totalSavings": round(max(total_savings, 0.0), 2),
        "rawText": raw_text,
        "totalText": total_text,
    }


def _collect_item_candidates_from_api(raw_items: Any) -> tuple[list[dict[str, Any]], list[str]]:
    parsed_items: list[dict[str, Any]] = []
    item_texts: list[str] = []
    if not isinstance(raw_items, list):
        return parsed_items, item_texts

    for raw_item in raw_items:
        if isinstance(raw_item, str):
            text = _normalize_text(raw_item)
            if not text:
                continue
            parsed = _parse_dm_item_text(text)
            if parsed is not None:
                parsed_items.append(parsed)
            item_texts.append(text)
            continue
        if not isinstance(raw_item, dict):
            continue

        title = _normalize_text(
            str(
                raw_item.get("description")
                or raw_item.get("name")
                or raw_item.get("title")
                or raw_item.get("itemName")
                or raw_item.get("articleName")
                or raw_item.get("productName")
                or raw_item.get("text")
                or raw_item.get("label")
                or ""
            )
        )
        qty_raw = (
            raw_item.get("quantity")
            or raw_item.get("qty")
            or raw_item.get("count")
            or raw_item.get("amount")
            or 1
        )
        quantity = 1.0
        if isinstance(qty_raw, (int, float)):
            quantity = float(qty_raw)
        else:
            try:
                quantity = float(str(qty_raw).replace(",", "."))
            except ValueError:
                quantity = _extract_quantity(str(qty_raw))
        if quantity <= 0:
            quantity = 1.0
        unit_price = _parse_api_amount(
            raw_item.get("unitPrice")
            or raw_item.get("price")
            or raw_item.get("singlePrice")
            or raw_item.get("salesPrice")
            or raw_item.get("unit_amount")
            or 0
        )
        line_total = _parse_api_amount(
            raw_item.get("lineTotal")
            or raw_item.get("total")
            or raw_item.get("totalAmount")
            or raw_item.get("amountTotal")
            or raw_item.get("sum")
            or raw_item.get("amount")
            or 0
        )
        discount = _parse_api_amount(raw_item.get("discountAmount") or raw_item.get("discount") or 0)

        serialized = _normalize_text(
            " ".join(str(v) for v in raw_item.values() if isinstance(v, (str, int, float)))
        )
        if not title and serialized:
            parsed = _parse_dm_item_text(serialized)
            if parsed is not None:
                parsed_items.append(parsed)
                item_texts.append(parsed.get("rawText") or serialized)
                continue

        if not title:
            continue
        if line_total <= 0 and unit_price > 0:
            line_total = round(unit_price * quantity, 2)
        if unit_price <= 0 and line_total > 0 and quantity > 0:
            unit_price = round(line_total / quantity, 2)

        parsed_items.append(
            {
                "title": title,
                "quantity": quantity,
                "price": round(max(unit_price, 0.0), 2),
                "lineTotal": round(max(line_total, 0.0), 2),
                "discount": round(max(discount, 0.0), 2),
            }
        )

    return parsed_items, item_texts


def _raw_order_from_ebon_payload(payload: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    order_id = str(payload.get("id") or hint.get("orderId") or "").strip()
    details_url = str(hint.get("detailsUrl") or "")
    if not order_id:
        order_id = _extract_ebon_id(details_url) or ""

    parsed_items, item_texts = _collect_item_candidates_from_api(payload.get("bonItems"))
    api_total = _parse_api_amount(payload.get("totalAmount") or hint.get("totalAmount") or 0)
    api_discount = _parse_api_amount(payload.get("discount") or 0)

    raw_text_chunks = [
        str(payload.get("title") or ""),
        str(payload.get("address") or ""),
        str(payload.get("storeName") or ""),
        str(payload.get("merchantName") or ""),
        str(hint.get("rawText") or ""),
    ]
    raw_text = _normalize_text("\n".join(chunk for chunk in raw_text_chunks if chunk))
    total_text = _normalize_text(
        " | ".join(
            chunk
            for chunk in (
                str(payload.get("totalAmount") or ""),
                str(payload.get("discount") or ""),
                str(hint.get("totalText") or ""),
            )
            if chunk
        )
    )

    promotions = parse_dm_promotions("\n".join([raw_text, total_text, "\n".join(item_texts)]))
    promo_sum = round(sum(float(promo.get("amount", 0.0) or 0.0) for promo in promotions), 2)
    if api_discount > 0 and api_discount > promo_sum:
        promotions.append({"description": "dm rabatt", "amount": round(api_discount, 2)})
        promo_sum = round(api_discount, 2)

    return {
        "orderId": order_id,
        "orderDate": str(payload.get("date") or hint.get("orderDate") or ""),
        "totalAmount": round(max(api_total, 0.0), 2),
        "currency": str(payload.get("currency") or hint.get("currency") or "EUR"),
        "orderStatus": str(payload.get("status") or hint.get("orderStatus") or ""),
        "detailsUrl": details_url,
        "items": parsed_items,
        "itemTexts": item_texts,
        "promotions": promotions,
        "totalSavings": promo_sum,
        "rawText": raw_text,
        "totalText": total_text,
        "storeName": str(payload.get("storeName") or payload.get("merchantName") or ""),
    }


def _is_receipt_item_title(title: str) -> bool:
    lowered = title.lower()
    if not lowered:
        return False
    if any(lowered.startswith(prefix) for prefix in _RECEIPT_NON_ITEM_PREFIXES):
        return False
    if "kunden-beleg" in lowered:
        return False
    if lowered in {"eur", "brutto", "netto", "mwst"}:
        return False
    if re.search(r"\d+=\d", lowered):
        return False
    if "%" in lowered and "coupon" not in lowered:
        return False
    return True


def _parse_receipt_text_payload(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None

    lines = [_normalize_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return None

    item_lines: list[str] = []
    promotion_lines: list[str] = []
    items: list[dict[str, Any]] = []
    promotions: list[dict[str, Any]] = []
    seen_item_keys: set[str] = set()
    seen_promo_keys: set[tuple[str, float]] = set()

    total_amount = 0.0
    order_date = ""

    for line in lines:
        if not order_date:
            date_match = _RECEIPT_DATE_RE.search(line)
            if date_match:
                order_date = date_match.group("date")

        total_match = _RECEIPT_TOTAL_RE.match(line)
        if total_match:
            total_amount = abs(_parse_dm_amount(total_match.group("amount")))
            continue

        discount_match = _RECEIPT_DISCOUNT_RE.match(line)
        if discount_match:
            description = _normalize_text(discount_match.group("description"))
            lowered_description = description.lower()
            if not any(keyword in lowered_description for keyword in _PROMOTION_KEYWORDS):
                continue
            amount = abs(_parse_dm_amount(discount_match.group("amount")))
            if amount > 0 and description:
                key = (description.lower(), round(amount, 2))
                if key not in seen_promo_keys:
                    promotions.append({"description": description, "amount": round(amount, 2)})
                    promotion_lines.append(line)
                    seen_promo_keys.add(key)
            continue

        item_match = _RECEIPT_ITEM_RE.match(line)
        if not item_match:
            continue
        title = _normalize_text(item_match.group("title"))
        if not _is_receipt_item_title(title):
            continue

        line_total = abs(_parse_dm_amount(item_match.group("amount")))
        if line_total <= 0:
            continue
        key = f"{title.lower()}|{line_total:.2f}"
        if key in seen_item_keys:
            continue
        seen_item_keys.add(key)
        item_lines.append(line)
        items.append(
            {
                "title": title,
                "quantity": 1.0,
                "price": round(line_total, 2),
                "lineTotal": round(line_total, 2),
                "discount": 0.0,
            }
        )

    if not promotions:
        promotions = parse_dm_promotions("\n".join(lines))
        promotion_lines = [str(promo.get("description") or "") for promo in promotions]

    if total_amount <= 0:
        total_amount = _extract_total_amount(" | ".join(lines), "\n".join(lines))

    total_savings = round(sum(float(promo.get("amount", 0.0) or 0.0) for promo in promotions), 2)
    total_entries: list[str] = []
    if total_amount > 0:
        total_entries.append(f"SUMME EUR {total_amount:.2f}".replace(".", ","))
    total_entries.extend(promotion_lines)
    return {
        "orderDate": order_date,
        "totalAmount": round(max(total_amount, 0.0), 2),
        "itemTexts": [],
        "items": items,
        "promotions": promotions,
        "totalSavings": total_savings,
        "rawText": "\n".join(lines),
        "totalText": " | ".join(entry for entry in total_entries if entry),
    }


def _parse_receipt_pdf_payload(pdf_bytes: bytes) -> dict[str, Any] | None:
    if not pdf_bytes:
        return None
    try:
        from pypdf import PdfReader
    except Exception:
        return None
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts = [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return None
    text = "\n".join(text_parts).strip()
    return _parse_receipt_text_payload(text)


_SCRAPE_ORDERS_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();

  const parseAmount = (value) => {
    const text = normalize(value).replace(/\u00a0/g, " ");
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
    const number = Number(raw);
    return Number.isFinite(number) ? sign * number : 0;
  };

  const parseOrderIdFromText = (text) => {
    const explicit = text.match(/(?:bestell(?:ung|nummer)?|auftragsnummer|order(?:\s*id)?|beleg(?:nr|nummer)?)\s*[:#-]?\s*([a-z0-9][a-z0-9-]{5,})/i);
    if (explicit && explicit[1]) {
      return explicit[1];
    }
    const fallback = text.match(/\b([A-Z]{2,8}-[A-Z0-9-]{3,})\b/);
    return fallback ? fallback[1] : "";
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

  const parseStatus = (text) => {
    const lowered = text.toLowerCase();
    if (lowered.includes("geliefert") || lowered.includes("delivered")) {
      return "Delivered";
    }
    if (lowered.includes("versandt") || lowered.includes("shipped")) {
      return "Shipped";
    }
    if (lowered.includes("storniert") || lowered.includes("cancel")) {
      return "Canceled";
    }
    if (lowered.includes("in bearbeitung") || lowered.includes("processing")) {
      return "Processing";
    }
    return "";
  };

  const promotionRegex = /((?:payback|coupon|gutschein|rabatt|bonus|vorteil|dm-app|app(?:-|\s)?coupon|punkte|spar)[^\n\r]{0,120}?)\s*[:\-]?\s*(-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})))/ig;

  const collectPromotions = (text) => {
    const promotions = [];
    const seen = new Set();
    let match = promotionRegex.exec(text);
    while (match) {
      const description = normalize(match[1] || "dm promotion");
      const amount = Math.abs(parseAmount(match[2] || ""));
      const key = `${description}|${amount}`;
      if (description && amount > 0 && !seen.has(key)) {
        promotions.push({ description, amount });
        seen.add(key);
      }
      match = promotionRegex.exec(text);
    }
    return promotions;
  };

  const collectItemTexts = (container) => {
    const selectors = [
      "[data-testid*='order-item']",
      "[data-testid*='item-name']",
      "[class*='order-item']",
      "[class*='line-item']",
      "[class*='product-item']",
      "[class*='product-name']",
      "li",
      "tr"
    ];
    const seen = new Set();
    const out = [];
    for (const selector of selectors) {
      const nodes = Array.from(container.querySelectorAll(selector));
      for (const node of nodes) {
        const text = normalize(node.textContent || "");
        if (!text || text.length < 3 || text.length > 240) {
          continue;
        }
        const lowered = text.toLowerCase();
        if (lowered.includes("bestell") || lowered.includes("gesamtsumme") || lowered.includes("zwischensumme")) {
          continue;
        }
        if (seen.has(text)) {
          continue;
        }
        seen.add(text);
        out.push(text);
        if (out.length >= 60) {
          return out;
        }
      }
      if (out.length >= 60) {
        break;
      }
    }
    return out;
  };

  const orderSelectors = [
    "[data-testid*='order-card']",
    "[data-testid*='order']",
    "[class*='order-card']",
    "[class*='orderCard']",
    "[class*='order-tile']",
    "article",
    "section"
  ];

  let orderNodes = [];
  for (const selector of orderSelectors) {
    const found = Array.from(document.querySelectorAll(selector));
    if (found.length > 0) {
      orderNodes = found;
      break;
    }
  }

  if (orderNodes.length === 0) {
    orderNodes = [document.body];
  }

  const rows = [];
  const seenRows = new Set();

  for (const card of orderNodes) {
    const text = normalize(card.textContent || "");
    if (!text) {
      continue;
    }

    const firstDetailLink = card.querySelector("a[href*='order'], a[href*='bestell'], a[href*='beleg'], a[href*='rechnung']");
    const detailsUrl = firstDetailLink ? String(firstDetailLink.getAttribute("href") || "") : "";

    const attrOrderId =
      card.getAttribute("data-order-id") ||
      card.getAttribute("data-orderid") ||
      card.getAttribute("data-testid") ||
      "";

    let orderId = "";
    if (attrOrderId && /[A-Za-z0-9-]{6,}/.test(attrOrderId)) {
      const m = attrOrderId.match(/[A-Za-z0-9][A-Za-z0-9-]{5,}/);
      orderId = m ? m[0] : "";
    }

    if (!orderId) {
      orderId = parseOrderIdFromUrl(detailsUrl);
    }
    if (!orderId) {
      orderId = parseOrderIdFromText(text);
    }

    const looksLikeOrder = /bestell|order|beleg|kauf|rechnung/i.test(text);
    if (!looksLikeOrder && !orderId) {
      continue;
    }

    let orderDate = "";
    const timeEl = card.querySelector("time");
    if (timeEl) {
      orderDate = normalize(timeEl.getAttribute("datetime") || timeEl.textContent || "");
    }
    if (!orderDate) {
      const dateMatch = text.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})/);
      if (dateMatch && dateMatch[1]) {
        orderDate = dateMatch[1];
      }
    }

    const totalNodes = Array.from(
      card.querySelectorAll("[data-testid*='total'], [class*='total'], [class*='sum'], [class*='betrag']")
    );
    const totalTexts = totalNodes
      .map((node) => normalize(node.textContent || ""))
      .filter((entry) => entry.length > 0)
      .slice(0, 6);

    let totalAmount = 0;
    for (const totalText of totalTexts) {
      const amount = Math.abs(parseAmount(totalText));
      if (amount > totalAmount) {
        totalAmount = amount;
      }
    }

    const promotions = collectPromotions(text);
    const totalSavings = promotions.reduce((acc, promo) => acc + (promo.amount || 0), 0);

    const row = {
      orderId,
      orderDate,
      totalAmount,
      currency: "EUR",
      orderStatus: parseStatus(text),
      detailsUrl,
      rawText: text,
      totalText: totalTexts.join(" | "),
      itemTexts: collectItemTexts(card),
      items: [],
      promotions,
      totalSavings,
    };

    const dedupeKey = `${orderId || "-"}|${orderDate || "-"}|${row.totalAmount || 0}`;
    if (seenRows.has(dedupeKey)) {
      continue;
    }
    seenRows.add(dedupeKey);
    rows.push(row);
    if (rows.length >= 200) {
      break;
    }
  }

  return rows;
}
"""


_SCRAPE_ORDER_DETAIL_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();

  const parseAmount = (value) => {
    const text = normalize(value).replace(/\u00a0/g, " ");
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
    const number = Number(raw);
    return Number.isFinite(number) ? sign * number : 0;
  };

  const promotionRegex = /((?:payback|coupon|gutschein|rabatt|bonus|vorteil|dm-app|app(?:-|\s)?coupon|punkte|spar)[^\n\r]{0,120}?)\s*[:\-]?\s*(-?(?:\d{1,3}(?:[.\s]\d{3})*(?:[,.]\d{2})|\d+(?:[,.]\d{2})))/ig;

  const collectPromotions = (text) => {
    const out = [];
    const seen = new Set();
    let match = promotionRegex.exec(text);
    while (match) {
      const description = normalize(match[1] || "dm promotion");
      const amount = Math.abs(parseAmount(match[2] || ""));
      const key = `${description}|${amount}`;
      if (description && amount > 0 && !seen.has(key)) {
        out.push({ description, amount });
        seen.add(key);
      }
      match = promotionRegex.exec(text);
    }
    return out;
  };

  const statusFromText = (text) => {
    const lowered = text.toLowerCase();
    if (lowered.includes("geliefert") || lowered.includes("delivered")) {
      return "Delivered";
    }
    if (lowered.includes("versandt") || lowered.includes("shipped")) {
      return "Shipped";
    }
    if (lowered.includes("storniert") || lowered.includes("cancel")) {
      return "Canceled";
    }
    if (lowered.includes("in bearbeitung") || lowered.includes("processing")) {
      return "Processing";
    }
    return "";
  };

  const rootText = normalize(document.body ? document.body.innerText || "" : "");
  const detailSelectors = [
    "[data-testid*='order-item']",
    "[data-testid*='item-name']",
    "[class*='order-item']",
    "[class*='line-item']",
    "[class*='product-item']",
    "[class*='product-name']",
    "table tr",
    "li"
  ];

  const itemTexts = [];
  const seenTexts = new Set();
  for (const selector of detailSelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    for (const node of nodes) {
      const text = normalize(node.textContent || "");
      if (!text || text.length < 3 || text.length > 240) {
        continue;
      }
      if (seenTexts.has(text)) {
        continue;
      }
      seenTexts.add(text);
      itemTexts.push(text);
      if (itemTexts.length >= 120) {
        break;
      }
    }
    if (itemTexts.length >= 120) {
      break;
    }
  }

  let orderDate = "";
  const timeEl = document.querySelector("time");
  if (timeEl) {
    orderDate = normalize(timeEl.getAttribute("datetime") || timeEl.textContent || "");
  }
  if (!orderDate) {
    const dateMatch = rootText.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})/);
    if (dateMatch && dateMatch[1]) {
      orderDate = dateMatch[1];
    }
  }

  const totalCandidates = [];
  const totalNodes = Array.from(document.querySelectorAll("[data-testid*='total'], [class*='total'], [class*='sum'], [class*='betrag']"));
  for (const node of totalNodes) {
    const text = normalize(node.textContent || "");
    if (text) {
      totalCandidates.push(text);
    }
  }

  let totalAmount = 0;
  for (const entry of totalCandidates) {
    const amount = Math.abs(parseAmount(entry));
    if (amount > totalAmount) {
      totalAmount = amount;
    }
  }

  const promotions = collectPromotions(rootText);
  return {
    rawText: rootText,
    totalText: totalCandidates.join(" | "),
    itemTexts,
    items: [],
    promotions,
    totalSavings: promotions.reduce((acc, promo) => acc + (promo.amount || 0), 0),
    totalAmount,
    orderDate,
    orderStatus: statusFromText(rootText),
  };
}
"""

_SCRAPE_PURCHASE_ROWS_SCRIPT = r"""
() => {
  const normalize = (value) => (value || "").replace(/\s+/g, " ").trim();
  const parseAmount = (value) => {
    const text = normalize(value).replace(/\u00a0/g, " ");
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
  const ebonIdFromHref = (href) => {
    if (!href) {
      return "";
    }
    const match = String(href).match(/\/ebons\/([0-9a-fA-F-]{8,})/);
    return match && match[1] ? match[1] : "";
  };
  const parseStatus = (text) => {
    const lowered = text.toLowerCase();
    if (lowered.includes("geliefert") || lowered.includes("delivered")) {
      return "Delivered";
    }
    if (lowered.includes("versandt") || lowered.includes("shipped")) {
      return "Shipped";
    }
    if (lowered.includes("storniert") || lowered.includes("cancel")) {
      return "Canceled";
    }
    if (lowered.includes("in bearbeitung") || lowered.includes("processing")) {
      return "Processing";
    }
    return "";
  };
  const nodes = Array.from(document.querySelectorAll("a[href*='/ebons/']"));
  const rows = [];
  const seen = new Set();

  for (const link of nodes) {
    const href = String(link.getAttribute("href") || "");
    const ebonId = ebonIdFromHref(href);
    if (!ebonId || seen.has(ebonId)) {
      continue;
    }
    seen.add(ebonId);
    const card = link.closest("article, section, li, div") || link;
    const rowText = normalize((card && card.textContent) || link.textContent || "");
    const dateMatch = rowText.match(/(\d{1,2}\.\d{1,2}\.\d{2,4})/);
    const dateText = dateMatch && dateMatch[1] ? dateMatch[1] : "";
    const totalMatch = rowText.match(/(\d+(?:[.,]\d{2}))\s*(?:€|eur)/i);
    const totalAmount = totalMatch && totalMatch[1] ? Math.abs(parseAmount(totalMatch[1])) : 0;
    rows.push({
      orderId: ebonId,
      ebonId,
      detailsUrl: href,
      orderDate: dateText,
      orderStatus: parseStatus(rowText),
      rawText: rowText,
      totalText: rowText,
      itemTexts: [],
      items: [],
      promotions: [],
      totalSavings: 0,
      totalAmount,
      currency: "EUR",
    });
  }
  return rows;
}
"""


_AUTH_STATE_SCRIPT = r"""
() => {
  const text = ((document.body && document.body.innerText) || "").toLowerCase();
  const hasPurchasesPath = /account\.dm\.de\/purchases/.test(window.location.href || "");
  const links = Array.from(document.querySelectorAll("a[href]"));
  const hasPurchaseLinks = links.some((a) => /\/ebons\/[0-9a-fA-F-]{8,}/.test(String(a.getAttribute("href") || "")));
  const hasAccountLinks = links.some((a) => {
    const href = String(a.getAttribute("href") || "");
    return /(\/purchases|\/profile|\/orders|\/myaccount)/i.test(href);
  });
  const interactive = Array.from(document.querySelectorAll("a,button"));
  const hasLogout = interactive.some((el) => {
    const blob = `${el.textContent || ""} ${el.getAttribute("aria-label") || ""}`.toLowerCase();
    return /(abmelden|logout|sign out)/i.test(blob);
  });
  const hasLoginIframe = Boolean(document.querySelector("iframe#___loginIframe___"));
  const hasError404Meta = Boolean(document.querySelector("meta[name='render:status_code'][content='404']"));
  const hasErrorText = /entschuldigung|seite existiert leider nicht/.test(text);
  return {
    hasPurchasesPath,
    hasPurchaseLinks,
    hasAccountLinks,
    hasLogout,
    hasLoginIframe,
    hasError404Meta,
    hasErrorText,
  };
}
"""


class DmPlaywrightClient:
    def __init__(
        self,
        *,
        state_file: Path,
        domain: str = "www.dm.de",
        headless: bool = True,
        max_pages: int = 10,
        detail_fetch_limit: int = -1,
        detail_retry_count: int = 2,
        detail_retry_backoff_ms: int = 800,
        detail_pause_ms: int = 120,
        detail_batch_size: int = 40,
        detail_batch_pause_ms: int = 1200,
        max_consecutive_detail_failures: int = 25,
        persist_state_on_success: bool = True,
        state_persist_interval: int = 25,
        session_keepalive_every: int = 30,
        dump_html_dir: Path | None = None,
    ) -> None:
        self._state_file = state_file
        self._domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
        self._headless = headless
        self._max_pages = None if max_pages <= 0 else max(1, max_pages)
        self._detail_fetch_limit = None if detail_fetch_limit < 0 else max(0, detail_fetch_limit)
        self._detail_retry_count = max(0, detail_retry_count)
        self._detail_retry_backoff_ms = max(0, detail_retry_backoff_ms)
        self._detail_pause_ms = max(0, detail_pause_ms)
        self._detail_batch_size = max(0, detail_batch_size)
        self._detail_batch_pause_ms = max(0, detail_batch_pause_ms)
        self._max_consecutive_detail_failures = (
            None if max_consecutive_detail_failures <= 0 else max_consecutive_detail_failures
        )
        self._persist_state_on_success = persist_state_on_success
        self._state_persist_interval = max(1, state_persist_interval)
        self._session_keepalive_every = None if session_keepalive_every <= 0 else session_keepalive_every
        self._dump_html_dir = dump_html_dir
        self._dump_index = 0

    def fetch_receipts(self) -> list[dict[str, Any]]:
        if not self._state_file.exists():
            raise DmReauthRequiredError(
                f"dm session state missing: {self._state_file}. "
                "Run 'lidltool connectors auth bootstrap --source-id dm_de' first."
            )

        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        with sync_playwright() as playwright:
            from lidltool.connectors.auth.browser_runtime import launch_playwright_chromium

            browser = launch_playwright_chromium(playwright=playwright, headless=self._headless)
            context = browser.new_context(storage_state=str(self._state_file))
            page = context.new_page()
            detail_page = context.new_page() if self._detail_fetch_limit != 0 else None

            detail_budget = self._detail_fetch_limit
            detail_processed = 0
            consecutive_detail_failures = 0
            session_validated = False

            try:
                raw_rows = self._fetch_purchase_rows(page)
                session_validated = True
                self._try_persist_state_snapshot(context)
                for raw_row in raw_rows:
                    normalized_row = _normalize_scraped_order(raw_row)
                    if normalized_row is None:
                        continue

                    order_id = str(normalized_row.get("orderId") or "").strip()
                    if not order_id or order_id in seen:
                        continue

                    can_fetch_detail = detail_page is not None and (
                        detail_budget is None or detail_budget > 0
                    )
                    if can_fetch_detail:
                        detail = self._fetch_detail_with_retries(context, detail_page, normalized_row)
                        detail_processed += 1
                        if detail_budget is not None:
                            detail_budget -= 1
                        if detail is not None:
                            normalized_row = self._merge_with_detail(normalized_row, detail)
                            consecutive_detail_failures = 0
                        else:
                            consecutive_detail_failures += 1
                        self._throttle_detail_processing(detail_processed)
                        if detail_processed % self._state_persist_interval == 0:
                            self._try_persist_state_snapshot(context)
                        if (
                            self._session_keepalive_every is not None
                            and detail_processed % self._session_keepalive_every == 0
                        ):
                            self._run_session_keepalive(page)
                        if (
                            self._max_consecutive_detail_failures is not None
                            and consecutive_detail_failures >= self._max_consecutive_detail_failures
                        ):
                            raise DmClientError(
                                "dm detail enrichment failed repeatedly. "
                                "Session may be throttled/expired; rerun bootstrap and retry."
                            )

                    if not normalized_row.get("orderDate"):
                        normalized_row["orderDate"] = datetime.now(tz=UTC).isoformat()
                    if not normalized_row.get("currency"):
                        normalized_row["currency"] = "EUR"

                    out.append(normalized_row)
                    seen.add(order_id)

            finally:
                if session_validated:
                    self._try_persist_state_snapshot(context)
                if detail_page is not None:
                    detail_page.close()
                context.close()
                browser.close()

        return out

    def _fetch_purchase_rows(self, page: Page) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            page.goto(_DM_ACCOUNT_PURCHASES_URL, wait_until="domcontentloaded")
            self._wait_for_purchases_ready(page)
        except Exception:
            return []

        page_idx = 1
        while True:
            self._dismiss_common_overlays(page)
            self._ensure_logged_in(page)
            self._ensure_account_access(page)
            self._maybe_dump_html(page, prefix="purchases")

            if "/ebons/" in str(page.url):
                ebon_id = _extract_ebon_id(str(page.url))
                if ebon_id and ebon_id not in seen:
                    rows.append(
                        {
                            "orderId": ebon_id,
                            "ebonId": ebon_id,
                            "detailsUrl": str(page.url),
                            "orderDate": "",
                            "orderStatus": "",
                            "rawText": _normalize_text(page.inner_text("body")),
                            "totalText": "",
                            "itemTexts": [],
                            "items": [],
                            "promotions": [],
                            "totalSavings": 0,
                            "totalAmount": 0,
                            "currency": "EUR",
                        }
                    )
                    seen.add(ebon_id)
                try:
                    page.goto(_DM_ACCOUNT_PURCHASES_URL, wait_until="domcontentloaded")
                    self._wait_for_purchases_ready(page)
                except Exception:
                    continue

            raw_rows = page.evaluate(_SCRAPE_PURCHASE_ROWS_SCRIPT)
            parsed_rows = raw_rows if isinstance(raw_rows, list) else []
            added = 0
            for row in parsed_rows:
                if not isinstance(row, dict):
                    continue
                order_id = str(row.get("orderId") or row.get("ebonId") or "").strip()
                if not order_id or order_id in seen:
                    continue
                seen.add(order_id)
                rows.append(row)
                added += 1
            if self._max_pages is not None and page_idx >= self._max_pages:
                break
            if not self._click_load_more(page):
                break
            if added == 0 and page_idx > 1:
                break
            page_idx += 1

        return rows

    def _try_persist_state_snapshot(self, context: Any) -> bool:
        if not self._persist_state_on_success:
            return False
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._state_file.with_suffix(self._state_file.suffix + ".tmp")
            context.storage_state(path=str(tmp_path))
            tmp_path.replace(self._state_file)
            return True
        except Exception:
            return False

    def _run_session_keepalive(self, page: Page) -> None:
        try:
            page.goto(_DM_ACCOUNT_PURCHASES_URL, wait_until="domcontentloaded")
            self._dismiss_common_overlays(page)
            self._ensure_logged_in(page)
            self._ensure_account_access(page)
            page.wait_for_timeout(500)
        except Exception:
            return

    def _wait_for_purchases_ready(self, page: Page) -> None:
        start = time.monotonic()
        deadline = start + 15.0
        min_warmup = 7.0
        while time.monotonic() < deadline:
            try:
                has_ebon_link = page.locator("a[href*='/ebons/']").count() > 0
                has_loading = page.locator("[data-dmid='loading-container']").count() > 0
                has_login_iframe = page.locator("iframe#___loginIframe___").count() > 0
                body_text = page.inner_text("body").lower()
            except Exception:
                page.wait_for_timeout(500)
                continue
            has_purchases_label = "meine einkäufe" in body_text or "meine einkaeufe" in body_text
            warmup_done = (time.monotonic() - start) >= min_warmup
            if has_ebon_link:
                return
            if warmup_done and has_purchases_label and (not has_loading) and (not has_login_iframe):
                return
            page.wait_for_timeout(500)

    def _click_load_more(self, page: Page) -> bool:
        selectors = (
            "button:has-text('Mehr anzeigen')",
            "button:has-text('Mehr laden')",
            "button:has-text('Show more')",
            "button:has-text('Load more')",
            "[data-testid*='load-more']",
            "[class*='load-more'] button",
        )
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.count() == 0 or not button.is_visible():
                    continue
                button.click(timeout=1200)
                self._wait_for_purchases_ready(page)
                return True
            except Exception:
                continue
        return False

    def _fetch_detail_with_retries(
        self,
        context: Any,
        detail_page: Page,
        order: dict[str, Any],
    ) -> dict[str, Any] | None:
        attempts = self._detail_retry_count + 1
        for attempt in range(1, attempts + 1):
            try:
                return self._fetch_detail(context, detail_page, order)
            except DmReauthRequiredError:
                raise
            except Exception:
                if attempt >= attempts:
                    return None
                if self._detail_retry_backoff_ms > 0:
                    detail_page.wait_for_timeout(self._detail_retry_backoff_ms * attempt)
        return None

    def _throttle_detail_processing(self, processed_count: int) -> None:
        if self._detail_pause_ms > 0:
            time.sleep(self._detail_pause_ms / 1000.0)
        if self._detail_batch_size > 0 and processed_count % self._detail_batch_size == 0:
            if self._detail_batch_pause_ms > 0:
                time.sleep(self._detail_batch_pause_ms / 1000.0)

    def _fetch_detail(self, context: Any, detail_page: Page, order: dict[str, Any]) -> dict[str, Any] | None:
        order_id = str(order.get("orderId") or "").strip()
        details_url_raw = str(order.get("detailsUrl") or "").strip()
        ebon_id = _extract_ebon_id(details_url_raw) or _extract_ebon_id(order_id)
        api_unauthorized = False
        detail_payload: dict[str, Any] | None = None

        if ebon_id:
            api_url = _DM_EBON_API_URL_TEMPLATE.format(ebon_id=ebon_id)
            try:
                response = context.request.get(api_url)
                status = int(response.status)
            except Exception:
                status = 0
                response = None
            if status in (401, 403):
                api_unauthorized = True
            if response is not None and 200 <= status < 300:
                try:
                    payload = response.json()
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    detail_payload = _raw_order_from_ebon_payload(payload, order)

        details_url_raw = str(order.get("detailsUrl") or "").strip()
        if not details_url_raw:
            if not ebon_id:
                return None
            details_url_raw = f"https://account.dm.de/ebons/{ebon_id}"

        details_url = details_url_raw
        parsed = urlparse(details_url_raw)
        if not parsed.scheme:
            details_url = f"https://account.dm.de/{details_url_raw.lstrip('/')}"

        try:
            with detail_page.expect_response(
                lambda response: "/api/customer/ebons/" in response.url,
                timeout=8000,
            ) as response_info:
                detail_page.goto(details_url, wait_until="domcontentloaded")
                detail_page.wait_for_timeout(1800)
            api_response = response_info.value
            if api_response is not None and 200 <= int(api_response.status) < 300:
                try:
                    api_payload = api_response.json()
                except Exception:
                    api_payload = None
                if isinstance(api_payload, dict):
                    page_api = _raw_order_from_ebon_payload(api_payload, order)
                    detail_payload = (
                        page_api
                        if detail_payload is None
                        else self._merge_with_detail(detail_payload, page_api)
                    )
            elif api_response is not None and int(api_response.status) in (401, 403):
                api_unauthorized = True
        except Exception:
            try:
                detail_page.goto(details_url, wait_until="domcontentloaded")
                detail_page.wait_for_timeout(1500)
            except Exception as exc:
                if api_unauthorized:
                    raise DmReauthRequiredError(
                        "dm session is not authorized for account eBon API access. "
                        "Run 'lidltool connectors auth bootstrap --source-id dm_de' again, open 'Meine Einkaeufe', then retry."
                    ) from exc
                return None

        self._dismiss_common_overlays(detail_page)
        self._ensure_logged_in(detail_page)
        self._ensure_account_access(detail_page)
        self._maybe_dump_html(detail_page, prefix="detail")

        payload = detail_page.evaluate(_SCRAPE_ORDER_DETAIL_SCRIPT)
        dom_payload: dict[str, Any] | None = None
        if isinstance(payload, dict):
            payload.setdefault("orderId", order_id)
            payload.setdefault("detailsUrl", details_url)
            dom_payload = payload

        pdf_detail = self._fetch_receipt_pdf_detail(detail_page, order_id=order_id, details_url=details_url)
        if pdf_detail is not None:
            detail_payload = (
                pdf_detail
                if detail_payload is None
                else self._merge_with_detail(detail_payload, pdf_detail)
            )
        elif detail_payload is None and dom_payload is not None:
            detail_payload = dom_payload
        elif detail_payload is not None and dom_payload is not None:
            # Use DOM scrape as a low-priority supplement only when PDF enrichment is unavailable.
            detail_payload = self._merge_with_detail(detail_payload, dom_payload)

        if detail_payload is None and api_unauthorized:
            raise DmReauthRequiredError(
                "dm session is not authorized for account eBon API access. "
                "Run 'lidltool connectors auth bootstrap --source-id dm_de' again, open 'Meine Einkaeufe', then retry."
            )
        return detail_payload

    def _fetch_receipt_pdf_detail(
        self,
        detail_page: Page,
        *,
        order_id: str,
        details_url: str,
    ) -> dict[str, Any] | None:
        selectors = (
            "button:has-text('Kassenbon anzeigen')",
            "button:has-text('Kassenbon')",
            "button:has-text('Bon anzeigen')",
        )
        def response_predicate(response: Any) -> bool:
            return _DM_DOWNLOAD_URL_TOKEN in response.url and "/download" in response.url

        for selector in selectors:
            try:
                button = detail_page.locator(selector).first
                if button.count() == 0 or not button.is_visible():
                    continue
                with detail_page.expect_response(response_predicate, timeout=8000) as response_info:
                    button.click(timeout=2500)
                response = response_info.value
                if response is None or not (200 <= int(response.status) < 300):
                    continue
                content_type = str(response.headers.get("content-type") or "").lower()
                if "pdf" not in content_type:
                    continue
                parsed = _parse_receipt_pdf_payload(response.body())
                if not isinstance(parsed, dict):
                    continue
                parsed.setdefault("orderId", order_id)
                parsed.setdefault("detailsUrl", details_url)
                parsed.setdefault("currency", "EUR")
                return parsed
            except Exception:
                continue
        return None

    def _merge_with_detail(self, order: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        merged = dict(order)
        merged["rawText"] = _normalize_text(
            "\n".join(
                [
                    str(order.get("rawText") or ""),
                    str(detail.get("rawText") or ""),
                ]
            )
        )
        merged["totalText"] = _normalize_text(
            " | ".join(
                [
                    str(order.get("totalText") or ""),
                    str(detail.get("totalText") or ""),
                ]
            )
        )

        item_texts: list[str] = []
        for source in (order.get("itemTexts"), detail.get("itemTexts")):
            if not isinstance(source, list):
                continue
            for value in source:
                if not isinstance(value, str):
                    continue
                normalized = _normalize_text(value)
                if normalized:
                    item_texts.append(normalized)
        if item_texts:
            merged["itemTexts"] = list(dict.fromkeys(item_texts))

        combined_items: list[dict[str, Any]] = []
        for source in (order.get("items"), detail.get("items")):
            if isinstance(source, list):
                combined_items.extend([entry for entry in source if isinstance(entry, dict)])
        if combined_items:
            merged["items"] = combined_items

        detail_promotions = detail.get("promotions")
        base_promotions = order.get("promotions")
        merged_promotions: list[dict[str, Any]] = []
        for source in (base_promotions, detail_promotions):
            if not isinstance(source, list):
                continue
            for promo in source:
                if not isinstance(promo, dict):
                    continue
                amount = abs(_parse_dm_amount(promo.get("amount") or ""))
                if amount <= 0:
                    continue
                description = _normalize_text(str(promo.get("description") or "dm promotion"))
                merged_promotions.append({"description": description, "amount": round(amount, 2)})

        if merged_promotions:
            deduped: list[dict[str, Any]] = []
            seen_keys: set[tuple[str, float]] = set()
            for promo in merged_promotions:
                key = (promo["description"].lower(), float(promo["amount"]))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped.append(promo)
            generic_dm_discount = next(
                (
                    promo
                    for promo in deduped
                    if str(promo.get("description") or "").strip().lower() in {"dm rabatt", "dm-rabatt"}
                ),
                None,
            )
            if generic_dm_discount is not None:
                specific_sum = round(
                    sum(
                        float(promo.get("amount", 0.0) or 0.0)
                        for promo in deduped
                        if promo is not generic_dm_discount
                    ),
                    2,
                )
                if specific_sum >= float(generic_dm_discount.get("amount", 0.0) or 0.0):
                    deduped = [promo for promo in deduped if promo is not generic_dm_discount]
            merged["promotions"] = deduped
            merged["totalSavings"] = round(
                sum(float(promo.get("amount", 0.0) or 0.0) for promo in deduped), 2
            )

        detail_total = abs(_parse_dm_amount(detail.get("totalAmount") or ""))
        if detail_total > 0:
            merged["totalAmount"] = detail_total

        if not merged.get("orderDate") and detail.get("orderDate"):
            merged["orderDate"] = str(detail.get("orderDate"))
        if not merged.get("orderStatus") and detail.get("orderStatus"):
            merged["orderStatus"] = str(detail.get("orderStatus"))

        normalized = _normalize_scraped_order(merged)
        return normalized if normalized is not None else order

    def _ensure_logged_in(self, page: Page) -> None:
        url = str(page.url).lower()
        if any(pattern in url for pattern in _REAUTH_URL_PATTERNS):
            raise DmReauthRequiredError(
                "dm session expired or invalid. Run 'lidltool connectors auth bootstrap --source-id dm_de' again."
            )

    def _dismiss_common_overlays(self, page: Page) -> None:
        # Best-effort cookie/privacy/modal dismissal to keep scraper flow unblocked.
        selectors = (
            "button:has-text('Alle akzeptieren')",
            "button:has-text('Akzeptieren')",
            "button:has-text('Einverstanden')",
            "button:has-text('Zustimmen')",
            "[data-dmid*='consent'] button",
            "[id*='consent'] button",
            "[class*='consent'] button",
        )
        for selector in selectors:
            try:
                button = page.locator(selector).first
                if button.count() == 0:
                    continue
                if not button.is_visible():
                    continue
                button.click(timeout=500)
                page.wait_for_timeout(250)
            except Exception:
                continue

    def _ensure_account_access(self, page: Page) -> None:
        try:
            raw_state = page.evaluate(_AUTH_STATE_SCRIPT)
        except Exception:
            return
        if not isinstance(raw_state, dict):
            return
        on_purchases_path = bool(raw_state.get("hasPurchasesPath"))
        has_purchase_links = bool(raw_state.get("hasPurchaseLinks"))
        has_account_links = bool(raw_state.get("hasAccountLinks"))
        has_logout = bool(raw_state.get("hasLogout"))
        has_error = bool(raw_state.get("hasError404Meta")) or bool(raw_state.get("hasErrorText"))
        has_login_iframe = bool(raw_state.get("hasLoginIframe"))
        has_positive_auth = on_purchases_path or has_purchase_links or has_account_links or has_logout
        if (has_error or has_login_iframe) and not has_positive_auth:
            raise DmReauthRequiredError(
                "dm session was captured without a fully authenticated account page. "
                "Run 'lidltool connectors auth bootstrap --source-id dm_de' again, accept privacy notices, open 'Meine Einkaeufe', then press Enter."
            )

    def _maybe_dump_html(self, page: Page, *, prefix: str) -> None:
        if self._dump_html_dir is None:
            return
        try:
            self._dump_html_dir.mkdir(parents=True, exist_ok=True)
            self._dump_index += 1
            url = _normalize_text(str(page.url))
            safe_url = re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[:120] or "page"
            file_name = f"{self._dump_index:03d}_{prefix}_{safe_url}.html"
            target = self._dump_html_dir / file_name
            target.write_text(page.content(), encoding="utf-8")
        except Exception:
            return


def parse_dm_date(value: str) -> str:
    cleaned = _normalize_text(value)
    if not cleaned:
        return datetime.now(tz=UTC).isoformat()

    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return parsed.replace(tzinfo=UTC).isoformat()
        except ValueError:
            continue

    textual_match = re.search(r"(\d{1,2})\.\s*([A-Za-z\u00e4\u00f6\u00fc\u00df\.]+)\s+(\d{4})", cleaned)
    if textual_match:
        day = int(textual_match.group(1))
        month_key = _normalize_for_date(textual_match.group(2).rstrip("."))
        month = _DE_MONTH_MAP.get(month_key)
        year = int(textual_match.group(3))
        if month is not None:
            try:
                parsed = datetime(year, month, day, tzinfo=UTC)
                return parsed.isoformat()
            except ValueError:
                pass

    return cleaned


def parse_dm_promotions(text: str) -> list[dict[str, Any]]:
    promotions: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    normalized_text = _normalize_text(text)

    for match in _PROMOTION_RE.finditer(normalized_text):
        description = _normalize_text(match.group(1) or "dm promotion")
        amount = abs(_parse_dm_amount(match.group(2) or ""))
        if amount <= 0:
            continue
        key = (description.lower(), round(amount, 2))
        if key in seen:
            continue
        seen.add(key)
        promotions.append({"description": description, "amount": round(amount, 2)})

    if promotions:
        return promotions

    # Fallback: line-based detection for formats where keyword and amount are split.
    for chunk in re.split(r"[|\n\r]+", text):
        line = _normalize_text(chunk)
        if not line:
            continue
        lowered = line.lower()
        if not any(keyword in lowered for keyword in _PROMOTION_KEYWORDS):
            continue
        amounts = _extract_amounts(line)
        if not amounts:
            continue
        amount = round(max(amounts), 2)
        key = (line.lower(), amount)
        if key in seen:
            continue
        seen.add(key)
        promotions.append({"description": line, "amount": amount})

    return promotions
