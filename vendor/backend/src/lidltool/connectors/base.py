from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

CONNECTOR_ACTIONS: tuple[str, ...] = (
    "authenticate",
    "refresh_auth",
    "healthcheck",
    "discover_new_records",
    "fetch_record_detail",
    "normalize",
    "extract_discounts",
)
ALLOWED_CONNECTOR_SCOPES: set[str] = {
    "auth.session",
    "read.health",
    "read.receipts",
    "read.receipt_detail",
    "transform.normalize",
    "transform.discounts",
}
DEFAULT_REQUIRED_SCOPES: dict[str, tuple[str, ...]] = {
    "authenticate": ("auth.session",),
    "refresh_auth": ("auth.session",),
    "healthcheck": ("read.health",),
    "discover_new_records": ("read.receipts",),
    "fetch_record_detail": ("read.receipt_detail",),
    "normalize": ("transform.normalize",),
    "extract_discounts": ("transform.discounts",),
}


class Connector(ABC):
    @abstractmethod
    def authenticate(self) -> dict[str, Any]:
        """Validate connector authentication preconditions."""

    @abstractmethod
    def refresh_auth(self) -> dict[str, Any]:
        """Refresh connector authentication/session state."""

    @abstractmethod
    def healthcheck(self) -> dict[str, Any]:
        """Check that connector upstream access is healthy."""

    @abstractmethod
    def discover_new_records(self) -> list[str]:
        """Return source-native references for records to ingest."""

    @abstractmethod
    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        """Fetch a source-native record payload for a record reference."""

    @abstractmethod
    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        """Normalize source-native payload into canonical ingestion shape."""

    @abstractmethod
    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract source discount rows for downstream mapping."""


class BaseConnectorAdapter(Connector):
    """Base adapter for connector implementations.

    Subclasses can override only relevant methods while inheriting strict method
    signatures required by the connector SDK contract tests.
    """

    required_scope_map: dict[str, tuple[str, ...]] = DEFAULT_REQUIRED_SCOPES

    @classmethod
    def required_scopes(cls) -> dict[str, tuple[str, ...]]:
        return dict(cls.required_scope_map)

    def authenticate(self) -> dict[str, Any]:
        raise NotImplementedError

    def refresh_auth(self) -> dict[str, Any]:
        raise NotImplementedError

    def healthcheck(self) -> dict[str, Any]:
        raise NotImplementedError

    def discover_new_records(self) -> list[str]:
        raise NotImplementedError

    def fetch_record_detail(self, record_ref: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize(self, record_detail: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def extract_discounts(self, record_detail: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError


def validate_connector_scope_contract(connector: Connector) -> None:
    required = (
        connector.required_scopes()
        if isinstance(connector, BaseConnectorAdapter)
        else DEFAULT_REQUIRED_SCOPES
    )
    for action in CONNECTOR_ACTIONS:
        scopes = required.get(action)
        if scopes is None:
            raise ValueError(f"connector is missing required scope declaration for action={action}")
        if not scopes:
            raise ValueError(f"connector declared empty scopes for action={action}")
        if any(scope == "*" for scope in scopes):
            raise ValueError(f"connector uses wildcard scope for action={action}")
        unknown = [scope for scope in scopes if scope not in ALLOWED_CONNECTOR_SCOPES]
        if unknown:
            raise ValueError(
                f"connector declared unknown scopes for action={action}: {', '.join(unknown)}"
            )


def require_connector_action_scope(
    connector: Connector,
    *,
    action: str,
    granted_scopes: set[str],
) -> None:
    required = (
        connector.required_scopes()
        if isinstance(connector, BaseConnectorAdapter)
        else DEFAULT_REQUIRED_SCOPES
    )
    action_scopes = required.get(action)
    if action_scopes is None:
        raise PermissionError(f"connector action has no declared scope contract: {action}")
    missing = [scope for scope in action_scopes if scope not in granted_scopes]
    if missing:
        raise PermissionError(
            f"connector action scope denied: action={action} missing_scopes={','.join(missing)}"
        )
