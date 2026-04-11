from __future__ import annotations

from dataclasses import dataclass

from lidltool.config import AppConfig
from lidltool.ocr.providers.base import OcrProvider, OcrResult
from lidltool.ocr.providers.external_api import ExternalApiProvider
from lidltool.ocr.providers.glm_ocr_local import GlmOcrLocalProvider
from lidltool.ocr.providers.openai_compatible import OpenAICompatibleProvider


@dataclass(slots=True)
class RoutedOcrResult:
    result: OcrResult
    fallback_used: bool
    attempted_providers: list[str]


class OcrProviderRouter:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._providers: dict[str, OcrProvider] = {
            "glm_ocr_local": GlmOcrLocalProvider(config),
            "openai_compatible": OpenAICompatibleProvider(config),
            "external_api": ExternalApiProvider(config),
        }

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> RoutedOcrResult:
        primary = self._config.ocr_default_provider or "glm_ocr_local"
        provider_order = [primary]
        fallback = (self._config.ocr_fallback_provider or "").strip()
        if (
            self._config.ocr_fallback_enabled
            and fallback
            and fallback != primary
            and fallback not in provider_order
        ):
            provider_order.append(fallback)
        attempted: list[str] = []
        last_error: Exception | None = None
        for provider_name in provider_order:
            provider = self._providers.get(provider_name)
            if provider is None:
                last_error = RuntimeError(f"unsupported OCR provider: {provider_name}")
                if provider_name == primary or not self._config.ocr_fallback_enabled:
                    raise last_error
                continue
            attempted.append(provider_name)
            configuration_error = provider.configuration_error()
            if configuration_error is not None:
                last_error = RuntimeError(configuration_error)
                if provider_name == primary and not self._config.ocr_fallback_enabled:
                    raise last_error
                continue
            try:
                result = provider.extract(
                    payload=payload,
                    mime_type=mime_type,
                    file_name=file_name,
                )
                return RoutedOcrResult(
                    result=result,
                    fallback_used=provider_name != primary,
                    attempted_providers=attempted,
                )
            except Exception as exc:
                last_error = exc
                if provider_name == primary and not self._config.ocr_fallback_enabled:
                    raise
                continue
        if last_error is not None:
            raise last_error
        raise RuntimeError("no OCR providers are available")
