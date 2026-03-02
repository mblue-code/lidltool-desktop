from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader

from lidltool.ocr.providers.base import OcrProvider, OcrResult


class TesseractProvider(OcrProvider):
    name = "tesseract"

    def extract(
        self,
        *,
        payload: bytes,
        mime_type: str,
        file_name: str,
    ) -> OcrResult:
        started = time.perf_counter()
        if mime_type == "application/pdf":
            text = self._extract_pdf_text(payload)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return OcrResult(
                provider=self.name,
                text=text,
                confidence=None,
                latency_ms=latency_ms,
                metadata={"strategy": "pypdf_text"},
            )

        if shutil.which("tesseract") is None:
            raise RuntimeError("tesseract executable not found in PATH")
        with tempfile.TemporaryDirectory(prefix="lidltool-ocr-") as tmp_dir:
            suffix = Path(file_name).suffix or ".img"
            in_path = Path(tmp_dir) / f"source{suffix}"
            in_path.write_bytes(payload)
            proc = subprocess.run(
                ["tesseract", str(in_path), "stdout"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                stderr = proc.stderr.strip() or "unknown tesseract error"
                raise RuntimeError(f"tesseract OCR failed: {stderr}")
            latency_ms = int((time.perf_counter() - started) * 1000)
            return OcrResult(
                provider=self.name,
                text=proc.stdout,
                confidence=None,
                latency_ms=latency_ms,
                metadata={"strategy": "tesseract_cli"},
            )

    @staticmethod
    def _extract_pdf_text(payload: bytes) -> str:
        with tempfile.NamedTemporaryFile(prefix="lidltool-ocr-", suffix=".pdf") as handle:
            handle.write(payload)
            handle.flush()
            reader = PdfReader(handle.name)
            chunks = []
            for page in reader.pages:
                chunk = page.extract_text() or ""
                chunks.append(chunk)
            text = "\n".join(chunks).strip()
            if not text:
                raise RuntimeError("pdf OCR fallback did not extract text")
            return text
