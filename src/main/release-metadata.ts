import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type {
  ConnectorMarketProfile,
  ConnectorReleaseVariant,
  ConnectorSupportPolicy,
  DesktopConnectorCatalog,
  DesktopReleaseMetadata,
  OfficialConnectorBundle
} from "../shared/contracts.ts";
import { loadTrustedDesktopCatalog, type TrustedDistributionPolicy } from "./trusted-distribution.ts";

interface MarketCatalogFile {
  schema_version: "1";
  support_policies: ConnectorSupportPolicy[];
  bundles: OfficialConnectorBundle[];
  profiles: ConnectorMarketProfile[];
  release_variants: ConnectorReleaseVariant[];
}

interface ResolveDesktopReleaseMetadataOptions {
  repoRootHint: string;
  requestedReleaseVariantId?: string | null;
  remoteCatalogUrl?: string | null;
  fetchImpl?: typeof fetch;
  trustedCatalogOverride?: unknown;
  trustRootsOverride?: unknown;
}

const DEFAULT_DESKTOP_RELEASE_VARIANT_ID = "desktop_universal_shell";
const CATALOG_PATH_SEGMENTS = ["src", "lidltool", "connectors", "official_market_catalog.json"] as const;

function fallbackSupportPolicies(): ConnectorSupportPolicy[] {
  return [
    {
      support_class: "official",
      display_name: "Official",
      shipping_policy: "Bundled with this desktop release.",
      ui_label: "Official",
      diagnostics_expectation: "Project-maintained desktop path.",
      update_expectations: "Ships with desktop releases.",
      maintainer_support: "Project-maintained."
    },
    {
      support_class: "community_verified",
      display_name: "Community verified",
      shipping_policy: "Signed community pack.",
      ui_label: "Community verified",
      diagnostics_expectation: "Conservative desktop trust checks apply.",
      update_expectations: "Updates depend on catalog availability.",
      maintainer_support: "Best effort by community maintainers."
    },
    {
      support_class: "community_unsigned",
      display_name: "Community unsigned",
      shipping_policy: "Manual import only.",
      ui_label: "Community unsigned",
      diagnostics_expectation: "Desktop keeps trust labeling conservative.",
      update_expectations: "Manual updates only.",
      maintainer_support: "No trusted desktop support guarantee."
    },
    {
      support_class: "local_custom",
      display_name: "Local custom",
      shipping_policy: "Operator supplied local pack.",
      ui_label: "Local custom",
      diagnostics_expectation: "Local validation only.",
      update_expectations: "Operator-managed.",
      maintainer_support: "Local responsibility."
    }
  ];
}

function fallbackVariant(): ConnectorReleaseVariant {
  return {
    variant_id: "desktop_local_shell_recovery",
    display_name: "Local Desktop Shell",
    product: "desktop",
    edition_kind: "universal_shell",
    default_market_profile_id: "desktop_local_only",
    selectable_market_profile_ids: ["desktop_local_only"],
    preloaded_bundle_ids: [],
    optional_bundle_ids: [],
    release_channel: "stable",
    description:
      "Fallback local desktop shell for occasional sync, review, export, backup, and manual receipt plugin tasks."
  };
}

function fallbackProfile(): ConnectorMarketProfile {
  return {
    profile_id: "desktop_local_only",
    display_name: "Local desktop use",
    market: "local",
    description:
      "Local-first desktop mode for occasional receipt sync, review, export, backup, and manual plugin management.",
    supported_products: ["desktop"],
    default_bundle_ids: [],
    recommended_bundle_ids: [],
    default_connector_plugin_ids: [],
    recommended_connector_plugin_ids: [],
    excluded_plugin_families: ["offer"],
    out_of_scope_notes: [
      "Always-on offer scraping, watchlists, and alerts stay in the self-hosted product."
    ]
  };
}

function fallbackTrustPolicy(): TrustedDistributionPolicy {
  return {
    rootKeys: [],
    blockedKeyIds: new Map(),
    blockedArchiveSha256: new Map(),
    revokedPluginVersions: new Map(),
    revokedEntryIds: new Map()
  };
}

function buildFallbackCatalog(reason: string): DesktopConnectorCatalog {
  return {
    schema_version: "1",
    catalog_id: "desktop-fallback-catalog",
    source_kind: "repo_static",
    verification_status: "unsigned",
    verification_reason: reason,
    signed_by_key_id: null,
    published_at: null,
    entries: [],
    diagnostics: [
      {
        severity: "error",
        code: "desktop_release_metadata_unavailable",
        message: reason,
        entry_id: null
      }
    ]
  };
}

function buildFallbackReleaseContext(
  options: ResolveDesktopReleaseMetadataOptions,
  reason: string
): DesktopReleaseContext {
  const variant = fallbackVariant();
  const profile = fallbackProfile();
  const supportPolicies = fallbackSupportPolicies();
  return {
    metadata: {
      schema_version: "1",
      product: "desktop",
      requested_release_variant_id: options.requestedReleaseVariantId ?? null,
      active_release_variant_id: variant.variant_id,
      active_release_variant: variant,
      requested_market_profile_id: profile.profile_id,
      selected_market_profile_id: profile.profile_id,
      selected_market_profile: profile,
      official_bundles: [],
      market_profiles: [profile],
      release_variants: [variant],
      support_policies: supportPolicies,
      discovery_catalog: buildFallbackCatalog(reason),
      supports_optional_receipt_packs: true
    },
    trustPolicy: fallbackTrustPolicy()
  };
}

function loadCatalog(repoRootHint: string): MarketCatalogFile {
  const catalogPath = join(repoRootHint, ...CATALOG_PATH_SEGMENTS);
  if (!existsSync(catalogPath)) {
    throw new Error(`Desktop market catalog not found at ${catalogPath}`);
  }
  return JSON.parse(readFileSync(catalogPath, "utf-8")) as MarketCatalogFile;
}

function resolveDesktopVariant(
  variants: ConnectorReleaseVariant[],
  requestedReleaseVariantId?: string | null
): ConnectorReleaseVariant {
  const desktopVariants = variants.filter((variant) => variant.product === "desktop");
  if (desktopVariants.length === 0) {
    throw new Error("Desktop market catalog does not define any desktop release variants.");
  }
  if (requestedReleaseVariantId) {
    const requested = desktopVariants.find((variant) => variant.variant_id === requestedReleaseVariantId);
    if (requested) {
      return requested;
    }
  }
  return (
    desktopVariants.find((variant) => variant.variant_id === DEFAULT_DESKTOP_RELEASE_VARIANT_ID) ??
    desktopVariants[0]
  );
}

function resolveDesktopProfile(
  profiles: ConnectorMarketProfile[],
  variant: ConnectorReleaseVariant
): ConnectorMarketProfile {
  const profile = profiles.find(
    (candidate) =>
      candidate.profile_id === variant.default_market_profile_id &&
      candidate.supported_products.includes("desktop")
  );
  if (!profile) {
    throw new Error(
      `Desktop release variant ${variant.variant_id} references an unsupported market profile: ${variant.default_market_profile_id}`
    );
  }
  return profile;
}

export interface DesktopReleaseContext {
  metadata: DesktopReleaseMetadata;
  trustPolicy: TrustedDistributionPolicy;
}

export async function resolveDesktopReleaseContext(
  options: ResolveDesktopReleaseMetadataOptions
): Promise<DesktopReleaseContext> {
  try {
    const catalog = loadCatalog(options.repoRootHint);
    const activeVariant = resolveDesktopVariant(catalog.release_variants, options.requestedReleaseVariantId);
    const selectedProfile = resolveDesktopProfile(catalog.profiles, activeVariant);
    const trustedCatalog = await loadTrustedDesktopCatalog({
      marketCatalog: catalog,
      remoteCatalogUrl: options.remoteCatalogUrl,
      fetchImpl: options.fetchImpl,
      bundledEnvelopeOverride: options.trustedCatalogOverride,
      trustRootsOverride: options.trustRootsOverride
    });

    return {
      metadata: {
        schema_version: catalog.schema_version,
        product: "desktop",
        requested_release_variant_id: options.requestedReleaseVariantId ?? null,
        active_release_variant_id: activeVariant.variant_id,
        active_release_variant: activeVariant,
        requested_market_profile_id: selectedProfile.profile_id,
        selected_market_profile_id: selectedProfile.profile_id,
        selected_market_profile: selectedProfile,
        official_bundles: catalog.bundles.filter((bundle) => bundle.supported_products.includes("desktop")),
        market_profiles: catalog.profiles.filter((profile) => profile.supported_products.includes("desktop")),
        release_variants: catalog.release_variants.filter((variant) => variant.product === "desktop"),
        support_policies: catalog.support_policies,
        discovery_catalog: {
          ...trustedCatalog.catalog,
          entries: trustedCatalog.catalog.entries.filter((entry) => entry.supported_products.includes("desktop"))
        },
        supports_optional_receipt_packs: true
      },
      trustPolicy: trustedCatalog.trustPolicy
    };
  } catch (error) {
    return buildFallbackReleaseContext(
      options,
      `Desktop release metadata is unavailable. ${String(error)} Manual receipt pack import still works with conservative trust labels.`
    );
  }
}

export async function resolveDesktopReleaseMetadata(
  options: ResolveDesktopReleaseMetadataOptions
): Promise<DesktopReleaseMetadata> {
  return (await resolveDesktopReleaseContext(options)).metadata;
}
