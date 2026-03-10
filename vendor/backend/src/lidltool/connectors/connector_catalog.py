from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from lidltool.config import AppConfig
from lidltool.connectors.market_catalog import (
    ConnectorMarketCatalog,
    ProductSurface,
    get_connector_market_catalog,
    support_policy_payload,
)
from lidltool.connectors.registry import ConnectorRegistry, build_builtin_connector_registry, get_connector_registry
from lidltool.connectors.sdk.manifest import TrustClass

CatalogEntryType = Literal["connector", "bundle", "desktop_pack"]
CatalogInstallMethod = Literal["built_in", "manual_import", "manual_mount", "download_url"]
CatalogSourceKind = Literal["repo_static"]
DesktopPackFormat = Literal["zip"]
HostKind = Literal["self_hosted", "electron"]


def _normalize_non_empty_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list or tuple")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name} entries must be strings")
        candidate = item.strip()
        if not candidate:
            raise ValueError(f"{field_name} entries must be non-empty")
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return tuple(normalized)


class CatalogCompatibilityHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_core_version: str | None = None
    max_core_version: str | None = None
    supported_host_kinds: tuple[HostKind, ...] = ()
    notes: tuple[str, ...] = ()

    @field_validator("supported_host_kinds", "notes", mode="before")
    @classmethod
    def _normalize_tuples(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _normalize_non_empty_tuple(value, field_name=str(info.field_name))


class ConnectorCatalogEntryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    entry_type: CatalogEntryType
    display_name: str
    summary: str
    description: str | None = None
    trust_class: TrustClass
    maintainer: str
    source: str
    supported_products: tuple[ProductSurface, ...]
    supported_markets: tuple[str, ...] = ()
    current_version: str | None = None
    compatibility: CatalogCompatibilityHint = Field(default_factory=CatalogCompatibilityHint)
    install_methods: tuple[CatalogInstallMethod, ...]
    docs_url: AnyUrl | None = None
    homepage_url: AnyUrl | None = None
    download_url: AnyUrl | None = None
    release_notes_summary: str | None = None

    @field_validator("supported_products", "supported_markets", "install_methods", mode="before")
    @classmethod
    def _normalize_tuples(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _normalize_non_empty_tuple(value, field_name=str(info.field_name))

    @field_validator("entry_id", "display_name", "summary", "maintainer", "source")
    @classmethod
    def _normalize_required_text(cls, value: str, info: Any) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError(f"{info.field_name} must be non-empty")
        return candidate

    @field_validator("description", "current_version", "release_notes_summary")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        return candidate or None

    @field_validator("install_methods")
    @classmethod
    def _validate_install_methods(cls, methods: tuple[CatalogInstallMethod, ...]) -> tuple[CatalogInstallMethod, ...]:
        if not methods:
            raise ValueError("install_methods must contain at least one install method")
        return methods

    def validate_common_policy(self) -> None:
        if self.trust_class != "official" and "built_in" in self.install_methods:
            raise ValueError("non-official catalog entries cannot claim install_methods=['built_in']")
        if "download_url" in self.install_methods and self.download_url is None:
            raise ValueError("download_url must be present when install_methods includes 'download_url'")


class ConnectorCatalogConnectorEntry(ConnectorCatalogEntryBase):
    entry_type: Literal["connector"]
    plugin_id: str
    source_id: str

    @field_validator("plugin_id", "source_id")
    @classmethod
    def _normalize_identity(cls, value: str, info: Any) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError(f"{info.field_name} must be non-empty")
        return candidate


class ConnectorCatalogBundleEntry(ConnectorCatalogEntryBase):
    entry_type: Literal["bundle"]
    bundle_id: str

    @field_validator("bundle_id")
    @classmethod
    def _normalize_bundle_id(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("bundle_id must be non-empty")
        return candidate


class ConnectorCatalogDesktopPackEntry(ConnectorCatalogEntryBase):
    entry_type: Literal["desktop_pack"]
    plugin_id: str
    source_id: str
    pack_format: DesktopPackFormat = "zip"

    @field_validator("plugin_id", "source_id")
    @classmethod
    def _normalize_identity(cls, value: str, info: Any) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError(f"{info.field_name} must be non-empty")
        return candidate

    @field_validator("install_methods")
    @classmethod
    def _validate_pack_install_methods(
        cls, methods: tuple[CatalogInstallMethod, ...]
    ) -> tuple[CatalogInstallMethod, ...]:
        if "manual_import" not in methods and "download_url" not in methods:
            raise ValueError("desktop_pack entries must support manual_import or download_url")
        return methods


ConnectorCatalogEntry = (
    ConnectorCatalogConnectorEntry | ConnectorCatalogBundleEntry | ConnectorCatalogDesktopPackEntry
)


class ConnectorCatalogRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    catalog_id: str = "connector_catalog"
    source_kind: CatalogSourceKind = "repo_static"
    entries: tuple[dict[str, Any], ...]

    @field_validator("catalog_id")
    @classmethod
    def _normalize_catalog_id(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("catalog_id must be non-empty")
        return candidate

    @field_validator("entries", mode="before")
    @classmethod
    def _normalize_entries(cls, value: Any) -> tuple[dict[str, Any], ...]:
        if not isinstance(value, (list, tuple)):
            raise ValueError("entries must be a list or tuple")
        normalized: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("entries must contain objects")
            normalized.append(dict(item))
        return tuple(normalized)


@dataclass(frozen=True, slots=True)
class ConnectorCatalogDiagnostic:
    severity: Literal["error"]
    code: str
    message: str
    entry_id: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "entry_id": self.entry_id,
        }


@dataclass(frozen=True, slots=True)
class LoadedConnectorCatalog:
    schema_version: str
    catalog_id: str
    source_kind: CatalogSourceKind
    source_path: Path
    entries: tuple[ConnectorCatalogEntry, ...]
    diagnostics: tuple[ConnectorCatalogDiagnostic, ...]


_ENTRY_ADAPTER = TypeAdapter(ConnectorCatalogEntry)


def connector_catalog_file_path() -> Path:
    return Path(__file__).with_name("curated_connector_catalog.json")


def _base_registry() -> ConnectorRegistry:
    return build_builtin_connector_registry()


def _market_profile_ids_for_bundle(
    market_catalog: ConnectorMarketCatalog, bundle_id: str
) -> tuple[str, ...]:
    matched: list[str] = []
    for profile in market_catalog.profiles:
        if bundle_id in profile.default_bundle_ids or bundle_id in profile.recommended_bundle_ids:
            matched.append(profile.profile_id)
    return tuple(matched)


def _release_variant_ids_for_bundle(
    market_catalog: ConnectorMarketCatalog, bundle_id: str
) -> tuple[str, ...]:
    matched: list[str] = []
    for variant in market_catalog.release_variants:
        if bundle_id in variant.preloaded_bundle_ids or bundle_id in variant.optional_bundle_ids:
            matched.append(variant.variant_id)
    return tuple(matched)


def _validate_entry_against_truth_sources(
    entry: ConnectorCatalogEntry,
    *,
    builtin_registry: ConnectorRegistry,
    market_catalog: ConnectorMarketCatalog,
) -> list[ConnectorCatalogDiagnostic]:
    diagnostics: list[ConnectorCatalogDiagnostic] = []
    try:
        entry.validate_common_policy()
        if entry.entry_type == "bundle":
            bundle = market_catalog.bundle(entry.bundle_id)
            if bundle is None:
                raise ValueError(f"bundle_id {entry.bundle_id!r} is not defined in the official market catalog")
            if entry.trust_class != bundle.support_class:
                raise ValueError(
                    f"bundle trust_class {entry.trust_class!r} does not match official bundle support_class {bundle.support_class!r}"
                )
            if entry.supported_products != bundle.supported_products:
                raise ValueError(
                    "bundle supported_products must match the official market catalog supported_products"
                )
            if entry.current_version is None:
                raise ValueError("bundle entries must declare current_version for discovery surfaces")
            return diagnostics

        manifest_entry = builtin_registry.get_entry_by_plugin_id(entry.plugin_id)
        manifest = manifest_entry.manifest if manifest_entry is not None else None
        if entry.trust_class == "official":
            if manifest is None:
                raise ValueError(
                    f"official catalog entry {entry.plugin_id!r} does not map to a built-in connector manifest"
                )
            if manifest.source_id != entry.source_id:
                raise ValueError(
                    f"catalog source_id {entry.source_id!r} does not match manifest source_id {manifest.source_id!r}"
                )
            if entry.current_version is not None and entry.current_version != manifest.plugin_version:
                raise ValueError(
                    f"catalog current_version {entry.current_version!r} does not match manifest plugin_version {manifest.plugin_version!r}"
                )
            if "built_in" not in entry.install_methods:
                raise ValueError("official connector entries must include install_methods=['built_in']")
        elif manifest is not None and manifest.source_id != entry.source_id:
            raise ValueError(
                f"catalog source_id {entry.source_id!r} does not match known manifest source_id {manifest.source_id!r}"
            )
        if entry.entry_type == "desktop_pack" and "desktop" not in entry.supported_products:
            raise ValueError("desktop_pack entries must include 'desktop' in supported_products")
    except ValueError as exc:
        diagnostics.append(
            ConnectorCatalogDiagnostic(
                severity="error",
                code="catalog_entry_truth_mismatch",
                message=str(exc),
                entry_id=entry.entry_id,
            )
        )
    return diagnostics


def load_connector_catalog(path: Path | None = None) -> LoadedConnectorCatalog:
    catalog_path = path or connector_catalog_file_path()
    diagnostics: list[ConnectorCatalogDiagnostic] = []
    try:
        raw_payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return LoadedConnectorCatalog(
            schema_version="1",
            catalog_id="connector_catalog",
            source_kind="repo_static",
            source_path=catalog_path,
            entries=(),
            diagnostics=(
                ConnectorCatalogDiagnostic(
                    severity="error",
                    code="catalog_load_failed",
                    message=str(exc),
                ),
            ),
        )

    try:
        root = ConnectorCatalogRoot.model_validate(raw_payload)
    except ValidationError as exc:
        return LoadedConnectorCatalog(
            schema_version="1",
            catalog_id="connector_catalog",
            source_kind="repo_static",
            source_path=catalog_path,
            entries=(),
            diagnostics=(
                ConnectorCatalogDiagnostic(
                    severity="error",
                    code="catalog_root_invalid",
                    message=str(exc),
                ),
            ),
        )

    builtin_registry = _base_registry()
    market_catalog = get_connector_market_catalog()
    entries: list[ConnectorCatalogEntry] = []
    seen_entry_ids: set[str] = set()

    for raw_entry in root.entries:
        entry_id = raw_entry.get("entry_id") if isinstance(raw_entry.get("entry_id"), str) else None
        try:
            entry = _ENTRY_ADAPTER.validate_python(raw_entry)
        except ValidationError as exc:
            diagnostics.append(
                ConnectorCatalogDiagnostic(
                    severity="error",
                    code="catalog_entry_invalid",
                    message=str(exc),
                    entry_id=entry_id,
                )
            )
            continue

        if entry.entry_id in seen_entry_ids:
            diagnostics.append(
                ConnectorCatalogDiagnostic(
                    severity="error",
                    code="catalog_entry_duplicate",
                    message=f"duplicate catalog entry_id {entry.entry_id!r}",
                    entry_id=entry.entry_id,
                )
            )
            continue
        seen_entry_ids.add(entry.entry_id)

        entry_diagnostics = _validate_entry_against_truth_sources(
            entry,
            builtin_registry=builtin_registry,
            market_catalog=market_catalog,
        )
        if entry_diagnostics:
            diagnostics.extend(entry_diagnostics)
            continue
        entries.append(entry)

    return LoadedConnectorCatalog(
        schema_version=root.schema_version,
        catalog_id=root.catalog_id,
        source_kind=root.source_kind,
        source_path=catalog_path,
        entries=tuple(entries),
        diagnostics=tuple(diagnostics),
    )


@lru_cache(maxsize=1)
def get_connector_catalog() -> LoadedConnectorCatalog:
    return load_connector_catalog()


def connector_catalog_entry_for_plugin(
    plugin_id: str | None,
    *,
    product: ProductSurface | None = None,
) -> ConnectorCatalogEntry | None:
    if not plugin_id:
        return None
    fallback: ConnectorCatalogEntry | None = None
    for entry in get_connector_catalog().entries:
        if entry.entry_type == "bundle":
            continue
        if entry.plugin_id != plugin_id:
            continue
        if product is not None and product not in entry.supported_products:
            continue
        if entry.entry_type == "connector":
            return entry
        fallback = entry
        if product is None:
            return fallback
    return fallback


def connector_catalog_entry_payload(
    entry: ConnectorCatalogEntry,
    *,
    product: ProductSurface | None,
    registry: ConnectorRegistry | None = None,
    market_catalog: ConnectorMarketCatalog | None = None,
) -> dict[str, Any]:
    resolved_market_catalog = market_catalog or get_connector_market_catalog()
    resolved_registry = registry
    official_bundle_ids: tuple[str, ...] = ()
    market_profile_ids: tuple[str, ...] = ()
    release_variant_ids: tuple[str, ...] = ()
    discovered_locally = False
    local_status: str | None = None
    enabled_locally = False
    blocked_by_policy = False
    local_block_reason: str | None = None

    if entry.entry_type == "bundle":
        official_bundle_ids = (entry.bundle_id,)
        market_profile_ids = _market_profile_ids_for_bundle(resolved_market_catalog, entry.bundle_id)
        release_variant_ids = _release_variant_ids_for_bundle(resolved_market_catalog, entry.bundle_id)
    else:
        official_bundle_ids = resolved_market_catalog.bundle_ids_for_plugin(entry.plugin_id)
        market_profile_ids = tuple(
            dict.fromkeys(
                [
                    *resolved_market_catalog.profile_ids_for_plugin(entry.plugin_id, membership="default"),
                    *resolved_market_catalog.profile_ids_for_plugin(entry.plugin_id, membership="recommended"),
                ]
            )
        )
        matched_variants: list[str] = []
        for bundle_id in official_bundle_ids:
            matched_variants.extend(_release_variant_ids_for_bundle(resolved_market_catalog, bundle_id))
        release_variant_ids = tuple(dict.fromkeys(matched_variants))

        if resolved_registry is not None:
            registry_entry = resolved_registry.get_entry(entry.source_id)
            if registry_entry is not None:
                discovered_locally = True
                local_status = registry_entry.status
                enabled_locally = registry_entry.enabled
                blocked_by_policy = registry_entry.block_reason is not None
                local_block_reason = registry_entry.block_reason

    payload = {
        "entry_id": entry.entry_id,
        "entry_type": entry.entry_type,
        "display_name": entry.display_name,
        "summary": entry.summary,
        "description": entry.description,
        "trust_class": entry.trust_class,
        "maintainer": entry.maintainer,
        "source": entry.source,
        "supported_products": list(entry.supported_products),
        "supported_markets": list(entry.supported_markets),
        "current_version": entry.current_version,
        "compatibility": {
            "min_core_version": entry.compatibility.min_core_version,
            "max_core_version": entry.compatibility.max_core_version,
            "supported_host_kinds": list(entry.compatibility.supported_host_kinds),
            "notes": list(entry.compatibility.notes),
        },
        "install_methods": list(entry.install_methods),
        "docs_url": str(entry.docs_url) if entry.docs_url is not None else None,
        "homepage_url": str(entry.homepage_url) if entry.homepage_url is not None else None,
        "download_url": str(entry.download_url) if entry.download_url is not None else None,
        "release_notes_summary": entry.release_notes_summary,
        "support_policy": support_policy_payload(entry.trust_class),
        "official_bundle_ids": list(official_bundle_ids),
        "market_profile_ids": list(market_profile_ids),
        "release_variant_ids": list(release_variant_ids),
        "availability": {
            "catalog_listed": True,
            "discovered_locally": discovered_locally,
            "local_status": local_status,
            "enabled_locally": enabled_locally,
            "blocked_by_policy": blocked_by_policy,
            "block_reason": local_block_reason,
            "officially_bundled": len(official_bundle_ids) > 0,
            "manual_install_supported": any(
                method in {"manual_import", "manual_mount"} for method in entry.install_methods
            ),
        },
    }

    if entry.entry_type == "bundle":
        payload["bundle_id"] = entry.bundle_id
    else:
        payload["plugin_id"] = entry.plugin_id
        payload["source_id"] = entry.source_id
        if entry.entry_type == "desktop_pack":
            payload["pack_format"] = entry.pack_format
    return payload


def connector_catalog_listing_payload(
    plugin_id: str | None,
    *,
    product: ProductSurface | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any] | None:
    entry = connector_catalog_entry_for_plugin(plugin_id, product=product)
    if entry is None:
        return None
    return connector_catalog_entry_payload(entry, product=product, registry=registry)


def connector_catalog_payload(
    *,
    product: ProductSurface | None = None,
    config: AppConfig | None = None,
    registry: ConnectorRegistry | None = None,
) -> dict[str, Any]:
    loaded = get_connector_catalog()
    resolved_registry = registry or get_connector_registry(config)
    filtered_entries = [
        connector_catalog_entry_payload(
            entry,
            product=product,
            registry=resolved_registry,
        )
        for entry in loaded.entries
        if product is None or product in entry.supported_products
    ]
    return {
        "schema_version": loaded.schema_version,
        "catalog_id": loaded.catalog_id,
        "source_kind": loaded.source_kind,
        "source_path": str(loaded.source_path),
        "entries": filtered_entries,
        "diagnostics": [item.payload() for item in loaded.diagnostics],
    }
