from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from lidltool.amazon.bootstrap_playwright import run_amazon_headful_bootstrap
from lidltool.amazon.client_playwright import AmazonClientError
from lidltool.amazon.profiles import get_country_profile, is_amazon_source_id, list_country_profiles
from lidltool.amazon.session import default_amazon_profile_dir, default_amazon_state_file
from lidltool.auth.bootstrap_playwright import run_headful_bootstrap
from lidltool.auth.token_store import TokenStore
from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_capabilities import ConnectorAuthCapabilities
from lidltool.connectors.auth.browser_runtime import (
    AuthBrowserRuntimeService,
    build_auth_browser_runtime_context,
    parse_auth_browser_start_request,
)
from lidltool.connectors.auth.auth_status import (
    AuthActionResult,
    AuthBootstrapSnapshot,
    AuthStatusSnapshot,
    BootstrapLifecycleState,
    NormalizedAuthState,
)
from lidltool.connectors.lifecycle import connector_runtime_options
from lidltool.connectors.registry import ConnectorRegistry, get_connector_registry
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.kaufland.bootstrap_playwright import run_kaufland_headful_bootstrap
from lidltool.kaufland.client_playwright import KauflandClientError
from lidltool.kaufland.session import default_kaufland_state_file
from lidltool.lidl.client import LidlClientError
from lidltool.lidl.market import resolve_lidl_market
from lidltool.rewe.bootstrap_playwright import run_rewe_headful_bootstrap
from lidltool.rewe.client_playwright import ReweClientError
from lidltool.rewe.session import default_rewe_state_file
from lidltool.rossmann.bootstrap_playwright import run_rossmann_headful_bootstrap
from lidltool.rossmann.client_playwright import RossmannClientError
from lidltool.rossmann.session import default_rossmann_state_file

DEFAULT_LIDL_BOOTSTRAP_HAR_OUT = Path("/tmp/lidl_auth_capture.har")


class ReceiptConnectorBuilder(Protocol):
    def __call__(
        self,
        *,
        source_id: str | None = None,
        connector_options: Mapping[str, Any] | None = None,
        tracking_source_id: str | None = None,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


@dataclass(slots=True)
class ConnectorBootstrapSession:
    source_id: str
    command: list[str]
    process: subprocess.Popen[str]
    started_at: datetime
    output: deque[str]
    lock: threading.Lock
    finished_at: datetime | None = None
    return_code: int | None = None
    canceled: bool = False


@dataclass(slots=True)
class ConnectorAuthSessionRegistry:
    sessions: dict[str, ConnectorBootstrapSession] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _StorageInspection:
    present: bool
    reauth_required: bool
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _BuiltinAuthBridge:
    source_id: str
    auth_kind: str
    handled_exceptions: tuple[type[Exception], ...]
    state_file_resolver: Callable[[AppConfig], Path] | None = None
    bootstrap_runner: Callable[..., bool] | None = None
    default_domain: str | None = None

    def inspect_storage(
        self,
        config: AppConfig,
        options: Mapping[str, Any] | None = None,
    ) -> _StorageInspection:
        normalized = dict(options or {})
        if self.auth_kind == "oauth_pkce":
            token_store = TokenStore.from_config(config)
            refresh_token = token_store.get_refresh_token()
            return _StorageInspection(
                present=bool(refresh_token),
                reauth_required=token_store.is_reauth_required(),
                metadata={
                    "token_file": str(config.token_file),
                    "refresh_token_present": bool(refresh_token),
                    "reauth_flag_set": token_store.is_reauth_required(),
                    "access_token_cached": token_store.get_access_cache() is not None,
                },
            )
        if self.state_file_resolver is None:
            return _StorageInspection(present=False, reauth_required=False, metadata={})
        target = _resolve_state_file(
            normalized.get("state_file"),
            self.state_file_resolver(config),
        )
        return _StorageInspection(
            present=target.exists(),
            reauth_required=False,
            metadata={"state_file": str(target), "session_file_present": target.exists()},
        )

    def run_bootstrap(
        self,
        config: AppConfig,
        manifest: ConnectorManifest,
        options: Mapping[str, Any] | None = None,
    ) -> AuthActionResult:
        normalized = dict(options or {})
        if self.auth_kind == "oauth_pkce":
            token_store = TokenStore.from_config(config)
            token_value = normalized.get("refresh_token")
            if not token_value and _bool_option(normalized, "headful", True):
                har_out = _resolve_state_file(
                    normalized.get("har_out"),
                    DEFAULT_LIDL_BOOTSTRAP_HAR_OUT,
                )
                market = resolve_lidl_market(manifest.source_id)
                token_value = run_headful_bootstrap(
                    har_out,
                    country=market.country_code,
                    language=market.language_code,
                )
            if not isinstance(token_value, str) or not token_value.strip():
                raise RuntimeError("auth token missing; run lidltool auth bootstrap")
            token_store.set_refresh_token(token_value.strip())
            return AuthActionResult(
                manifest=manifest,
                source_id=manifest.source_id,
                state="connected",
                status="confirmed",
                ok=True,
                metadata={"token_file": str(config.token_file)},
                handled_exceptions=self.handled_exceptions,
            )

        if self.state_file_resolver is None or self.bootstrap_runner is None:
            raise RuntimeError(
                f"connector bootstrap bridge is not registered for source: {manifest.source_id}"
            )
        target = _resolve_state_file(
            normalized.get("state_file"),
            self.state_file_resolver(config),
        )
        profile_dir = None
        if is_amazon_source_id(manifest.source_id):
            profile_dir = _resolve_optional_path(
                normalized.get("profile_dir"),
            ) or default_amazon_profile_dir(config, source_id=manifest.source_id)
        domain = _string_option(normalized, "domain", self.default_domain or "")
        debug_html_dir = _resolve_optional_path(normalized.get("dump_html"))
        bootstrap_kwargs: dict[str, Any] = {
            "source_id": manifest.source_id,
            "domain": domain or None,
            "debug_html_dir": debug_html_dir,
        }
        if profile_dir is not None:
            bootstrap_kwargs["profile_dir"] = profile_dir
        ok = bool(self.bootstrap_runner(target, **bootstrap_kwargs))
        return AuthActionResult(
            manifest=manifest,
            source_id=manifest.source_id,
            state="connected" if ok else "auth_failed",
            status="confirmed" if ok else "no_op",
            ok=ok,
            detail=None if ok else f"{manifest.display_name} session capture failed",
            metadata={
                "state_file": str(target),
                "profile_dir": str(profile_dir) if profile_dir is not None else None,
                "domain": domain or get_country_profile(source_id=manifest.source_id).domain,
                "dump_html": str(debug_html_dir) if debug_html_dir is not None else None,
            },
            handled_exceptions=self.handled_exceptions,
        )


_BUILTIN_AUTH_BRIDGES: dict[str, _BuiltinAuthBridge] = {
    "lidl_plus_de": _BuiltinAuthBridge(
        source_id="lidl_plus_de",
        auth_kind="oauth_pkce",
        handled_exceptions=(LidlClientError,),
    ),
    "lidl_plus_gb": _BuiltinAuthBridge(
        source_id="lidl_plus_gb",
        auth_kind="oauth_pkce",
        handled_exceptions=(LidlClientError,),
    ),
    "lidl_plus_fr": _BuiltinAuthBridge(
        source_id="lidl_plus_fr",
        auth_kind="oauth_pkce",
        handled_exceptions=(LidlClientError,),
    ),
    "rewe_de": _BuiltinAuthBridge(
        source_id="rewe_de",
        auth_kind="browser_session",
        handled_exceptions=(ReweClientError,),
        state_file_resolver=default_rewe_state_file,
        bootstrap_runner=run_rewe_headful_bootstrap,
        default_domain="shop.rewe.de",
    ),
    "kaufland_de": _BuiltinAuthBridge(
        source_id="kaufland_de",
        auth_kind="browser_session",
        handled_exceptions=(KauflandClientError,),
        state_file_resolver=default_kaufland_state_file,
        bootstrap_runner=run_kaufland_headful_bootstrap,
        default_domain="www.kaufland.de",
    ),
    "rossmann_de": _BuiltinAuthBridge(
        source_id="rossmann_de",
        auth_kind="browser_session",
        handled_exceptions=(RossmannClientError,),
        state_file_resolver=default_rossmann_state_file,
        bootstrap_runner=run_rossmann_headful_bootstrap,
        default_domain="www.rossmann.de",
    ),
}

for _amazon_profile in list_country_profiles():
    _BUILTIN_AUTH_BRIDGES[_amazon_profile.source_id] = _BuiltinAuthBridge(
        source_id=_amazon_profile.source_id,
        auth_kind="browser_session",
        handled_exceptions=(AmazonClientError,),
        state_file_resolver=lambda config, source_id=_amazon_profile.source_id: default_amazon_state_file(
            config,
            source_id=source_id,
        ),
        bootstrap_runner=run_amazon_headful_bootstrap,
        default_domain=_amazon_profile.domain,
    )


def _resolve_optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str):
        return Path(value).expanduser().resolve()
    raise TypeError(f"expected path-like value, got {type(value).__name__}")


def _resolve_state_file(value: object, default: Path) -> Path:
    resolved = _resolve_optional_path(value)
    if resolved is not None:
        return resolved
    return default.expanduser().resolve()


def _string_option(options: Mapping[str, Any], key: str, default: str) -> str:
    value = options.get(key, default)
    return str(value)


def _bool_option(options: Mapping[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def connector_bootstrap_is_running(session: ConnectorBootstrapSession) -> bool:
    if session.return_code is not None:
        return False
    polled = session.process.poll()
    if polled is None:
        return True
    with session.lock:
        session.return_code = polled
        if session.finished_at is None:
            session.finished_at = datetime.now(tz=UTC)
    return False


def serialize_connector_bootstrap(session: ConnectorBootstrapSession) -> AuthBootstrapSnapshot:
    running = connector_bootstrap_is_running(session)
    with session.lock:
        started_at = session.started_at
        finished_at = session.finished_at
        return_code = session.return_code
        output_tail = tuple(list(session.output)[-30:])
        canceled = session.canceled
    state: BootstrapLifecycleState = (
        "running" if running else "canceled" if canceled else "succeeded" if return_code == 0 else "failed"
    )
    return AuthBootstrapSnapshot(
        source_id=session.source_id,
        state=state,
        command=tuple(session.command),
        pid=session.process.pid,
        started_at=started_at,
        finished_at=finished_at,
        return_code=return_code,
        output_tail=output_tail,
        can_cancel=running,
    )


def stream_connector_bootstrap_output(
    registry: ConnectorAuthSessionRegistry,
    *,
    source_id: str,
) -> None:
    session = registry.sessions.get(source_id)
    if session is None:
        return
    try:
        stream = session.process.stdout
        if stream is not None:
            for line in stream:
                stripped = line.rstrip()
                if not stripped:
                    continue
                with session.lock:
                    session.output.append(stripped)
        return_code: int | None = session.process.wait()
    except Exception as exc:  # noqa: BLE001
        with session.lock:
            session.output.append(f"bootstrap monitor failed: {exc}")
        return_code = session.process.poll()
    with session.lock:
        session.return_code = return_code
        session.finished_at = datetime.now(tz=UTC)


def terminate_connector_bootstrap(session: ConnectorBootstrapSession) -> None:
    if not connector_bootstrap_is_running(session):
        return
    session.process.terminate()
    try:
        session.process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        session.process.kill()
        session.process.wait(timeout=5)
    with session.lock:
        session.return_code = session.process.returncode
        session.finished_at = datetime.now(tz=UTC)
        session.canceled = True


def any_connector_bootstrap_running(
    sessions: Mapping[str, ConnectorBootstrapSession],
) -> bool:
    return any(connector_bootstrap_is_running(session) for session in sessions.values())


def start_connector_command_session(
    registry: ConnectorAuthSessionRegistry,
    *,
    source_id: str,
    command: list[str],
    cwd: Path,
    env: Mapping[str, str],
    process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    thread_name: str,
) -> ConnectorBootstrapSession:
    process = process_factory(
        command,
        cwd=str(cwd),
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    session = ConnectorBootstrapSession(
        source_id=source_id,
        command=command,
        process=process,
        started_at=datetime.now(tz=UTC),
        output=deque(maxlen=400),
        lock=threading.Lock(),
    )
    registry.sessions[source_id] = session
    thread = threading.Thread(
        target=stream_connector_bootstrap_output,
        kwargs={"registry": registry, "source_id": source_id},
        daemon=True,
        name=thread_name,
    )
    thread.start()
    return session


class ConnectorAuthOrchestrationService:
    def __init__(
        self,
        *,
        config: AppConfig,
        registry: ConnectorRegistry | None = None,
        session_registry: ConnectorAuthSessionRegistry | None = None,
        connector_builder: ReceiptConnectorBuilder | None = None,
        repo_root: Path | None = None,
        process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        browser_runtime: AuthBrowserRuntimeService | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or get_connector_registry(config)
        self._session_registry = session_registry or ConnectorAuthSessionRegistry()
        self._connector_builder = connector_builder
        self._repo_root = (repo_root or Path.cwd()).expanduser().resolve()
        self._process_factory = process_factory
        self._browser_runtime = browser_runtime or AuthBrowserRuntimeService()

    @property
    def session_registry(self) -> ConnectorAuthSessionRegistry:
        return self._session_registry

    def capabilities_for_source(self, source_id: str) -> ConnectorAuthCapabilities:
        manifest = self._registry.require_manifest(source_id)
        if manifest.auth is None:
            raise RuntimeError(f"connector manifest auth capabilities missing for source: {source_id}")
        return manifest.auth

    def get_auth_status(
        self,
        *,
        source_id: str,
        connector_options: Mapping[str, Any] | None = None,
        validate_session: bool = True,
    ) -> AuthStatusSnapshot:
        resolved_options = self._resolve_connector_options(
            source_id=source_id,
            connector_options=connector_options,
        )
        manifest = self._registry.require_manifest(source_id)
        capabilities = self.capabilities_for_source(source_id)
        bridge = _BUILTIN_AUTH_BRIDGES.get(source_id)
        bootstrap_session = self._session_registry.sessions.get(source_id)
        bootstrap = (
            serialize_connector_bootstrap(bootstrap_session)
            if bootstrap_session is not None
            else None
        )
        if bootstrap is not None and bootstrap.state == "running":
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="bootstrap_running",
                detail="auth bootstrap is currently running",
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata={"bootstrap_command": list(bootstrap.command or ())},
            )
        if bootstrap is not None and bootstrap.state == "canceled":
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="bootstrap_canceled",
                detail="auth bootstrap was canceled",
                bootstrap=bootstrap,
                connector_options=resolved_options,
            )

        if bridge is None and self._connector_builder is not None:
            plugin_snapshot = self._plugin_runtime_auth_status(
                source_id=source_id,
                manifest=manifest,
                capabilities=capabilities,
                bootstrap=bootstrap,
                connector_options=resolved_options,
                validate_session=validate_session,
            )
            if plugin_snapshot is not None:
                return plugin_snapshot

        inspection = (
            bridge.inspect_storage(self._config, resolved_options)
            if bridge is not None
            else _StorageInspection(present=False, reauth_required=False, metadata={})
        )
        if capabilities.auth_kind == "none":
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="connected",
                detail="connector does not require authentication",
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata=inspection.metadata,
            )
        if not inspection.present:
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="not_connected",
                detail="connector credentials or session state are not configured",
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata=inspection.metadata,
            )
        if inspection.reauth_required:
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="reauth_required",
                detail="connector marked its stored auth state as requiring re-authentication",
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata=inspection.metadata,
            )
        if not validate_session or self._connector_builder is None:
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="connected",
                detail="connector auth storage is present",
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata=inspection.metadata,
            )

        try:
            resolved = self._connector_builder(
                source_id=source_id,
                connector_options=resolved_options,
            )
            resolved.connector.authenticate()
        except Exception as exc:  # noqa: BLE001
            normalized_state = "reauth_required" if _looks_like_reauth_error(exc) else "auth_failed"
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state=normalized_state,
                detail=str(exc),
                bootstrap=bootstrap,
                connector_options=resolved_options,
                metadata=inspection.metadata,
                diagnostics={
                    "failure_class": "session_validation_failed",
                    "exception_type": type(exc).__name__,
                    "validation_error": str(exc),
                    "plugin_id": manifest.plugin_id,
                    "runtime_kind": manifest.runtime_kind,
                    "bootstrap_state": bootstrap.state if bootstrap is not None else None,
                    "bootstrap_return_code": (
                        bootstrap.return_code if bootstrap is not None else None
                    ),
                },
            )

        return self._status_snapshot(
            manifest=manifest,
            capabilities=capabilities,
            state="connected",
            detail="connector auth/session validated successfully",
            bootstrap=bootstrap,
            connector_options=resolved_options,
            metadata=inspection.metadata,
        )

    def run_bootstrap(
        self,
        *,
        source_id: str,
        options: Mapping[str, Any] | None = None,
    ) -> AuthActionResult:
        resolved_options = self._resolve_connector_options(
            source_id=source_id,
            connector_options=options,
        )
        manifest = self._registry.require_manifest(source_id)
        bridge = _BUILTIN_AUTH_BRIDGES.get(source_id)
        if bridge is None:
            if self._connector_builder is None:
                raise RuntimeError(f"connector bootstrap bridge is not registered for source: {source_id}")
            return self._run_plugin_bootstrap(
                source_id=source_id,
                manifest=manifest,
                options=resolved_options,
            )
        return bridge.run_bootstrap(self._config, manifest, resolved_options)

    def start_bootstrap(
        self,
        *,
        source_id: str,
        env: Mapping[str, str] | None = None,
        connector_options: Mapping[str, Any] | None = None,
        extra_args: tuple[str, ...] = (),
    ) -> AuthActionResult:
        manifest = self._registry.require_manifest(source_id)
        capabilities = self.capabilities_for_source(source_id)
        resolved_options = self._resolve_connector_options(
            source_id=source_id,
            connector_options=connector_options,
        )
        option_args = self._bootstrap_option_args(
            manifest=manifest,
            options=resolved_options,
        )
        command = self._build_bootstrap_command(
            source_id,
            extra_args=(*option_args, *extra_args),
        )
        if command is None:
            raise RuntimeError(f"connector bootstrap not supported for source: {source_id}")
        existing = self._session_registry.sessions.get(source_id)
        if existing is not None and connector_bootstrap_is_running(existing):
            snapshot = serialize_connector_bootstrap(existing)
            return AuthActionResult(
                manifest=manifest,
                source_id=source_id,
                state="connecting",
                status="reused",
                ok=True,
                detail="reusing running auth bootstrap session",
                bootstrap=AuthBootstrapSnapshot(
                    source_id=snapshot.source_id,
                    state=snapshot.state,
                    command=snapshot.command,
                    pid=snapshot.pid,
                    started_at=snapshot.started_at,
                    finished_at=snapshot.finished_at,
                    return_code=snapshot.return_code,
                    output_tail=snapshot.output_tail,
                    can_cancel=snapshot.can_cancel,
                    was_reused=True,
                ),
            )
        session = start_connector_command_session(
            self._session_registry,
            source_id=source_id,
            command=command,
            cwd=self._repo_root,
            env=self._build_process_env(extra_env=env),
            process_factory=self._process_factory,
            thread_name=f"connector-auth-bootstrap-{source_id}",
        )
        return AuthActionResult(
            manifest=manifest,
            source_id=source_id,
            state="connecting",
            status="started",
            ok=True,
            detail="auth bootstrap started",
            bootstrap=serialize_connector_bootstrap(session),
            metadata={
                "supports_live_session_bootstrap": capabilities.supports_live_session_bootstrap,
            },
        )

    def get_bootstrap_status(self, *, source_id: str) -> AuthBootstrapSnapshot:
        session = self._session_registry.sessions.get(source_id)
        if session is None:
            return AuthBootstrapSnapshot(source_id=source_id, state="idle")
        return serialize_connector_bootstrap(session)

    def cancel_bootstrap(self, *, source_id: str) -> AuthActionResult:
        manifest = self._registry.require_manifest(source_id)
        session = self._session_registry.sessions.get(source_id)
        if session is None:
            self._cancel_plugin_auth_flow(source_id=source_id)
            return AuthActionResult(
                manifest=manifest,
                source_id=source_id,
                state="not_connected",
                status="no_op",
                ok=True,
                detail="no active auth bootstrap session",
            )
        terminate_connector_bootstrap(session)
        self._cancel_plugin_auth_flow(source_id=source_id)
        return AuthActionResult(
            manifest=manifest,
            source_id=source_id,
            state="bootstrap_canceled",
            status="canceled",
            ok=True,
            detail="auth bootstrap canceled",
            bootstrap=serialize_connector_bootstrap(session),
        )

    def confirm_bootstrap(self, *, source_id: str) -> AuthActionResult:
        manifest = self._registry.require_manifest(source_id)
        capabilities = self.capabilities_for_source(source_id)
        if not capabilities.supports_manual_confirm:
            return AuthActionResult(
                manifest=manifest,
                source_id=source_id,
                state="connected" if capabilities.auth_kind == "none" else "not_connected",
                status="not_supported",
                ok=True,
                detail="manual auth confirmation is not implemented for this connector",
            )
        return AuthActionResult(
            manifest=manifest,
            source_id=source_id,
            state="connected",
            status="confirmed",
            ok=True,
            detail="manual auth confirmation completed",
        )

    def any_bootstrap_running(self) -> bool:
        return any_connector_bootstrap_running(self._session_registry.sessions)

    def _build_process_env(self, *, extra_env: Mapping[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env["LIDLTOOL_DB"] = str(self._config.db_path)
        env["LIDLTOOL_CONFIG_DIR"] = str(self._config.config_dir)
        if self._config.db_url:
            env["LIDLTOOL_DB_URL"] = self._config.db_url
        if self._config.credential_encryption_key:
            env["LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"] = self._config.credential_encryption_key
        env["PYTHONUNBUFFERED"] = "1"
        if extra_env:
            env.update({str(key): str(value) for key, value in extra_env.items()})
        return env

    def _resolve_connector_options(
        self,
        *,
        source_id: str,
        connector_options: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        options = connector_runtime_options(
            source_id=source_id,
            config=self._config,
            registry=self._registry,
            allow_reconcile_writes=False,
        )
        options.update(dict(connector_options or {}))
        return options

    def _build_bootstrap_command(
        self,
        source_id: str,
        *,
        extra_args: tuple[str, ...] = (),
    ) -> list[str] | None:
        manifest = self._registry.get_manifest(source_id)
        if manifest is None:
            return None
        if manifest.builtin_cli is not None and manifest.builtin_cli.bootstrap_args is not None:
            return [sys.executable, *manifest.builtin_cli.bootstrap_args, *extra_args]
        capabilities = manifest.auth
        if (
            manifest.runtime_kind in {"subprocess_python", "subprocess_binary"}
            and capabilities is not None
            and capabilities.supports_live_session_bootstrap
        ):
            return [
                sys.executable,
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                source_id,
                *extra_args,
            ]
        return None

    def _bootstrap_option_args(
        self,
        *,
        manifest: ConnectorManifest,
        options: Mapping[str, Any],
    ) -> tuple[str, ...]:
        allowed_keys = self._bootstrap_option_allowlist(manifest)
        args: list[str] = []
        for key, value in options.items():
            if allowed_keys is not None and key not in allowed_keys:
                continue
            if value is None:
                continue
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            else:
                rendered = str(value)
            args.extend(("--option", f"{key}={rendered}"))
        return tuple(args)

    def _bootstrap_option_allowlist(self, manifest: ConnectorManifest) -> set[str] | None:
        auth_kind = manifest.auth.auth_kind if manifest.auth is not None else None
        if auth_kind == "oauth_pkce":
            return {"refresh_token", "headful", "har_out"}
        if auth_kind == "browser_session":
            return {"state_file", "profile_dir", "domain", "dump_html"}
        return None

    def _plugin_runtime_auth_status(
        self,
        *,
        source_id: str,
        manifest: ConnectorManifest,
        capabilities: ConnectorAuthCapabilities,
        bootstrap: AuthBootstrapSnapshot | None,
        connector_options: Mapping[str, Any] | None,
        validate_session: bool,
    ) -> AuthStatusSnapshot | None:
        if manifest.plugin_family != "receipt":
            return None
        try:
            resolved = self._connector_builder(
                source_id=source_id,
                connector_options=connector_options,
            )
            payload = resolved.connector.get_auth_status()
        except Exception as exc:  # noqa: BLE001
            return self._status_snapshot(
                manifest=manifest,
                capabilities=capabilities,
                state="auth_failed",
                detail=str(exc),
                bootstrap=bootstrap,
                connector_options=connector_options,
                diagnostics={
                    "failure_class": "plugin_auth_status_failed",
                    "exception_type": type(exc).__name__,
                    "plugin_id": manifest.plugin_id,
                    "runtime_kind": manifest.runtime_kind,
                },
            )

        state = self._normalize_plugin_auth_state(
            str(payload.get("status") or ""),
            bool(payload.get("is_authenticated")),
        )
        detail = payload.get("detail")
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        diagnostics = {
            "plugin_id": manifest.plugin_id,
            "runtime_kind": manifest.runtime_kind,
            "plugin_auth_status": payload.get("status"),
        }
        if validate_session and bool(payload.get("is_authenticated")):
            try:
                resolved.connector.healthcheck()
            except Exception as exc:  # noqa: BLE001
                normalized_state = "reauth_required" if _looks_like_reauth_error(exc) else "auth_failed"
                return self._status_snapshot(
                    manifest=manifest,
                    capabilities=capabilities,
                    state=normalized_state,
                    detail=str(exc),
                    bootstrap=bootstrap,
                    connector_options=connector_options,
                    metadata=metadata,
                    diagnostics={
                        **diagnostics,
                        "failure_class": "session_validation_failed",
                        "exception_type": type(exc).__name__,
                        "validation_error": str(exc),
                    },
                )

        return self._status_snapshot(
            manifest=manifest,
            capabilities=capabilities,
            state=state,
            detail=str(detail) if detail is not None else None,
            bootstrap=bootstrap,
            connector_options=connector_options,
            metadata=dict(metadata),
            diagnostics=diagnostics,
        )

    def _run_plugin_bootstrap(
        self,
        *,
        source_id: str,
        manifest: ConnectorManifest,
        options: Mapping[str, Any] | None,
    ) -> AuthActionResult:
        capabilities = self.capabilities_for_source(source_id)
        if self._connector_builder is None:
            raise RuntimeError(f"connector bootstrap bridge is not registered for source: {source_id}")
        resolved = self._connector_builder(source_id=source_id, connector_options=options)
        payload = resolved.connector.start_auth()
        flow_status = str(payload.get("status") or "no_op")
        confirm_payload: dict[str, Any] | None = None
        browser_request = parse_auth_browser_start_request(payload.get("metadata"))
        if browser_request is not None:
            try:
                browser_result = self._browser_runtime.run(
                    browser_request,
                    environment=self._build_process_env(),
                )
            except Exception:
                self._cancel_plugin_auth_flow(source_id=source_id, connector_options=options)
                raise
            confirm_payload = self._invoke_plugin_auth_action(
                source_id=source_id,
                connector_options=options,
                action="confirm_auth",
                runtime_context=build_auth_browser_runtime_context(browser_result),
            )
            flow_status = str(confirm_payload.get("status") or flow_status)
        snapshot = self._plugin_runtime_auth_status(
            source_id=source_id,
            manifest=manifest,
            capabilities=capabilities,
            bootstrap=None,
            connector_options=options,
            validate_session=False,
        )
        return AuthActionResult(
            manifest=manifest,
            source_id=source_id,
            state=self._normalize_plugin_bootstrap_state(flow_status, snapshot.state if snapshot is not None else "not_connected"),
            status=self._normalize_plugin_bootstrap_status(flow_status),
            ok=flow_status not in {"not_supported"},
            detail=(
                str(
                    (confirm_payload.get("detail") if confirm_payload is not None else payload.get("detail"))
                    or (snapshot.detail if snapshot is not None else "")
                )
                or None
            ),
            metadata={
                **(dict(snapshot.metadata) if snapshot is not None else {}),
                **(
                    dict(confirm_payload.get("metadata", {}))
                    if confirm_payload is not None and isinstance(confirm_payload.get("metadata"), Mapping)
                    else {}
                ),
            },
            diagnostics=dict(snapshot.diagnostics) if snapshot is not None else {},
        )

    def _invoke_plugin_auth_action(
        self,
        *,
        source_id: str,
        connector_options: Mapping[str, Any] | None,
        action: str,
        runtime_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._connector_builder is None:
            raise RuntimeError(f"connector bootstrap bridge is not registered for source: {source_id}")
        resolved = self._connector_builder(
            source_id=source_id,
            connector_options=connector_options,
            runtime_context=runtime_context,
        )
        method = getattr(resolved.connector, action)
        payload = method()
        if not isinstance(payload, dict):
            raise RuntimeError(f"connector {action} returned no payload")
        return payload

    def _cancel_plugin_auth_flow(
        self,
        *,
        source_id: str,
        connector_options: Mapping[str, Any] | None = None,
    ) -> None:
        if self._connector_builder is None:
            return
        manifest = self._registry.get_manifest(source_id)
        if manifest is None or manifest.runtime_kind not in {"subprocess_python", "subprocess_binary"}:
            return
        try:
            self._invoke_plugin_auth_action(
                source_id=source_id,
                connector_options=connector_options,
                action="cancel_auth",
            )
        except Exception:
            return

    def _normalize_plugin_auth_state(
        self,
        plugin_state: str,
        is_authenticated: bool,
    ) -> NormalizedAuthState:
        normalized = plugin_state.strip().lower()
        if normalized == "authenticated" or is_authenticated:
            return "connected"
        if normalized == "pending":
            return "connecting"
        if normalized == "expired":
            return "reauth_required"
        if normalized in {"not_supported", "unknown"}:
            return "not_connected"
        return "not_connected" if normalized == "requires_auth" else "auth_failed"

    def _normalize_plugin_bootstrap_state(
        self,
        flow_status: str,
        fallback: NormalizedAuthState,
    ) -> NormalizedAuthState:
        normalized = flow_status.strip().lower()
        if normalized in {"started", "pending"}:
            return "connecting"
        if normalized == "canceled":
            return "bootstrap_canceled"
        if normalized == "confirmed":
            return "connected"
        if normalized == "not_supported":
            return "not_connected"
        return fallback

    def _normalize_plugin_bootstrap_status(self, flow_status: str) -> str:
        normalized = flow_status.strip().lower()
        if normalized in {"started", "pending"}:
            return "started"
        if normalized in {"canceled", "confirmed", "not_supported", "no_op"}:
            return normalized
        return "no_op"

    def _status_snapshot(
        self,
        *,
        manifest: ConnectorManifest,
        capabilities: ConnectorAuthCapabilities,
        state: str,
        detail: str | None,
        bootstrap: AuthBootstrapSnapshot | None,
        connector_options: Mapping[str, Any] | None,
        metadata: dict[str, Any] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> AuthStatusSnapshot:
        del connector_options
        available_actions = capabilities.available_actions()
        if state == "bootstrap_running":
            available_actions = tuple(action for action in available_actions if action == "cancel_auth")
        return AuthStatusSnapshot(
            manifest=manifest,
            capabilities=capabilities,
            state=state,  # type: ignore[arg-type]
            detail=detail,
            bootstrap=bootstrap,
            available_actions=available_actions,
            implemented_actions=capabilities.implemented_actions,
            compatibility_actions=capabilities.compatibility_actions,
            reserved_actions=capabilities.reserved_actions,
            metadata=metadata or {},
            diagnostics=diagnostics or {},
        )


def _looks_like_reauth_error(exc: Exception) -> bool:
    lowered = str(exc).strip().lower()
    return any(
        token in lowered
        for token in (
            "auth",
            "login",
            "session",
            "token",
            "expired",
            "reauth",
            "storage state",
            "missing",
            "requires authentication",
        )
    )
