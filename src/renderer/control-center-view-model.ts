import type {
  ConnectorCatalogEntry,
  DesktopReleaseMetadata,
  ReceiptPluginPackInfo
} from "../shared/contracts.ts";
import type { DesktopLocale } from "../i18n/index.ts";
import type { StatusDescriptor } from "./control-center-model.ts";
import {
  catalogProfileSummary,
  catalogSupportSummary,
  compareVersions,
  describeCatalogEntry,
  describeInstalledPack,
  findCatalogDesktopPackEntry,
  formatInstallMethods,
  formatPluginTrust,
  formatTrustClassLabel,
  packInstallSource,
  packOriginSummary,
  packSupportSummary
} from "./control-center-model.ts";

export type SyncSourceOption = {
  id: string;
  label: string;
  defaultDomain?: string;
  syncFamily: "lidl_plus" | "amazon" | "browser" | "generic";
};

export type InstalledPackRow = {
  pack: ReceiptPluginPackInfo;
  catalogEntry: ConnectorCatalogEntry | null;
  packStatus: StatusDescriptor;
  updateTarget: ConnectorCatalogEntry | null;
  trustLabel: string;
  supportLabel: string;
  installSourceLabel: string;
  originSummary: string;
  supportSummary: string;
  profileSummary: string | null;
};

export type TrustedPackRow = {
  entry: ConnectorCatalogEntry;
  installedPack: ReceiptPluginPackInfo | null;
  availability: StatusDescriptor;
  updateAvailable: boolean;
  trustedUrlInstallAllowed: boolean;
  entryTypeLabel: string;
  installMethodsLabel: string;
  supportLabel: string;
  supportSummary: string;
  profileSummary: string;
};

export type ControlCenterViewModel = {
  sourceOptions: SyncSourceOption[];
  defaultBundleLabels: string[];
  recommendedBundleLabels: string[];
  installedEnabledCount: number;
  installedPackRows: InstalledPackRow[];
  trustedPackRows: TrustedPackRow[];
};

const DEFAULT_SOURCE_OPTIONS: SyncSourceOption[] = [
  { id: "lidl_plus_de", label: "Lidl Plus (DE)", syncFamily: "lidl_plus" },
  { id: "lidl_plus_gb", label: "Lidl Plus (GB)", syncFamily: "lidl_plus" },
  { id: "lidl_plus_fr", label: "Lidl Plus (FR)", syncFamily: "lidl_plus" },
  { id: "amazon_de", label: "Amazon (DE)", defaultDomain: "amazon.de", syncFamily: "amazon" },
  { id: "amazon_fr", label: "Amazon (FR)", defaultDomain: "amazon.fr", syncFamily: "amazon" },
  { id: "amazon_gb", label: "Amazon (UK)", defaultDomain: "amazon.co.uk", syncFamily: "amazon" },
  { id: "kaufland_de", label: "Kaufland (DE)", defaultDomain: "www.kaufland.de", syncFamily: "browser" },
  { id: "dm_de", label: "dm (DE)", defaultDomain: "www.dm.de", syncFamily: "browser" }
];

function sourceLabelFromId(sourceId: string, displayName?: string, supportedMarkets?: string[]): string {
  const rawMarket = supportedMarkets?.[0] ?? sourceId.split("_").at(-1)?.toUpperCase();
  const market = rawMarket === "GB" ? "UK" : rawMarket;
  if (displayName && market) {
    return `${displayName} (${market})`;
  }
  if (displayName) {
    return displayName;
  }
  return sourceId;
}

function defaultDomainForSource(sourceId: string): string | undefined {
  switch (sourceId) {
    case "amazon_de":
      return "amazon.de";
    case "amazon_fr":
      return "amazon.fr";
    case "amazon_gb":
      return "amazon.co.uk";
    case "rewe_de":
      return "shop.rewe.de";
    case "kaufland_de":
      return "www.kaufland.de";
    case "dm_de":
      return "www.dm.de";
    default:
      return undefined;
  }
}

function syncFamilyForSource(sourceId: string): SyncSourceOption["syncFamily"] {
  if (sourceId.startsWith("lidl_plus_")) {
    return "lidl_plus";
  }
  if (sourceId.startsWith("amazon_")) {
    return "amazon";
  }
  if (["rewe_de", "kaufland_de", "dm_de"].includes(sourceId)) {
    return "browser";
  }
  return "generic";
}

function buildSyncSourceOptions(
  releaseMetadata: DesktopReleaseMetadata | null,
  pluginPacks: ReceiptPluginPackInfo[]
): SyncSourceOption[] {
  const byId = new Map<string, SyncSourceOption>();
  for (const option of DEFAULT_SOURCE_OPTIONS) {
    byId.set(option.id, option);
  }

  for (const entry of releaseMetadata?.discovery_catalog.entries ?? []) {
    if (entry.entry_type !== "connector" || !entry.source_id) {
      continue;
    }
    byId.set(entry.source_id, {
      id: entry.source_id,
      label: sourceLabelFromId(entry.source_id, entry.display_name, entry.supported_markets),
      defaultDomain: defaultDomainForSource(entry.source_id),
      syncFamily: syncFamilyForSource(entry.source_id)
    });
  }

  for (const pack of pluginPacks) {
    if (pack.status !== "enabled") {
      continue;
    }
    byId.set(pack.sourceId, {
      id: pack.sourceId,
      label: sourceLabelFromId(pack.sourceId, pack.displayName),
      defaultDomain: defaultDomainForSource(pack.sourceId),
      syncFamily: syncFamilyForSource(pack.sourceId)
    });
  }

  return Array.from(byId.values()).sort((left, right) => left.label.localeCompare(right.label));
}

function bundleLabelsForIds(releaseMetadata: DesktopReleaseMetadata | null, bundleIds: string[]): string[] {
  if (!releaseMetadata) {
    return [];
  }
  const labelsByBundleId = new Map(
    releaseMetadata.official_bundles.map((bundle) => [bundle.bundle_id, bundle.display_name] as const)
  );
  return bundleIds.map((bundleId) => labelsByBundleId.get(bundleId) ?? bundleId);
}

function formatCatalogEntryType(
  entryType: ConnectorCatalogEntry["entry_type"],
  locale: DesktopLocale
): string {
  if (entryType === "bundle") {
    return locale === "de" ? "Bundle" : "Bundle";
  }
  if (entryType === "desktop_pack") {
    return locale === "de" ? "Belegpaket" : "Receipt pack";
  }
  return locale === "de" ? "Anbindung" : "Connector";
}

export function buildControlCenterViewModel(
  releaseMetadata: DesktopReleaseMetadata | null,
  pluginPacks: ReceiptPluginPackInfo[],
  locale: DesktopLocale
): ControlCenterViewModel {
  const sourceOptions = buildSyncSourceOptions(releaseMetadata, pluginPacks);
  const trustedPackEntries = (releaseMetadata?.discovery_catalog.entries ?? []).filter(
    (entry): entry is ConnectorCatalogEntry => entry.entry_type === "desktop_pack"
  );
  const installedPackByPluginId = new Map(pluginPacks.map((pack) => [pack.pluginId, pack] as const));
  const installedPackRows = pluginPacks.map((pack) => {
    const catalogEntry = releaseMetadata
      ? findCatalogDesktopPackEntry(releaseMetadata.discovery_catalog.entries, pack.pluginId)
      : null;
    const updateTarget =
      catalogEntry &&
      catalogEntry.current_version &&
      compareVersions(pack.version, catalogEntry.current_version) < 0 &&
      !catalogEntry.availability.blocked_by_policy
        ? catalogEntry
        : null;

    return {
      pack,
      catalogEntry,
      packStatus: describeInstalledPack(pack, locale),
      updateTarget,
      trustLabel: formatPluginTrust(pack, locale),
      supportLabel: formatTrustClassLabel(pack.trustClass, locale),
      installSourceLabel: packInstallSource(pack, locale),
      originSummary: packOriginSummary(pack, locale),
      supportSummary: packSupportSummary(pack, catalogEntry, locale),
      profileSummary: catalogEntry ? catalogProfileSummary(catalogEntry, releaseMetadata, locale) : null
    };
  });
  const trustedPackRows = trustedPackEntries.map((entry) => {
    const installedPack = entry.plugin_id ? (installedPackByPluginId.get(entry.plugin_id) ?? null) : null;
    return {
      entry,
      installedPack,
      availability: describeCatalogEntry(entry, installedPack, locale),
      updateAvailable:
        installedPack !== null &&
        entry.current_version !== null &&
        compareVersions(installedPack.version, entry.current_version) < 0,
      trustedUrlInstallAllowed:
        releaseMetadata?.discovery_catalog.verification_status === "trusted" &&
        entry.install_methods.includes("download_url") &&
        !entry.availability.blocked_by_policy,
      entryTypeLabel: formatCatalogEntryType(entry.entry_type, locale),
      installMethodsLabel: formatInstallMethods(entry.install_methods, locale),
      supportLabel: formatTrustClassLabel(entry.trust_class, locale),
      supportSummary: catalogSupportSummary(entry, locale),
      profileSummary: catalogProfileSummary(entry, releaseMetadata, locale)
    };
  });

  return {
    sourceOptions,
    defaultBundleLabels: bundleLabelsForIds(
      releaseMetadata,
      releaseMetadata?.selected_market_profile.default_bundle_ids ?? []
    ),
    recommendedBundleLabels: bundleLabelsForIds(
      releaseMetadata,
      releaseMetadata?.selected_market_profile.recommended_bundle_ids ?? []
    ),
    installedEnabledCount: pluginPacks.filter((pack) => pack.status === "enabled").length,
    installedPackRows,
    trustedPackRows
  };
}
