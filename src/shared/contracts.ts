export type SyncSourceId = "lidl" | "amazon" | "rewe" | "kaufland" | "dm" | "rossmann";
export type DesktopLocale = "en" | "de";
export type ConnectorTrustClass = "official" | "community_verified" | "community_unsigned" | "local_custom";
export type ConnectorProduct = "self_hosted" | "desktop";
export type ConnectorBundleState = "enabled" | "available" | "disabled";
export type ConnectorReleaseChannel = "stable" | "preview" | "experimental";
export type ConnectorReleaseEditionKind = "universal_shell" | "regional_edition";
export type ConnectorCatalogEntryType = "connector" | "bundle" | "desktop_pack";
export type ConnectorCatalogInstallMethod = "built_in" | "manual_import" | "manual_mount" | "download_url";
export type ConnectorCatalogSourceKind = "bundled_signed" | "remote_signed" | "repo_static";
export type ConnectorVerificationStatus = "trusted" | "unsigned" | "signature_invalid" | "revoked" | "incompatible";

export type ConnectorSourceId = Exclude<SyncSourceId, "lidl">;

export interface BackendConfig {
  apiBaseUrl: string;
  dbPath: string;
  userDataDir: string;
  receiptPluginStorageDir: string;
}

export interface BackendStatus {
  running: boolean;
  pid: number | null;
  startedAt: string | null;
  command: string;
}

export type DesktopRuntimeEnvironment = "development" | "packaged";
export type DesktopRuntimeAssetStatus = "ready" | "missing" | "lookup";
export type DesktopBackendCommandSource = "env_override" | "bundled" | "managed_dev" | "path_lookup";

export interface DesktopRuntimeDiagnostics {
  environment: DesktopRuntimeEnvironment;
  fullAppReady: boolean;
  frontendDistPath: string;
  frontendDistStatus: DesktopRuntimeAssetStatus;
  backendSourcePath: string;
  backendSourceStatus: DesktopRuntimeAssetStatus;
  backendCommand: string;
  backendCommandSource: DesktopBackendCommandSource;
  backendCommandStatus: DesktopRuntimeAssetStatus;
}

export interface CommandResult {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
}

export interface SyncRequest {
  source: SyncSourceId;
  full?: boolean;
  headless?: boolean;
  years?: number;
  maxPages?: number;
  domain?: string;
}

export interface ExportRequest {
  outPath: string;
  format?: "json";
}

export interface BackupRequest {
  outDir: string;
  includeExportJson?: boolean;
  includeDocuments?: boolean;
}

export interface ImportRequest {
  backupDir: string;
  includeDocuments?: boolean;
  includeToken?: boolean;
  includeCredentialKey?: boolean;
  restartBackend?: boolean;
}

export interface CommandLogEvent {
  timestamp: string;
  stream: "stdout" | "stderr";
  line: string;
  source: "backend" | "sync" | "export" | "backup" | "restore";
}

export type ReceiptPluginPackStatus = "enabled" | "disabled" | "invalid" | "incompatible" | "revoked";
export type ReceiptPluginIntegrityStatus = "verified" | "failed";
export type ReceiptPluginSignatureStatus = "unsigned" | "verified" | "signature_invalid" | "revoked";
export type ReceiptPluginCompatibilityStatus = "compatible" | "incompatible" | "invalid";
export type ReceiptPluginInstallSource = "manual_file" | "catalog_url";

export interface ReceiptPluginPackInfo {
  pluginId: string;
  sourceId: string;
  displayName: string;
  version: string;
  pluginFamily: "receipt";
  runtimeKind: string;
  pluginOrigin: string;
  trustClass: string;
  enabled: boolean;
  status: ReceiptPluginPackStatus;
  installPath: string;
  manifestPath: string;
  runtimeRoot: string;
  importedFileName: string;
  importedFromPath: string;
  installedAt: string;
  updatedAt: string;
  archiveSha256: string;
  integrityStatus: ReceiptPluginIntegrityStatus;
  signatureStatus: ReceiptPluginSignatureStatus;
  trustStatus: ConnectorVerificationStatus;
  trustReason: string | null;
  signingKeyId: string | null;
  compatibilityStatus: ReceiptPluginCompatibilityStatus;
  compatibilityReason: string | null;
  installedVia: ReceiptPluginInstallSource;
  catalogEntryId: string | null;
  catalogDownloadUrl: string | null;
  diagnostics: string[];
}

export interface ReceiptPluginPackListResult {
  storageDir: string;
  urlInstallSupported: boolean;
  activePluginSearchPaths: string[];
  packs: ReceiptPluginPackInfo[];
}

export interface ReceiptPluginPackInstallResult {
  action: "installed" | "updated" | "reinstalled";
  pack: ReceiptPluginPackInfo;
  restartedBackend: boolean;
  backendStatus: BackendStatus | null;
}

export interface ReceiptPluginPackToggleResult {
  pack: ReceiptPluginPackInfo;
  restartedBackend: boolean;
  backendStatus: BackendStatus | null;
}

export interface ReceiptPluginPackUninstallResult {
  pluginId: string;
  removedPath: string | null;
  restartedBackend: boolean;
  backendStatus: BackendStatus | null;
}

export interface ReceiptPluginCatalogInstallRequest {
  entryId: string;
}

export interface ConnectorSupportPolicy {
  support_class: ConnectorTrustClass;
  display_name: string;
  shipping_policy: string;
  ui_label: string;
  diagnostics_expectation: string;
  update_expectations: string;
  maintainer_support: string;
}

export interface OfficialConnectorBundle {
  bundle_id: string;
  display_name: string;
  market: string;
  region: string | null;
  connector_plugin_ids: string[];
  supported_products: ConnectorProduct[];
  default_state: {
    self_hosted: ConnectorBundleState;
    desktop: ConnectorBundleState;
  };
  support_class: ConnectorTrustClass;
  support_level: string;
  release_channel: ConnectorReleaseChannel;
  description: string | null;
}

export interface ConnectorMarketProfile {
  profile_id: string;
  display_name: string;
  market: string;
  description: string;
  supported_products: ConnectorProduct[];
  default_bundle_ids: string[];
  recommended_bundle_ids: string[];
  default_connector_plugin_ids: string[];
  recommended_connector_plugin_ids: string[];
  excluded_plugin_families: string[];
  out_of_scope_notes: string[];
}

export interface ConnectorReleaseVariant {
  variant_id: string;
  display_name: string;
  product: ConnectorProduct;
  edition_kind: ConnectorReleaseEditionKind;
  default_market_profile_id: string;
  selectable_market_profile_ids: string[];
  preloaded_bundle_ids: string[];
  optional_bundle_ids: string[];
  release_channel: ConnectorReleaseChannel;
  description: string;
}

export interface ConnectorCatalogCompatibility {
  min_core_version: string | null;
  max_core_version: string | null;
  supported_host_kinds: Array<"self_hosted" | "electron">;
  notes: string[];
}

export interface ConnectorCatalogAvailability {
  catalog_listed: boolean;
  discovered_locally: boolean;
  local_status: string | null;
  enabled_locally: boolean;
  blocked_by_policy: boolean;
  block_reason: string | null;
  officially_bundled: boolean;
  manual_install_supported: boolean;
}

export interface ConnectorCatalogEntry {
  entry_id: string;
  entry_type: ConnectorCatalogEntryType;
  display_name: string;
  summary: string;
  description: string | null;
  trust_class: ConnectorTrustClass;
  maintainer: string;
  source: string;
  supported_products: ConnectorProduct[];
  supported_markets: string[];
  current_version: string | null;
  compatibility: ConnectorCatalogCompatibility;
  install_methods: ConnectorCatalogInstallMethod[];
  docs_url: string | null;
  homepage_url: string | null;
  download_url: string | null;
  release_notes_summary: string | null;
  support_policy: ConnectorSupportPolicy | null;
  official_bundle_ids: string[];
  market_profile_ids: string[];
  release_variant_ids: string[];
  availability: ConnectorCatalogAvailability;
  bundle_id?: string;
  plugin_id?: string;
  source_id?: string;
  pack_format?: "zip";
}

export interface ConnectorCatalogDiagnostic {
  severity: "error";
  code: string;
  message: string;
  entry_id: string | null;
}

export interface DesktopConnectorCatalog {
  schema_version: "1";
  catalog_id: string;
  source_kind: ConnectorCatalogSourceKind;
  verification_status: ConnectorVerificationStatus;
  verification_reason: string | null;
  signed_by_key_id: string | null;
  published_at: string | null;
  entries: ConnectorCatalogEntry[];
  diagnostics: ConnectorCatalogDiagnostic[];
}

export interface DesktopReleaseMetadata {
  schema_version: "1";
  product: "desktop";
  requested_release_variant_id: string | null;
  active_release_variant_id: string;
  active_release_variant: ConnectorReleaseVariant;
  requested_market_profile_id: string | null;
  selected_market_profile_id: string;
  selected_market_profile: ConnectorMarketProfile;
  official_bundles: OfficialConnectorBundle[];
  market_profiles: ConnectorMarketProfile[];
  release_variants: ConnectorReleaseVariant[];
  support_policies: ConnectorSupportPolicy[];
  discovery_catalog: DesktopConnectorCatalog;
  supports_optional_receipt_packs: boolean;
}
