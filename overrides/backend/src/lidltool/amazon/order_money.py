from __future__ import annotations

import re
from dataclasses import dataclass, field
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

_REFUND_LABEL_KEYWORDS = (
    "summe_der_erstattung",
    "gesamterstattungsbetrag",
    "erstattung",
    "refund_total",
    "refund_amount",
    "refunded",
    "refund",
)


@dataclass(frozen=True, slots=True)
class AmazonFinancialNormalization:
    gross_total_cents: int
    final_order_total_cents: int
    refund_total_cents: int
    net_spending_total_cents: int
    payment_adjustment_total_cents: int = 0
    flags: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


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


def is_refund_summary_label(label: Any) -> bool:
    normalized = normalize_text_key(label)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in _REFUND_LABEL_KEYWORDS)


def _has_amount_value(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _order_total_entries(order: dict[str, Any]) -> list[dict[str, Any]]:
    raw_subtotals = order.get("subtotals")
    subtotals = raw_subtotals if isinstance(raw_subtotals, list) else []
    return [
        subtotal
        for subtotal in subtotals
        if isinstance(subtotal, dict)
        and str(subtotal.get("category") or "").strip().lower() == "order_total"
    ]


def _refund_total_cents(order: dict[str, Any]) -> int:
    raw_subtotals = order.get("subtotals")
    subtotals = raw_subtotals if isinstance(raw_subtotals, list) else []
    total = 0
    seen: set[tuple[str, int]] = set()
    for subtotal in subtotals:
        if not isinstance(subtotal, dict):
            continue
        category = str(subtotal.get("category") or "").strip().lower()
        label = subtotal.get("label")
        if category != "refund_info" and not is_refund_summary_label(label):
            continue
        amount_cents = abs(to_int_cents(subtotal.get("amount")))
        if amount_cents <= 0:
            continue
        key = (normalize_text_key(label), amount_cents)
        if key in seen:
            continue
        seen.add(key)
        total += amount_cents
    return total


def _payment_adjustment_total_cents(order: dict[str, Any]) -> int:
    raw_adjustments = order.get("paymentAdjustments")
    adjustments = raw_adjustments if isinstance(raw_adjustments, list) else []
    total = 0
    seen: set[tuple[str, int, str]] = set()
    for adjustment in adjustments:
        if not isinstance(adjustment, dict):
            continue
        subkind = str(adjustment.get("subkind") or "").strip()
        label = str(adjustment.get("label") or "")
        if not subkind:
            subkind = payment_adjustment_subkind(label) or ""
        amount_cents = abs(
            to_int_cents(
                adjustment.get("amount_cents")
                if adjustment.get("amount_cents") is not None
                else adjustment.get("amount")
            )
        )
        if not subkind or amount_cents <= 0:
            continue
        key = (subkind, amount_cents, label)
        if key in seen:
            continue
        seen.add(key)
        total += amount_cents
    return total


def _resolve_final_order_total_cents(order: dict[str, Any], gross_total_cents: int) -> tuple[int, str, str | None]:
    original_order = order.get("originalOrder")
    if isinstance(original_order, dict) and _has_amount_value(original_order.get("totalAmount")):
        return max(0, to_int_cents(original_order.get("totalAmount"))), "original_order_total", None

    if _has_amount_value(order.get("totalAmount")):
        return max(0, to_int_cents(order.get("totalAmount"))), "order_total_amount", None

    order_total_entries = _order_total_entries(order)
    for entry in reversed(order_total_entries):
        if _has_amount_value(entry.get("amount")):
            return max(0, to_int_cents(entry.get("amount"))), "subtotal_order_total", None

    return max(0, gross_total_cents), "gross_total_fallback", "missing_final_order_total"


def normalize_order_financials(
    order: dict[str, Any],
    *,
    gross_total_cents: int | None = None,
    payment_adjustment_total_cents: int | None = None,
) -> AmazonFinancialNormalization:
    resolved_gross_total_cents = (
        max(0, int(gross_total_cents))
        if gross_total_cents is not None
        else max_positive_order_total_subtotal_cents(order)
    )
    if resolved_gross_total_cents <= 0 and _has_amount_value(order.get("totalGross")):
        resolved_gross_total_cents = max(0, to_int_cents(order.get("totalGross")))
    if resolved_gross_total_cents <= 0 and _has_amount_value(order.get("totalAmount")):
        resolved_gross_total_cents = max(0, to_int_cents(order.get("totalAmount")))

    final_total_cents, final_source, warning = _resolve_final_order_total_cents(
        order, resolved_gross_total_cents
    )
    refund_total_cents = _refund_total_cents(order)
    resolved_payment_adjustment_total_cents = (
        max(0, int(payment_adjustment_total_cents))
        if payment_adjustment_total_cents is not None
        else _payment_adjustment_total_cents(order)
    )
    net_spending_total_cents = max(final_total_cents - refund_total_cents, 0)

    flags: list[str] = []
    warnings: list[str] = []
    if warning:
        warnings.append(warning)
    if refund_total_cents > 0:
        flags.append("fully_refunded" if net_spending_total_cents == 0 else "partial_refund")
    if final_source == "original_order_total":
        flags.append("final_total_from_original_order")
    elif final_source == "subtotal_order_total":
        flags.append("final_total_from_subtotal")
    elif final_source == "gross_total_fallback":
        flags.append("final_total_from_gross_fallback")
    if final_total_cents != resolved_gross_total_cents:
        flags.append("final_total_differs_from_gross")
    if refund_total_cents > final_total_cents:
        flags.append("refund_exceeds_final_total")

    return AmazonFinancialNormalization(
        gross_total_cents=resolved_gross_total_cents,
        final_order_total_cents=final_total_cents,
        refund_total_cents=refund_total_cents,
        net_spending_total_cents=net_spending_total_cents,
        payment_adjustment_total_cents=resolved_payment_adjustment_total_cents,
        flags=tuple(flags),
        warnings=tuple(warnings),
        diagnostics={
            "final_order_total_source": final_source,
        },
    )


def amazon_financials_payload(financials: AmazonFinancialNormalization) -> dict[str, Any]:
    return {
        "gross_total_cents": financials.gross_total_cents,
        "final_order_total_cents": financials.final_order_total_cents,
        "refund_total_cents": financials.refund_total_cents,
        "net_spending_total_cents": financials.net_spending_total_cents,
        "payment_adjustment_total_cents": financials.payment_adjustment_total_cents,
        "flags": list(financials.flags),
        "warnings": list(financials.warnings),
        "diagnostics": financials.diagnostics,
    }


def max_positive_order_total_subtotal_cents(order: dict[str, Any]) -> int:
    candidates: list[int] = []
    for subtotal in _order_total_entries(order):
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
