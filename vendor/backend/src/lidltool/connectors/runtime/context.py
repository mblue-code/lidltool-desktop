from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from lidltool.config import AppConfig
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.runtime import (
    PLUGIN_RUNTIME_CONTEXT_ENV,
    PLUGIN_RUNTIME_CONTEXT_VERSION,
    PluginRuntimeContext,
)


def _plugin_host_kind() -> str:
    return (
        "electron"
        if os.getenv("LIDLTOOL_CONNECTOR_HOST_KIND", "").strip().lower() == "electron"
        else "self_hosted"
    )


def _plugin_storage_payload(*, source_config: AppConfig, tracking_source_id: str) -> dict[str, str]:
    root_dir = (source_config.config_dir / "connector_plugin_runtime" / tracking_source_id).resolve()
    return {
        "root_dir": str(root_dir),
        "data_dir": str((root_dir / "data").resolve()),
        "cache_dir": str((root_dir / "cache").resolve()),
        "temp_dir": str((root_dir / "tmp").resolve()),
        "log_dir": str((root_dir / "logs").resolve()),
    }


def build_plugin_runtime_environment(
    *,
    source_config: AppConfig,
    source_id: str,
    tracking_source_id: str,
    manifest: ConnectorManifest | None = None,
    working_directory: Path | None = None,
    connector_options: Mapping[str, Any] | None = None,
    runtime_context: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    payload = {
        "schema_version": PLUGIN_RUNTIME_CONTEXT_VERSION,
        "source_id": source_id,
        "tracking_source_id": tracking_source_id,
        "config_dir": str(source_config.config_dir),
        "db_path": str(source_config.db_path),
        "connector_options": dict(connector_options or {}),
        "runtime_context": dict(runtime_context or {}),
        "storage": _plugin_storage_payload(
            source_config=source_config,
            tracking_source_id=tracking_source_id,
        ),
        "runtime": {
            "host_kind": _plugin_host_kind(),
            "plugin_id": manifest.plugin_id if manifest is not None else None,
            "plugin_version": manifest.plugin_version if manifest is not None else None,
            "plugin_family": manifest.plugin_family if manifest is not None else None,
            "runtime_kind": manifest.runtime_kind if manifest is not None else None,
            "working_directory": str(working_directory.resolve()) if working_directory is not None else None,
        },
    }
    return {
        "LIDLTOOL_CONFIG_DIR": str(source_config.config_dir),
        PLUGIN_RUNTIME_CONTEXT_ENV: json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


def load_plugin_runtime_context(
    env: Mapping[str, str] | None = None,
) -> PluginRuntimeContext:
    from lidltool.connectors.sdk.runtime import load_plugin_runtime_context as load_public_runtime_context

    return load_public_runtime_context(env)
