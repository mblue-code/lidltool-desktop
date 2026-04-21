from __future__ import annotations

import json
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from lidltool.connectors.plugin_status import PluginRegistryEntry
from lidltool.connectors.sdk.manifest import ConnectorManifest

_MANIFEST_FILE_NAMES = ("manifest.json", "manifest.toml")
_EXTERNAL_RUNTIME_KINDS = {"subprocess_python", "subprocess_binary"}
_EXTERNAL_PLUGIN_ORIGINS = {"external", "local_path"}


@dataclass(frozen=True, slots=True)
class ExternalManifestCandidate:
    manifest: ConnectorManifest | None
    origin_path: Path
    origin_directory: Path
    search_path: Path
    plugin_id: str | None = None
    source_id: str | None = None
    plugin_version: str | None = None
    plugin_family: str | None = None
    trust_class: str | None = None
    runtime_kind: str | None = None
    plugin_origin: str | None = None
    diagnostics: tuple[str, ...] = ()

    def as_invalid_entry(self, *, block_reason: str, status_detail: str) -> PluginRegistryEntry:
        return PluginRegistryEntry.invalid(
            block_reason=block_reason,
            status_detail=status_detail,
            plugin_id=self.plugin_id,
            source_id=self.source_id,
            plugin_version=self.plugin_version,
            plugin_family=self.plugin_family,
            trust_class=self.trust_class,
            runtime_kind=self.runtime_kind,
            plugin_origin=self.plugin_origin,
            origin_path=self.origin_path,
            origin_directory=self.origin_directory,
            search_path=self.search_path,
            diagnostics=self.diagnostics,
        )


def discover_external_manifest_candidates(search_paths: Iterable[Path]) -> list[ExternalManifestCandidate]:
    candidates: list[ExternalManifestCandidate] = []
    seen_manifest_paths: set[Path] = set()
    for search_path in _normalized_search_paths(search_paths):
        for manifest_path in _iter_manifest_files(search_path):
            resolved_manifest_path = manifest_path.resolve()
            if resolved_manifest_path in seen_manifest_paths:
                continue
            seen_manifest_paths.add(resolved_manifest_path)
            candidates.append(_load_candidate(resolved_manifest_path, search_path=search_path))
    return candidates


def _normalized_search_paths(paths: Iterable[Path]) -> list[Path]:
    normalized: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def _iter_manifest_files(search_path: Path) -> list[Path]:
    if not search_path.exists():
        return []
    if search_path.is_file():
        if search_path.name in _MANIFEST_FILE_NAMES:
            return [search_path]
        return []
    discovered: list[Path] = []
    for file_name in _MANIFEST_FILE_NAMES:
        discovered.extend(search_path.rglob(file_name))
    return sorted({path.resolve() for path in discovered})


def _load_candidate(manifest_path: Path, *, search_path: Path) -> ExternalManifestCandidate:
    origin_directory = manifest_path.parent.resolve()
    try:
        raw_payload = _read_manifest_file(manifest_path)
        metadata = _extract_manifest_metadata(raw_payload)
        manifest = ConnectorManifest.model_validate(raw_payload)
    except (ValidationError, ValueError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        return ExternalManifestCandidate(
            manifest=None,
            origin_path=manifest_path,
            origin_directory=origin_directory,
            search_path=search_path,
            plugin_id=locals().get("metadata", {}).get("plugin_id"),
            source_id=locals().get("metadata", {}).get("source_id"),
            plugin_version=locals().get("metadata", {}).get("plugin_version"),
            plugin_family=locals().get("metadata", {}).get("plugin_family"),
            trust_class=locals().get("metadata", {}).get("trust_class"),
            runtime_kind=locals().get("metadata", {}).get("runtime_kind"),
            plugin_origin=locals().get("metadata", {}).get("plugin_origin"),
            diagnostics=(str(exc),),
        )

    return ExternalManifestCandidate(
        manifest=manifest,
        origin_path=manifest_path,
        origin_directory=origin_directory,
        search_path=search_path,
        plugin_id=manifest.plugin_id,
        source_id=manifest.source_id,
        plugin_version=manifest.plugin_version,
        plugin_family=manifest.plugin_family,
        trust_class=manifest.trust_class,
        runtime_kind=manifest.runtime_kind,
        plugin_origin=manifest.plugin_origin,
    )


def validate_external_manifest_candidate(
    candidate: ExternalManifestCandidate,
) -> tuple[ConnectorManifest | None, PluginRegistryEntry | None]:
    manifest = candidate.manifest
    if manifest is None:
        detail = candidate.diagnostics[0] if candidate.diagnostics else "manifest validation failed"
        return None, candidate.as_invalid_entry(
            block_reason="manifest_validation_failed",
            status_detail=f"invalid connector manifest: {detail}",
        )
    if manifest.plugin_origin not in _EXTERNAL_PLUGIN_ORIGINS:
        return None, candidate.as_invalid_entry(
            block_reason="invalid_plugin_origin",
            status_detail=(
                "external manifests must use plugin_origin='external' or plugin_origin='local_path'"
            ),
        )
    if manifest.runtime_kind not in _EXTERNAL_RUNTIME_KINDS:
        return None, candidate.as_invalid_entry(
            block_reason="unsupported_external_runtime_kind",
            status_detail=(
                "external manifests must use runtime_kind='subprocess_python' or "
                "runtime_kind='subprocess_binary'"
            ),
        )
    if manifest.entrypoint is None:
        return None, candidate.as_invalid_entry(
            block_reason="missing_entrypoint",
            status_detail=f"external runtime {manifest.runtime_kind!r} requires manifest.entrypoint",
        )
    return manifest, None


def _read_manifest_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".toml":
        with path.open("rb") as fh:
            payload = tomllib.load(fh)
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest must be an object")
    return payload


def _extract_manifest_metadata(payload: dict[str, Any]) -> dict[str, str]:
    fields = (
        "plugin_id",
        "source_id",
        "plugin_version",
        "plugin_family",
        "trust_class",
        "runtime_kind",
        "plugin_origin",
    )
    metadata: dict[str, str] = {}
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            metadata[field] = value.strip()
    return metadata
