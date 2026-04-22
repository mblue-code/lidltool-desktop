from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from lidltool.config import build_config
from lidltool.ocr.provider_router import OcrProviderRouter
from lidltool.ocr.providers.glm_ocr_local import GlmOcrLocalProvider
from lidltool.ocr.providers.openai_compatible import OpenAICompatibleProvider


def _make_pdf_bytes(lines: list[str]) -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=24)
        y += 36
    try:
        return document.tobytes()
    finally:
        document.close()


def _blank_ocr_config() -> object:
    with tempfile.TemporaryDirectory(prefix="desktop-ocr-short-circuit-") as tmpdir:
        config = build_config(db_override=Path(tmpdir) / "test.sqlite")
    config.ocr_default_provider = "glm_ocr_local"
    config.ocr_fallback_enabled = False
    config.ocr_fallback_provider = None
    config.ocr_glm_local_base_url = None
    config.ocr_glm_local_model = None
    config.ocr_openai_base_url = None
    config.ocr_openai_api_key = None
    config.ocr_openai_model = None
    config.ai_base_url = None
    config.ai_model = None
    return config


class OcrProviderShortCircuitTest(unittest.TestCase):
    def test_router_allows_embedded_pdf_text_without_ocr_runtime_config(self) -> None:
        routed = OcrProviderRouter(_blank_ocr_config()).extract(
            payload=_make_pdf_bytes(["LIDL", "TOTAL 4,48"]),
            mime_type="application/pdf",
            file_name="receipt.pdf",
        )

        self.assertEqual(routed.result.provider, "glm_ocr_local")
        self.assertIn("LIDL", routed.result.text)
        self.assertEqual(routed.attempted_providers, ["glm_ocr_local"])
        self.assertEqual(routed.result.metadata["document_strategy"], "pypdf_text")

    def test_glm_local_uses_embedded_pdf_text_without_runtime_config(self) -> None:
        provider = GlmOcrLocalProvider(_blank_ocr_config())

        result = provider.extract(
            payload=_make_pdf_bytes(["LIDL", "TOTAL 4,48"]),
            mime_type="application/pdf",
            file_name="receipt.pdf",
        )

        self.assertEqual(result.provider, "glm_ocr_local")
        self.assertIn("LIDL", result.text)
        self.assertEqual(result.metadata["document_strategy"], "pypdf_text")

    def test_openai_compatible_uses_embedded_pdf_text_without_runtime_config(self) -> None:
        provider = OpenAICompatibleProvider(_blank_ocr_config())

        result = provider.extract(
            payload=_make_pdf_bytes(["REWE", "SUMME EUR 21,95"]),
            mime_type="application/pdf",
            file_name="receipt.pdf",
        )

        self.assertEqual(result.provider, "openai_compatible")
        self.assertIn("REWE", result.text)
        self.assertEqual(result.metadata["document_strategy"], "pypdf_text")


if __name__ == "__main__":
    unittest.main()
