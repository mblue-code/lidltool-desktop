from __future__ import annotations

from statistics import mean
from typing import Any

from lidltool.ocr.parser import ParsedReceipt
from lidltool.ocr.providers.base import OcrResult


def score_transaction(parsed: ParsedReceipt, ocr: OcrResult) -> float:
    base = ocr.confidence if ocr.confidence is not None else 0.72
    if parsed.total_gross_cents <= 0:
        base -= 0.15
    if not parsed.items:
        base -= 0.2
    return _clamp(base)


def score_items(parsed: ParsedReceipt) -> list[float]:
    scores: list[float] = []
    for item in parsed.items:
        score = 0.75
        name = str(item.get("name") or "")
        total_raw = item.get("line_total_cents")
        total_cents = (
            int(total_raw)
            if isinstance(total_raw, int | float | str) and str(total_raw).strip() != ""
            else 0
        )
        if len(name) >= 4:
            score += 0.1
        if total_cents > 0:
            score += 0.1
        scores.append(_clamp(score))
    return scores


def confidence_metadata(
    *,
    parsed: ParsedReceipt,
    ocr: OcrResult,
    fallback_used: bool,
    attempted_providers: list[str],
) -> dict[str, Any]:
    item_scores = score_items(parsed)
    transaction_score = score_transaction(parsed, ocr)
    return {
        "transaction_confidence": transaction_score,
        "item_confidence_scores": item_scores,
        "item_confidence_mean": _clamp(mean(item_scores)) if item_scores else None,
        "ocr_provider": ocr.provider,
        "ocr_confidence": ocr.confidence,
        "ocr_latency_ms": ocr.latency_ms,
        "ocr_fallback_used": fallback_used,
        "ocr_attempted_providers": attempted_providers,
        "ocr_metadata": ocr.metadata or {},
    }


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))
