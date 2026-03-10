from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lidltool.connectors.sdk.manifest import ConnectorManifest

PluginLoadStatus = Literal[
    "discovered",
    "valid",
    "invalid",
    "blocked_by_policy",
    "incompatible",
    "enabled",
    "disabled",
]


@dataclass(frozen=True, slots=True)
class PluginCompatibilitySnapshot:
    compatible: bool
    host_kind: str
    core_version: str
    reason: str | None = None
    min_core_version: str | None = None
    max_core_version: str | None = None
    supported_host_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PluginRegistryEntry:
    status: PluginLoadStatus
    discovered: bool
    valid: bool
    enabled: bool
    manifest: ConnectorManifest | None = None
    plugin_id: str | None = None
    source_id: str | None = None
    plugin_version: str | None = None
    plugin_family: str | None = None
    trust_class: str | None = None
    runtime_kind: str | None = None
    plugin_origin: str | None = None
    origin_path: Path | None = None
    origin_directory: Path | None = None
    search_path: Path | None = None
    compatibility: PluginCompatibilitySnapshot | None = None
    block_reason: str | None = None
    status_detail: str | None = None
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_manifest(
        cls,
        *,
        manifest: ConnectorManifest,
        status: PluginLoadStatus,
        enabled: bool,
        compatibility: PluginCompatibilitySnapshot,
        block_reason: str | None = None,
        status_detail: str | None = None,
        origin_path: Path | None = None,
        origin_directory: Path | None = None,
        search_path: Path | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> PluginRegistryEntry:
        return cls(
            status=status,
            discovered=True,
            valid=True,
            enabled=enabled,
            manifest=manifest,
            plugin_id=manifest.plugin_id,
            source_id=manifest.source_id,
            plugin_version=manifest.plugin_version,
            plugin_family=manifest.plugin_family,
            trust_class=manifest.trust_class,
            runtime_kind=manifest.runtime_kind,
            plugin_origin=manifest.plugin_origin,
            origin_path=origin_path,
            origin_directory=origin_directory,
            search_path=search_path,
            compatibility=compatibility,
            block_reason=block_reason,
            status_detail=status_detail,
            diagnostics=diagnostics,
        )

    @classmethod
    def invalid(
        cls,
        *,
        status_detail: str,
        block_reason: str,
        plugin_id: str | None = None,
        source_id: str | None = None,
        plugin_version: str | None = None,
        plugin_family: str | None = None,
        trust_class: str | None = None,
        runtime_kind: str | None = None,
        plugin_origin: str | None = None,
        origin_path: Path | None = None,
        origin_directory: Path | None = None,
        search_path: Path | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> PluginRegistryEntry:
        return cls(
            status="invalid",
            discovered=True,
            valid=False,
            enabled=False,
            plugin_id=plugin_id,
            source_id=source_id,
            plugin_version=plugin_version,
            plugin_family=plugin_family,
            trust_class=trust_class,
            runtime_kind=runtime_kind,
            plugin_origin=plugin_origin,
            origin_path=origin_path,
            origin_directory=origin_directory,
            search_path=search_path,
            block_reason=block_reason,
            status_detail=status_detail,
            diagnostics=diagnostics,
        )
