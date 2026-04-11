from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lidltool.config import AppConfig

PLUGIN_RUNTIME_CONTEXT_ENV = "LIDLTOOL_PLUGIN_RUNTIME_CONTEXT"


@dataclass(frozen=True, slots=True)
class PluginRuntimeContext:
    source_id: str
    tracking_source_id: str
    config_dir: Path
    db_path: Path
    connector_options: dict[str, Any]
    runtime_context: dict[str, Any]


def build_plugin_runtime_environment(
    *,
    source_config: AppConfig,
    source_id: str,
    tracking_source_id: str,
    connector_options: Mapping[str, Any] | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    payload = {
        "source_id": source_id,
        "tracking_source_id": tracking_source_id,
        "config_dir": str(source_config.config_dir),
        "db_path": str(source_config.db_path),
        "connector_options": dict(connector_options or {}),
        "runtime_context": dict(runtime_context or {}),
    }
    return {
        "LIDLTOOL_CONFIG_DIR": str(source_config.config_dir),
        PLUGIN_RUNTIME_CONTEXT_ENV: json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


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
    connector_options = payload.get("connector_options") or {}
    if not isinstance(connector_options, dict):
        raise ValueError("plugin runtime connector_options must be a JSON object")
    runtime_context = payload.get("runtime_context") or {}
    if not isinstance(runtime_context, dict):
        raise ValueError("plugin runtime runtime_context must be a JSON object")
    source_id = str(payload.get("source_id") or "").strip()
    tracking_source_id = str(payload.get("tracking_source_id") or source_id).strip()
    config_dir = Path(
        str(payload.get("config_dir") or resolved_env.get("LIDLTOOL_CONFIG_DIR") or "~/.config/lidltool")
    ).expanduser().resolve()
    db_path = Path(
        str(payload.get("db_path") or "~/.local/share/lidltool/db.sqlite")
    ).expanduser().resolve()
    return PluginRuntimeContext(
        source_id=source_id,
        tracking_source_id=tracking_source_id or source_id,
        config_dir=config_dir,
        db_path=db_path,
        connector_options=dict(connector_options),
        runtime_context=dict(runtime_context),
    )
