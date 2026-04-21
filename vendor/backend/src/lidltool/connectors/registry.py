from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from lidltool.config import AppConfig
from lidltool.connectors.external_loading import (
    discover_external_manifest_candidates,
    validate_external_manifest_candidate,
)
from lidltool.connectors.manifest import ConnectorManifest, ManifestValidationError
from lidltool.connectors.market_catalog import connector_distribution_payload
from lidltool.connectors.operator_status import operator_state_payload, support_summary_payload
from lidltool.connectors.plugin_policy import evaluate_plugin_compatibility, evaluate_plugin_policy
from lidltool.connectors.plugin_status import PluginRegistryEntry

_BUILTIN_CONNECTOR_MANIFEST_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "plugin_id": "builtin.lidl_plus_de",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "lidl_plus_de",
        "display_name": "Lidl Plus",
        "merchant_name": "Lidl",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.lidl_adapter:LidlConnectorAdapter",
        "auth_kind": "oauth_pkce",
        "auth": {
            "auth_kind": "oauth_pkce",
            "supports_live_session_bootstrap": True,
            "supports_reauth": True,
            "supports_headless_refresh": True,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": False,
            "implemented_actions": [],
            "compatibility_actions": ["start_auth", "cancel_auth"],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": [
            "healthcheck",
            "historical_sync",
            "incremental_sync",
            "live_session_bootstrap",
            "discount_classification",
            "receipt_images",
            "manual_reauth",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                "lidl_plus_de",
            ],
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "lidl_plus_de",
            ],
        },
        "metadata": {"maturity": "working"},
    },
    {
        "plugin_id": "builtin.amazon_de",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "amazon_de",
        "display_name": "Amazon",
        "merchant_name": "Amazon",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.amazon_adapter:AmazonConnectorAdapter",
        "auth_kind": "browser_session",
        "auth": {
            "auth_kind": "browser_session",
            "supports_live_session_bootstrap": True,
            "supports_reauth": True,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": True,
            "implemented_actions": [],
            "compatibility_actions": ["start_auth", "cancel_auth"],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": [
            "healthcheck",
            "historical_sync",
            "incremental_sync",
            "live_session_bootstrap",
            "order_history",
            "manual_reauth",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                "amazon_de",
            ],
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "amazon_de",
            ],
        },
        "metadata": {"maturity": "preview"},
    },
    {
        "plugin_id": "builtin.amazon_fr",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "amazon_fr",
        "display_name": "Amazon",
        "merchant_name": "Amazon",
        "country_code": "FR",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.amazon_adapter:AmazonConnectorAdapter",
        "auth_kind": "browser_session",
        "auth": {
            "auth_kind": "browser_session",
            "supports_live_session_bootstrap": True,
            "supports_reauth": True,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": True,
            "implemented_actions": [],
            "compatibility_actions": ["start_auth", "cancel_auth"],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": [
            "healthcheck",
            "historical_sync",
            "incremental_sync",
            "live_session_bootstrap",
            "order_history",
            "manual_reauth",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                "amazon_fr",
            ],
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "amazon_fr",
            ],
        },
        "metadata": {"maturity": "preview"},
    },
    {
        "plugin_id": "builtin.amazon_gb",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "amazon_gb",
        "display_name": "Amazon",
        "merchant_name": "Amazon",
        "country_code": "GB",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.amazon_adapter:AmazonConnectorAdapter",
        "auth_kind": "browser_session",
        "auth": {
            "auth_kind": "browser_session",
            "supports_live_session_bootstrap": True,
            "supports_reauth": True,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": True,
            "implemented_actions": [],
            "compatibility_actions": ["start_auth", "cancel_auth"],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": [
            "healthcheck",
            "historical_sync",
            "incremental_sync",
            "live_session_bootstrap",
            "order_history",
            "manual_reauth",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                "amazon_gb",
            ],
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "amazon_gb",
            ],
        },
        "metadata": {"maturity": "preview"},
    },
    {
        "plugin_id": "builtin.netto_de",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "netto_de",
        "display_name": "Netto",
        "merchant_name": "Netto",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.netto_adapter:NettoConnectorAdapter",
        "auth_kind": "none",
        "auth": {
            "auth_kind": "none",
            "supports_live_session_bootstrap": False,
            "supports_reauth": False,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": False,
            "implemented_actions": [],
            "compatibility_actions": [],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": ["healthcheck"],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": None,
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "netto_de",
            ],
        },
        "metadata": {"maturity": "stub"},
    },
    {
        "plugin_id": "builtin.rossmann_de",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "rossmann_de",
        "display_name": "Rossmann",
        "merchant_name": "Rossmann",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.rossmann_adapter:RossmannConnectorAdapter",
        "auth_kind": "browser_session",
        "auth": {
            "auth_kind": "browser_session",
            "supports_live_session_bootstrap": True,
            "supports_reauth": True,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": True,
            "implemented_actions": [],
            "compatibility_actions": ["start_auth", "cancel_auth"],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": [
            "healthcheck",
            "historical_sync",
            "incremental_sync",
            "live_session_bootstrap",
            "order_history",
            "manual_reauth",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
        "builtin_cli": {
            "bootstrap_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "auth",
                "bootstrap",
                "--source-id",
                "rossmann_de",
            ],
            "sync_args": [
                "-m",
                "lidltool.cli",
                "connectors",
                "sync",
                "--source-id",
                "rossmann_de",
            ],
        },
        "metadata": {"maturity": "preview"},
    },
    {
        "plugin_id": "builtin.dm_de_offers",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "offer",
        "source_id": "dm_de_offers",
        "display_name": "dm Offers",
        "merchant_name": "dm",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.offer_file_feed_adapter:OfferFileFeedConnectorAdapter",
        "auth_kind": "none",
        "capabilities": [
            "healthcheck",
            "offer_feed",
            "offer_detail_fetch",
            "offer_normalization",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted"],
        },
    },
    {
        "plugin_id": "builtin.rossmann_de_offers",
        "plugin_version": "1.0.0",
        "connector_api_version": "1",
        "plugin_family": "offer",
        "source_id": "rossmann_de_offers",
        "display_name": "Rossmann Offers",
        "merchant_name": "Rossmann",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "builtin",
        "entrypoint": "lidltool.connectors.offer_file_feed_adapter:OfferFileFeedConnectorAdapter",
        "auth_kind": "none",
        "capabilities": [
            "healthcheck",
            "offer_feed",
            "offer_detail_fetch",
            "offer_normalization",
        ],
        "trust_class": "official",
        "plugin_origin": "builtin",
        "install_status": "bundled",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted"],
        },
    },
)


def _plugin_host_kind() -> str:
    return "electron" if os.getenv("LIDLTOOL_CONNECTOR_HOST_KIND", "").strip().lower() == "electron" else "self_hosted"


class ConnectorRegistry:
    def __init__(self, entries: Iterable[PluginRegistryEntry]) -> None:
        self._entries: list[PluginRegistryEntry] = []
        self._manifests: list[ConnectorManifest] = []
        self._entry_by_source_id: dict[str, PluginRegistryEntry] = {}
        self._entry_by_plugin_id: dict[str, PluginRegistryEntry] = {}
        self._by_source_id: dict[str, ConnectorManifest] = {}
        self._by_plugin_id: dict[str, ConnectorManifest] = {}
        for entry in entries:
            self._entries.append(entry)
            if entry.source_id is not None and (
                entry.source_id not in self._entry_by_source_id or entry.manifest is not None
            ):
                self._entry_by_source_id[entry.source_id] = entry
            if entry.plugin_id is not None and (
                entry.plugin_id not in self._entry_by_plugin_id or entry.manifest is not None
            ):
                self._entry_by_plugin_id[entry.plugin_id] = entry
            if entry.manifest is None:
                continue
            manifest = entry.manifest
            if manifest.source_id in self._by_source_id:
                raise ManifestValidationError(
                    f"duplicate source_id in connector registry: {manifest.source_id}"
                )
            if manifest.plugin_id in self._by_plugin_id:
                raise ManifestValidationError(
                    f"duplicate plugin_id in connector registry: {manifest.plugin_id}"
                )
            self._manifests.append(manifest)
            self._by_source_id[manifest.source_id] = manifest
            self._by_plugin_id[manifest.plugin_id] = manifest

    @classmethod
    def from_definitions(
        cls, definitions: Iterable[ConnectorManifest | Mapping[str, Any]]
    ) -> ConnectorRegistry:
        entries: list[PluginRegistryEntry] = []
        for definition in definitions:
            if isinstance(definition, ConnectorManifest):
                manifest = definition
                compatibility = evaluate_plugin_compatibility(manifest, host_kind=_plugin_host_kind())
                entries.append(
                    PluginRegistryEntry.from_manifest(
                        manifest=manifest,
                        status="enabled" if compatibility.compatible else "incompatible",
                        enabled=compatibility.compatible,
                        compatibility=compatibility,
                        block_reason=compatibility.reason,
                    )
                )
                continue
            try:
                manifest = ConnectorManifest.model_validate(definition)
            except ValidationError as exc:
                raise ManifestValidationError(f"invalid connector manifest: {exc}") from exc
            compatibility = evaluate_plugin_compatibility(manifest, host_kind=_plugin_host_kind())
            entries.append(
                PluginRegistryEntry.from_manifest(
                    manifest=manifest,
                    status="enabled" if compatibility.compatible else "incompatible",
                    enabled=compatibility.compatible,
                    compatibility=compatibility,
                    block_reason=compatibility.reason,
                )
            )
        return cls(entries)

    def list_manifests(self, *, plugin_family: str | None = None) -> list[ConnectorManifest]:
        if plugin_family is None:
            return list(self._manifests)
        return [manifest for manifest in self._manifests if manifest.plugin_family == plugin_family]

    def list_entries(self, *, plugin_family: str | None = None) -> list[PluginRegistryEntry]:
        if plugin_family is None:
            return list(self._entries)
        return [
            entry for entry in self._entries if entry.plugin_family == plugin_family
        ]

    def get_manifest(self, source_id: str) -> ConnectorManifest | None:
        return self._by_source_id.get(source_id)

    def get_entry(self, source_id: str) -> PluginRegistryEntry | None:
        return self._entry_by_source_id.get(source_id)

    def get_entry_by_plugin_id(self, plugin_id: str) -> PluginRegistryEntry | None:
        return self._entry_by_plugin_id.get(plugin_id)

    def require_manifest(self, source_id: str) -> ConnectorManifest:
        manifest = self.get_manifest(source_id)
        if manifest is None:
            raise ManifestValidationError(f"unknown connector source_id: {source_id}")
        return manifest

    def has_source(self, source_id: str) -> bool:
        return source_id in self._by_source_id


def build_builtin_connector_registry(
    definitions: Iterable[ConnectorManifest | Mapping[str, Any]] | None = None,
) -> ConnectorRegistry:
    return ConnectorRegistry.from_definitions(
        definitions if definitions is not None else _BUILTIN_CONNECTOR_MANIFEST_DEFINITIONS
    )


def build_connector_registry(
    *,
    config: AppConfig | None = None,
    definitions: Iterable[ConnectorManifest | Mapping[str, Any]] | None = None,
) -> ConnectorRegistry:
    builtin_registry = build_builtin_connector_registry(definitions)
    if config is None or definitions is not None:
        return builtin_registry

    entries = list(builtin_registry.list_entries())
    seen_source_ids = {manifest.source_id for manifest in builtin_registry.list_manifests()}
    seen_plugin_ids = {manifest.plugin_id for manifest in builtin_registry.list_manifests()}

    for candidate in discover_external_manifest_candidates(config.connector_plugin_search_paths):
        manifest, invalid_entry = validate_external_manifest_candidate(candidate)
        if invalid_entry is not None:
            entries.append(invalid_entry)
            continue
        assert manifest is not None
        if manifest.source_id in seen_source_ids:
            entries.append(
                candidate.as_invalid_entry(
                    block_reason="duplicate_source_id",
                    status_detail=f"duplicate source_id in connector registry: {manifest.source_id}",
                )
            )
            continue
        if manifest.plugin_id in seen_plugin_ids:
            entries.append(
                candidate.as_invalid_entry(
                    block_reason="duplicate_plugin_id",
                    status_detail=f"duplicate plugin_id in connector registry: {manifest.plugin_id}",
                )
            )
            continue
        seen_source_ids.add(manifest.source_id)
        seen_plugin_ids.add(manifest.plugin_id)
        decision = evaluate_plugin_policy(manifest, config=config, host_kind=_plugin_host_kind())
        entries.append(
            PluginRegistryEntry.from_manifest(
                manifest=manifest,
                status=decision.status,
                enabled=decision.enabled,
                compatibility=decision.compatibility,
                block_reason=decision.block_reason,
                status_detail=decision.detail,
                origin_path=candidate.origin_path,
                origin_directory=candidate.origin_directory,
                search_path=candidate.search_path,
            )
        )

    return ConnectorRegistry(entries)


@lru_cache(maxsize=1)
def _get_builtin_connector_registry() -> ConnectorRegistry:
    return build_builtin_connector_registry()


def get_connector_registry(config: AppConfig | None = None) -> ConnectorRegistry:
    if config is None:
        return _get_builtin_connector_registry()
    return build_connector_registry(config=config)


def connector_manifest_payload(
    manifest: ConnectorManifest,
    *,
    entry: PluginRegistryEntry | None = None,
    include_sensitive_details: bool = True,
) -> dict[str, Any]:
    from lidltool.connectors.connector_catalog import connector_catalog_listing_payload

    catalog_listing = connector_catalog_listing_payload(manifest.plugin_id)
    payload: dict[str, Any] = {
        "manifest_version": manifest.manifest_version,
        "plugin_id": manifest.plugin_id,
        "plugin_version": manifest.plugin_version,
        "connector_api_version": manifest.connector_api_version,
        "plugin_family": manifest.plugin_family,
        "source_id": manifest.source_id,
        "display_name": manifest.display_name,
        "merchant_name": manifest.merchant_name,
        "country_code": manifest.country_code,
        "runtime_kind": manifest.runtime_kind,
        "auth_kind": manifest.auth_kind,
        "auth": manifest.auth.model_dump(mode="python") if manifest.auth is not None else None,
        "capabilities": list(manifest.capabilities),
        "trust_class": manifest.trust_class,
        "plugin_origin": manifest.plugin_origin,
        "install_status": manifest.install_status,
        "config_schema": (
            {
                "fields": [field.model_dump(mode="python") for field in manifest.config_schema.fields]
            }
            if manifest.config_schema is not None
            else None
        ),
        "compatibility": {
            "min_core_version": manifest.compatibility.min_core_version,
            "max_core_version": manifest.compatibility.max_core_version,
            "supported_host_kinds": list(manifest.compatibility.supported_host_kinds),
        },
        "actions": (
            {
                "required": list(manifest.actions.required),
                "optional": list(manifest.actions.optional),
                "reserved": list(manifest.actions.reserved),
            }
            if manifest.actions is not None
            else None
        ),
        "policy": {
            "trust": {
                "execution_model": manifest.policy.trust.execution_model,
                "requires_operator_approval": manifest.policy.trust.requires_operator_approval,
                "notes": manifest.policy.trust.notes,
            },
            "ai": {
                "allow_model_mediation": manifest.policy.ai.allow_model_mediation,
                "allow_model_generated_actions": manifest.policy.ai.allow_model_generated_actions,
                "redacted_fields": list(manifest.policy.ai.redacted_fields),
            },
        },
        "distribution": connector_distribution_payload(
            plugin_id=manifest.plugin_id,
            source_id=manifest.source_id,
            trust_class=manifest.trust_class,
        ),
        "support": support_summary_payload(manifest.trust_class),
    }
    if entry is not None:
        payload["status"] = entry.status
        payload["valid"] = entry.valid
        payload["enabled"] = entry.enabled
        payload["block_reason"] = entry.block_reason
        payload["status_detail"] = entry.status_detail
        if include_sensitive_details:
            payload["origin_path"] = str(entry.origin_path) if entry.origin_path is not None else None
            payload["origin_directory"] = (
                str(entry.origin_directory) if entry.origin_directory is not None else None
            )
            payload["search_path"] = str(entry.search_path) if entry.search_path is not None else None
            payload["diagnostics"] = list(entry.diagnostics)
        payload["compatibility_result"] = (
            {
                "compatible": entry.compatibility.compatible,
                "host_kind": entry.compatibility.host_kind,
                "core_version": entry.compatibility.core_version,
                "reason": entry.compatibility.reason,
                "min_core_version": entry.compatibility.min_core_version,
                "max_core_version": entry.compatibility.max_core_version,
                "supported_host_kinds": list(entry.compatibility.supported_host_kinds),
            }
            if entry.compatibility is not None
            else None
        )
        payload["operator_state"] = operator_state_payload(
            status=entry.status,
            enabled=entry.enabled,
            discovered=entry.discovered,
            plugin_origin=entry.plugin_origin,
            catalog_listed=catalog_listing is not None,
            block_reason=entry.block_reason,
            status_detail=entry.status_detail,
        )
    else:
        payload["operator_state"] = operator_state_payload(
            status="enabled" if manifest.plugin_origin == "builtin" else None,
            enabled=manifest.plugin_origin == "builtin",
            discovered=True,
            plugin_origin=manifest.plugin_origin,
            catalog_listed=catalog_listing is not None,
        )
    return payload


def connector_registry_entry_payload(entry: PluginRegistryEntry) -> dict[str, Any]:
    if entry.manifest is not None:
        return connector_manifest_payload(entry.manifest, entry=entry)
    from lidltool.connectors.connector_catalog import connector_catalog_listing_payload

    catalog_listing = connector_catalog_listing_payload(entry.plugin_id)
    return {
        "manifest_version": None,
        "plugin_id": entry.plugin_id,
        "plugin_version": entry.plugin_version,
        "connector_api_version": None,
        "plugin_family": entry.plugin_family,
        "source_id": entry.source_id,
        "display_name": entry.source_id or entry.plugin_id or "unknown plugin",
        "merchant_name": None,
        "country_code": None,
        "runtime_kind": entry.runtime_kind,
        "auth_kind": None,
        "auth": None,
        "capabilities": [],
        "trust_class": entry.trust_class,
        "plugin_origin": entry.plugin_origin,
        "install_status": "blocked",
        "compatibility": None,
        "actions": None,
        "policy": None,
        "status": entry.status,
        "valid": entry.valid,
        "enabled": entry.enabled,
        "block_reason": entry.block_reason,
        "status_detail": entry.status_detail,
        "origin_path": str(entry.origin_path) if entry.origin_path is not None else None,
        "origin_directory": (
            str(entry.origin_directory) if entry.origin_directory is not None else None
        ),
        "search_path": str(entry.search_path) if entry.search_path is not None else None,
        "diagnostics": list(entry.diagnostics),
        "compatibility_result": (
            {
                "compatible": entry.compatibility.compatible,
                "host_kind": entry.compatibility.host_kind,
                "core_version": entry.compatibility.core_version,
                "reason": entry.compatibility.reason,
                "min_core_version": entry.compatibility.min_core_version,
                "max_core_version": entry.compatibility.max_core_version,
                "supported_host_kinds": list(entry.compatibility.supported_host_kinds),
            }
            if entry.compatibility is not None
            else None
        ),
        "distribution": connector_distribution_payload(
            plugin_id=entry.plugin_id,
            source_id=entry.source_id,
            trust_class=entry.trust_class,
        ),
        "support": support_summary_payload(entry.trust_class),
        "operator_state": operator_state_payload(
            status=entry.status,
            enabled=entry.enabled,
            discovered=entry.discovered,
            plugin_origin=entry.plugin_origin,
            catalog_listed=catalog_listing is not None,
            block_reason=entry.block_reason,
            status_detail=entry.status_detail,
        ),
    }


def source_manifest_payload(
    source_id: str,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
    include_sensitive_details: bool = True,
) -> dict[str, Any] | None:
    resolved_registry = registry or get_connector_registry(config)
    entry = resolved_registry.get_entry(source_id)
    if entry is None or entry.manifest is None:
        return None
    return connector_manifest_payload(
        entry.manifest,
        entry=entry,
        include_sensitive_details=include_sensitive_details,
    )


def source_catalog(
    plugin_family: str | None = "receipt",
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> list[dict[str, Any]]:
    resolved_registry = registry or get_connector_registry(config)
    return [
        connector_registry_entry_payload(entry)
        for entry in resolved_registry.list_entries(plugin_family=plugin_family)
    ]


def source_display_name(
    source_id: str,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> str:
    payload = source_manifest_payload(source_id, config=config, registry=registry)
    if payload is not None and isinstance(payload.get("display_name"), str):
        return str(payload["display_name"])
    return source_id.replace("_", " ").title()


def source_bootstrap_command(
    source_id: str,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> list[str] | None:
    resolved_registry = registry or get_connector_registry(config)
    manifest = resolved_registry.get_manifest(source_id)
    if manifest is None or manifest.builtin_cli is None or manifest.builtin_cli.bootstrap_args is None:
        return None
    return [sys.executable, *manifest.builtin_cli.bootstrap_args]


def source_sync_command(
    source_id: str,
    *,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> list[str] | None:
    resolved_registry = registry or get_connector_registry(config)
    manifest = resolved_registry.get_manifest(source_id)
    if manifest is None or manifest.builtin_cli is None or manifest.builtin_cli.sync_args is None:
        return None
    return [sys.executable, *manifest.builtin_cli.sync_args]
