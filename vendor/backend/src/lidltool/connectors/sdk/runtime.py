from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

PLUGIN_RUNTIME_CONTEXT_ENV = "LIDLTOOL_PLUGIN_RUNTIME_CONTEXT"
PLUGIN_RUNTIME_CONTEXT_VERSION = "1"

HostKind = Literal["self_hosted", "electron"]
AuthBrowserMode = Literal["local_display", "remote_vnc", "headless_capture_only"]

AUTH_BROWSER_METADATA_KEY = "auth_browser"


class PluginRuntimeStorage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root_dir: Path
    data_dir: Path
    cache_dir: Path
    temp_dir: Path
    log_dir: Path


class PluginRuntimeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_kind: HostKind = "self_hosted"
    plugin_id: str | None = None
    plugin_version: str | None = None
    plugin_family: Literal["receipt", "offer"] | None = None
    runtime_kind: str | None = None
    working_directory: Path | None = None


class PluginRuntimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = PLUGIN_RUNTIME_CONTEXT_VERSION
    source_id: str
    tracking_source_id: str
    config_dir: Path
    db_path: Path
    connector_options: dict[str, Any] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    storage: PluginRuntimeStorage
    runtime: PluginRuntimeInfo = Field(default_factory=PluginRuntimeInfo)


class AuthBrowserPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_url: str
    callback_url_prefixes: tuple[str, ...]
    require_navigation_away_before_completion: bool = False
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    wait_until: Literal["domcontentloaded", "load", "networkidle"] = "domcontentloaded"
    interactive: bool = True
    capture_storage_state: bool = False


class AuthBrowserStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    plan: AuthBrowserPlan


class AuthBrowserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flow_id: str
    session_id: str
    mode: AuthBrowserMode
    start_url: str
    final_url: str
    callback_url: str
    started_at: str
    completed_at: str
    storage_state: dict[str, Any] | None = None


_CONTEXT_ADAPTER: TypeAdapter[PluginRuntimeContext] = TypeAdapter(PluginRuntimeContext)
_REQUEST_ADAPTER: TypeAdapter[AuthBrowserStartRequest] = TypeAdapter(AuthBrowserStartRequest)
_RESULT_ADAPTER: TypeAdapter[AuthBrowserResult] = TypeAdapter(AuthBrowserResult)


def load_plugin_runtime_context(
    env: Mapping[str, str] | None = None,
) -> PluginRuntimeContext:
    resolved_env = dict(os.environ if env is None else env)
    raw_payload = resolved_env.get(PLUGIN_RUNTIME_CONTEXT_ENV)
    if raw_payload:
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError(f"{PLUGIN_RUNTIME_CONTEXT_ENV} must be a JSON object")
    else:
        payload = {}

    source_id = str(payload.get("source_id") or "").strip()
    tracking_source_id = str(payload.get("tracking_source_id") or source_id).strip() or source_id
    config_dir = Path(
        str(payload.get("config_dir") or resolved_env.get("LIDLTOOL_CONFIG_DIR") or "~/.config/lidltool")
    ).expanduser().resolve()
    db_path = Path(
        str(payload.get("db_path") or "~/.local/share/lidltool/db.sqlite")
    ).expanduser().resolve()
    connector_options = payload.get("connector_options") or {}
    if not isinstance(connector_options, dict):
        raise ValueError("plugin runtime connector_options must be a JSON object")
    runtime_context = payload.get("runtime_context") or {}
    if not isinstance(runtime_context, dict):
        raise ValueError("plugin runtime runtime_context must be a JSON object")

    storage_payload = payload.get("storage")
    if not isinstance(storage_payload, dict):
        storage_root = (config_dir / "connector_plugin_runtime" / tracking_source_id).resolve()
        storage_payload = {
            "root_dir": storage_root,
            "data_dir": (storage_root / "data").resolve(),
            "cache_dir": (storage_root / "cache").resolve(),
            "temp_dir": (storage_root / "tmp").resolve(),
            "log_dir": (storage_root / "logs").resolve(),
        }

    runtime_payload = payload.get("runtime")
    if not isinstance(runtime_payload, dict):
        runtime_payload = {
            "host_kind": str(
                payload.get("host_kind")
                or resolved_env.get("LIDLTOOL_CONNECTOR_HOST_KIND")
                or "self_hosted"
            ).strip()
            or "self_hosted",
        }

    normalized_payload = {
        "schema_version": str(payload.get("schema_version") or PLUGIN_RUNTIME_CONTEXT_VERSION),
        "source_id": source_id,
        "tracking_source_id": tracking_source_id,
        "config_dir": config_dir,
        "db_path": db_path,
        "connector_options": dict(connector_options),
        "runtime_context": dict(runtime_context),
        "storage": storage_payload,
        "runtime": runtime_payload,
    }
    return _CONTEXT_ADAPTER.validate_python(normalized_payload)


def build_auth_browser_metadata(
    *,
    flow_id: str,
    plan: AuthBrowserPlan,
) -> dict[str, Any]:
    payload = AuthBrowserStartRequest(flow_id=flow_id, plan=plan)
    return {AUTH_BROWSER_METADATA_KEY: payload.model_dump(mode="python")}


def parse_auth_browser_start_request(metadata: Mapping[str, Any] | None) -> AuthBrowserStartRequest | None:
    if not isinstance(metadata, Mapping):
        return None
    payload = metadata.get(AUTH_BROWSER_METADATA_KEY)
    if payload is None:
        return None
    return _REQUEST_ADAPTER.validate_python(payload)


def build_auth_browser_runtime_context(result: AuthBrowserResult) -> dict[str, Any]:
    return {AUTH_BROWSER_METADATA_KEY: result.model_dump(mode="python")}


def parse_auth_browser_runtime_context(
    runtime_context: Mapping[str, Any] | None,
) -> AuthBrowserResult | None:
    if not isinstance(runtime_context, Mapping):
        return None
    payload = runtime_context.get(AUTH_BROWSER_METADATA_KEY)
    if payload is None:
        return None
    return _RESULT_ADAPTER.validate_python(payload)
