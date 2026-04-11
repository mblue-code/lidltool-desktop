from __future__ import annotations

from typing import Any

from lidltool.connectors.base import BaseConnectorAdapter


class StubConnectorNotImplementedError(RuntimeError):
    pass


class StubConnectorAdapter(BaseConnectorAdapter):
    def __init__(self, *, source: str, store_name: str) -> None:
        self._source = source
        self._store_name = store_name

    def _message(self) -> str:
        return (
            f"connector stub only for source={self._source} store={self._store_name}; "
            "implementation not available yet"
        )

    def authenticate(self) -> dict[str, Any]:
        return {"authenticated": False, "stub": True, "error": self._message()}

    def refresh_auth(self) -> dict[str, Any]:
        return {"refreshed": False, "stub": True, "error": self._message()}

    def healthcheck(self) -> dict[str, Any]:
        return {"healthy": False, "stub": True, "error": self._message()}

    def discover_new_records(self) -> list[str]:
        return []

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        raise StubConnectorNotImplementedError(
            f"{self._message()}; record_ref={record_ref} cannot be fetched"
        )

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        raise StubConnectorNotImplementedError(
            f"{self._message()}; normalization is unavailable"
        )

    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        return []
