from __future__ import annotations

import threading
import time
from typing import Any

from lidltool.config import AppConfig
from lidltool.ocr.document_preparation import prepare_document_for_vision
from lidltool.ocr.providers.base import OcrProvider, OcrResult

_DESKTOP_LOCAL_MODEL_NAME = "rapidocr_ppocr_v4"


class DesktopLocalProvider(OcrProvider):
    name = "desktop_local"

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._engine: Any | None = None
        self._engine_lock = threading.Lock()

    def configuration_error(self) -> str | None:
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            return (
                "Desktop local OCR runtime is unavailable; "
                f"rapidocr_onnxruntime could not be imported: {exc}"
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
                metadata={
                    "strategy": "desktop_local_pdf_text",
                    "model": _DESKTOP_LOCAL_MODEL_NAME,
                    **prepared.metadata,
                },
            )

        started = time.perf_counter()
        engine = self._engine_instance()
        text_chunks: list[str] = []
        confidences: list[float] = []

        for image in prepared.images:
            result, _elapsed = engine(image.payload)
            page_text, page_confidences = _coerce_rapidocr_result(result)
            if page_text:
                text_chunks.append(page_text)
            confidences.extend(page_confidences)

        text = "\n\n".join(chunk for chunk in text_chunks if chunk.strip()).strip()
        if not text:
            raise RuntimeError("desktop local OCR produced no text")

        latency_ms = int((time.perf_counter() - started) * 1000)
        confidence = (
            max(min(sum(confidences) / len(confidences), 1.0), 0.0)
            if confidences
            else None
        )
        return OcrResult(
            provider=self.name,
            text=text,
            confidence=confidence,
            latency_ms=latency_ms,
            metadata={
                "strategy": "desktop_local_rapidocr",
                "model": _DESKTOP_LOCAL_MODEL_NAME,
                "pages_processed": len(prepared.images),
                **prepared.metadata,
            },
        )

    def _engine_instance(self) -> Any:
        if self._engine is not None:
            return self._engine
        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
            return self._engine


def _coerce_rapidocr_result(result: Any) -> tuple[str, list[float]]:
    if result is None:
        return "", []
    if not isinstance(result, list):
        raise RuntimeError("desktop local OCR returned an invalid result payload")

    text_chunks: list[str] = []
    confidences: list[float] = []
    for item in result:
        if not isinstance(item, list | tuple) or len(item) < 3:
            continue
        text = item[1]
        score = item[2]
        normalized_text = str(text).strip() if text is not None else ""
        if normalized_text:
            text_chunks.append(normalized_text)
        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            continue
        confidences.append(max(min(numeric_score, 1.0), 0.0))
    return "\n".join(text_chunks).strip(), confidences
