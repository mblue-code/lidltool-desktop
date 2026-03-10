from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lidltool.config import AppConfig
from lidltool.connectors.sdk.manifest import PluginFamily, TrustClass

ProductSurface = Literal["self_hosted", "desktop"]
BundleState = Literal["enabled", "available", "disabled"]
ReleaseChannel = Literal["stable", "preview", "experimental"]
BundleSupportLevel = Literal["maintained", "preview", "best_effort"]
ReleaseEditionKind = Literal["universal_shell", "regional_edition"]

DEFAULT_MARKET_PROFILE_ID = "global_shell"
DEFAULT_SELF_HOSTED_RELEASE_VARIANT_ID = "self_hosted_oss_universal"


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


class SupportPolicyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    support_class: TrustClass
    display_name: str
    shipping_policy: str
    ui_label: str
    diagnostics_expectation: str
    update_expectations: str
    maintainer_support: str


class BundleDefaultState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    self_hosted: BundleState = "available"
    desktop: BundleState = "available"


class OfficialConnectorBundleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    display_name: str
    market: str
    region: str | None = None
    connector_plugin_ids: tuple[str, ...]
    supported_products: tuple[ProductSurface, ...]
    default_state: BundleDefaultState = Field(default_factory=BundleDefaultState)
    support_class: TrustClass = "official"
    support_level: BundleSupportLevel = "maintained"
    release_channel: ReleaseChannel = "stable"
    description: str | None = None

    @field_validator("connector_plugin_ids", "supported_products", mode="before")
    @classmethod
    def _normalize_tuples(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _normalize_non_empty_tuple(value, field_name=str(info.field_name))

    @model_validator(mode="after")
    def _validate_bundle(self) -> OfficialConnectorBundleDefinition:
        if not self.connector_plugin_ids:
            raise ValueError("connector_plugin_ids must contain at least one plugin id")
        if self.support_class != "official":
            raise ValueError("official bundles must use support_class='official'")
        return self


class MarketProfileDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    display_name: str
    market: str
    description: str
    supported_products: tuple[ProductSurface, ...]
    default_bundle_ids: tuple[str, ...] = ()
    recommended_bundle_ids: tuple[str, ...] = ()
    default_connector_plugin_ids: tuple[str, ...] = ()
    recommended_connector_plugin_ids: tuple[str, ...] = ()
    excluded_plugin_families: tuple[PluginFamily, ...] = ()
    out_of_scope_notes: tuple[str, ...] = ()

    @field_validator(
        "supported_products",
        "default_bundle_ids",
        "recommended_bundle_ids",
        "default_connector_plugin_ids",
        "recommended_connector_plugin_ids",
        "excluded_plugin_families",
        "out_of_scope_notes",
        mode="before",
    )
    @classmethod
    def _normalize_tuples(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _normalize_non_empty_tuple(value, field_name=str(info.field_name))


class ReleaseVariantDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_id: str
    display_name: str
    product: ProductSurface
    edition_kind: ReleaseEditionKind
    default_market_profile_id: str
    selectable_market_profile_ids: tuple[str, ...]
    preloaded_bundle_ids: tuple[str, ...] = ()
    optional_bundle_ids: tuple[str, ...] = ()
    release_channel: ReleaseChannel = "stable"
    description: str

    @field_validator(
        "selectable_market_profile_ids",
        "preloaded_bundle_ids",
        "optional_bundle_ids",
        mode="before",
    )
    @classmethod
    def _normalize_tuples(cls, value: Any, info: Any) -> tuple[str, ...]:
        return _normalize_non_empty_tuple(value, field_name=str(info.field_name))

    @model_validator(mode="after")
    def _validate_variant(self) -> ReleaseVariantDefinition:
        if self.default_market_profile_id not in self.selectable_market_profile_ids:
            raise ValueError(
                "default_market_profile_id must be present in selectable_market_profile_ids"
            )
        return self


class ConnectorMarketCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"]
    support_policies: tuple[SupportPolicyDefinition, ...]
    bundles: tuple[OfficialConnectorBundleDefinition, ...]
    profiles: tuple[MarketProfileDefinition, ...]
    release_variants: tuple[ReleaseVariantDefinition, ...]

    @field_validator("support_policies", "bundles", "profiles", "release_variants", mode="before")
    @classmethod
    def _normalize_model_lists(cls, value: Any, info: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"{info.field_name} must be a list or tuple")
        return tuple(value)

    @model_validator(mode="after")
    def _validate_references(self) -> ConnectorMarketCatalog:
        support_classes = [item.support_class for item in self.support_policies]
        if len(support_classes) != len(set(support_classes)):
            raise ValueError("support_policies must use unique support_class values")

        bundle_ids = [item.bundle_id for item in self.bundles]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("bundles must use unique bundle_id values")

        profile_ids = [item.profile_id for item in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("profiles must use unique profile_id values")

        variant_ids = [item.variant_id for item in self.release_variants]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("release_variants must use unique variant_id values")

        bundle_id_set = set(bundle_ids)
        profile_id_set = set(profile_ids)
        variant_id_set = set(variant_ids)
        for profile in self.profiles:
            unknown_default = set(profile.default_bundle_ids) - bundle_id_set
            if unknown_default:
                raise ValueError(
                    f"profile {profile.profile_id} references unknown default_bundle_ids: {sorted(unknown_default)}"
                )
            unknown_recommended = set(profile.recommended_bundle_ids) - bundle_id_set
            if unknown_recommended:
                raise ValueError(
                    "profile "
                    f"{profile.profile_id} references unknown recommended_bundle_ids: {sorted(unknown_recommended)}"
                )
        for variant in self.release_variants:
            if variant.default_market_profile_id not in profile_id_set:
                raise ValueError(
                    "release variant "
                    f"{variant.variant_id} references unknown default_market_profile_id: "
                    f"{variant.default_market_profile_id}"
                )
            unknown_profiles = set(variant.selectable_market_profile_ids) - profile_id_set
            if unknown_profiles:
                raise ValueError(
                    "release variant "
                    f"{variant.variant_id} references unknown selectable_market_profile_ids: "
                    f"{sorted(unknown_profiles)}"
                )
            unknown_preloaded = set(variant.preloaded_bundle_ids) - bundle_id_set
            if unknown_preloaded:
                raise ValueError(
                    "release variant "
                    f"{variant.variant_id} references unknown preloaded_bundle_ids: "
                    f"{sorted(unknown_preloaded)}"
                )
            unknown_optional = set(variant.optional_bundle_ids) - bundle_id_set
            if unknown_optional:
                raise ValueError(
                    "release variant "
                    f"{variant.variant_id} references unknown optional_bundle_ids: "
                    f"{sorted(unknown_optional)}"
                )
        if DEFAULT_MARKET_PROFILE_ID not in profile_id_set:
            raise ValueError(f"default market profile is missing: {DEFAULT_MARKET_PROFILE_ID}")
        if DEFAULT_SELF_HOSTED_RELEASE_VARIANT_ID not in variant_id_set:
            raise ValueError(
                "default self-hosted release variant is missing: "
                f"{DEFAULT_SELF_HOSTED_RELEASE_VARIANT_ID}"
            )
        return self

    def support_policy_for_class(
        self, trust_class: TrustClass | str | None
    ) -> SupportPolicyDefinition | None:
        if trust_class is None:
            return None
        for item in self.support_policies:
            if item.support_class == trust_class:
                return item
        return None

    def bundle_ids_for_plugin(self, plugin_id: str | None) -> tuple[str, ...]:
        if not plugin_id:
            return ()
        return tuple(
            bundle.bundle_id for bundle in self.bundles if plugin_id in bundle.connector_plugin_ids
        )

    def profile_ids_for_plugin(
        self, plugin_id: str | None, *, membership: Literal["default", "recommended"]
    ) -> tuple[str, ...]:
        if not plugin_id:
            return ()
        matched: list[str] = []
        for profile in self.profiles:
            direct_ids = (
                profile.default_connector_plugin_ids
                if membership == "default"
                else profile.recommended_connector_plugin_ids
            )
            bundle_ids = (
                profile.default_bundle_ids
                if membership == "default"
                else profile.recommended_bundle_ids
            )
            if plugin_id in direct_ids:
                matched.append(profile.profile_id)
                continue
            for bundle_id in bundle_ids:
                bundle = self.bundle(bundle_id)
                if bundle is not None and plugin_id in bundle.connector_plugin_ids:
                    matched.append(profile.profile_id)
                    break
        return tuple(matched)

    def profile(self, profile_id: str) -> MarketProfileDefinition | None:
        for profile in self.profiles:
            if profile.profile_id == profile_id:
                return profile
        return None

    def bundle(self, bundle_id: str) -> OfficialConnectorBundleDefinition | None:
        for bundle in self.bundles:
            if bundle.bundle_id == bundle_id:
                return bundle
        return None

    def release_variant(self, variant_id: str) -> ReleaseVariantDefinition | None:
        for variant in self.release_variants:
            if variant.variant_id == variant_id:
                return variant
        return None

    def release_variants_for_product(
        self, product: ProductSurface
    ) -> tuple[ReleaseVariantDefinition, ...]:
        return tuple(variant for variant in self.release_variants if variant.product == product)

    def resolve_profile(
        self,
        *,
        product: ProductSurface,
        requested_profile_id: str | None,
        default_variant_id: str | None,
    ) -> tuple[str | None, MarketProfileDefinition]:
        if requested_profile_id:
            requested = self.profile(requested_profile_id)
            if requested is not None and product in requested.supported_products:
                return requested_profile_id, requested
        variant = self.release_variant(default_variant_id or "")
        if variant is not None:
            default_profile = self.profile(variant.default_market_profile_id)
            if default_profile is not None and product in default_profile.supported_products:
                return requested_profile_id, default_profile
        fallback = self.profile(DEFAULT_MARKET_PROFILE_ID)
        if fallback is None or product not in fallback.supported_products:
            raise ValueError(f"no valid market profile for product {product}")
        return requested_profile_id, fallback


def _catalog_file_path() -> Path:
    return Path(__file__).with_name("official_market_catalog.json")


@lru_cache(maxsize=1)
def get_connector_market_catalog() -> ConnectorMarketCatalog:
    return ConnectorMarketCatalog.model_validate_json(_catalog_file_path().read_text(encoding="utf-8"))


def support_policy_payload(trust_class: TrustClass | str | None) -> dict[str, Any] | None:
    policy = get_connector_market_catalog().support_policy_for_class(trust_class)
    if policy is None:
        return None
    return {
        "support_class": policy.support_class,
        "display_name": policy.display_name,
        "shipping_policy": policy.shipping_policy,
        "ui_label": policy.ui_label,
        "diagnostics_expectation": policy.diagnostics_expectation,
        "update_expectations": policy.update_expectations,
        "maintainer_support": policy.maintainer_support,
    }


def connector_distribution_payload(
    *,
    plugin_id: str | None,
    source_id: str | None,
    trust_class: TrustClass | str | None,
) -> dict[str, Any]:
    catalog = get_connector_market_catalog()
    from lidltool.connectors.connector_catalog import connector_catalog_listing_payload

    catalog_listing = connector_catalog_listing_payload(plugin_id)
    return {
        "plugin_id": plugin_id,
        "source_id": source_id,
        "support_class": trust_class,
        "support_policy": support_policy_payload(trust_class),
        "official_bundle_ids": list(catalog.bundle_ids_for_plugin(plugin_id)),
        "default_market_profile_ids": list(
            catalog.profile_ids_for_plugin(plugin_id, membership="default")
        ),
        "recommended_market_profile_ids": list(
            catalog.profile_ids_for_plugin(plugin_id, membership="recommended")
        ),
        "listed_in_connector_catalog": catalog_listing is not None,
        "catalog_listing": catalog_listing,
    }


def _bundle_payload(bundle: OfficialConnectorBundleDefinition) -> dict[str, Any]:
    return {
        "bundle_id": bundle.bundle_id,
        "display_name": bundle.display_name,
        "market": bundle.market,
        "region": bundle.region,
        "connector_plugin_ids": list(bundle.connector_plugin_ids),
        "supported_products": list(bundle.supported_products),
        "default_state": {
            "self_hosted": bundle.default_state.self_hosted,
            "desktop": bundle.default_state.desktop,
        },
        "support_class": bundle.support_class,
        "support_level": bundle.support_level,
        "release_channel": bundle.release_channel,
        "description": bundle.description,
    }


def _profile_payload(profile: MarketProfileDefinition) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "market": profile.market,
        "description": profile.description,
        "supported_products": list(profile.supported_products),
        "default_bundle_ids": list(profile.default_bundle_ids),
        "recommended_bundle_ids": list(profile.recommended_bundle_ids),
        "default_connector_plugin_ids": list(profile.default_connector_plugin_ids),
        "recommended_connector_plugin_ids": list(profile.recommended_connector_plugin_ids),
        "excluded_plugin_families": list(profile.excluded_plugin_families),
        "out_of_scope_notes": list(profile.out_of_scope_notes),
    }


def _release_variant_payload(variant: ReleaseVariantDefinition) -> dict[str, Any]:
    return {
        "variant_id": variant.variant_id,
        "display_name": variant.display_name,
        "product": variant.product,
        "edition_kind": variant.edition_kind,
        "default_market_profile_id": variant.default_market_profile_id,
        "selectable_market_profile_ids": list(variant.selectable_market_profile_ids),
        "preloaded_bundle_ids": list(variant.preloaded_bundle_ids),
        "optional_bundle_ids": list(variant.optional_bundle_ids),
        "release_channel": variant.release_channel,
        "description": variant.description,
    }


def product_market_strategy_payload(
    *,
    product: ProductSurface,
    requested_profile_id: str | None = None,
    active_release_variant_id: str | None = None,
) -> dict[str, Any]:
    catalog = get_connector_market_catalog()
    default_variant_id = active_release_variant_id
    if default_variant_id is None and product == "self_hosted":
        default_variant_id = DEFAULT_SELF_HOSTED_RELEASE_VARIANT_ID
    _, selected_profile = catalog.resolve_profile(
        product=product,
        requested_profile_id=requested_profile_id,
        default_variant_id=default_variant_id,
    )
    active_variant = (
        catalog.release_variant(active_release_variant_id)
        if active_release_variant_id is not None
        else catalog.release_variant(default_variant_id or "")
    )
    return {
        "schema_version": catalog.schema_version,
        "product": product,
        "requested_market_profile_id": requested_profile_id,
        "selected_market_profile_id": selected_profile.profile_id,
        "selected_market_profile": _profile_payload(selected_profile),
        "active_release_variant_id": active_variant.variant_id if active_variant is not None else None,
        "active_release_variant": (
            _release_variant_payload(active_variant) if active_variant is not None else None
        ),
        "official_bundles": [
            _bundle_payload(bundle)
            for bundle in catalog.bundles
            if product in bundle.supported_products
        ],
        "market_profiles": [
            _profile_payload(profile)
            for profile in catalog.profiles
            if product in profile.supported_products
        ],
        "release_variants": [
            _release_variant_payload(variant)
            for variant in catalog.release_variants_for_product(product)
        ],
        "support_policies": [
            support_policy_payload(item.support_class) for item in catalog.support_policies
        ],
    }


def self_hosted_market_strategy_payload(config: AppConfig | None = None) -> dict[str, Any]:
    requested_profile_id = config.connector_market_profile if config is not None else None
    return product_market_strategy_payload(
        product="self_hosted",
        requested_profile_id=requested_profile_id,
        active_release_variant_id=DEFAULT_SELF_HOSTED_RELEASE_VARIANT_ID,
    )
