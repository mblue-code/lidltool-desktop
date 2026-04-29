from __future__ import annotations

import re
from typing import Any

_NORMALIZE_TEXT_RE = re.compile(r"[^a-z0-9]+")
_PAYMENT_ADJUSTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "gift_card_balance": (
        "geschenkgutschein",
        "gift_card",
        "giftcard",
        "gift_voucher",
        "giftvoucher",
        "gift_certificate",
        "giftcertificate",
        "bon_cadeau",
        "cheque_cadeau",
    ),
    "store_credit": (
        "gutschein_eingeloest",
        "gutschein_eingelost",
        "voucher_redeemed",
        "credit_balance",
        "store_credit",
    ),
    "reward_points": (
        "praemienpunkte",
        "reward_points",
        "rewards_points",
        "punkte_eingeloest",
    ),
}


def to_int_cents(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        raw = (
            value.replace("€", "")
            .replace("EUR", "")
            .replace("£", "")
            .replace("GBP", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        if not raw:
            return 0
        try:
            return int(round(float(raw) * 100))
        except ValueError:
            return 0
    return 0


def normalize_text_key(value: Any) -> str:
    if value is None:
        return ""
    normalized = (
        str(value)
        .strip()
        .lower()
        .translate(
            str.maketrans(
                {
                    "ä": "ae",
                    "ö": "oe",
                    "ü": "ue",
                    "ß": "ss",
                    "é": "e",
                    "è": "e",
                    "ê": "e",
                    "à": "a",
                    "ç": "c",
                }
            )
        )
    )
    return _NORMALIZE_TEXT_RE.sub("_", normalized).strip("_")


def payment_adjustment_subkind(label: Any) -> str | None:
    normalized = normalize_text_key(label)
    if not normalized:
        return None
    for subkind, keywords in _PAYMENT_ADJUSTMENT_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return subkind
    return None


def max_positive_order_total_subtotal_cents(order: dict[str, Any]) -> int:
    raw_subtotals = order.get("subtotals")
    subtotals = raw_subtotals if isinstance(raw_subtotals, list) else []
    candidates: list[int] = []
    for subtotal in subtotals:
        if not isinstance(subtotal, dict):
            continue
        category = str(subtotal.get("category") or "").strip().lower()
        if category != "order_total":
            continue
        amount_cents = to_int_cents(subtotal.get("amount"))
        if amount_cents > 0:
            candidates.append(amount_cents)
    return max(candidates, default=0)


def resolve_total_gross_cents(
    *,
    order: dict[str, Any],
    explicit_total_cents: int,
    total_is_explicit: bool,
    line_total_sum: int,
    basket_discount_total_cents: int,
    payment_adjustment_total_cents: int,
) -> int:
    if payment_adjustment_total_cents > 0:
        subtotal_order_total_cents = max_positive_order_total_subtotal_cents(order)
        if subtotal_order_total_cents > 0:
            return subtotal_order_total_cents
        if total_is_explicit and explicit_total_cents > 0:
            return explicit_total_cents
        inferred_prepayment_cents = line_total_sum
        candidates = [
            amount for amount in (inferred_prepayment_cents, line_total_sum) if amount > 0
        ]
        if candidates:
            return max(candidates)
    if total_is_explicit:
        return explicit_total_cents
    return max(0, line_total_sum + basket_discount_total_cents)


def resolve_discount_total_cents(
    *,
    order: dict[str, Any],
    item_discount_total_cents: int,
    basket_discount_total_cents: int,
    payment_adjustment_total_cents: int,
) -> int | None:
    explicit_total_savings_cents = to_int_cents(order.get("totalSavings"))
    if explicit_total_savings_cents > payment_adjustment_total_cents:
        explicit_total_savings_cents -= payment_adjustment_total_cents
    else:
        explicit_total_savings_cents = 0
    inferred_discount_total_cents = abs(item_discount_total_cents) + abs(basket_discount_total_cents)
    resolved = max(explicit_total_savings_cents, inferred_discount_total_cents)
    return resolved if resolved > 0 else None
