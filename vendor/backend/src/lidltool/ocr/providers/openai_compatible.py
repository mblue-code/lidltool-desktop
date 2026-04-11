from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urlparse

from lidltool.ai.config import get_ai_api_key, get_ai_oauth_access_token
from lidltool.config import AppConfig
from lidltool.ocr.document_preparation import PreparedOcrImage, prepare_document_for_vision
from lidltool.ocr.providers.base import OcrProvider, OcrResult

_DEFAULT_SYSTEM_PROMPT = (
    "You are a receipt OCR engine. Transcribe the receipt faithfully in reading order. "
    "Preserve line breaks, do not summarize, and do not add commentary."
)
_DEFAULT_USER_PROMPT = (
    "Extract the receipt text from this document and return plain text only."
)


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
        configuration_error = self.configuration_error()
        if configuration_error is not None:
            raise RuntimeError(configuration_error)

        prepared = prepare_document_for_vision(
            payload=payload,
            mime_type=mime_type,
            file_name=file_name,
        )
        if prepared.text is not None:
            return OcrResult(
                provider=self.name,
                text=prepared.text,
                confidence=None,
                latency_ms=None,
                metadata=prepared.metadata,
            )

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
            metadata={
                "strategy": "openai_chat_completion",
                "model": model,
                "base_url": base_url,
                **prepared.metadata,
            },
        )

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


def _content_parts(images: list[PreparedOcrImage]) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = [{"type": "text", "text": _DEFAULT_USER_PROMPT}]
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
