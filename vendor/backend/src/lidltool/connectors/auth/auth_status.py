from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from lidltool.connectors.auth.auth_capabilities import (
    AuthLifecycleCapabilityAction,
    ConnectorAuthCapabilities,
)
from lidltool.connectors.sdk.manifest import ConnectorManifest

NormalizedAuthState = Literal[
    "not_connected",
    "connecting",
    "connected",
    "reauth_required",
    "auth_failed",
    "bootstrap_running",
    "bootstrap_canceled",
]
BootstrapLifecycleState = Literal["idle", "running", "succeeded", "failed", "canceled"]
AuthActionStatus = Literal["started", "reused", "canceled", "confirmed", "no_op", "not_supported"]


@dataclass(frozen=True, slots=True)
class AuthBootstrapSnapshot:
    source_id: str
    state: BootstrapLifecycleState
    command: tuple[str, ...] | None = None
    pid: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    return_code: int | None = None
    output_tail: tuple[str, ...] = ()
    can_cancel: bool = False
    was_reused: bool = False


@dataclass(frozen=True, slots=True)
class AuthStatusSnapshot:
    manifest: ConnectorManifest
    capabilities: ConnectorAuthCapabilities
    state: NormalizedAuthState
    detail: str | None = None
    bootstrap: AuthBootstrapSnapshot | None = None
    available_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    implemented_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    compatibility_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    reserved_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuthActionResult:
    manifest: ConnectorManifest
    source_id: str
    state: NormalizedAuthState
    status: AuthActionStatus
    ok: bool
    detail: str | None = None
    bootstrap: AuthBootstrapSnapshot | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    handled_exceptions: tuple[type[Exception], ...] = ()
