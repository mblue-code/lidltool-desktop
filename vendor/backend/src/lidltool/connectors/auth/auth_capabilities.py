from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, field_validator

AuthKind = Literal[
    "oauth_pkce",
    "browser_session",
    "api_key",
    "cookie_import",
    "file_import",
    "manual_only",
    "none",
]
AuthLifecycleCapabilityAction = Literal["start_auth", "cancel_auth", "confirm_auth"]
AuthBootstrapMethod = Literal[
    "browser",
    "oauth_pkce",
    "headless_refresh",
    "manual_token_import",
    "session_file_import",
]
DEFAULT_RESERVED_AUTH_ACTIONS: tuple[AuthLifecycleCapabilityAction, ...] = (
    "start_auth",
    "cancel_auth",
    "confirm_auth",
)


class ConnectorAuthCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    auth_kind: AuthKind
    supports_live_session_bootstrap: bool = False
    supports_reauth: bool = False
    supports_headless_refresh: bool = False
    supports_manual_confirm: bool = False
    supports_oauth_callback: bool = False
    supports_session_file: bool = False
    bootstrap_methods: tuple[AuthBootstrapMethod, ...] = ()
    implemented_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    compatibility_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    reserved_actions: tuple[AuthLifecycleCapabilityAction, ...] = DEFAULT_RESERVED_AUTH_ACTIONS

    @field_validator(
        "bootstrap_methods",
        "implemented_actions",
        "compatibility_actions",
        "reserved_actions",
        mode="before",
    )
    @classmethod
    def _normalize_actions(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError("auth actions must be a list or tuple")
        normalized: list[AuthLifecycleCapabilityAction] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError("auth actions must contain only strings")
            candidate = item.strip()
            if not candidate:
                raise ValueError("auth actions must contain non-empty strings")
            if candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)  # type: ignore[arg-type]
        return tuple(normalized)

    def available_actions(self) -> tuple[AuthLifecycleCapabilityAction, ...]:
        return tuple(dict.fromkeys((*self.implemented_actions, *self.compatibility_actions)))


def infer_auth_capabilities(
    *,
    auth_kind: AuthKind,
    capabilities: Sequence[str],
    optional_actions: Sequence[str],
    reserved_actions: Sequence[str],
) -> ConnectorAuthCapabilities:
    capability_set = {str(item).strip() for item in capabilities if str(item).strip()}
    optional = cast(
        tuple[AuthLifecycleCapabilityAction, ...],
        tuple(
        action
        for action in optional_actions
        if action in {"start_auth", "cancel_auth", "confirm_auth"}
        ),
    )
    reserved = cast(
        tuple[AuthLifecycleCapabilityAction, ...],
        tuple(
        action
        for action in reserved_actions
        if action in {"start_auth", "cancel_auth", "confirm_auth"}
        ),
    ) or DEFAULT_RESERVED_AUTH_ACTIONS

    supports_live_session_bootstrap = "live_session_bootstrap" in capability_set
    supports_reauth = "manual_reauth" in capability_set or auth_kind not in {"none", "manual_only"}
    supports_headless_refresh = auth_kind == "oauth_pkce"
    supports_manual_confirm = "confirm_auth" in optional
    supports_session_file = auth_kind == "browser_session"
    bootstrap_methods: tuple[AuthBootstrapMethod, ...] = ()
    if supports_live_session_bootstrap:
        bootstrap_methods = ("browser",)
    if auth_kind == "oauth_pkce":
        bootstrap_methods = tuple(
            dict.fromkeys((*bootstrap_methods, "oauth_pkce", "headless_refresh"))
        )
    if supports_session_file:
        bootstrap_methods = tuple(dict.fromkeys((*bootstrap_methods, "session_file_import")))
    if auth_kind in {"api_key", "cookie_import", "file_import", "manual_only"}:
        bootstrap_methods = tuple(dict.fromkeys((*bootstrap_methods, "manual_token_import")))

    compatibility_actions: tuple[AuthLifecycleCapabilityAction, ...] = ()
    if supports_live_session_bootstrap:
        compatibility_actions = ("start_auth", "cancel_auth")
        if supports_manual_confirm:
            compatibility_actions = (*compatibility_actions, "confirm_auth")

    if auth_kind == "none":
        return ConnectorAuthCapabilities(
            auth_kind=auth_kind,
            supports_reauth=False,
            supports_headless_refresh=False,
            supports_manual_confirm=False,
            supports_oauth_callback=False,
            supports_session_file=False,
            bootstrap_methods=(),
            reserved_actions=(),
        )

    return ConnectorAuthCapabilities(
        auth_kind=auth_kind,
        supports_live_session_bootstrap=supports_live_session_bootstrap,
        supports_reauth=supports_reauth,
        supports_headless_refresh=supports_headless_refresh,
        supports_manual_confirm=supports_manual_confirm,
        supports_oauth_callback=False,
        supports_session_file=supports_session_file,
        bootstrap_methods=bootstrap_methods,
        implemented_actions=optional,  # future external runtime-hosted plugins
        compatibility_actions=compatibility_actions,
        reserved_actions=reserved,
    )
