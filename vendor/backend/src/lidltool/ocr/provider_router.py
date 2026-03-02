from __future__ import annotations

from dataclasses import dataclass

from lidltool.config import AppConfig
from lidltool.ocr.providers.base import OcrProvider, OcrResult
from lidltool.ocr.providers.external_api import ExternalApiProvider
from lidltool.ocr.providers.tesseract import TesseractProvider


@dataclass(slots=True)
class RoutedOcrResult:
    result: OcrResult
    fallback_used: bool
    attempted_providers: list[str]


class OcrProviderRouter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._providers: dict[str, OcrProvider] = {
            "external_api": ExternalApiProvider(config),
            "tesseract": TesseractProvider(),
        }

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> RoutedOcrResult:
        primary = self._config.ocr_default_provider or "external_api"
        fallback = "tesseract" if primary != "tesseract" else "external_api"
        attempted: list[str] = []
        try:
            attempted.append(primary)
            first_result = self._providers[primary].extract(
                payload=payload,
                mime_type=mime_type,
                file_name=file_name,
            )
            return RoutedOcrResult(
                result=first_result,
                fallback_used=False,
                attempted_providers=attempted,
            )
        except Exception:
            if not self._config.ocr_fallback_enabled:
                raise
            attempted.append(fallback)
            fallback_result = self._providers[fallback].extract(
                payload=payload,
                mime_type=mime_type,
                file_name=file_name,
            )
            return RoutedOcrResult(
                result=fallback_result,
                fallback_used=True,
                attempted_providers=attempted,
            )
