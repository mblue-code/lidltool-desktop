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


def parse_receipt_text(text: str, *, fallback_store: str = "OCR Upload") -> ParsedReceipt:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    purchased_at = _extract_date(lines) or datetime.now(tz=UTC)
    store_name = _extract_store_name(lines, fallback_store=fallback_store)
    total_cents = _extract_total(lines)
    items = _extract_items(lines)
    fingerprint = sha256(text.encode("utf-8")).hexdigest()
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


def _extract_store_name(lines: list[str], *, fallback_store: str) -> str:
    if not lines:
        return fallback_store
    first = lines[0]
    if len(first) > 2 and not any(char.isdigit() for char in first):
        return first[:120]
    return fallback_store


def _extract_date(lines: list[str]) -> datetime | None:
    for line in lines[:10]:
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
    for line in lines:
        if _TOTAL_RE.search(line):
            continue
        price_match = _PRICE_RE.search(line)
        if price_match is None:
            continue
        amount = _to_cents(price_match.group("amount"))
        name = line[: price_match.start()].strip(" -:\t")
        if len(name) < 2:
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
    return items


def _to_cents(raw: str) -> int:
    normalized = raw.replace(",", ".")
    return int((Decimal(normalized) * 100).to_integral_value())
