from __future__ import annotations

import base64
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from lidltool.config import AppConfig
from lidltool.ocr.document_preparation import PreparedOcrImage, prepare_document_for_vision
from lidltool.ocr.providers.base import OcrProvider, OcrResult

_OLLAMA_PROMPT = "Text Recognition:"


class GlmOcrLocalProvider(OcrProvider):
    name = "glm_ocr_local"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._timeout_s = max(config.ocr_request_timeout_s, 1.0)
        self._retries = max(config.ocr_request_retries, 0)
        self._rapidocr_engine: Any | None = None

    def configuration_error(self) -> str | None:
        if self._should_use_packaged_engine():
            try:
                self._resolve_rapidocr_engine()
            except Exception as exc:  # noqa: BLE001
                return f"GLM-OCR local packaged engine is unavailable: {exc}"
            return None
        if not self._base_url():
            return "GLM-OCR local base URL is not configured"
        if not self._model():
            return "GLM-OCR local model is not configured"
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

        if self._should_use_packaged_engine():
            return self._extract_with_packaged_engine(
                prepared_images=prepared.images,
                prepared_metadata=prepared.metadata,
            )

        base_url = self._base_url()
        model = self._model()
        if base_url is None or model is None:
            raise RuntimeError("GLM-OCR local provider is not configured")

        parsed = urlparse(base_url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise RuntimeError("GLM-OCR local base URL must use http or https")

        if self._api_mode() == "ollama_generate":
            return self._extract_with_ollama(
                prepared_images=prepared.images,
                prepared_metadata=prepared.metadata,
                base_url=base_url,
                model=model,
            )
        return self._extract_with_openai(
            prepared_images=prepared.images,
            prepared_metadata=prepared.metadata,
            base_url=base_url,
            model=model,
        )

    def _extract_with_packaged_engine(
        self,
        *,
        prepared_images: list[PreparedOcrImage],
        prepared_metadata: dict[str, object],
    ) -> OcrResult:
        engine = self._resolve_rapidocr_engine()
        started = time.perf_counter()
        text_chunks: list[str] = []
        confidences: list[float] = []
        pages_with_text = 0
        for image in prepared_images:
            result, _ = engine(image.payload)
            page_lines = _coerce_rapidocr_lines(result)
            if not page_lines:
                continue
            pages_with_text += 1
            text_chunks.append("\n".join(page_lines))
            confidences.extend(_coerce_rapidocr_confidences(result))
        text = "\n\n".join(chunk for chunk in text_chunks if chunk.strip()).strip()
        if not text:
            raise RuntimeError("GLM-OCR local packaged engine did not detect any text")
        latency_ms = int((time.perf_counter() - started) * 1000)
        confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else None
        )
        return OcrResult(
            provider=self.name,
            text=text,
            confidence=confidence,
            latency_ms=latency_ms,
            metadata={
                "strategy": "glm_ocr_local_rapidocr_onnxruntime",
                "pages_processed": len(prepared_images),
                "pages_with_text": pages_with_text,
                **prepared_metadata,
            },
        )

    def _extract_with_openai(
        self,
        *,
        prepared_images: list[PreparedOcrImage],
        prepared_metadata: dict[str, object],
        base_url: str,
        model: str,
    ) -> OcrResult:
        try:
            from openai import OpenAI
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"openai SDK is unavailable: {exc}") from exc

        started = time.perf_counter()
        client = OpenAI(
            base_url=base_url,
            api_key=(self._config.ocr_glm_local_api_key or "").strip() or "EMPTY",
            timeout=self._timeout_s,
            max_retries=self._retries,
        )
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": _content_parts(prepared_images),
                }
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
                "strategy": "glm_ocr_local_vllm",
                "model": model,
                "base_url": base_url,
                **prepared_metadata,
            },
        )

    def _extract_with_ollama(
        self,
        *,
        prepared_images: list[PreparedOcrImage],
        prepared_metadata: dict[str, object],
        base_url: str,
        model: str,
    ) -> OcrResult:
        started = time.perf_counter()
        headers = {"Content-Type": "application/json"}
        api_key = (self._config.ocr_glm_local_api_key or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body = {
            "model": model,
            "prompt": _OLLAMA_PROMPT,
            "images": [base64.b64encode(image.payload).decode("ascii") for image in prepared_images],
            "stream": False,
            "options": {"temperature": 0},
        }
        with httpx.Client(
            timeout=self._timeout_s,
            verify=not self._config.allow_insecure_tls_verify,
        ) as client:
            response = client.post(_ollama_generate_url(base_url), headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
        text = _coerce_ollama_text(data)
        latency_ms = int((time.perf_counter() - started) * 1000)
        return OcrResult(
            provider=self.name,
            text=text,
            confidence=None,
            latency_ms=latency_ms,
            metadata={
                "strategy": "glm_ocr_local_ollama_generate",
                "model": model,
                "base_url": base_url,
                **prepared_metadata,
            },
        )

    def _base_url(self) -> str | None:
        normalized = (self._config.ocr_glm_local_base_url or "").strip()
        return normalized or None

    def _model(self) -> str | None:
        normalized = (self._config.ocr_glm_local_model or "").strip()
        return normalized or None

    def _api_mode(self) -> str:
        normalized = (self._config.ocr_glm_local_api_mode or "").strip().lower()
        return normalized or "ollama_generate"

    def _should_use_packaged_engine(self) -> bool:
        return self._base_url() is None

    def _resolve_rapidocr_engine(self) -> Any:
        if self._rapidocr_engine is not None:
            return self._rapidocr_engine
        try:
            from rapidocr_onnxruntime import RapidOCR
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"rapidocr_onnxruntime import failed: {exc}") from exc
        self._rapidocr_engine = RapidOCR()
        return self._rapidocr_engine


def _data_url(*, payload: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _content_parts(images: list[PreparedOcrImage]) -> list[dict[str, object]]:
    parts: list[dict[str, object]] = [{"type": "text", "text": "Text Recognition:"}]
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
        raise RuntimeError("GLM-OCR local response did not include choices")
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
    raise RuntimeError("GLM-OCR local response did not include text content")


def _ollama_generate_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/generate"):
        target_path = path
    elif path.endswith("/v1"):
        target_path = f"{path[:-3]}/api/generate" if path[:-3] else "/api/generate"
    elif path:
        target_path = f"{path}/api/generate"
    else:
        target_path = "/api/generate"
    return urlunparse(parsed._replace(path=target_path, params="", query="", fragment=""))


def _coerce_ollama_text(data: Any) -> str:
    if not isinstance(data, dict):
        raise RuntimeError("GLM-OCR Ollama response must be a JSON object")
    response = data.get("response")
    if not isinstance(response, str):
        raise RuntimeError("GLM-OCR Ollama response did not include text content")
    normalized = response.strip()
    if "<|begin_of_image|>" in normalized:
        raise RuntimeError("GLM-OCR Ollama returned malformed OCR output")
    if normalized.startswith("```") and normalized.endswith("```"):
        normalized = normalized.strip("`").strip()
    if not normalized:
        raise RuntimeError("GLM-OCR Ollama response did not include text content")
    return normalized


def _coerce_rapidocr_lines(result: Any) -> list[str]:
    if not isinstance(result, list):
        return []
    lines: list[str] = []
    for item in result:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        text = item[1]
        if isinstance(text, str) and text.strip():
            lines.append(text.strip())
    return lines


def _coerce_rapidocr_confidences(result: Any) -> list[float]:
    if not isinstance(result, list):
        return []
    confidences: list[float] = []
    for item in result:
        if not isinstance(item, list | tuple) or len(item) < 3:
            continue
        raw_confidence = item[2]
        if isinstance(raw_confidence, int | float):
            confidences.append(float(raw_confidence))
    return confidences
