import type {
  ConnectorCatalogDiagnostic,
  ConnectorCatalogEntry,
  ConnectorCatalogInstallMethod,
  ConnectorMarketProfile,
  ConnectorProduct,
  ConnectorReleaseVariant,
  ConnectorSupportPolicy,
  ConnectorTrustClass,
  ConnectorVerificationStatus,
  DesktopConnectorCatalog,
  OfficialConnectorBundle
} from "../shared/contracts.ts";

interface MarketCatalogFile {
  support_policies: ConnectorSupportPolicy[];
  bundles: OfficialConnectorBundle[];
  profiles: ConnectorMarketProfile[];
  release_variants: ConnectorReleaseVariant[];
}

export interface RawCatalogRoot {
  schema_version: string;
  catalog_id?: unknown;
  source_kind?: unknown;
  entries?: unknown;
}

type RawRecord = Record<string, unknown>;

function isRecord(value: unknown): value is RawRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(record: RawRecord, field: string): string {
  const value = record[field];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`${field} must be a non-empty string`);
  }
  return value.trim();
}

function asOptionalString(record: RawRecord, field: string): string | null {
  const value = record[field];
  if (value == null) {
    return null;
  }
  if (typeof value !== "string") {
    throw new Error(`${field} must be a string`);
  }
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : null;
}

function asStringArray(record: RawRecord, field: string): string[] {
  const value = record[field];
  if (!Array.isArray(value)) {
    throw new Error(`${field} must be an array`);
  }
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const item of value) {
    if (typeof item !== "string" || item.trim().length === 0) {
      throw new Error(`${field} entries must be non-empty strings`);
    }
    const candidate = item.trim();
    if (seen.has(candidate)) {
      continue;
    }
    seen.add(candidate);
    normalized.push(candidate);
  }
  return normalized;
}

function buildDiagnostic(
  code: string,
  message: string,
  entryId: string | null = null
): ConnectorCatalogDiagnostic {
  return {
    severity: "error",
    code,
    message,
    entry_id: entryId
  };
}

function profileIdsForPlugin(
  marketCatalog: MarketCatalogFile,
  pluginId: string,
  membership: "default" | "recommended"
): string[] {
  const matched: string[] = [];
  for (const profile of marketCatalog.profiles) {
    const directIds =
      membership === "default" ? profile.default_connector_plugin_ids : profile.recommended_connector_plugin_ids;
    const bundleIds = membership === "default" ? profile.default_bundle_ids : profile.recommended_bundle_ids;
    if (directIds.includes(pluginId)) {
      matched.push(profile.profile_id);
      continue;
    }
    for (const bundleId of bundleIds) {
      const bundle = marketCatalog.bundles.find((candidate) => candidate.bundle_id === bundleId);
      if (bundle && bundle.connector_plugin_ids.includes(pluginId)) {
        matched.push(profile.profile_id);
        break;
      }
    }
  }
  return [...new Set(matched)];
}

function releaseVariantIdsForBundle(marketCatalog: MarketCatalogFile, bundleId: string): string[] {
  return marketCatalog.release_variants
    .filter(
      (variant) => variant.preloaded_bundle_ids.includes(bundleId) || variant.optional_bundle_ids.includes(bundleId)
    )
    .map((variant) => variant.variant_id);
}

function parseCatalogEntry(
  rawEntry: RawRecord,
  marketCatalog: MarketCatalogFile
): ConnectorCatalogEntry {
  const entryType = asString(rawEntry, "entry_type");
  const trustClass = asString(rawEntry, "trust_class") as ConnectorTrustClass;
  const supportedProducts = asStringArray(rawEntry, "supported_products") as ConnectorProduct[];
  const installMethods = asStringArray(rawEntry, "install_methods") as ConnectorCatalogInstallMethod[];
  const compatibility = isRecord(rawEntry.compatibility) ? rawEntry.compatibility : {};
  const compatibilityRecord = compatibility as RawRecord;

  if (installMethods.length === 0) {
    throw new Error("install_methods must contain at least one method");
  }
  if (trustClass !== "official" && installMethods.includes("built_in")) {
    throw new Error("non-official catalog entries cannot claim install_methods=['built_in']");
  }
  if (installMethods.includes("download_url") && asOptionalString(rawEntry, "download_url") === null) {
    throw new Error("download_url must be present when install_methods includes 'download_url'");
  }

  const entry: ConnectorCatalogEntry = {
    entry_id: asString(rawEntry, "entry_id"),
    entry_type: entryType as ConnectorCatalogEntry["entry_type"],
    display_name: asString(rawEntry, "display_name"),
    summary: asString(rawEntry, "summary"),
    description: asOptionalString(rawEntry, "description"),
    trust_class: trustClass,
    maintainer: asString(rawEntry, "maintainer"),
    source: asString(rawEntry, "source"),
    supported_products: supportedProducts,
    supported_markets: asStringArray(rawEntry, "supported_markets"),
    current_version: asOptionalString(rawEntry, "current_version"),
    compatibility: {
      min_core_version:
        typeof compatibilityRecord.min_core_version === "string" ? compatibilityRecord.min_core_version : null,
      max_core_version:
        typeof compatibilityRecord.max_core_version === "string" ? compatibilityRecord.max_core_version : null,
      supported_host_kinds: Array.isArray(compatibilityRecord.supported_host_kinds)
        ? compatibilityRecord.supported_host_kinds.filter(
            (value): value is "self_hosted" | "electron" => value === "self_hosted" || value === "electron"
          )
        : [],
      notes: Array.isArray(compatibilityRecord.notes)
        ? compatibilityRecord.notes.filter((value): value is string => typeof value === "string")
        : []
    },
    install_methods: installMethods,
    docs_url: asOptionalString(rawEntry, "docs_url"),
    homepage_url: asOptionalString(rawEntry, "homepage_url"),
    download_url: asOptionalString(rawEntry, "download_url"),
    release_notes_summary: asOptionalString(rawEntry, "release_notes_summary"),
    support_policy: marketCatalog.support_policies.find((policy) => policy.support_class === trustClass) ?? null,
    official_bundle_ids: [],
    market_profile_ids: [],
    release_variant_ids: [],
    availability: {
      catalog_listed: true,
      discovered_locally: false,
      local_status: null,
      enabled_locally: false,
      blocked_by_policy: false,
      block_reason: null,
      officially_bundled: false,
      manual_install_supported: installMethods.includes("manual_import") || installMethods.includes("manual_mount")
    }
  };

  if (entryType === "bundle") {
    const bundleId = asString(rawEntry, "bundle_id");
    const bundle = marketCatalog.bundles.find((candidate) => candidate.bundle_id === bundleId);
    if (!bundle) {
      throw new Error(`bundle_id '${bundleId}' is not defined in the official market catalog`);
    }
    if (bundle.support_class !== trustClass) {
      throw new Error("bundle trust_class must match the official market catalog support_class");
    }
    if (JSON.stringify(bundle.supported_products) !== JSON.stringify(supportedProducts)) {
      throw new Error("bundle supported_products must match the official market catalog supported_products");
    }
    entry.bundle_id = bundleId;
    entry.official_bundle_ids = [bundleId];
    entry.market_profile_ids = marketCatalog.profiles
      .filter(
        (profile) =>
          profile.default_bundle_ids.includes(bundleId) || profile.recommended_bundle_ids.includes(bundleId)
      )
      .map((profile) => profile.profile_id);
    entry.release_variant_ids = releaseVariantIdsForBundle(marketCatalog, bundleId);
    entry.availability.officially_bundled = true;
    return entry;
  }

  const pluginId = asString(rawEntry, "plugin_id");
  const sourceId = asString(rawEntry, "source_id");
  entry.plugin_id = pluginId;
  entry.source_id = sourceId;
  entry.official_bundle_ids = marketCatalog.bundles
    .filter((bundle) => bundle.connector_plugin_ids.includes(pluginId))
    .map((bundle) => bundle.bundle_id);
  entry.market_profile_ids = [
    ...new Set([
      ...profileIdsForPlugin(marketCatalog, pluginId, "default"),
      ...profileIdsForPlugin(marketCatalog, pluginId, "recommended")
    ])
  ];
  entry.release_variant_ids = [
    ...new Set(entry.official_bundle_ids.flatMap((bundleId) => releaseVariantIdsForBundle(marketCatalog, bundleId)))
  ];
  entry.availability.officially_bundled = entry.official_bundle_ids.length > 0;

  if (entryType === "desktop_pack") {
    entry.pack_format = (asOptionalString(rawEntry, "pack_format") ?? "zip") as "zip";
    if (!supportedProducts.includes("desktop")) {
      throw new Error("desktop_pack entries must include 'desktop' in supported_products");
    }
    if (!installMethods.includes("manual_import") && !installMethods.includes("download_url")) {
      throw new Error("desktop_pack entries must support manual_import or download_url");
    }
  }

  return entry;
}

export function loadDesktopConnectorCatalog(
  rawCatalog: unknown,
  marketCatalog: MarketCatalogFile,
  options: {
    catalogId?: string;
    sourceKind?: DesktopConnectorCatalog["source_kind"];
    verificationStatus?: ConnectorVerificationStatus;
    verificationReason?: string | null;
    signedByKeyId?: string | null;
    publishedAt?: string | null;
    diagnostics?: ConnectorCatalogDiagnostic[];
    revokedEntryIds?: ReadonlyMap<string, string>;
    revokedPluginVersions?: ReadonlyMap<string, string>;
  } = {}
): DesktopConnectorCatalog {
  let parsed: RawCatalogRoot;
  try {
    parsed = typeof rawCatalog === "string" ? (JSON.parse(rawCatalog) as RawCatalogRoot) : (rawCatalog as RawCatalogRoot);
  } catch (error) {
    return {
      schema_version: "1",
      catalog_id: options.catalogId ?? "connector_catalog",
      source_kind: options.sourceKind ?? "repo_static",
      verification_status: options.verificationStatus ?? "unsigned",
      verification_reason: options.verificationReason ?? String(error),
      signed_by_key_id: options.signedByKeyId ?? null,
      published_at: options.publishedAt ?? null,
      entries: [],
      diagnostics: [...(options.diagnostics ?? []), buildDiagnostic("catalog_load_failed", String(error))]
    };
  }

  if (parsed.schema_version !== "1" || !Array.isArray(parsed.entries)) {
    return {
      schema_version: "1",
      catalog_id: options.catalogId ?? "connector_catalog",
      source_kind: options.sourceKind ?? "repo_static",
      verification_status: options.verificationStatus ?? "unsigned",
      verification_reason: options.verificationReason ?? "Desktop connector catalog root is invalid.",
      signed_by_key_id: options.signedByKeyId ?? null,
      published_at: options.publishedAt ?? null,
      entries: [],
      diagnostics: [
        ...(options.diagnostics ?? []),
        buildDiagnostic("catalog_root_invalid", "Desktop connector catalog root is invalid.")
      ]
    };
  }

  const diagnostics: ConnectorCatalogDiagnostic[] = [...(options.diagnostics ?? [])];
  const entries: ConnectorCatalogEntry[] = [];
  const seen = new Set<string>();
  for (const rawEntry of parsed.entries) {
    if (!isRecord(rawEntry)) {
      diagnostics.push(buildDiagnostic("catalog_entry_invalid", "Catalog entries must be objects."));
      continue;
    }
    const entryId = typeof rawEntry.entry_id === "string" ? rawEntry.entry_id : null;
    try {
      const entry = parseCatalogEntry(rawEntry, marketCatalog);
      if (seen.has(entry.entry_id)) {
        throw new Error(`duplicate catalog entry_id '${entry.entry_id}'`);
      }
      seen.add(entry.entry_id);
      const revokedEntryReason = options.revokedEntryIds?.get(entry.entry_id) ?? null;
      const revokedPluginReason =
        entry.plugin_id && entry.current_version
          ? options.revokedPluginVersions?.get(`${entry.plugin_id}@${entry.current_version}`) ?? null
          : null;
      if (revokedEntryReason || revokedPluginReason) {
        entry.availability.blocked_by_policy = true;
        entry.availability.block_reason = revokedEntryReason ?? revokedPluginReason;
      }
      entries.push(entry);
    } catch (error) {
      diagnostics.push(buildDiagnostic("catalog_entry_invalid", String(error), entryId));
    }
  }

  return {
    schema_version: "1",
    catalog_id: typeof parsed.catalog_id === "string" && parsed.catalog_id.trim().length > 0
      ? parsed.catalog_id.trim()
      : options.catalogId ?? "connector_catalog",
    source_kind: options.sourceKind ?? (parsed.source_kind === "repo_static" ? "repo_static" : "repo_static"),
    verification_status: options.verificationStatus ?? "unsigned",
    verification_reason: options.verificationReason ?? null,
    signed_by_key_id: options.signedByKeyId ?? null,
    published_at: options.publishedAt ?? null,
    entries,
    diagnostics
  };
}
