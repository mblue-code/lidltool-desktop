from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256


@dataclass(slots=True)
class ParsedReceipt:
    source_transaction_id: str
    purchased_at: datetime
    store_name: str
    total_gross_cents: int
    currency: str
    items: list[dict[str, object]]


_DATE_RE = re.compile(r"(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")
_PRICE_RE = re.compile(r"(?P<amount>-?\d+[.,]\d{2})")
_TOTAL_RE = re.compile(r"(summe|total)\s*[: ]\s*(?P<amount>\d+[.,]\d{2})", re.IGNORECASE)
_LABELED_TOTAL_PATTERNS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (0, re.compile(r"\b(net amount|grand total|amount due)\b[^0-9-]*(?P<amount>-?\d+(?:[.,]\d{2})?)", re.IGNORECASE)),
    (1, re.compile(r"\b(total|summe|gesamt)\b[^0-9-]*(?P<amount>-?\d+(?:[.,]\d{2})?)", re.IGNORECASE)),
    (2, re.compile(r"\b(gross amount|subtotal|sub total)\b[^0-9-]*(?P<amount>-?\d+(?:[.,]\d{2})?)", re.IGNORECASE)),
)
_SKIP_TOTAL_TOKENS = (
    "change",
    "discount",
    "tender",
    "cash",
    "payment",
    "tax",
    "vat",
    "refund",
)
_SKIP_ITEM_TOKENS = (
    "bill no",
    "date",
    "miti",
    "name",
    "address",
    "pan no",
    "payment mode",
    "remarks",
    "gross amount",
    "discount",
    "net amount",
    "tender",
    "change",
    "vat no",
    "tax invoice",
    "conditions apply",
    "thank you",
    "counter",
    "cashier",
    "total",
    "summe",
    "gesamt",
    "gesamtbetrag",
    "geg.",
    "rückgeld",
    "rueckgeld",
    "steuer",
    "netto",
    "brutto",
)
_HEADER_TOKENS = (
    "qty",
    "rate",
    "amount",
    "particulars",
)
_MARKDOWN_FENCE_RE = re.compile(r"```(?:[A-Za-z0-9_-]+)?\s*\n?(.*?)```", re.DOTALL)
_LEADING_CHATTER_RE = re.compile(
    r"^\s*(?:here(?:'s| is)\s+)?(?:the\s+)?(?:text|receipt text|ocr text|content)"
    r"(?:\s+(?:extracted|recognized|transcribed))?"
    r"(?:\s+from\s+(?:the\s+)?(?:image|receipt|document))?\s*:?\s*$",
    re.IGNORECASE,
)
_STACKED_WEIGHT_ROW_RE = re.compile(
    r"(?P<qty>\d+(?:[.,]\d{1,3})?)\s*x\s*(?P<unit_price>\d+(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)


def parse_receipt_text(text: str, *, fallback_store: str = "OCR Upload") -> ParsedReceipt:
    normalized_text = normalize_receipt_text(text)
    lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]
    purchased_at = _extract_date(lines) or datetime.now(tz=UTC)
    store_name = _extract_store_name(lines, fallback_store=fallback_store)
    total_cents = _extract_total(lines)
    items = _extract_items(lines)
    fingerprint = sha256(normalized_text.encode("utf-8")).hexdigest()
    return ParsedReceipt(
        source_transaction_id=f"ocr:{fingerprint[:24]}",
        purchased_at=purchased_at,
        store_name=store_name,
        total_gross_cents=total_cents,
        currency="EUR",
        items=items,
    )


def to_canonical_payload(parsed: ParsedReceipt) -> dict[str, object]:
    return {
        "id": parsed.source_transaction_id,
        "purchased_at": parsed.purchased_at.isoformat(),
        "store_name": parsed.store_name,
        "total_gross_cents": parsed.total_gross_cents,
        "currency": parsed.currency,
        "items": parsed.items,
        "fingerprint": parsed.source_transaction_id.split(":", 1)[-1],
    }


def normalize_receipt_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""

    fenced_match = _MARKDOWN_FENCE_RE.search(normalized)
    if fenced_match is not None:
        fenced_text = fenced_match.group(1).strip()
        if fenced_text:
            normalized = fenced_text

    lines = [line.rstrip() for line in normalized.splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and _LEADING_CHATTER_RE.fullmatch(lines[0].strip()):
        lines.pop(0)
        while lines and not lines[0].strip():
            lines.pop(0)
    normalized = "\n".join(lines).strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        normalized = normalized.strip("`").strip()
    return normalized


def _extract_store_name(lines: list[str], *, fallback_store: str) -> str:
    if not lines:
        return fallback_store
    first = lines[0]
    if len(first) > 2 and not any(char.isdigit() for char in first):
        return first[:120]
    return fallback_store


def _extract_date(lines: list[str]) -> datetime | None:
    for line in lines:
        match = _DATE_RE.search(line)
        if not match:
            continue
        raw = match.group("date").replace("/", ".").replace("-", ".")
        parts = raw.split(".")
        if len(parts) != 3:
            continue
        day, month, year = parts
        if len(year) == 2:
            year = f"20{year}"
        try:
            return datetime(int(year), int(month), int(day), tzinfo=UTC)
        except ValueError:
            continue
    return None


def _extract_total(lines: list[str]) -> int:
    labeled_candidates: list[tuple[int, int, int]] = []
    for index, line in enumerate(lines):
        lowered = line.casefold()
        if any(token in lowered for token in _SKIP_TOTAL_TOKENS):
            continue
        for priority, pattern in _LABELED_TOTAL_PATTERNS:
            match = pattern.search(line)
            if match:
                labeled_candidates.append((priority, index, _to_cents(match.group("amount"))))
                break
    if labeled_candidates:
        labeled_candidates.sort(key=lambda candidate: (candidate[0], -candidate[1]))
        return labeled_candidates[0][2]
    for line in reversed(lines):
        match = _TOTAL_RE.search(line)
        if match:
            return _to_cents(match.group("amount"))
    for line in reversed(lines):
        values = _PRICE_RE.findall(line)
        if values:
            return _to_cents(values[-1])
    return 0


def _extract_items(lines: list[str]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        lowered = line.casefold()
        if _TOTAL_RE.search(line):
            index += 1
            continue
        if any(token in lowered for token in _SKIP_ITEM_TOKENS):
            index += 1
            continue
        if line.count("-") >= 8:
            index += 1
            continue
        if all(token in lowered for token in _HEADER_TOKENS):
            index += 1
            continue
        table_item = _parse_table_row_item(line=line, line_no=len(items) + 1)
        if table_item is not None:
            items.append(table_item)
            index += 1
            continue
        if index + 1 < len(lines):
            paired_item = _parse_stacked_item(
                name_line=line,
                amount_line=lines[index + 1],
                line_no=len(items) + 1,
            )
            if paired_item is not None:
                items.append(paired_item)
                index += 2
                continue
        if len(_PRICE_RE.findall(line)) != 1:
            index += 1
            continue
        price_match = _PRICE_RE.search(line)
        if price_match is None:
            index += 1
            continue
        amount = _to_cents(price_match.group("amount"))
        name = line[: price_match.start()].strip(" -:\t")
        if len(name) < 2:
            index += 1
            continue
        line_no = len(items) + 1
        items.append(
            {
                "line_no": line_no,
                "source_item_id": f"line:{line_no}",
                "name": name[:240],
                "qty": "1.000",
                "unit": None,
                "unit_price_cents": amount,
                "line_total_cents": amount,
                "category": None,
            }
        )
        index += 1
    return items


def _to_cents(raw: str) -> int:
    normalized = raw.replace(",", ".")
    return int((Decimal(normalized) * 100).to_integral_value())


def _parse_table_row_item(*, line: str, line_no: int) -> dict[str, object] | None:
    parts = line.split()
    if len(parts) < 5 or not parts[0].isdigit():
        return None
    tail = parts[-3:]
    if not _is_amount_token(tail[0]) or not _is_amount_token(tail[1]) or not _is_amount_token(tail[2]):
        return None
    name = " ".join(parts[1:-3]).strip(" -:\t")
    if len(name) < 2:
        return None
    qty = Decimal(tail[0].replace(",", "."))
    unit_price_cents = _to_cents_with_optional_decimals(tail[1])
    line_total_cents = _to_cents_with_optional_decimals(tail[2])
    return {
        "line_no": line_no,
        "source_item_id": f"line:{line_no}",
        "name": name[:240],
        "qty": f"{qty:.3f}",
        "unit": None,
        "unit_price_cents": unit_price_cents,
        "line_total_cents": line_total_cents,
        "category": None,
    }


def _parse_stacked_item(*, name_line: str, amount_line: str, line_no: int) -> dict[str, object] | None:
    if _PRICE_RE.search(name_line) is not None:
        return None
    stripped_name = name_line.strip(" -:\t")
    if len(stripped_name) < 2:
        return None
    weighted_item = _parse_weighted_item(
        name_line=stripped_name,
        amount_line=amount_line,
        line_no=line_no,
    )
    if weighted_item is not None:
        return weighted_item
    if any(char.isdigit() for char in stripped_name):
        return None
    amount_match = re.fullmatch(r"(?P<amount>-?\d+[.,]\d{2})(?:\s+[A-Z])?", amount_line.strip())
    if amount_match is None:
        return None
    amount = _to_cents(amount_match.group("amount"))
    return {
        "line_no": line_no,
        "source_item_id": f"line:{line_no}",
        "name": stripped_name[:240],
        "qty": "1.000",
        "unit": None,
        "unit_price_cents": amount,
        "line_total_cents": amount,
        "category": None,
    }


def _parse_weighted_item(*, name_line: str, amount_line: str, line_no: int) -> dict[str, object] | None:
    amount_match = _STACKED_WEIGHT_ROW_RE.fullmatch(amount_line.strip())
    if amount_match is None:
        return None
    qty_raw = amount_match.group("qty").replace(",", ".")
    unit_price_raw = amount_match.group("unit_price")
    qty = Decimal(qty_raw)
    unit_price_cents = _to_cents_with_optional_decimals(unit_price_raw)
    line_total_cents = int((qty * Decimal(unit_price_cents)).to_integral_value())
    return {
        "line_no": line_no,
        "source_item_id": f"line:{line_no}",
        "name": name_line[:240],
        "qty": f"{qty:.3f}",
        "unit": "kg",
        "unit_price_cents": unit_price_cents,
        "line_total_cents": line_total_cents,
        "category": None,
    }


def _is_amount_token(token: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:[.,]\d{1,2})?", token))


def _to_cents_with_optional_decimals(raw: str) -> int:
    normalized = raw.replace(",", ".")
    if "." not in normalized:
        normalized = f"{normalized}.00"
    elif normalized.rsplit(".", 1)[1] and len(normalized.rsplit(".", 1)[1]) == 1:
        normalized = f"{normalized}0"
    return _to_cents(normalized)
