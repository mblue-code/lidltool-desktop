from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from lidltool.config import AppConfig
from lidltool.ocr.providers.base import OcrProvider, OcrResult


class ExternalApiProvider(OcrProvider):
    name = "external_api"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._url = config.ocr_external_api_url
        self._api_key = config.ocr_external_api_key
        self._timeout_s = max(config.ocr_request_timeout_s, 1.0)

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> OcrResult:
        if not self._url:
            raise RuntimeError("external OCR API URL is not configured")
        parsed = urlparse(self._url)
        if not parsed.scheme:
            raise RuntimeError("external OCR API URL must include URL scheme")
        if parsed.scheme.lower() != "https" and not self._config.allow_insecure_transport:
            raise RuntimeError(
                "external OCR API URL must use https "
                "(set LIDLTOOL_ALLOW_INSECURE_TRANSPORT=true only for local testing)"
            )
        started = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = {
            "file_name": file_name,
            "mime_type": mime_type,
            "file_base64": base64.b64encode(payload).decode("ascii"),
        }
        with httpx.Client(
            timeout=self._timeout_s,
            verify=not self._config.allow_insecure_tls_verify,
        ) as client:
            response = client.post(self._url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        text, confidence = _coerce_ocr_response(data)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return OcrResult(
            provider=self.name,
            text=text,
            confidence=confidence,
            latency_ms=latency_ms,
            metadata={"response_shape": list(data.keys()) if isinstance(data, dict) else None},
        )


def _coerce_ocr_response(data: Any) -> tuple[str, float | None]:
    if isinstance(data, dict):
        text_value = data.get("text")
        if isinstance(text_value, str):
            confidence = _float_or_none(data.get("confidence"))
            return text_value, confidence
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("text"), str):
            return str(result["text"]), _float_or_none(result.get("confidence"))
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict) and isinstance(message.get("content"), str):
                    return str(message["content"]), None
    raise RuntimeError("unsupported external OCR response schema")


def _float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
