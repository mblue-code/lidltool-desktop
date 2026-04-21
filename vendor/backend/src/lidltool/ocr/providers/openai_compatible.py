from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urlparse

from lidltool.ai.runtime.providers import parse_completion_text
from lidltool.ai.config import get_ai_api_key, get_ai_oauth_access_token
from lidltool.config import AppConfig
from lidltool.ocr.document_preparation import (
    PreparedOcrImage,
    prepare_document_for_vision,
    prepare_document_images_for_vision,
)
from lidltool.ocr.providers.base import OcrProvider, OcrResult

_DEFAULT_SYSTEM_PROMPT = (
    "You are a receipt OCR engine. Transcribe the receipt faithfully in reading order. "
    "Preserve line breaks, do not summarize, and do not add commentary."
)
_DEFAULT_USER_PROMPT = (
    "Extract the receipt text from this document and return plain text only."
)
_VISION_STRUCTURED_SYSTEM_PROMPT = (
    "You convert receipt images into strict JSON. "
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
    "Deposit lines such as Pfand/Mehrweg are basket items, not discounts. "
    "Represent them in `items` with `is_deposit=true`. "
    "Negative-value lines and savings rows belong in `discounts`, not `items`. "
    "Put coupons, discounts, bonus credits, bottle-return credits, and markdown rows into `discounts`. "
    "If a discount clearly applies to the previous item, set `item_index` to that 1-based item index. "
    "If a receipt contains quantity/weight continuation rows, merge them into the previous item instead of "
    "creating a new item. "
    "Use integer cent amounts in EUR. "
    "Use this JSON shape: "
    "{store_name, purchased_at, total_gross_cents, currency, discount_total_cents, "
    "items:[{name, qty, unit, unit_price_cents, line_total_cents, is_deposit}], "
    "discounts:[{label, amount_cents, scope, item_index, kind, subkind}], ignored_lines:[...]}. "
    "Set `discount_total_cents` to the total savings represented by `discounts`. "
    "Set `ignored_lines` to notable non-item lines you intentionally excluded."
)
_VISION_STRUCTURED_USER_PROMPT = "Extract structured receipt JSON from this document."


class OpenAICompatibleProvider(OcrProvider):
    name = "openai_compatible"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._timeout_s = max(config.ocr_request_timeout_s, 1.0)
        self._retries = max(config.ocr_request_retries, 0)

    def configuration_error(self) -> str | None:
        if not self._resolve_base_url():
            return (
                "OpenAI-compatible OCR base URL is not configured; "
                "set LIDLTOOL_OCR_OPENAI_BASE_URL or LIDLTOOL_AI_BASE_URL"
            )
        if not self._resolve_model():
            return (
                "OpenAI-compatible OCR model is not configured; "
                "set LIDLTOOL_OCR_OPENAI_MODEL or LIDLTOOL_AI_MODEL"
            )
        if not self._resolve_api_key():
            return (
                "OpenAI-compatible OCR API key is not configured; "
                "set LIDLTOOL_OCR_OPENAI_API_KEY or LIDLTOOL_AI_API_KEY"
            )
        return None

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> OcrResult:
        prepared = prepare_document_for_vision(
            payload=payload,
            mime_type=mime_type,
            file_name=file_name,
        )
        configuration_error = self.configuration_error()
        if prepared.text is not None and configuration_error is not None:
            return OcrResult(
                provider=self.name,
                text=prepared.text,
                confidence=None,
                latency_ms=None,
                metadata=prepared.metadata,
            )
        if configuration_error is not None:
            raise RuntimeError(configuration_error)

        base_url = self._resolve_base_url()
        api_key = self._resolve_api_key()
        model = self._resolve_model()
        if base_url is None or api_key is None or model is None:
            raise RuntimeError("OpenAI-compatible OCR provider is not configured")

        parsed = urlparse(base_url)
        if not parsed.scheme:
            raise RuntimeError("OpenAI-compatible OCR base URL must include URL scheme")
        if parsed.scheme.lower() != "https" and not self._config.allow_insecure_transport:
            raise RuntimeError(
                "OpenAI-compatible OCR base URL must use https "
                "(set LIDLTOOL_ALLOW_INSECURE_TRANSPORT=true only for local testing)"
            )

        try:
            from openai import OpenAI
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

        started = time.perf_counter()
        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=self._timeout_s,
            max_retries=self._retries,
        )
        structured_candidate = self._maybe_extract_structured_candidate(
            client=client,
            payload=payload,
            mime_type=mime_type,
            file_name=file_name,
            prepared=prepared,
            model=model,
            base_url=base_url,
        )
        metadata = {
            "model": model,
            "base_url": base_url,
            **prepared.metadata,
        }
        if structured_candidate is not None:
            metadata["structured_vision_candidate"] = structured_candidate
        if prepared.text is not None:
            return OcrResult(
                provider=self.name,
                text=prepared.text,
                confidence=None,
                latency_ms=None,
                metadata=metadata,
            )
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _content_parts(prepared.images),
                },
            ],
        )
        text = _coerce_completion_text(response)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return OcrResult(
            provider=self.name,
            text=text,
            confidence=None,
            latency_ms=latency_ms,
            metadata={"strategy": "openai_chat_completion", **metadata},
        )

    def _maybe_extract_structured_candidate(
        self,
        *,
        client: Any,
        payload: bytes,
        mime_type: str,
        file_name: str,
        prepared: Any,
        model: str,
        base_url: str,
    ) -> dict[str, object] | None:
        if not self._config.ocr_structured_vision_enabled:
            return None
        try:
            images = prepared.images or prepare_document_images_for_vision(
                payload=payload,
                mime_type=mime_type,
                file_name=file_name,
            )
        except Exception as exc:  # noqa: BLE001
            return {"status": "error", "reason": f"image_preparation_failed: {exc}"}
        if not images:
            return {"status": "skipped", "reason": "no_images"}
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=2400,
                messages=[
                    {"role": "system", "content": _VISION_STRUCTURED_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _content_parts(images, user_prompt=_VISION_STRUCTURED_USER_PROMPT),
                    },
                ],
            )
            raw_text = _coerce_completion_text(response)
            parsed = parse_completion_text(raw_text)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if not isinstance(parsed, dict):
                return {
                    "status": "error",
                    "reason": "non_object_json",
                    "raw_text": raw_text,
                    "latency_ms": latency_ms,
                    "model": model,
                    "base_url": base_url,
                }
            return {
                "status": "ok",
                "payload": parsed,
                "raw_text": raw_text,
                "latency_ms": latency_ms,
                "model": model,
                "base_url": base_url,
                "image_count": len(images),
            }
        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {
                "status": "error",
                "reason": str(exc),
                "latency_ms": latency_ms,
                "model": model,
                "base_url": base_url,
            }

    def _resolve_base_url(self) -> str | None:
        for candidate in (self._config.ocr_openai_base_url, self._config.ai_base_url):
            normalized = (candidate or "").strip()
            if normalized:
                return normalized
        return None

    def _resolve_model(self) -> str | None:
        for candidate in (self._config.ocr_openai_model, self._config.ai_model):
            normalized = (candidate or "").strip()
            if normalized:
                return normalized
        return None

    def _resolve_api_key(self) -> str | None:
        direct = (self._config.ocr_openai_api_key or "").strip()
        if direct:
            return direct
        oauth_token = get_ai_oauth_access_token(self._config)
        if oauth_token:
            return oauth_token
        api_key = get_ai_api_key(self._config)
        if api_key:
            return api_key
        return None

def _data_url(*, payload: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _content_parts(
    images: list[PreparedOcrImage],
    *,
    user_prompt: str = _DEFAULT_USER_PROMPT,
) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = [{"type": "text", "text": user_prompt}]
    for image in images:
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_url(payload=image.payload, mime_type=image.mime_type)},
            }
        )
    return parts


def _coerce_completion_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("OpenAI-compatible OCR response did not include choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                continue
            if isinstance(item, dict):
                raw_text = item.get("text")
                if isinstance(raw_text, str) and raw_text.strip():
                    chunks.append(raw_text.strip())
        joined = "\n".join(chunks).strip()
        if joined:
            return joined
    raise RuntimeError("OpenAI-compatible OCR response did not include text content")
