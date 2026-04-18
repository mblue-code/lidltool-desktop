import { useEffect, useMemo, useState } from "react";

import type {
  BackupRequest,
  BackendConfig,
  BackendStatus,
  CommandLogEvent,
  CommandResult,
  DesktopRuntimeDiagnostics,
  ExportRequest,
  ImportRequest,
  ReceiptPluginPackInfo,
  SyncRequest,
  SyncSourceId
} from "@shared/contracts";
import { useDesktopI18n } from "./i18n";
import {
  catalogProfileSummary,
  catalogSupportSummary,
  compareVersions,
  describeBackendCommand,
  describeCatalogEntry,
  describeControlCenterMode,
  describeInstalledPack,
  findCatalogDesktopPackEntry,
  formatCatalogEntryType,
  formatCatalogVerification,
  formatEditionKind,
  formatInstallMethods,
  formatPluginTrust,
  formatTrustClassLabel,
  packInstallSource,
  packOriginSummary,
  packSupportSummary
} from "./control-center-model";

type SyncSourceOption = {
  id: SyncSourceId;
  label: string;
  defaultDomain?: string;
  syncFamily: "lidl_plus" | "amazon" | "browser" | "generic";
};

const DEFAULT_SOURCE_OPTIONS: SyncSourceOption[] = [
  { id: "lidl_plus_de", label: "Lidl Plus (DE)", syncFamily: "lidl_plus" },
  { id: "lidl_plus_gb", label: "Lidl Plus (GB)", syncFamily: "lidl_plus" },
  { id: "lidl_plus_fr", label: "Lidl Plus (FR)", syncFamily: "lidl_plus" },
  { id: "amazon_de", label: "Amazon (DE)", defaultDomain: "amazon.de", syncFamily: "amazon" },
  { id: "amazon_fr", label: "Amazon (FR)", defaultDomain: "amazon.fr", syncFamily: "amazon" },
  { id: "amazon_gb", label: "Amazon (UK)", defaultDomain: "amazon.co.uk", syncFamily: "amazon" },
  { id: "rewe_de", label: "REWE (DE)", defaultDomain: "shop.rewe.de", syncFamily: "browser" },
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
  releaseMetadata: Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>> | null,
  pluginPacks: ReceiptPluginPackInfo[]
): SyncSourceOption[] {
  const byId = new Map<string, SyncSourceOption>();
  for (const option of DEFAULT_SOURCE_OPTIONS) {
    byId.set(option.id, option);
  }

  for (const entry of releaseMetadata?.discovery_catalog.entries ?? []) {
    if (entry.entry_type !== "connector" || !entry.supported_products.includes("desktop") || !entry.source_id) {
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
    if (!pack.enabled || pack.status !== "enabled") {
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

function defaultYearMonth(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function defaultExportPath(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  const stamp = new Date().toISOString().replaceAll(":", "-");
  return `${trimmed}${separator}exports${separator}receipts-${stamp}.json`;
}

function defaultBackupDir(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  const stamp = new Date().toISOString().replaceAll(":", "-");
  return `${trimmed}${separator}backups${separator}backup-${stamp}`;
}

function defaultImportDir(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  return `${trimmed}${separator}backups`;
}

function bundleLabelsForIds(
  releaseMetadata: NonNullable<Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>>> | null,
  bundleIds: string[]
): string[] {
  if (!releaseMetadata) {
    return [];
  }
  return bundleIds.map((bundleId) => {
    const match = releaseMetadata.official_bundles.find((bundle) => bundle.bundle_id === bundleId);
    return match?.display_name ?? bundleId;
  });
}

function sourceJourneySummary(source: SyncSourceId): string {
  if (source.startsWith("lidl_plus_")) {
    return "Use the built-in Lidl path when you just want a one-off local refresh of recent or full receipt history.";
  }
  if (source.startsWith("amazon_")) {
    return "Amazon sync uses the saved desktop session for the selected market and can scan multiple years when you need a broader local import.";
  }
  return "Use a receipt pack when you want an occasional local sync for another retailer, then review or export the results on this computer.";
}

function sourceSyncNotice(source: SyncSourceId, locale: string): string | null {
  if (source !== "dm_de") {
    return null;
  }
  if (locale === "de") {
    return "dm-Syncs können sichtbar länger dauern. Die Desktop-App hält dabei absichtliche Wartephasen ein, damit Login, Session und Detailseiten stabil bleiben.";
  }
  return "dm sync can take noticeably longer. The desktop app keeps intentional wait phases so login, session refresh, and receipt detail pages stay stable.";
}

export default function App() {
  const { locale, setLocale, t } = useDesktopI18n();
  const [{ year, month }] = useState(defaultYearMonth);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [backend, setBackend] = useState<BackendStatus | null>(null);
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState<DesktopRuntimeDiagnostics | null>(null);
  const [releaseMetadata, setReleaseMetadata] = useState<Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>> | null>(null);
  const [releaseMetadataError, setReleaseMetadataError] = useState<string | null>(null);
  const [pluginLoadError, setPluginLoadError] = useState<string | null>(null);
  const [source, setSource] = useState<SyncSourceId>("lidl_plus_de");
  const [fullSync, setFullSync] = useState(false);
  const [headless, setHeadless] = useState(true);
  const [domain, setDomain] = useState("");
  const [years, setYears] = useState(2);
  const [maxPages, setMaxPages] = useState(8);
  const [busy, setBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<CommandResult | null>(null);
  const [exportResult, setExportResult] = useState<CommandResult | null>(null);
  const [exportOutPath, setExportOutPath] = useState("");
  const [backupResult, setBackupResult] = useState<CommandResult | null>(null);
  const [backupOutDir, setBackupOutDir] = useState("");
  const [backupIncludeExportJson, setBackupIncludeExportJson] = useState(true);
  const [backupIncludeDocuments, setBackupIncludeDocuments] = useState(true);
  const [importResult, setImportResult] = useState<CommandResult | null>(null);
  const [importBackupDir, setImportBackupDir] = useState("");
  const [importIncludeDocuments, setImportIncludeDocuments] = useState(true);
  const [importIncludeToken, setImportIncludeToken] = useState(true);
  const [importIncludeCredentialKey, setImportIncludeCredentialKey] = useState(true);
  const [importRestartBackend, setImportRestartBackend] = useState(true);
  const [pluginPacks, setPluginPacks] = useState<ReceiptPluginPackInfo[]>([]);
  const [pluginSearchPaths, setPluginSearchPaths] = useState<string[]>([]);
  const [pluginStatusMessage, setPluginStatusMessage] = useState<string | null>(null);
  const [cardsResult, setCardsResult] = useState<unknown>(null);
  const [logs, setLogs] = useState<CommandLogEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const sourceOptions = useMemo(
    () => buildSyncSourceOptions(releaseMetadata, pluginPacks),
    [pluginPacks, releaseMetadata]
  );
  const selectedSourceMeta = useMemo(() => sourceOptions.find((option) => option.id === source), [source, sourceOptions]);

  const backendStatusText = useMemo(() => {
    if (!backend) {
      return t("shell.backend.status.loading");
    }
    if (backend.running) {
      return t("shell.backend.status.running", { pid: backend.pid ?? "n/a" });
    }
    return t("shell.backend.status.stopped");
  }, [backend, t]);

  const controlCenterMode = useMemo(
    () => describeControlCenterMode(bootError, runtimeDiagnostics),
    [bootError, runtimeDiagnostics]
  );

  const curatedDesktopEntries = useMemo(
    () => releaseMetadata?.discovery_catalog.entries ?? [],
    [releaseMetadata]
  );
  const curatedDesktopPackEntries = useMemo(
    () => curatedDesktopEntries.filter((entry) => entry.entry_type === "desktop_pack"),
    [curatedDesktopEntries]
  );
  const defaultBundleLabels = useMemo(
    () => bundleLabelsForIds(releaseMetadata, releaseMetadata?.selected_market_profile.default_bundle_ids ?? []),
    [releaseMetadata]
  );
  const recommendedBundleLabels = useMemo(
    () => bundleLabelsForIds(releaseMetadata, releaseMetadata?.selected_market_profile.recommended_bundle_ids ?? []),
    [releaseMetadata]
  );
  const installedEnabledCount = useMemo(
    () => pluginPacks.filter((pack) => pack.status === "enabled").length,
    [pluginPacks]
  );

  useEffect(() => {
    let disposeLogs: (() => void) | null = null;
    let disposeBootError: (() => void) | null = null;

    async function boot(): Promise<void> {
      const results = await Promise.allSettled([
        window.desktopApi.getConfig(),
        window.desktopApi.getBootError(),
        window.desktopApi.getBackendStatus(),
        window.desktopApi.getRuntimeDiagnostics(),
        window.desktopApi.listReceiptPlugins(),
        window.desktopApi.getReleaseMetadata()
      ]);

      const [cfgResult, bootErrorResult, statusResult, runtimeResult, receiptPluginsResult, metadataResult] = results;

      if (cfgResult.status === "fulfilled") {
        setConfig(cfgResult.value);
      } else {
        setError(t("shell.error.desktopApiInit", { detail: String(cfgResult.reason) }));
      }

      if (bootErrorResult.status === "fulfilled") {
        setBootError(bootErrorResult.value);
      }

      if (statusResult.status === "fulfilled") {
        setBackend(statusResult.value);
      }

      if (runtimeResult.status === "fulfilled") {
        setRuntimeDiagnostics(runtimeResult.value);
      }

      if (receiptPluginsResult.status === "fulfilled") {
        setPluginPacks(receiptPluginsResult.value.packs);
        setPluginSearchPaths(receiptPluginsResult.value.activePluginSearchPaths);
        setPluginLoadError(null);
      } else {
        setPluginLoadError(String(receiptPluginsResult.reason));
      }

      if (metadataResult.status === "fulfilled") {
        setReleaseMetadata(metadataResult.value);
        setReleaseMetadataError(null);
      } else {
        setReleaseMetadataError(String(metadataResult.reason));
      }

      disposeLogs = window.desktopApi.onLog((event) => {
        setLogs((prev) => [...prev.slice(-399), event]);
      });
      disposeBootError = window.desktopApi.onBootError((message) => {
        setBootError(message);
      });
    }

    void boot();

    return () => {
      disposeLogs?.();
      disposeBootError?.();
    };
  }, [t]);

  useEffect(() => {
    const nextDomain = selectedSourceMeta?.defaultDomain ?? "";
    setDomain(nextDomain);
  }, [source, selectedSourceMeta]);

  useEffect(() => {
    if (sourceOptions.length === 0) {
      return;
    }
    if (!sourceOptions.some((option) => option.id === source)) {
      setSource(sourceOptions[0]!.id);
    }
  }, [source, sourceOptions]);

  useEffect(() => {
    if (config && !exportOutPath) {
      setExportOutPath(defaultExportPath(config.userDataDir));
    }
  }, [config, exportOutPath]);

  useEffect(() => {
    if (config && !backupOutDir) {
      setBackupOutDir(defaultBackupDir(config.userDataDir));
    }
  }, [config, backupOutDir]);

  useEffect(() => {
    if (config && !importBackupDir) {
      setImportBackupDir(defaultImportDir(config.userDataDir));
    }
  }, [config, importBackupDir]);

  async function refreshReleaseMetadata(): Promise<void> {
    try {
      const nextMetadata = await window.desktopApi.getReleaseMetadata();
      setReleaseMetadata(nextMetadata);
      setReleaseMetadataError(null);
    } catch (err) {
      setReleaseMetadataError(String(err));
    }
  }

  async function refreshReceiptPlugins(): Promise<void> {
    try {
      const result = await window.desktopApi.listReceiptPlugins();
      setPluginPacks(result.packs);
      setPluginSearchPaths(result.activePluginSearchPaths);
      setPluginLoadError(null);
    } catch (err) {
      setPluginLoadError(String(err));
    }
  }

  async function handleStartBackend(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const status = await window.desktopApi.startBackend();
      setBackend(status);
    } catch (err) {
      setError(t("shell.error.backendStart", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleStopBackend(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const status = await window.desktopApi.stopBackend();
      setBackend(status);
    } catch (err) {
      setError(t("shell.error.backendStop", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunSync(): Promise<void> {
    setBusy(true);
    setError(null);
    setSyncResult(null);

    const payload: SyncRequest = {
      source,
      full: selectedSourceMeta?.syncFamily === "lidl_plus" ? fullSync : undefined,
      headless:
        selectedSourceMeta?.syncFamily === "amazon" || selectedSourceMeta?.syncFamily === "browser"
          ? headless
          : undefined,
      domain:
        selectedSourceMeta?.syncFamily === "amazon" || selectedSourceMeta?.syncFamily === "browser"
          ? domain || undefined
          : undefined,
      years: selectedSourceMeta?.syncFamily === "amazon" ? years : undefined,
      maxPages:
        selectedSourceMeta?.syncFamily === "amazon" || selectedSourceMeta?.syncFamily === "browser"
          ? maxPages
          : undefined
    };

    try {
      const result = await window.desktopApi.runSync(payload);
      setSyncResult(result);
      setBackend(await window.desktopApi.getBackendStatus());
    } catch (err) {
      setError(t("shell.error.sync", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadCards(): Promise<void> {
    if (!config) {
      setError(t("shell.error.configUnavailable"));
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (!backend?.running) {
        const status = await window.desktopApi.startBackend();
        setBackend(status);
      }
      const url = new URL("/api/v1/dashboard/cards", config.apiBaseUrl);
      url.searchParams.set("db", config.dbPath);
      url.searchParams.set("year", String(year));
      url.searchParams.set("month", String(month));
      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      setCardsResult(await response.json());
    } catch (err) {
      setError(t("shell.error.cards", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleOpenFullApp(): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      const url = await window.desktopApi.openFullApp();
      window.location.assign(url);
    } catch (err) {
      setError(t("shell.error.openFullApp", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunExport(): Promise<void> {
    setBusy(true);
    setError(null);
    setExportResult(null);

    const outPath = exportOutPath.trim();
    if (!outPath) {
      setBusy(false);
      setError(t("shell.error.exportRequired"));
      return;
    }

    const payload: ExportRequest = {
      outPath,
      format: "json"
    };

    try {
      const result = await window.desktopApi.runExport(payload);
      setExportResult(result);
    } catch (err) {
      setError(t("shell.error.export", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunBackup(): Promise<void> {
    setBusy(true);
    setError(null);
    setBackupResult(null);

    const outDir = backupOutDir.trim();
    if (!outDir) {
      setBusy(false);
      setError(t("shell.error.backupRequired"));
      return;
    }

    const payload: BackupRequest = {
      outDir,
      includeExportJson: backupIncludeExportJson,
      includeDocuments: backupIncludeDocuments
    };

    try {
      const result = await window.desktopApi.runBackup(payload);
      setBackupResult(result);
    } catch (err) {
      setError(t("shell.error.backup", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunImport(): Promise<void> {
    setBusy(true);
    setError(null);
    setImportResult(null);

    const backupDir = importBackupDir.trim();
    if (!backupDir) {
      setBusy(false);
      setError(t("shell.error.importRequired"));
      return;
    }

    const payload: ImportRequest = {
      backupDir,
      includeDocuments: importIncludeDocuments,
      includeToken: importIncludeToken,
      includeCredentialKey: importIncludeCredentialKey,
      restartBackend: importRestartBackend
    };

    try {
      const result = await window.desktopApi.runImport(payload);
      setImportResult(result);
      setBackend(await window.desktopApi.getBackendStatus());
    } catch (err) {
      setError(t("shell.error.import", { detail: String(err) }));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshPluginState(): Promise<void> {
    setBusy(true);
    setError(null);
    setPluginStatusMessage(null);
    try {
      await Promise.all([refreshReceiptPlugins(), refreshReleaseMetadata()]);
      setPluginStatusMessage("Refreshed local plugin packs and edition catalog details.");
    } catch (err) {
      setError(`Could not refresh receipt pack details. ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleInstallReceiptPlugin(): Promise<void> {
    setBusy(true);
    setError(null);
    setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.installReceiptPluginFromDialog();
      if (!result) {
        setPluginStatusMessage("No local pack was selected.");
        return;
      }
      setPluginStatusMessage(
        result.action === "installed"
          ? `Imported ${result.pack.displayName} ${result.pack.version}. Review the trust label, then enable it when you are ready.`
          : result.action === "updated"
            ? `Updated ${result.pack.displayName} to ${result.pack.version}.`
            : `Reinstalled ${result.pack.displayName} ${result.pack.version}.`
      );
      if (result.backendStatus) {
        setBackend(result.backendStatus);
      }
      await refreshReceiptPlugins();
    } catch (err) {
      setError(`Could not import the local receipt pack. ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleInstallReceiptPluginFromCatalog(entryId: string): Promise<void> {
    setBusy(true);
    setError(null);
    setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.installReceiptPluginFromCatalogEntry({ entryId });
      setPluginStatusMessage(
        result.action === "installed"
          ? `Installed trusted pack ${result.pack.displayName} ${result.pack.version}. Enable it when you want it active in the next backend run.`
          : result.action === "updated"
            ? `Updated trusted pack ${result.pack.displayName} to ${result.pack.version}.`
            : `Reinstalled trusted pack ${result.pack.displayName} ${result.pack.version}.`
      );
      if (result.backendStatus) {
        setBackend(result.backendStatus);
      }
      await Promise.all([refreshReleaseMetadata(), refreshReceiptPlugins()]);
    } catch (err) {
      setError(`Could not install the trusted receipt pack. ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleReceiptPlugin(pluginId: string, enabled: boolean): Promise<void> {
    setBusy(true);
    setError(null);
    setPluginStatusMessage(null);
    try {
      const result = enabled
        ? await window.desktopApi.enableReceiptPlugin(pluginId)
        : await window.desktopApi.disableReceiptPlugin(pluginId);
      setPluginStatusMessage(enabled ? `Enabled ${result.pack.displayName}.` : `Disabled ${result.pack.displayName}.`);
      if (result.backendStatus) {
        setBackend(result.backendStatus);
      }
      await refreshReceiptPlugins();
    } catch (err) {
      setError(`Could not update the receipt pack state. ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleUninstallReceiptPlugin(pluginId: string): Promise<void> {
    setBusy(true);
    setError(null);
    setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.uninstallReceiptPlugin(pluginId);
      setPluginStatusMessage(`Removed ${result.pluginId} from local desktop storage.`);
      if (result.backendStatus) {
        setBackend(result.backendStatus);
      }
      await refreshReceiptPlugins();
    } catch (err) {
      setError(`Could not remove the receipt pack. ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="shell-header">
        <div>
          <p className="eyebrow">{t("app.brand.title")}</p>
          <h1>Local receipt sync, review, export, and backup.</h1>
          <p className="shell-subtitle">
            LidlTool Desktop is the occasional-use companion for this computer. Use it when you want a quick sync,
            a local export, a backup, or a simple connector setup without running a full self-hosted server.
          </p>
        </div>
        <label className="locale-switcher">
          <span>{t("app.header.language")}</span>
          <select value={locale} onChange={(event) => void setLocale(event.target.value as typeof locale)}>
            <option value="en">{t("app.language.english")}</option>
            <option value="de">{t("app.language.german")}</option>
          </select>
        </label>
      </header>

      <section className="hero card">
        <div className="hero-copy">
          <span className={`status-chip status-tone-${controlCenterMode.tone}`}>{controlCenterMode.label}</span>
          <h2>{controlCenterMode.title}</h2>
          <p>{controlCenterMode.detail}</p>
          <p className="muted">
            Start here when you want a straightforward local task on this computer. Open the main app only when you
            want the fuller workflow.
          </p>
        </div>
        <div className="hero-actions">
          <button type="button" disabled={busy || runtimeDiagnostics?.fullAppReady === false} onClick={() => void handleOpenFullApp()}>
            Open main app
          </button>
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => void (backend?.running ? handleStopBackend() : handleStartBackend())}
          >
            {backend?.running ? "Stop local service" : "Start local service"}
          </button>
          <a className="button-link secondary" href="#quick-sync">
            Import receipts
          </a>
          <a className="button-link secondary" href="#plugins">
            Manage connectors
          </a>
        </div>
        <div className="journey-grid">
          <a className="journey-card" href="#quick-sync">
            <h3>Import receipts</h3>
            <p>Pick a store, keep the default settings, and run a local import.</p>
          </a>
          <a className="journey-card" href="#plugins">
            <h3>Add or manage connectors</h3>
            <p>Import a connector file, enable a pack, or install a trusted optional pack.</p>
          </a>
          <a className="journey-card" href="#safety">
            <h3>Protect your data</h3>
            <p>Create a backup, export your receipts, or restore this desktop profile.</p>
          </a>
        </div>
      </section>

      {bootError ? <p className="error">{t("shell.bootError", { detail: bootError })}</p> : null}

      <section className="grid two-cols">
        <article className="card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Start here</p>
              <h2>Use LidlTool on this computer</h2>
            </div>
            <span className={`status-chip ${backend?.running ? "status-enabled" : "status-disabled"}`}>{backendStatusText}</span>
          </div>
          <p>
            The desktop shell keeps things simple: open the full app when you want the richer workflow, or keep this
            lighter shell open for quick local tasks.
          </p>
          <div className="key-value-grid">
            <div>
              <span className="label">Main app</span>
              <strong>{runtimeDiagnostics?.fullAppReady ? "Bundled and ready" : "Control center only"}</strong>
            </div>
            <div>
              <span className="label">Local service</span>
              <strong>{backend?.running ? "Running on demand" : "Stopped until you need it"}</strong>
            </div>
            <div>
              <span className="label">Your data</span>
              <strong>{config?.dbPath ?? t("common.loading")}</strong>
            </div>
            <div>
              <span className="label">Runtime source</span>
              <strong>{describeBackendCommand(runtimeDiagnostics)}</strong>
            </div>
          </div>
          <div className="actions">
            <button type="button" disabled={busy || runtimeDiagnostics?.fullAppReady === false} onClick={() => void handleOpenFullApp()}>
              Open main app
            </button>
            <button type="button" disabled={busy} onClick={() => void handleStartBackend()}>
              Start local service
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void handleStopBackend()}>
              Stop local service
            </button>
          </div>
          <details>
            <summary>Startup details</summary>
            <dl className="plugin-meta">
              <div>
                <dt>Environment</dt>
                <dd>{runtimeDiagnostics?.environment ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Frontend assets</dt>
                <dd>{runtimeDiagnostics?.frontendDistStatus ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Frontend path</dt>
                <dd>{runtimeDiagnostics?.frontendDistPath ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Backend source</dt>
                <dd>{runtimeDiagnostics?.backendSourceStatus ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Backend source path</dt>
                <dd>{runtimeDiagnostics?.backendSourcePath ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Backend command</dt>
                <dd>{runtimeDiagnostics?.backendCommand ?? t("common.loading")}</dd>
              </div>
              <div>
                <dt>Local API</dt>
                <dd>{config?.apiBaseUrl ?? t("common.loading")}</dd>
              </div>
            </dl>
          </details>
        </article>

        <article id="quick-sync" className="card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Quick import</p>
              <h2>{t("shell.sync.title")}</h2>
            </div>
            <span className="status-chip status-disabled">{selectedSourceMeta?.label ?? source}</span>
          </div>
          <p>{sourceJourneySummary(source)}</p>
          {sourceSyncNotice(source, locale) ? (
            <div className="callout warning">
              <strong>dm</strong>
              <span>{sourceSyncNotice(source, locale)}</span>
            </div>
          ) : null}
          <label>
            {t("common.source")}
            <select value={source} onChange={(event) => setSource(event.target.value as SyncSourceId)}>
              {sourceOptions.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <details>
            <summary>Import options</summary>
            <div className="stack-fields">
              {selectedSourceMeta?.syncFamily === "lidl_plus" ? (
                <label className="inline-checkbox">
                  <input type="checkbox" checked={fullSync} onChange={(event) => setFullSync(event.target.checked)} />
                  {t("shell.sync.fullHistory")}
                </label>
              ) : selectedSourceMeta?.syncFamily === "amazon" || selectedSourceMeta?.syncFamily === "browser" ? (
                <>
                  <label className="inline-checkbox">
                    <input type="checkbox" checked={headless} onChange={(event) => setHeadless(event.target.checked)} />
                    {t("shell.sync.headless")}
                  </label>
                  <label>
                    {t("shell.sync.domain")}
                    <input value={domain} onChange={(event) => setDomain(event.target.value)} />
                  </label>
                  {selectedSourceMeta?.syncFamily === "amazon" ? (
                    <label>
                      {t("shell.sync.years")}
                      <input type="number" min={1} max={10} value={years} onChange={(event) => setYears(Number(event.target.value) || 1)} />
                    </label>
                  ) : null}
                  <label>
                    {t("shell.sync.maxPages")}
                    <input type="number" min={1} max={100} value={maxPages} onChange={(event) => setMaxPages(Number(event.target.value) || 1)} />
                  </label>
                </>
              ) : (
                <p className="muted">
                  This source uses its default runtime options in the desktop shell.
                </p>
              )}
            </div>
          </details>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleRunSync()}>
              {t("shell.sync.action.run")}
            </button>
          </div>
          <details open={Boolean(syncResult)}>
            <summary>Latest import result</summary>
            <pre>{syncResult ? prettyJson(syncResult) : t("shell.results.empty.sync")}</pre>
          </details>
        </article>
      </section>

      <section id="plugins" className="card">
        <div className="section-heading">
          <div>
            <p className="section-kicker">Connectors</p>
            <h2>Stores and packs on this desktop</h2>
          </div>
          <span className="status-chip status-disabled">
            {pluginPacks.length} installed / {installedEnabledCount} enabled
          </span>
        </div>
        <p>
          Add connector files, turn packs on or off, and install trusted optional packs for this edition from one place.
        </p>
        <div className="actions">
          <button type="button" disabled={busy} onClick={() => void handleInstallReceiptPlugin()}>
            Add connector file
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => void handleRefreshPluginState()}>
            Refresh connector list
          </button>
        </div>
        <div className="key-value-grid">
          <div>
            <span className="label">Installed packs</span>
            <strong>{pluginPacks.length}</strong>
          </div>
          <div>
            <span className="label">Ready to use</span>
            <strong>{installedEnabledCount}</strong>
          </div>
          <div>
            <span className="label">Trusted optional packs</span>
            <strong>{curatedDesktopPackEntries.length}</strong>
          </div>
          <div>
            <span className="label">Pack storage</span>
            <strong>{config?.receiptPluginStorageDir ?? t("common.loading")}</strong>
          </div>
        </div>
        {pluginStatusMessage ? <p className="success-text">{pluginStatusMessage}</p> : null}
        {pluginLoadError ? (
          <div className="callout warning">
            <p>Desktop could not fully read installed pack state.</p>
            <p className="muted">{pluginLoadError}</p>
          </div>
        ) : null}
        <div className="grid two-cols">
          <article className="subpanel">
            <div className="subpanel-heading">
              <h3>Installed on this computer</h3>
              <p className="muted">
                Packs stay local to this computer, and activation is always explicit.
              </p>
            </div>
            {pluginPacks.length === 0 ? (
              <div className="empty-state">
                <h3>No local receipt packs installed yet.</h3>
                <p>Start with a connector file, or add a trusted optional pack listed for this build.</p>
              </div>
            ) : (
              <div className="plugin-list">
                {pluginPacks.map((pack) => {
                  const catalogEntry = releaseMetadata
                    ? findCatalogDesktopPackEntry(releaseMetadata.discovery_catalog.entries, pack.pluginId)
                    : null;
                  const packStatus = describeInstalledPack(pack);
                  const updateTarget =
                    catalogEntry &&
                    !!catalogEntry.current_version &&
                    compareVersions(pack.version, catalogEntry.current_version) < 0 &&
                    !catalogEntry.availability.blocked_by_policy
                      ? catalogEntry
                      : null;

                  return (
                    <article key={pack.pluginId} className="plugin-pack">
                      <div className="plugin-pack-header">
                        <div>
                          <h3>{pack.displayName}</h3>
                          <p className="muted">
                            {pack.pluginId} · {pack.version}
                          </p>
                        </div>
                        <span className={`status-chip ${packStatus.chipClass}`}>{packStatus.label}</span>
                      </div>
                      <p>{packStatus.detail}</p>
                      {updateTarget ? <p className="success-text">Trusted update available: {updateTarget.current_version}</p> : null}
                      {pack.trustReason ? <p className="error compact">{pack.trustReason}</p> : null}
                      {pack.compatibilityReason ? <p className="error compact">{pack.compatibilityReason}</p> : null}
                      <div className="actions">
                        {updateTarget ? (
                          <button type="button" disabled={busy} onClick={() => void handleInstallReceiptPluginFromCatalog(updateTarget.entry_id)}>
                            Update from trusted catalog
                          </button>
                        ) : null}
                        <button
                          type="button"
                          disabled={busy || pack.status === "invalid" || pack.status === "revoked" || pack.status === "incompatible"}
                          onClick={() => void handleToggleReceiptPlugin(pack.pluginId, !pack.enabled)}
                        >
                          {pack.enabled ? "Disable pack" : "Enable pack"}
                        </button>
                        <button type="button" className="secondary" disabled={busy} onClick={() => void handleUninstallReceiptPlugin(pack.pluginId)}>
                          Remove pack
                        </button>
                      </div>
                      <details>
                        <summary>Details</summary>
                        <dl className="plugin-meta">
                          <div>
                            <dt>Trust</dt>
                            <dd>{formatPluginTrust(pack)}</dd>
                          </div>
                          <div>
                            <dt>Support</dt>
                            <dd>{formatTrustClassLabel(pack.trustClass)}</dd>
                          </div>
                          <div>
                            <dt>Installed via</dt>
                            <dd>{packInstallSource(pack)}</dd>
                          </div>
                          <div>
                            <dt>Retailer</dt>
                            <dd>{pack.sourceId}</dd>
                          </div>
                          <div>
                            <dt>Runtime</dt>
                            <dd>{pack.runtimeKind}</dd>
                          </div>
                          <div>
                            <dt>Install path</dt>
                            <dd>{pack.installPath}</dd>
                          </div>
                        </dl>
                        <p className="muted">{packOriginSummary(pack)}</p>
                        <p className="muted">{packSupportSummary(pack, catalogEntry)}</p>
                        {catalogEntry ? <p className="muted">{catalogProfileSummary(catalogEntry, releaseMetadata)}</p> : null}
                        {pack.diagnostics.length > 0 ? <pre>{prettyJson(pack.diagnostics)}</pre> : null}
                      </details>
                    </article>
                  );
                })}
              </div>
            )}
          </article>

          <article className="subpanel">
            <div className="subpanel-heading">
              <h3>Optional trusted packs</h3>
              <p className="muted">
                Add more supported stores when you need them. Manual connector-file import always stays available too.
              </p>
            </div>
            {curatedDesktopPackEntries.length === 0 ? (
              <div className="empty-state">
                <h3>No optional trusted receipt packs are listed for this build.</h3>
                <p>Manual connector-file import remains the fallback path.</p>
              </div>
            ) : (
              <div className="plugin-list">
                {curatedDesktopPackEntries.map((entry) => {
                  const installedPack = entry.plugin_id
                    ? (pluginPacks.find((pack) => pack.pluginId === entry.plugin_id) ?? null)
                    : null;
                  const availability = describeCatalogEntry(entry, installedPack);
                  const updateAvailable =
                    installedPack &&
                    !!entry.current_version &&
                    compareVersions(installedPack.version, entry.current_version) < 0;
                  const trustedUrlInstallAllowed =
                    releaseMetadata?.discovery_catalog.verification_status === "trusted" &&
                    entry.install_methods.includes("download_url") &&
                    !!entry.download_url &&
                    !entry.availability.blocked_by_policy;

                  return (
                    <article key={entry.entry_id} className="plugin-pack">
                      <div className="plugin-pack-header">
                        <div>
                          <h3>{entry.display_name}</h3>
                          <p className="muted">
                            {formatCatalogEntryType(entry.entry_type)} · {entry.current_version ?? "version not declared"}
                          </p>
                        </div>
                        <span className={`status-chip ${availability.chipClass}`}>{availability.label}</span>
                      </div>
                      <p>{entry.summary}</p>
                      <p className="muted">{availability.detail}</p>
                      {updateAvailable ? <p className="success-text">Trusted update available: {entry.current_version}</p> : null}
                      {entry.availability.blocked_by_policy ? (
                        <p className="error compact">{entry.availability.block_reason ?? "Catalog entry blocked by policy."}</p>
                      ) : null}
                      <div className="actions">
                        {trustedUrlInstallAllowed ? (
                          <button type="button" disabled={busy} onClick={() => void handleInstallReceiptPluginFromCatalog(entry.entry_id)}>
                            {installedPack ? (updateAvailable ? "Install trusted update" : "Reinstall trusted pack") : "Install trusted pack"}
                          </button>
                        ) : null}
                        {entry.docs_url ? (
                          <a className="button-link secondary" href={entry.docs_url} target="_blank" rel="noreferrer">
                            Docs
                          </a>
                        ) : null}
                      </div>
                      <details>
                        <summary>Details</summary>
                        <dl className="plugin-meta">
                          <div>
                            <dt>Support</dt>
                            <dd>{formatTrustClassLabel(entry.trust_class)}</dd>
                          </div>
                          <div>
                            <dt>Install path</dt>
                            <dd>{formatInstallMethods(entry.install_methods)}</dd>
                          </div>
                          <div>
                            <dt>Maintainer</dt>
                            <dd>{entry.maintainer}</dd>
                          </div>
                          <div>
                            <dt>Markets</dt>
                            <dd>{entry.supported_markets.length > 0 ? entry.supported_markets.join(", ") : "Unspecified"}</dd>
                          </div>
                        </dl>
                        <p className="muted">{catalogSupportSummary(entry)}</p>
                        <p className="muted">{catalogProfileSummary(entry, releaseMetadata)}</p>
                        {entry.release_notes_summary ? <p className="muted">{entry.release_notes_summary}</p> : null}
                        {entry.homepage_url ? (
                          <a className="button-link secondary" href={entry.homepage_url} target="_blank" rel="noreferrer">
                            Homepage
                          </a>
                        ) : null}
                      </details>
                    </article>
                  );
                })}
              </div>
            )}
            <details>
              <summary>Edition details</summary>
              <dl className="plugin-meta">
                <div>
                  <dt>Release</dt>
                  <dd>{releaseMetadata?.active_release_variant.display_name ?? "Loading"}</dd>
                </div>
                <div>
                  <dt>Edition</dt>
                  <dd>{releaseMetadata ? formatEditionKind(releaseMetadata.active_release_variant.edition_kind) : "Loading"}</dd>
                </div>
                <div>
                  <dt>Market profile</dt>
                  <dd>{releaseMetadata?.selected_market_profile.display_name ?? "Loading"}</dd>
                </div>
                <div>
                  <dt>Verification</dt>
                  <dd>{formatCatalogVerification(releaseMetadata?.discovery_catalog ?? null)}</dd>
                </div>
                <div>
                  <dt>Default bundles</dt>
                  <dd>{defaultBundleLabels.length > 0 ? defaultBundleLabels.join(", ") : "None bundled by default"}</dd>
                </div>
                <div>
                  <dt>Recommended</dt>
                  <dd>{recommendedBundleLabels.length > 0 ? recommendedBundleLabels.join(", ") : "No extra recommendations"}</dd>
                </div>
              </dl>
              <p className="muted">
                {releaseMetadata?.selected_market_profile.description ??
                  "Desktop is preparing the current release profile."}
              </p>
              {releaseMetadata?.selected_market_profile.out_of_scope_notes.length ? (
                <div className="callout warning">
                  {releaseMetadata.selected_market_profile.out_of_scope_notes.map((note) => (
                    <p key={note}>{note}</p>
                  ))}
                </div>
              ) : null}
              {releaseMetadata?.discovery_catalog.diagnostics.length ? (
                <div className="callout warning">
                  <p>{releaseMetadata.discovery_catalog.diagnostics[0]?.message}</p>
                </div>
              ) : null}
              {releaseMetadataError ? (
                <div className="callout warning">
                  <p>Edition metadata could not be refreshed. Manual connector-file import still works.</p>
                  <p className="muted">{releaseMetadataError}</p>
                </div>
              ) : null}
            </details>
          </article>
        </div>
      </section>

      <section id="safety" className="grid two-cols">
        <article className="card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Protect your data</p>
              <h2>Backup, export, and restore</h2>
            </div>
          </div>
          <p>
            Keep this desktop profile safe with a full backup, a portable JSON export, or a restore when you need to
            recover the same machine.
          </p>
          <div className="stack-fields">
            <details>
              <summary>{t("shell.backup.title")}</summary>
              <div className="stack-fields">
                <p className="muted">Create a local backup folder for this desktop install.</p>
                <label>
                  {t("shell.backup.outputDir")}
                  <input value={backupOutDir} onChange={(event) => setBackupOutDir(event.target.value)} />
                </label>
                <label className="inline-checkbox">
                  <input checked={backupIncludeExportJson} type="checkbox" onChange={(event) => setBackupIncludeExportJson(event.target.checked)} />
                  {t("shell.backup.includeExport")}
                </label>
                <label className="inline-checkbox">
                  <input checked={backupIncludeDocuments} type="checkbox" onChange={(event) => setBackupIncludeDocuments(event.target.checked)} />
                  {t("shell.backup.includeDocuments")}
                </label>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={() => void handleRunBackup()}>
                    {t("shell.backup.action.run")}
                  </button>
                </div>
              </div>
            </details>
            <details>
              <summary>{t("shell.export.title")}</summary>
              <div className="stack-fields">
                <p className="muted">Export normalized receipt data to one JSON file for your own local tools.</p>
                <label>
                  {t("shell.export.outputPath")}
                  <input value={exportOutPath} onChange={(event) => setExportOutPath(event.target.value)} />
                </label>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={() => void handleRunExport()}>
                    {t("shell.export.action.run")}
                  </button>
                </div>
              </div>
            </details>
            <details>
              <summary>{t("shell.restore.title")}</summary>
              <div className="stack-fields">
                <p className="muted">Restore this desktop profile from a local backup folder.</p>
                <label>
                  {t("shell.restore.backupDir")}
                  <input value={importBackupDir} onChange={(event) => setImportBackupDir(event.target.value)} />
                </label>
                <label className="inline-checkbox">
                  <input checked={importIncludeCredentialKey} type="checkbox" onChange={(event) => setImportIncludeCredentialKey(event.target.checked)} />
                  {t("shell.restore.includeCredentialKey")}
                </label>
                <label className="inline-checkbox">
                  <input checked={importIncludeToken} type="checkbox" onChange={(event) => setImportIncludeToken(event.target.checked)} />
                  {t("shell.restore.includeToken")}
                </label>
                <label className="inline-checkbox">
                  <input checked={importIncludeDocuments} type="checkbox" onChange={(event) => setImportIncludeDocuments(event.target.checked)} />
                  {t("shell.restore.includeDocuments")}
                </label>
                <label className="inline-checkbox">
                  <input checked={importRestartBackend} type="checkbox" onChange={(event) => setImportRestartBackend(event.target.checked)} />
                  {t("shell.restore.restartBackend")}
                </label>
                <div className="actions">
                  <button type="button" disabled={busy} onClick={() => void handleRunImport()}>
                    {t("shell.restore.action.run")}
                  </button>
                </div>
              </div>
            </details>
          </div>
        </article>

        <article className="card">
          <div className="section-heading">
            <div>
              <p className="section-kicker">Recent activity</p>
              <h2>Latest local results and checks</h2>
            </div>
          </div>
          <p className="muted">
            Use this area for quick confirmation after an import, export, backup, or restore.
          </p>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleLoadCards()}>
              {t("shell.analytics.action.load")}
            </button>
          </div>
          <details open={Boolean(syncResult)}>
            <summary>{t("shell.results.sync")}</summary>
            <pre>{syncResult ? prettyJson(syncResult) : t("shell.results.empty.sync")}</pre>
          </details>
          <details open={Boolean(exportResult)}>
            <summary>{t("shell.results.export")}</summary>
            <pre>{exportResult ? prettyJson(exportResult) : t("shell.results.empty.export")}</pre>
          </details>
          <details open={Boolean(backupResult)}>
            <summary>{t("shell.results.backup")}</summary>
            <pre>{backupResult ? prettyJson(backupResult) : t("shell.results.empty.backup")}</pre>
          </details>
          <details open={Boolean(importResult)}>
            <summary>{t("shell.results.restore")}</summary>
            <pre>{importResult ? prettyJson(importResult) : t("shell.results.empty.restore")}</pre>
          </details>
          <details>
            <summary>Dashboard cards</summary>
            <pre>{cardsResult ? prettyJson(cardsResult) : t("shell.analytics.empty")}</pre>
          </details>
          <details open={logs.length > 0}>
            <summary>{t("shell.logs.title")}</summary>
            <div className="logbox">
              {logs.length === 0
                ? t("shell.logs.empty")
                : logs.map((entry, idx) => (
                    <div key={`${entry.timestamp}-${idx}`} className={`logline ${entry.stream}`}>
                      [{entry.source}] [{entry.stream}] {entry.line}
                    </div>
                  ))}
            </div>
          </details>
        </article>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}
