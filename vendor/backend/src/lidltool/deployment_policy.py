from __future__ import annotations

import ipaddress
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class HttpExposureMode(StrEnum):
    LOCALHOST = "localhost"
    CONTAINER_LOCALHOST = "container_localhost"
    PRIVATE_NETWORK = "private_network"
    REVERSE_PROXY_TLS = "reverse_proxy_tls"


REMOTE_HTTP_EXPOSURE_MODES = {
    HttpExposureMode.PRIVATE_NETWORK,
    HttpExposureMode.REVERSE_PROXY_TLS,
}
_UNSAFE_TRUSTED_PROXY_CIDRS = {"0.0.0.0/0", "::/0"}


@dataclass(frozen=True, slots=True)
class DeploymentPolicy:
    exposure_mode: HttpExposureMode
    bind_host: str
    bind_is_loopback: bool
    requires_remote_safeguards: bool
    bootstrap_token_configured: bool
    bootstrap_token_required_at_startup: bool


def normalize_http_exposure_mode(value: Any) -> str:
    if isinstance(value, HttpExposureMode):
        return value.value
    raw = str(value or "").strip().lower()
    if raw in {mode.value for mode in HttpExposureMode}:
        return raw
    allowed = ", ".join(mode.value for mode in HttpExposureMode)
    raise ValueError(f"http_exposure_mode must be one of: {allowed}")


def _argv_bind_host() -> str | None:
    argv = tuple(sys.argv[1:])
    for index, argument in enumerate(argv):
        if argument == "--host" and index + 1 < len(argv):
            candidate = argv[index + 1].strip()
            if candidate:
                return candidate
        if argument.startswith("--host="):
            candidate = argument.partition("=")[2].strip()
            if candidate:
                return candidate
    return None


def resolve_bind_host(bind_host: str | None = None) -> str:
    resolved = (
        bind_host
        or os.getenv("LIDLTOOL_HTTP_BIND_HOST")
        or _argv_bind_host()
        or "127.0.0.1"
    ).strip()
    return resolved or "127.0.0.1"


def is_loopback_bind_host(host: str) -> bool:
    normalized = host.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    if lowered == "localhost":
        return True
    try:
        return ipaddress.ip_address(lowered).is_loopback
    except ValueError:
        return False


def is_remote_exposure_mode(value: str) -> bool:
    return normalize_http_exposure_mode(value) in {
        mode.value for mode in REMOTE_HTTP_EXPOSURE_MODES
    }


def evaluate_deployment_policy(
    config: Any,
    *,
    bind_host: str | None = None,
    has_human_users: bool | None = None,
) -> DeploymentPolicy:
    exposure_mode = HttpExposureMode(normalize_http_exposure_mode(config.http_exposure_mode))
    resolved_bind_host = resolve_bind_host(bind_host)
    bind_is_loopback = is_loopback_bind_host(resolved_bind_host)
    trusted_proxy_cidrs = tuple(str(item).strip() for item in config.http_trusted_proxy_cidrs if str(item).strip())
    auth_mode = str(config.openclaw_auth_mode or "").strip().lower()
    api_key_configured = bool((config.openclaw_api_key or "").strip())
    bootstrap_token_configured = bool((config.auth_bootstrap_token or "").strip())
    requires_remote_safeguards = exposure_mode in REMOTE_HTTP_EXPOSURE_MODES

    for cidr in trusted_proxy_cidrs:
        if cidr in _UNSAFE_TRUSTED_PROXY_CIDRS:
            raise RuntimeError(
                "FATAL: refusing to trust every proxy hop via "
                "LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS.\n"
                "Remove 0.0.0.0/0 or ::/0 and trust only the exact reverse-proxy source CIDRs."
            )

    if auth_mode not in {"enforce", "warn_only"}:
        raise RuntimeError(
            "FATAL: openclaw_auth_mode must be either 'enforce' or 'warn_only'."
        )

    if exposure_mode == HttpExposureMode.LOCALHOST:
        if not bind_is_loopback:
            raise RuntimeError(
                "FATAL: refusing to bind the HTTP server to a non-loopback address while "
                "LIDLTOOL_HTTP_EXPOSURE_MODE=localhost.\n"
                "Keep the bind host on 127.0.0.1/localhost, or explicitly set "
                "LIDLTOOL_HTTP_EXPOSURE_MODE=private_network or reverse_proxy_tls for intentional "
                "remote access."
            )
        if trusted_proxy_cidrs:
            raise RuntimeError(
                "FATAL: LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS is only supported with "
                "LIDLTOOL_HTTP_EXPOSURE_MODE=reverse_proxy_tls.\n"
                "Remove the trusted proxy CIDRs for localhost-only deployments, or switch the "
                "exposure mode to reverse_proxy_tls."
            )
    elif exposure_mode == HttpExposureMode.CONTAINER_LOCALHOST:
        if trusted_proxy_cidrs:
            raise RuntimeError(
                "FATAL: LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS is only supported with "
                "LIDLTOOL_HTTP_EXPOSURE_MODE=reverse_proxy_tls.\n"
                "Remove the trusted proxy CIDRs for Docker-local deployments, or switch the "
                "exposure mode to reverse_proxy_tls."
            )
    else:
        if not api_key_configured:
            raise RuntimeError(
                "FATAL: LIDLTOOL_OPENCLAW_API_KEY is required for non-local deployments.\n"
                "Set LIDLTOOL_HTTP_EXPOSURE_MODE=localhost to keep the app local-only, or "
                "configure a real service/OpenClaw API key before exposing the service through a "
                "VPN, private network, or reverse proxy."
            )
        if auth_mode != "enforce":
            raise RuntimeError(
                "FATAL: refusing non-local deployment while openclaw_auth_mode is not 'enforce'.\n"
                "Set openclaw_auth_mode='enforce' before using private_network or "
                "reverse_proxy_tls exposure."
            )
        if exposure_mode == HttpExposureMode.PRIVATE_NETWORK:
            if bind_is_loopback:
                raise RuntimeError(
                    "FATAL: LIDLTOOL_HTTP_EXPOSURE_MODE=private_network requires a non-loopback "
                    "bind host.\n"
                    "Use '--host 0.0.0.0' (or another private address), or keep "
                    "LIDLTOOL_HTTP_EXPOSURE_MODE=localhost for loopback-only access."
                )
            if trusted_proxy_cidrs:
                raise RuntimeError(
                    "FATAL: trusted proxy CIDRs are only valid in reverse_proxy_tls mode.\n"
                    "Private-network/VPN mode serves the app directly; if TLS terminates at a "
                    "reverse proxy, switch LIDLTOOL_HTTP_EXPOSURE_MODE to reverse_proxy_tls."
                )
        elif not trusted_proxy_cidrs:
            raise RuntimeError(
                "FATAL: LIDLTOOL_HTTP_EXPOSURE_MODE=reverse_proxy_tls requires "
                "LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS.\n"
                "Session cookies only become Secure on direct HTTPS or on requests forwarded from "
                "an explicitly trusted proxy CIDR with proto=https."
            )

    bootstrap_token_required_at_startup = bool(
        has_human_users is False and requires_remote_safeguards
    )
    if bootstrap_token_required_at_startup and not bootstrap_token_configured:
        raise RuntimeError(
            "FATAL: refusing to start a non-local deployment before first-user bootstrap "
            "completes.\n"
            "Complete setup over localhost first, or configure LIDLTOOL_AUTH_BOOTSTRAP_TOKEN for "
            "an explicitly token-gated remote bootstrap."
        )

    return DeploymentPolicy(
        exposure_mode=exposure_mode,
        bind_host=resolved_bind_host,
        bind_is_loopback=bind_is_loopback,
        requires_remote_safeguards=requires_remote_safeguards,
        bootstrap_token_configured=bootstrap_token_configured,
        bootstrap_token_required_at_startup=bootstrap_token_required_at_startup,
    )
