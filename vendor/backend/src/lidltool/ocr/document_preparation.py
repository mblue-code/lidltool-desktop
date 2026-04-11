from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from pypdf import PdfReader

_PDF_RENDER_DPI = 144


@dataclass(slots=True)
class PreparedOcrImage:
    payload: bytes
    mime_type: str
    file_name: str


@dataclass(slots=True)
class PreparedOcrDocument:
    text: str | None
    images: list[PreparedOcrImage]
    metadata: dict[str, object]


def prepare_document_for_vision(
    *,
    payload: bytes,
    mime_type: str,
    file_name: str,
) -> PreparedOcrDocument:
    if mime_type != "application/pdf":
        return PreparedOcrDocument(
            text=None,
            images=[PreparedOcrImage(payload=payload, mime_type=mime_type, file_name=file_name)],
            metadata={"document_strategy": "direct_image", "file_name": file_name},
        )

    text = _extract_pdf_text(payload)
    if text:
        return PreparedOcrDocument(
            text=text,
            images=[],
            metadata={"document_strategy": "pypdf_text", "file_name": file_name},
        )

    images = _render_pdf_pages(payload=payload, file_name=file_name)
    if not images:
        raise RuntimeError("PDF could not be rasterized into OCR images")

    return PreparedOcrDocument(
        text=None,
        images=images,
        metadata={
            "document_strategy": "pdf_rasterized_images",
            "file_name": file_name,
            "pages_rendered": len(images),
        },
    )


def _extract_pdf_text(payload: bytes) -> str:
    reader = PdfReader(BytesIO(payload))
    chunks = []
    for page in reader.pages:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _render_pdf_pages(*, payload: bytes, file_name: str) -> list[PreparedOcrImage]:
    document = fitz.open(stream=payload, filetype="pdf")
    stem = Path(file_name).stem or "document"
    rendered: list[PreparedOcrImage] = []
    try:
        for page_index in range(document.page_count):
            page = document.load_page(page_index)
            pixmap = page.get_pixmap(dpi=_PDF_RENDER_DPI, alpha=False)
            rendered.append(
                PreparedOcrImage(
                    payload=pixmap.tobytes("png"),
                    mime_type="image/png",
                    file_name=f"{stem}-page-{page_index + 1}.png",
                )
            )
    finally:
        document.close()
    return rendered

