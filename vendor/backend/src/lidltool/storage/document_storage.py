from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from lidltool.config import AppConfig


class DocumentStorageError(RuntimeError):
    """Raised when a document cannot be persisted."""


class DocumentStorage:
    def __init__(self, config: AppConfig) -> None:
        self._base_path = config.document_storage_path
        self._max_upload_size_bytes = max(config.max_upload_size_mb, 1) * 1024 * 1024
        self._allowed_mime_types = set(config.allowed_upload_mime_types)

    def validate(self, *, mime_type: str, payload: bytes) -> None:
        if mime_type not in self._allowed_mime_types:
            raise DocumentStorageError(f"unsupported mime_type: {mime_type}")
        if len(payload) > self._max_upload_size_bytes:
            raise DocumentStorageError(
                f"upload too large: {len(payload)} bytes (max={self._max_upload_size_bytes})"
            )

    def store(
        self,
        *,
        file_name: str,
        mime_type: str,
        payload: bytes,
    ) -> tuple[str, str]:
        self.validate(mime_type=mime_type, payload=payload)
        sha256 = hashlib.sha256(payload).hexdigest()
        suffix = Path(file_name).suffix or self._suffix_for_mime(mime_type)
        key = f"{uuid4().hex}{suffix}"
        target = self._base_path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return target.resolve().as_uri(), sha256

    def read_bytes(self, *, storage_uri: str) -> bytes:
        if not storage_uri.startswith("file://"):
            raise DocumentStorageError(f"unsupported storage uri: {storage_uri}")
        path = Path(storage_uri.removeprefix("file://"))
        if not path.exists():
            raise DocumentStorageError(f"document missing at {storage_uri}")
        return path.read_bytes()

    @staticmethod
    def _suffix_for_mime(mime_type: str) -> str:
        if mime_type == "application/pdf":
            return ".pdf"
        if mime_type == "image/png":
            return ".png"
        if mime_type == "image/jpeg":
            return ".jpg"
        return ".bin"
