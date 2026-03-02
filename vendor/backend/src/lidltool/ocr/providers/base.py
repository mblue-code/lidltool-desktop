from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OcrResult:
    provider: str
    text: str
    confidence: float | None = None
    latency_ms: int | None = None
    metadata: dict[str, object] | None = None


class OcrProvider:
    name: str

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> OcrResult:
        raise NotImplementedError
