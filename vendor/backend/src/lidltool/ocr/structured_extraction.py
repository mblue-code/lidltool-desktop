from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from lidltool.ai.runtime.models import JsonCompletionRequest, ModelRuntime, RuntimeTask
from lidltool.ai.runtime.providers import OpenAICompatibleRuntimeAdapter, is_local_endpoint
from lidltool.ai.runtime.resolver import resolve_runtime_client
from lidltool.config import AppConfig
from lidltool.ocr.parser import ParsedReceipt, parse_receipt_text, to_canonical_payload

LOGGER = logging.getLogger(__name__)

_NON_ITEM_NAME_RE = re.compile(
    r"(?i)\b("
    r"datum|uhrzeit|beleg|trace|zahlung|payment|mastercard|visa|ec[- ]?karte|"
    r"betrag|steuer|netto|brutto|summe|gesamtbetrag|tse|signatur|transaktion|"
    r"terminal|kasse|bed\.|bon[- ]?nr|kundenbeleg|bonus|coupon|gutschein|"
    r"kontaktlos|contactless|approved|debit|capt\.|ref|vu[- ]nr|pos[- ]info"
    r")\b"
)
_ITEM_DISCOUNT_LABEL_RE = re.compile(
    r"(?i)\b(rabatt|discount|coupon|gutschein|bonus|vorteil|aktion|frischerabatt)\b"
)
_DEPOSIT_LABEL_RE = re.compile(r"(?i)\b(pfand|deposit|mehrweg)\b")
_DEPOSIT_RETURN_LABEL_RE = re.compile(r"(?i)\b(leergut|pfandgutsch|deposit return|bottle return)\b")
_ZERO_WIDTH_SPACE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e]")
_CONTINUATION_LINE_RE = re.compile(
    r"(?i)^\s*(\d+[.,]\d+\s*(kg|g|lb|oz|l|ml)|\d+\s*(stk|stuck|pcs|piece)\s*x)\s*$"
)
_KNOWN_CHAIN_TOKEN_RE = re.compile(
    r"(?i)\b(rewe|penny|lidl|aldi|edeka|rossmann|kaufland|netto|marktkauf|dm)\b"
)
_LEGAL_SUFFIX_RE = re.compile(r"(?i)\b(gmbh|ohg|ag|kg|mbh|ug)\b")
_GERMAN_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{2,4})(?!\d)")
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DATE_HINT_KEYWORD_RE = re.compile(r"(?i)\b(datum|bon[- ]?nr|kasse|bed\.|uhr|zeit|geg\.)\b")
_SYSTEM_PROMPT = (
    "You convert OCR receipt text into strict JSON. "
    "Return JSON only. Do not include markdown. "
    "Treat the receipt as sections: header, basket items, discounts/credits, totals, payment, and footer. "
    "Extract only purchased basket items into `items`. "
    "Do not put payment lines, card details, timestamps, tax tables, TSE/signature rows, "
    "store metadata, bonus summaries, or footer text into `items`. "
    "Use the merchant printed in the header as `store_name`. Do not use the file name as the merchant. "
    "Normalize obvious OCR spacing artifacts in the merchant name, for example 'R E W E' should become 'REWE'. "
    "Use the printed transaction date on the receipt as `purchased_at` in ISO format YYYY-MM-DD. "
    "For German-style dates like DD.MM.YYYY, preserve day and month correctly and do not swap them. "
    "When several dates appear, prefer the sale date near Bon-Nr., Datum, Uhrzeit, payment, or register metadata. "
    "Do not invent a date from TSE signature blocks or unrelated footer text. "
    "Deposit lines such as Pfand/Mehrweg are basket items, not discounts. "
    "Represent them in `items` with `is_deposit=true`. "
    "Negative-value lines and savings rows belong in `discounts`, not `items`. "
    "Put coupons, discounts, bonus credits, bottle-return credits, and markdown rows into `discounts`. "
    "Examples of discount-like rows include Rabatt, Discount, Coupon, Gutschein, Bonus, Vorteil, Aktion, "
    "Frischerabatt, Mitarbeiterrabatt, Inflationsrabatt, Scan u. Go, Leergutbon, LEERGUT EINWEG, and Pfandgutsch. "
    "If a discount clearly applies to the previous item, set `item_index` to that 1-based item index. "
    "If a receipt contains quantity/weight continuation rows, merge them into the previous item instead of "
    "creating a new item. "
    "On text-layer eBon receipts, lines after SUMME/payment/customer-slip sections are usually not basket items. "
    "Ignore rows like Kundenbeleg, Kartenzahlung, PAYBACK summaries, Punktestand, zusätzliche Vorteile, "
    "Betrag EUR, Cashback EUR, Gesamt EUR, AS-Zeit, Trace-Nr., and TSE-Start/TSE-Stop. "
    "Use integer cent amounts in EUR. "
    "Use this JSON shape: "
    "{store_name, purchased_at, total_gross_cents, currency, discount_total_cents, "
    "items:[{name, qty, unit, unit_price_cents, line_total_cents, is_deposit}], "
    "discounts:[{label, amount_cents, scope, item_index, kind, subkind}], ignored_lines:[...]}. "
    "Set `discount_total_cents` to the total savings represented by `discounts`. "
    "Set `ignored_lines` to notable non-item lines you intentionally excluded."
)
_REPAIR_PROMPT = (
    "You are repairing a failed receipt JSON extraction. "
    "Return JSON only and keep the same schema as before. "
    "The previous candidates failed because merchant, date, discounts, and footer lines were mixed up. "
    "Fix the extraction so that `items` contains only real purchased basket items. "
    "Move negative-value lines such as discounts, coupons, Mitarbeiterrabatt, Leergutbon, and Pfandgutsch to `discounts`. "
    "Keep positive Pfand/Mehrweg charges as deposit items in `items`. "
    "Ignore payment, tax, PAYBACK, TSE, customer-slip, and footer rows. "
    "Use the printed merchant from the receipt text, not the file name. "
    "Use the printed transaction date from the receipt text in ISO format YYYY-MM-DD. "
    "If quantity or weight continuation rows exist, merge them into the related basket item. "
    "Prefer a consistent, reconciled basket over copying noisy footer lines."
)


class StructuredReceiptItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    qty: str = "1.000"
    unit: str | None = None
    unit_price_cents: int | None = Field(default=None, ge=0)
    line_total_cents: int = Field(ge=0)
    is_deposit: bool = False

    @model_validator(mode="before")
    @classmethod
    def _coerce_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("qty") is None and payload.get("quantity") is not None:
            payload["qty"] = str(payload.get("quantity"))
        elif payload.get("qty") is not None and not isinstance(payload.get("qty"), str):
            payload["qty"] = str(payload.get("qty"))
        if payload.get("line_total_cents") is None:
            for candidate in ("total_price_cents", "total_cents", "amount_cents", "price_cents"):
                if payload.get(candidate) is not None:
                    payload["line_total_cents"] = payload.get(candidate)
                    break
        if payload.get("unit_price_cents") is None:
            for candidate in (
                "unit_price",
                "unitPrice_cents",
                "unit_price_cents_per_kg",
                "unit_price_cents_per_unit",
            ):
                if payload.get(candidate) is not None:
                    payload["unit_price_cents"] = payload.get(candidate)
                    break
        if payload.get("weight_kg") is not None:
            payload["qty"] = str(payload.get("weight_kg"))
            payload.setdefault("unit", "kg")
        return payload

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if len(normalized) < 2:
            raise ValueError("item name must be at least 2 characters")
        return normalized[:240]

    @field_validator("qty")
    @classmethod
    def _validate_qty(cls, value: str) -> str:
        normalized = _normalize_text(value) or "1.000"
        Decimal(normalized.replace(",", "."))
        return normalized.replace(",", ".")


class StructuredReceiptDiscount(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    amount_cents: int = Field(gt=0)
    scope: str = "transaction"
    item_index: int | None = Field(default=None, ge=1)
    kind: str = "discount"
    subkind: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("label") is None:
            for candidate in ("description", "name", "title"):
                if payload.get(candidate) is not None:
                    payload["label"] = payload.get(candidate)
                    break
        if payload.get("amount_cents") is not None:
            try:
                payload["amount_cents"] = abs(int(payload["amount_cents"]))
            except Exception:  # noqa: BLE001
                pass
        item_index = payload.get("item_index")
        if item_index is not None:
            try:
                item_index_int = int(item_index)
                payload["item_index"] = item_index_int if item_index_int > 0 else None
            except Exception:  # noqa: BLE001
                payload["item_index"] = None
        if payload.get("scope") is None:
            payload["scope"] = "item" if payload.get("item_index") is not None else "transaction"
        elif str(payload.get("scope")).lower() == "basket":
            payload["scope"] = "transaction"
        if payload.get("subkind") is not None:
            payload["subkind"] = _normalize_text(str(payload["subkind"])).lower().replace(" ", "_")
        return payload

    @field_validator("label")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        normalized = _normalize_text(value)
        if len(normalized) < 2:
            raise ValueError("discount label must be at least 2 characters")
        return normalized[:240]

    @field_validator("scope")
    @classmethod
    def _validate_scope(cls, value: str) -> str:
        normalized = _normalize_text(value).lower()
        if normalized not in {"item", "transaction"}:
            raise ValueError("discount scope must be 'item' or 'transaction'")
        return normalized


class StructuredReceiptPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    store_name: str | None = None
    purchased_at: str | None = None
    total_gross_cents: int | None = Field(default=None, ge=0)
    currency: str = "EUR"
    discount_total_cents: int = Field(default=0, ge=0)
    items: list[StructuredReceiptItem] = Field(default_factory=list)
    discounts: list[StructuredReceiptDiscount] = Field(default_factory=list)
    ignored_lines: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value)
        if payload.get("total_gross_cents") is None:
            for candidate in (
                "total_cents",
                "grand_total_cents",
                "receipt_total_cents",
                "total_amount_cents",
            ):
                if payload.get(candidate) is not None:
                    payload["total_gross_cents"] = payload.get(candidate)
                    break
        if payload.get("discount_total_cents") is None and isinstance(payload.get("discounts"), list):
            total = 0
            for discount in payload["discounts"]:
                if isinstance(discount, dict):
                    try:
                        total += abs(int(discount.get("amount_cents", 0) or 0))
                    except Exception:  # noqa: BLE001
                        continue
            payload["discount_total_cents"] = total
        return payload

    @field_validator("store_name")
    @classmethod
    def _validate_store_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_text(value)
        return normalized[:120] if normalized else None

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str) -> str:
        normalized = _normalize_text(value).upper() or "EUR"
        return normalized[:8]


class LineTotalMode(str, Enum):
    AS_IS = "as_is"
    UNIT_FOR_MULTI_QTY = "unit_for_multi_qty"


@dataclass(slots=True)
class StructuredExtractionResult:
    canonical: dict[str, object]
    discounts: list[dict[str, object]]
    source: str
    metadata: dict[str, object]


@dataclass(slots=True)
class _StructuredCandidate:
    source: str
    payload: StructuredReceiptPayload
    validation_error: str | None
    score: int


class OcrStructuredReceiptExtractor:
    def __init__(
        self,
        *,
        config: AppConfig,
        runtime: ModelRuntime | None = None,
    ) -> None:
        self._config = config
        self._runtime = runtime

    def extract(
        self,
        *,
        ocr_text: str,
        fallback_store: str,
        ocr_provider: str | None,
        ocr_metadata: dict[str, object] | None = None,
    ) -> StructuredExtractionResult:
        fallback_parsed = parse_receipt_text(ocr_text, fallback_store=fallback_store)
        fallback_canonical = to_canonical_payload(fallback_parsed)
        candidate_errors: list[dict[str, object]] = []
        candidates: list[_StructuredCandidate] = []

        runtime = self._runtime or _resolve_structured_runtime(
            config=self._config,
            ocr_provider=ocr_provider,
        )
        if runtime is not None:
            request = JsonCompletionRequest(
                task=RuntimeTask.OCR_TEXT_FALLBACK,
                model_name=runtime.model_name or "gpt-5.2-codex",
                system_prompt=_SYSTEM_PROMPT,
                user_json={
                    "ocr_text": ocr_text,
                    "fallback_parser": {
                        "store_name": fallback_parsed.store_name,
                        "purchased_at": fallback_parsed.purchased_at.isoformat(),
                        "total_gross_cents": fallback_parsed.total_gross_cents,
                        "currency": fallback_parsed.currency,
                    },
                },
                temperature=0,
                max_tokens=2400,
                timeout_s=min(max(self._config.ocr_request_timeout_s, 10.0), 90.0),
                max_retries=max(self._config.ocr_request_retries, 1),
                metadata={"source": "ocr_structured_receipt"},
            )
            try:
                response = runtime.complete_json(request)
                candidates.append(
                    _candidate_from_raw(
                        source="text",
                        raw_payload=response.data,
                        ocr_text=ocr_text,
                        fallback=fallback_parsed,
                    )
                )
            except (RuntimeError, ValidationError, ValueError, TypeError) as exc:
                LOGGER.warning("ocr.structured.failed provider=%s error=%s", ocr_provider or "-", exc)
                candidate_errors.append({"source": "text", "reason": "structured_extraction_failed", "error": str(exc)})
        else:
            candidate_errors.append({"source": "text", "reason": "runtime_unavailable"})

        vision_candidate = _vision_candidate_from_metadata(ocr_metadata)
        if vision_candidate is not None:
            try:
                candidates.append(
                    _candidate_from_raw(
                        source="vision",
                        raw_payload=vision_candidate,
                        ocr_text=ocr_text,
                        fallback=fallback_parsed,
                    )
                )
            except (ValidationError, ValueError, TypeError) as exc:
                candidate_errors.append(
                    {"source": "vision", "reason": "structured_extraction_failed", "error": str(exc)}
                )
        elif isinstance(ocr_metadata, dict):
            candidate = ocr_metadata.get("structured_vision_candidate")
            if isinstance(candidate, dict) and candidate:
                candidate_errors.append(
                    {
                        "source": "vision",
                        "reason": str(candidate.get("reason") or candidate.get("status") or "unavailable"),
                    }
                )

        selected = _select_best_candidate(candidates)
        if selected is None and runtime is not None:
            repair_candidate = _request_repair_candidate(
                runtime=runtime,
                ocr_text=ocr_text,
                fallback=fallback_parsed,
                candidates=candidates,
                candidate_errors=candidate_errors,
                config=self._config,
            )
            if repair_candidate is not None:
                try:
                    candidates.append(
                        _candidate_from_raw(
                            source="repair",
                            raw_payload=repair_candidate,
                            ocr_text=ocr_text,
                            fallback=fallback_parsed,
                        )
                    )
                except (ValidationError, ValueError, TypeError) as exc:
                    candidate_errors.append(
                        {"source": "repair", "reason": "structured_extraction_failed", "error": str(exc)}
                    )
            selected = _select_best_candidate(candidates)

        if selected is None:
            return StructuredExtractionResult(
                canonical=fallback_canonical,
                discounts=[],
                source="parser",
                metadata={
                    "strategy": "parser_fallback",
                    "reason": "structured_validation_failed",
                    "failure_mode": True,
                    "candidate_errors": candidate_errors,
                    "candidates": [
                        {
                            "source": candidate.source,
                            "validation_error": candidate.validation_error,
                            "score": candidate.score,
                            "structured_raw": candidate.payload.model_dump(mode="python"),
                        }
                        for candidate in candidates
                    ],
                },
            )

        canonical = _payload_to_canonical_payload(
            payload=selected.payload,
            fallback=fallback_parsed,
        )
        discounts = _payload_to_discount_rows(selected.payload)
        return StructuredExtractionResult(
            canonical=canonical,
            discounts=discounts,
            source="structured",
            metadata={
                "strategy": "structured_extraction",
                "selected_source": selected.source,
                "provider_kind": runtime.provider_kind.value if runtime is not None else None,
                "model_name": runtime.model_name if runtime is not None else None,
                "structured_raw": selected.payload.model_dump(mode="python"),
                "validation": {"status": "accepted", "parser_fallback_avoided": True},
                "candidates": [
                    {
                        "source": candidate.source,
                        "validation_error": candidate.validation_error,
                        "score": candidate.score,
                        "selected": candidate.source == selected.source,
                    }
                    for candidate in candidates
                ],
                "candidate_errors": candidate_errors,
            },
        )


def _resolve_structured_runtime(
    *,
    config: AppConfig,
    ocr_provider: str | None,
) -> ModelRuntime | None:
    if ocr_provider == "glm_ocr_local":
        runtime = _build_ocr_openai_runtime(
            task=RuntimeTask.OCR_TEXT_FALLBACK,
            base_url=config.ocr_glm_local_base_url,
            api_key=config.ocr_glm_local_api_key or "EMPTY",
            model_name=config.ocr_glm_local_model,
            timeout_s=config.ocr_request_timeout_s,
            max_retries=config.ocr_request_retries,
            allow_insecure_transport=config.allow_insecure_transport,
            require_chat_mode=config.ocr_glm_local_api_mode == "openai_chat_completion",
        )
        if runtime is not None and runtime.health().healthy:
            return runtime
    if ocr_provider == "openai_compatible":
        runtime = _build_ocr_openai_runtime(
            task=RuntimeTask.OCR_TEXT_FALLBACK,
            base_url=config.ocr_openai_base_url,
            api_key=config.ocr_openai_api_key,
            model_name=config.ocr_openai_model,
            timeout_s=config.ocr_request_timeout_s,
            max_retries=config.ocr_request_retries,
            allow_insecure_transport=config.allow_insecure_transport,
            require_chat_mode=True,
        )
        if runtime is not None and runtime.health().healthy:
            return runtime
    shared_runtime = resolve_runtime_client(
        config,
        task=RuntimeTask.OCR_TEXT_FALLBACK,
    )
    if shared_runtime is not None and shared_runtime.health().healthy:
        return shared_runtime
    return None


def _build_ocr_openai_runtime(
    *,
    task: RuntimeTask,
    base_url: str | None,
    api_key: str | None,
    model_name: str | None,
    timeout_s: float,
    max_retries: int,
    allow_insecure_transport: bool,
    require_chat_mode: bool,
) -> ModelRuntime | None:
    if not require_chat_mode or not base_url or not model_name:
        return None
    return OpenAICompatibleRuntimeAdapter(
        task=task,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_s=timeout_s,
        max_retries=max_retries,
        allow_remote=not is_local_endpoint(base_url),
        allow_insecure_transport=allow_insecure_transport,
    )


def _vision_candidate_from_metadata(ocr_metadata: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(ocr_metadata, dict):
        return None
    candidate = ocr_metadata.get("structured_vision_candidate")
    if not isinstance(candidate, dict):
        return None
    if str(candidate.get("status") or "").lower() != "ok":
        return None
    payload = candidate.get("payload")
    return payload if isinstance(payload, dict) else None


def _candidate_from_raw(
    *,
    source: str,
    raw_payload: Any,
    ocr_text: str,
    fallback: ParsedReceipt,
) -> _StructuredCandidate:
    if not isinstance(raw_payload, dict):
        raise TypeError("structured candidate payload must be a JSON object")
    normalized_payload = _normalize_structured_payload(
        payload=raw_payload,
        ocr_text=ocr_text,
        fallback=fallback,
    )
    payload = StructuredReceiptPayload.model_validate(normalized_payload)
    usable, validation_error = _structured_payload_is_usable(payload=payload, fallback=fallback)
    score = _candidate_score(payload=payload, fallback=fallback, usable=usable)
    return _StructuredCandidate(
        source=source,
        payload=payload,
        validation_error=validation_error,
        score=score,
    )


def _select_best_candidate(candidates: list[_StructuredCandidate]) -> _StructuredCandidate | None:
    usable = [candidate for candidate in candidates if candidate.validation_error is None]
    if not usable:
        return None
    return sorted(
        usable,
        key=lambda candidate: (
            candidate.score,
            1 if candidate.source == "vision" else 0,
            len(candidate.payload.discounts),
            len(_effective_structured_items(candidate.payload)),
        ),
        reverse=True,
    )[0]


def _candidate_score(
    *,
    payload: StructuredReceiptPayload,
    fallback: ParsedReceipt,
    usable: bool,
) -> int:
    score = 100 if usable else 0
    if payload.total_gross_cents == fallback.total_gross_cents:
        score += 8
    if payload.purchased_at and _coerce_datetime(payload.purchased_at) is not None:
        score += 10
    if payload.store_name:
        score += 10
        normalized_store = _normalize_text(payload.store_name)
        if not _looks_like_file_name(normalized_store):
            score += 10
        score += _merchant_specificity_score(normalized_store)
        if normalized_store.lower() == _normalize_text(fallback.store_name).lower():
            score += 4
    item_count = len(_effective_structured_items(payload))
    score += min(item_count, 20)
    score += min(len(payload.discounts) * 2, 20)
    if any(discount.amount_cents > 0 for discount in payload.discounts):
        score += 4
    return score


def _request_repair_candidate(
    *,
    runtime: ModelRuntime,
    ocr_text: str,
    fallback: ParsedReceipt,
    candidates: list[_StructuredCandidate],
    candidate_errors: list[dict[str, object]],
    config: AppConfig,
) -> dict[str, object] | None:
    request = JsonCompletionRequest(
        task=RuntimeTask.OCR_TEXT_FALLBACK,
        model_name=runtime.model_name or "gpt-5.2-codex",
        system_prompt=_REPAIR_PROMPT,
        user_json={
            "ocr_text": ocr_text,
            "fallback_parser": {
                "store_name": fallback.store_name,
                "purchased_at": fallback.purchased_at.isoformat(),
                "total_gross_cents": fallback.total_gross_cents,
                "currency": fallback.currency,
                "items": fallback.items,
            },
            "previous_candidates": [
                {
                    "source": candidate.source,
                    "validation_error": candidate.validation_error,
                    "structured_raw": candidate.payload.model_dump(mode="python"),
                }
                for candidate in candidates
            ],
            "candidate_errors": candidate_errors,
            "repair_focus": [
                "merchant normalization",
                "date disambiguation",
                "discount/footer separation",
                "deposit vs deposit-return handling",
            ],
        },
        temperature=0,
        max_tokens=2600,
        timeout_s=min(max(config.ocr_request_timeout_s, 10.0), 90.0),
        max_retries=max(config.ocr_request_retries, 1),
        metadata={"source": "ocr_structured_receipt_repair"},
    )
    try:
        response = runtime.complete_json(request)
    except RuntimeError as exc:
        LOGGER.warning("ocr.structured.repair.failed error=%s", exc)
        return None
    return response.data if isinstance(response.data, dict) else None


def _structured_payload_is_usable(
    *,
    payload: StructuredReceiptPayload,
    fallback: ParsedReceipt,
) -> tuple[bool, str | None]:
    resolved_total = payload.total_gross_cents or fallback.total_gross_cents
    if resolved_total <= 0:
        return False, "missing_total"
    filtered_items = _effective_structured_items(payload)
    if not filtered_items:
        return False, "no_usable_items"
    line_total_mode = _resolve_line_total_mode(filtered_items, payload=payload, resolved_total=resolved_total)
    if line_total_mode is None:
        return False, "totals_do_not_reconcile"
    computed_total = sum(_effective_line_total(item, mode=line_total_mode) for item in filtered_items)
    discount_total = sum(
        discount.amount_cents for discount in payload.discounts if not _is_deposit_charge_discount(discount)
    )
    expected_total = computed_total - discount_total
    return True, None


def _normalize_structured_payload(
    *,
    payload: dict[str, object],
    ocr_text: str,
    fallback: ParsedReceipt,
) -> dict[str, object]:
    normalized = dict(payload)
    merchant_hint = _extract_merchant_hint(ocr_text)
    normalized["store_name"] = _normalize_merchant_name(
        value=normalized.get("store_name"),
        merchant_hint=merchant_hint,
        fallback_store=fallback.store_name,
    )
    normalized["purchased_at"] = _normalize_purchased_at(
        value=normalized.get("purchased_at"),
        ocr_text=ocr_text,
        fallback=fallback,
    )

    normalized_discounts = _normalize_discount_list(normalized.get("discounts"))
    normalized_items: list[dict[str, object]] = []
    ignored_lines = [
        _normalize_text(str(line))
        for line in (normalized.get("ignored_lines") if isinstance(normalized.get("ignored_lines"), list) else [])
        if _normalize_text(str(line))
    ]

    raw_items = normalized.get("items")
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        name = _normalize_text(str(item.get("name") or ""))
        if not name:
            continue
        item["name"] = name

        signed_total = _coerce_signed_int(
            item.get("line_total_cents")
            or item.get("total_price_cents")
            or item.get("total_cents")
            or item.get("amount_cents")
            or item.get("price_cents")
        )
        if signed_total is not None and signed_total < 0:
            normalized_discounts.append(_discount_from_item(item=item, amount_cents=abs(signed_total)))
            ignored_lines.append(name)
            continue
        if _is_discount_like_item(item):
            amount_cents = _coerce_signed_int(
                item.get("discount_cents") or item.get("amount_cents") or item.get("line_total_cents")
            )
            normalized_discounts.append(
                _discount_from_item(item=item, amount_cents=abs(amount_cents) if amount_cents else None)
            )
            ignored_lines.append(name)
            continue
        if _looks_like_continuation_line(name) or _looks_like_footer_line(name):
            ignored_lines.append(name)
            continue
        if _is_positive_deposit_item(item):
            item["is_deposit"] = True
        normalized_items.append(item)

    normalized["items"] = normalized_items
    normalized["discounts"] = _dedupe_discount_dicts(normalized_discounts)
    normalized["ignored_lines"] = sorted({line for line in ignored_lines if line})
    normalized["discount_total_cents"] = sum(
        discount.get("amount_cents", 0)
        for discount in normalized["discounts"]
        if isinstance(discount, dict) and not _is_deposit_charge_discount_dict(discount)
    )
    return normalized


def _payload_to_canonical_payload(
    *,
    payload: StructuredReceiptPayload,
    fallback: ParsedReceipt,
) -> dict[str, object]:
    purchased_at = _coerce_datetime(payload.purchased_at) or fallback.purchased_at
    effective_discount_total = _effective_discount_total(payload)
    items: list[dict[str, object]] = []
    structured_items = _effective_structured_items(payload)
    resolved_total = payload.total_gross_cents or fallback.total_gross_cents
    line_total_mode = _resolve_line_total_mode(structured_items, payload=payload, resolved_total=resolved_total)
    if line_total_mode is None:
        line_total_mode = LineTotalMode.AS_IS
    line_no = 0
    for item in structured_items:
        if _looks_like_non_item(item.name):
            continue
        line_no += 1
        items.append(
            {
                "line_no": line_no,
                "source_item_id": f"line:{line_no}",
                "name": item.name,
                "qty": item.qty,
                "unit": item.unit,
                "unit_price_cents": item.unit_price_cents,
                "line_total_cents": _effective_line_total(item, mode=line_total_mode),
                "category": None,
                "is_deposit": item.is_deposit,
            }
        )
    return {
        "id": fallback.source_transaction_id,
        "purchased_at": purchased_at.isoformat(),
        "store_name": payload.store_name or fallback.store_name,
        "total_gross_cents": payload.total_gross_cents or fallback.total_gross_cents,
        "discount_total_cents": effective_discount_total,
        "currency": payload.currency or fallback.currency,
        "items": items,
        "fingerprint": fallback.source_transaction_id.split(":", 1)[-1],
    }


def _payload_to_discount_rows(payload: StructuredReceiptPayload) -> list[dict[str, object]]:
    discounts: list[dict[str, object]] = []
    for discount in payload.discounts:
        if _is_deposit_charge_discount(discount):
            continue
        item_line_no = discount.item_index if discount.scope == "item" else None
        kind = _normalize_discount_kind(discount.kind, discount.label)
        discounts.append(
            {
                "line_no": item_line_no,
                "promotion_id": (
                    f"ocr-{discount.scope}-{discount.item_index or 'transaction'}-{discount.amount_cents}"
                ),
                "label": discount.label,
                "scope": discount.scope,
                "amount_cents": discount.amount_cents,
                "type": kind,
                "subkind": discount.subkind,
                "funded_by": "retailer",
            }
        )
    return discounts


def _normalize_discount_list(raw_discounts: object) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for raw_discount in raw_discounts if isinstance(raw_discounts, list) else []:
        if not isinstance(raw_discount, dict):
            continue
        label = _normalize_text(
            str(
                raw_discount.get("label")
                or raw_discount.get("description")
                or raw_discount.get("name")
                or ""
            )
        )
        if not label:
            continue
        amount_cents = abs(
            _coerce_signed_int(raw_discount.get("amount_cents") or raw_discount.get("discount_cents") or 0) or 0
        )
        if amount_cents <= 0:
            continue
        item_index = _coerce_positive_int(raw_discount.get("item_index"))
        scope = _normalize_text(str(raw_discount.get("scope") or "")).lower()
        if scope not in {"item", "transaction"}:
            scope = "item" if item_index is not None else "transaction"
        subkind = _normalize_discount_subkind(raw_discount.get("subkind"), label=label)
        kind = _normalize_discount_kind(str(raw_discount.get("kind") or "discount"), label)
        if subkind == "deposit_return":
            scope = "transaction"
        normalized.append(
            {
                "label": label,
                "amount_cents": amount_cents,
                "scope": scope,
                "item_index": item_index,
                "kind": kind,
                "subkind": subkind,
            }
        )
    return normalized


def _effective_discount_total(payload: StructuredReceiptPayload) -> int:
    non_deposit_total = sum(
        discount.amount_cents for discount in payload.discounts if not _is_deposit_charge_discount(discount)
    )
    if non_deposit_total > 0:
        return non_deposit_total
    if payload.discount_total_cents > 0 and not any(
        _is_deposit_discount(discount) for discount in payload.discounts
    ):
        return payload.discount_total_cents
    return 0


def _discount_from_item(
    *,
    item: dict[str, object],
    amount_cents: int | None,
) -> dict[str, object]:
    label = _normalize_text(str(item.get("name") or "Rabatt"))
    subkind = _normalize_discount_subkind(item.get("subkind"), label=label)
    return {
        "label": label,
        "amount_cents": max(amount_cents or 0, 0),
        "scope": "transaction",
        "item_index": None,
        "kind": _normalize_discount_kind(str(item.get("kind") or "discount"), label),
        "subkind": subkind,
    }


def _dedupe_discount_dicts(discounts: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, int, str, str | None]] = set()
    for discount in discounts:
        key = (
            _normalize_text(str(discount.get("label") or "")).lower(),
            int(discount.get("amount_cents") or 0),
            _normalize_text(str(discount.get("scope") or "transaction")).lower(),
            _normalize_text(str(discount.get("subkind") or "")).lower() or None,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(discount)
    return deduped


def _effective_structured_items(payload: StructuredReceiptPayload) -> list[StructuredReceiptItem]:
    items = [
        item
        for item in payload.items
        if not _looks_like_non_item(item.name) and not _should_drop_item_as_deposit_return(item, payload)
    ]
    items.extend(_deposit_items_from_discounts(payload))
    return items


def _resolve_line_total_mode(
    items: list[StructuredReceiptItem],
    *,
    payload: StructuredReceiptPayload,
    resolved_total: int,
) -> LineTotalMode | None:
    discount_total = sum(
        discount.amount_cents for discount in payload.discounts if not _is_deposit_charge_discount(discount)
    )
    as_is_item_total = sum(_effective_line_total(item, mode=LineTotalMode.AS_IS) for item in items)
    as_is_total = as_is_item_total - discount_total
    if abs(as_is_total - resolved_total) <= 5 or abs(as_is_item_total - resolved_total) <= 5:
        return LineTotalMode.AS_IS
    unit_for_multi_item_total = sum(
        _effective_line_total(item, mode=LineTotalMode.UNIT_FOR_MULTI_QTY) for item in items
    )
    unit_for_multi_total = unit_for_multi_item_total - discount_total
    if abs(unit_for_multi_total - resolved_total) <= 5 or abs(unit_for_multi_item_total - resolved_total) <= 5:
        return LineTotalMode.UNIT_FOR_MULTI_QTY
    return None


def _effective_line_total(item: StructuredReceiptItem, *, mode: LineTotalMode) -> int:
    if (
        mode == LineTotalMode.UNIT_FOR_MULTI_QTY
        and item.unit_price_cents is not None
        and not item.is_deposit
    ):
        qty = _parse_qty_value(item.qty)
        unit = _normalize_text(item.unit).lower()
        if (
            qty is not None
            and qty > 1
            and qty == qty.to_integral_value()
            and unit not in {"kg", "g", "lb", "oz", "l", "ml"}
        ):
            return item.unit_price_cents
    return item.line_total_cents


def _parse_qty_value(value: str) -> Decimal | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        return Decimal(normalized.replace(",", "."))
    except Exception:  # noqa: BLE001
        return None


def _deposit_items_from_discounts(payload: StructuredReceiptPayload) -> list[StructuredReceiptItem]:
    deposit_items: list[StructuredReceiptItem] = []
    for discount in payload.discounts:
        if not _is_deposit_charge_discount(discount):
            continue
        deposit_items.append(
            StructuredReceiptItem(
                name="Pfand",
                qty="1.000",
                line_total_cents=discount.amount_cents,
                is_deposit=True,
            )
        )
    return deposit_items


def _is_deposit_discount(discount: StructuredReceiptDiscount) -> bool:
    return _is_deposit_charge_discount(discount) or _is_deposit_return_discount(discount)


def _is_deposit_charge_discount(discount: StructuredReceiptDiscount) -> bool:
    return bool(_DEPOSIT_LABEL_RE.search(discount.label)) and not _is_deposit_return_discount(discount)


def _is_deposit_return_discount(discount: StructuredReceiptDiscount) -> bool:
    label = discount.label
    return bool(_DEPOSIT_RETURN_LABEL_RE.search(label) or "deposit_return" == (discount.subkind or "").lower())


def _is_deposit_charge_discount_dict(discount: dict[str, object]) -> bool:
    label = _normalize_text(str(discount.get("label") or ""))
    subkind = _normalize_text(str(discount.get("subkind") or "")).lower()
    return bool(_DEPOSIT_LABEL_RE.search(label)) and subkind != "deposit_return"


def _should_drop_item_as_deposit_return(
    item: StructuredReceiptItem,
    payload: StructuredReceiptPayload,
) -> bool:
    if not item.is_deposit:
        return False
    item_name = _normalize_text(item.name).lower()
    for discount in payload.discounts:
        if not _is_deposit_return_discount(discount):
            continue
        if discount.amount_cents != item.line_total_cents:
            continue
        discount_label = _normalize_text(discount.label).lower()
        if discount_label in item_name or item_name in discount_label:
            return True
    return False


def _normalize_discount_kind(kind: str, label: str) -> str:
    normalized_kind = _normalize_text(kind).lower() or "discount"
    if normalized_kind != "discount":
        return normalized_kind
    if "coupon" in label.lower():
        return "coupon"
    if "bonus" in label.lower():
        return "bonus"
    return "discount"


def _normalize_discount_subkind(value: object, *, label: str) -> str | None:
    normalized = _normalize_text(str(value or "")).lower().replace(" ", "_")
    if normalized:
        if normalized in {"deposit_refund", "deposit-return"}:
            return "deposit_return"
        return normalized
    lowered_label = label.lower()
    if _DEPOSIT_RETURN_LABEL_RE.search(label):
        return "deposit_return"
    if "coupon" in lowered_label:
        return "coupon"
    if "bonus" in lowered_label:
        return "bonus"
    return None


def _is_discount_like_item(item: dict[str, object]) -> bool:
    name = _normalize_text(str(item.get("name") or ""))
    if not name:
        return False
    if _DEPOSIT_RETURN_LABEL_RE.search(name):
        return True
    if _ITEM_DISCOUNT_LABEL_RE.search(name):
        return True
    return name.lower().startswith("mitarbeiterrabatt")


def _is_positive_deposit_item(item: dict[str, object]) -> bool:
    name = _normalize_text(str(item.get("name") or ""))
    if not name or _DEPOSIT_RETURN_LABEL_RE.search(name):
        return False
    amount_cents = _coerce_signed_int(
        item.get("line_total_cents")
        or item.get("total_price_cents")
        or item.get("amount_cents")
        or item.get("price_cents")
    )
    return bool(_DEPOSIT_LABEL_RE.search(name)) and (amount_cents is None or amount_cents >= 0)


def _looks_like_footer_line(name: str) -> bool:
    lowered = _normalize_text(name).lower()
    if not lowered:
        return True
    if _looks_like_non_item(lowered):
        return True
    return any(
        token in lowered
        for token in (
            "payback",
            "punktestand",
            "coupon eingelost",
            "zusatzlichen vorteile",
            "für sie da",
            "fragen",
            "www.rewe.de",
            "rückgeld",
            "gesamtbetrag",
        )
    )


def _looks_like_continuation_line(name: str) -> bool:
    return bool(_CONTINUATION_LINE_RE.match(name))


def _looks_like_non_item(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return True
    if _NON_ITEM_NAME_RE.search(normalized):
        return True
    if _looks_like_continuation_line(normalized):
        return True
    if len(normalized) > 80 and sum(char.isdigit() for char in normalized) > 8:
        return True
    return False


def _looks_like_file_name(value: str) -> bool:
    normalized = _normalize_text(value).lower()
    if not normalized:
        return True
    return (
        normalized.endswith(".pdf")
        or normalized.endswith(".jpg")
        or normalized.endswith(".jpeg")
        or normalized.endswith(".png")
        or ("_" in normalized and any(char.isdigit() for char in normalized))
    )


def _merchant_specificity_score(value: str) -> int:
    normalized = _normalize_text(value)
    if not normalized:
        return 0
    score = min(len(normalized.split()), 4)
    lowered = normalized.lower()
    if any(token in lowered for token in ("gmbh", "ohg", "ag", "kg", "markt")):
        score += 6
    if lowered in {"rewe", "aldi", "lidl", "penny", "dm", "rossmann", "edeka"}:
        score -= 4
    return score


def _normalize_merchant_name(
    *,
    value: object,
    merchant_hint: str | None,
    fallback_store: str,
) -> str | None:
    candidate = _normalize_text(str(value or ""))
    candidate = _collapse_spaced_chain_name(candidate)
    hint = _collapse_spaced_chain_name(_normalize_text(merchant_hint))
    fallback_normalized = _collapse_spaced_chain_name(_normalize_text(fallback_store))
    if not candidate or _looks_like_file_name(candidate):
        candidate = hint or fallback_normalized
    elif hint and _merchant_specificity_score(hint) > _merchant_specificity_score(candidate):
        candidate = hint
    if candidate and _looks_like_file_name(candidate):
        return hint or None
    return candidate or None


def _collapse_spaced_chain_name(value: str | None) -> str:
    normalized = _normalize_text(value)
    for chain in ("REWE", "ALDI", "LIDL", "PENNY", "EDEKA"):
        parts = r"\s*".join(chain)
        normalized = re.sub(rf"\b{parts}\b", chain, normalized, flags=re.IGNORECASE)
    return normalized


def _extract_merchant_hint(ocr_text: str) -> str | None:
    lines = [_normalize_text(line) for line in ocr_text.splitlines() if _normalize_text(line)]
    if not lines:
        return None
    candidates: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        lowered = line.lower()
        if len(line) > 120 or lowered.startswith("http") or "tel." in lowered or "uid nr" in lowered:
            continue
        if sum(char.isdigit() for char in line) > 8:
            continue
        score = 0
        if _KNOWN_CHAIN_TOKEN_RE.search(line):
            score += 8
        if _LEGAL_SUFFIX_RE.search(line):
            score += 8
        if index < 5:
            score += 2
        if index >= max(len(lines) - 8, 0):
            score += 3
        if "markt" in lowered:
            score += 2
        if line.isupper():
            score += 1
        if score > 0:
            candidates.append((score, line))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], _merchant_specificity_score(item[1])), reverse=True)[0][1]


def _normalize_purchased_at(
    *,
    value: object,
    ocr_text: str,
    fallback: ParsedReceipt,
) -> str:
    parsed_value = _parse_date_only(value)
    hints = _extract_date_hints(ocr_text)
    if parsed_value is not None:
        normalized_value = parsed_value.isoformat()
        if any(hint == normalized_value for _, hint in hints):
            return normalized_value
    if hints:
        return hints[0][1]
    if parsed_value is not None:
        return parsed_value.isoformat()
    return fallback.purchased_at.date().isoformat()


def _extract_date_hints(ocr_text: str) -> list[tuple[int, str]]:
    hints: list[tuple[int, str]] = []
    for index, raw_line in enumerate(ocr_text.splitlines()):
        line = _normalize_text(raw_line)
        lowered = line.lower()
        if not line or "tse" in lowered:
            continue
        line_score = 0
        if _DATE_HINT_KEYWORD_RE.search(line):
            line_score += 6
        if "payback" in lowered or "coupon" in lowered or "vorteile" in lowered:
            line_score -= 4
        if "summe" in lowered:
            line_score += 1
        line_score += max(0, 2 - min(abs(index - 24), 2))
        for match in _GERMAN_DATE_RE.finditer(line):
            day, month, year = match.groups()
            year_int = int(year)
            if year_int < 100:
                year_int += 2000
            try:
                parsed = datetime(year_int, int(month), int(day), tzinfo=UTC)
            except ValueError:
                continue
            hints.append((line_score + 4, parsed.date().isoformat()))
        for match in _ISO_DATE_RE.finditer(line):
            year, month, day = match.groups()
            try:
                parsed = datetime(int(year), int(month), int(day), tzinfo=UTC)
            except ValueError:
                continue
            hints.append((line_score + 2, parsed.date().isoformat()))
    seen: dict[str, int] = {}
    for score, iso_date in hints:
        seen[iso_date] = max(score, seen.get(iso_date, -10))
    return sorted(((score, iso_date) for iso_date, score in seen.items()), reverse=True)


def _parse_date_only(value: object) -> datetime | None:
    if value is None:
        return None
    normalized = _normalize_text(str(value))
    if not normalized:
        return None
    parsed = _coerce_datetime(normalized)
    if parsed is not None:
        return parsed
    german_match = _GERMAN_DATE_RE.search(normalized)
    if german_match is None:
        return None
    day, month, year = german_match.groups()
    year_int = int(year)
    if year_int < 100:
        year_int += 2000
    try:
        return datetime(year_int, int(month), int(day), tzinfo=UTC)
    except ValueError:
        return None


def _coerce_signed_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    normalized = _normalize_text(str(value)).replace("€", "")
    normalized = re.sub(r"(?i)\beur\b", "", normalized)
    if not normalized:
        return None
    if re.search(r"[.,]\d{1,2}$", normalized):
        cents_text = normalized.replace(".", "").replace(",", ".")
        try:
            return int(round(float(cents_text) * 100))
        except ValueError:
            return None
    try:
        return int(round(float(normalized.replace(",", "."))))
    except ValueError:
        return None


def _coerce_positive_int(value: object) -> int | None:
    parsed = _coerce_signed_int(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _normalize_text(value: str | None) -> str:
    normalized = _ZERO_WIDTH_SPACE_RE.sub("", value or "")
    normalized = " ".join(normalized.replace("\xa0", " ").split())
    return normalized.strip()


def _coerce_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
