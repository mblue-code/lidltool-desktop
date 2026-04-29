import { useEffect, useMemo } from "react";

import type { SyncSourceId } from "@shared/contracts";
import { useDesktopI18n } from "./i18n";
import {
  describeBackendCommand,
  describeControlCenterMode,
  formatCatalogVerification,
  formatEditionKind,
} from "./control-center-model";
import { buildControlCenterViewModel } from "./control-center-view-model";
import {
  prettyJson,
  sourceJourneySummary,
  sourceSyncNotice
} from "./control-center-helpers";
import { useControlCenterActions } from "./use-control-center-actions";
import { useControlCenterState } from "./use-control-center-state";
import logoMark from "./assets/logo-mark.svg";

export default function App() {
  const { locale, setLocale, t } = useDesktopI18n();
  const state = useControlCenterState({ t });
  const {
    backend,
    backupIncludeDocuments,
    backupIncludeExportJson,
    backupOutDir,
    backupResult,
    bootError,
    busy,
    cardsResult,
    config,
    diagnosticsBundleResult,
    diagnosticsSummary,
    domain,
    error,
    exportOutPath,
    exportResult,
    fullSync,
    headless,
    importBackupDir,
    importIncludeCredentialKey,
    importIncludeDocuments,
    importIncludeToken,
    importRestartBackend,
    importResult,
    logs,
    maxPages,
    pluginLoadError,
    pluginStatusMessage,
    releaseMetadata,
    releaseMetadataError,
    runtimeDiagnostics,
    setBackupIncludeDocuments,
    setBackupIncludeExportJson,
    setBackupOutDir,
    setDomain,
    setExportOutPath,
    setFullSync,
    setHeadless,
    setImportBackupDir,
    setImportIncludeCredentialKey,
    setImportIncludeDocuments,
    setImportIncludeToken,
    setImportRestartBackend,
    setMaxPages,
    setSource,
    setYears,
    source,
    syncResult,
    years
  } = state;

  const controlCenterViewModel = useMemo(
    () => buildControlCenterViewModel(releaseMetadata, state.pluginPacks, locale),
    [locale, releaseMetadata, state.pluginPacks]
  );
  const {
    sourceOptions,
    defaultBundleLabels,
    recommendedBundleLabels,
    installedEnabledCount,
    installedPackRows,
    trustedPackRows
  } = controlCenterViewModel;
  const selectedSourceMeta = useMemo(
    () => sourceOptions.find((option) => option.id === source) ?? sourceOptions[0]!,
    [source, sourceOptions]
  );

  const {
    handleInstallReceiptPlugin,
    handleInstallReceiptPluginFromCatalog,
    handleCreateDiagnosticsBundle,
    handleLoadCards,
    handleOpenFullApp,
    handleOpenBugReport,
    handleRefreshPluginState,
    handleRunBackup,
    handleRunExport,
    handleRunImport,
    handleRunSync,
    handleStartBackend,
    handleStopBackend,
    handleToggleReceiptPlugin,
    handleUninstallReceiptPlugin
  } = useControlCenterActions({
    locale,
    t,
    selectedSourceMeta,
    state
  });

  useEffect(() => {
    const nextDomain = selectedSourceMeta.defaultDomain ?? "";
    setDomain(nextDomain);
  }, [selectedSourceMeta, setDomain, source]);

  useEffect(() => {
    if (!sourceOptions.some((option) => option.id === source)) {
      setSource(sourceOptions[0]!.id);
    }
  }, [setSource, source, sourceOptions]);

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
    () => describeControlCenterMode(bootError, runtimeDiagnostics, locale),
    [bootError, locale, runtimeDiagnostics]
  );

  return (
    <main className="shell">
      <header className="shell-header">
        <div className="brand-lockup">
          <div className="brand-mark-frame">
            <img className="brand-mark" src={logoMark} alt="" aria-hidden="true" />
          </div>
          <div className="brand-copy">
            <p className="eyebrow">{t("app.brand.title")}</p>
            <h1>Local receipt sync, review, export, and backup.</h1>
            <p className="shell-subtitle">
              LidlTool Desktop is the occasional-use companion for this computer. Use it when you want a quick sync,
              a local export, a backup, or a simple connector setup without running a full self-hosted server.
            </p>
          </div>
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
              <strong>{describeBackendCommand(runtimeDiagnostics, locale)}</strong>
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
            <span className="status-chip status-disabled">{selectedSourceMeta.label}</span>
          </div>
          <p>{sourceJourneySummary(source, locale)}</p>
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
              {selectedSourceMeta.syncFamily === "lidl_plus" ? (
                <label className="inline-checkbox">
                  <input type="checkbox" checked={fullSync} onChange={(event) => setFullSync(event.target.checked)} />
                  {t("shell.sync.fullHistory")}
                </label>
              ) : selectedSourceMeta.syncFamily === "amazon" || selectedSourceMeta.syncFamily === "browser" ? (
                <>
                  <label className="inline-checkbox">
                    <input type="checkbox" checked={headless} onChange={(event) => setHeadless(event.target.checked)} />
                    {t("shell.sync.headless")}
                  </label>
                  <label>
                    {t("shell.sync.domain")}
                    <input value={domain} onChange={(event) => setDomain(event.target.value)} />
                  </label>
                  {selectedSourceMeta.syncFamily === "amazon" ? (
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
            {installedPackRows.length} installed / {installedEnabledCount} enabled
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
              <strong>{installedPackRows.length}</strong>
            </div>
            <div>
              <span className="label">Ready to use</span>
              <strong>{installedEnabledCount}</strong>
            </div>
            <div>
              <span className="label">Trusted optional packs</span>
              <strong>{trustedPackRows.length}</strong>
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
            {installedPackRows.length === 0 ? (
              <div className="empty-state">
                <h3>No local receipt packs installed yet.</h3>
                <p>Start with a connector file, or add a trusted optional pack listed for this build.</p>
              </div>
            ) : (
              <div className="plugin-list">
                {installedPackRows.map((row) => {
                  const { pack, catalogEntry, packStatus, profileSummary, supportSummary, trustLabel, supportLabel, installSourceLabel, originSummary, updateTarget } = row;
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
                            <dd>{trustLabel}</dd>
                          </div>
                          <div>
                            <dt>Support</dt>
                            <dd>{supportLabel}</dd>
                          </div>
                          <div>
                            <dt>Installed via</dt>
                            <dd>{installSourceLabel}</dd>
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
                        <p className="muted">{originSummary}</p>
                        <p className="muted">{supportSummary}</p>
                        {profileSummary ? <p className="muted">{profileSummary}</p> : null}
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
            {trustedPackRows.length === 0 ? (
              <div className="empty-state">
                <h3>No optional trusted receipt packs are listed for this build.</h3>
                <p>Manual connector-file import remains the fallback path.</p>
              </div>
            ) : (
              <div className="plugin-list">
                {trustedPackRows.map((row) => {
                  const { availability, entry, entryTypeLabel, installMethodsLabel, installedPack, profileSummary, supportLabel, supportSummary, trustedUrlInstallAllowed, updateAvailable } = row;
                  return (
                    <article key={entry.entry_id} className="plugin-pack">
                      <div className="plugin-pack-header">
                        <div>
                          <h3>{entry.display_name}</h3>
                          <p className="muted">
                            {entryTypeLabel} · {entry.current_version ?? "version not declared"}
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
                            <dd>{supportLabel}</dd>
                          </div>
                          <div>
                            <dt>Install path</dt>
                            <dd>{installMethodsLabel}</dd>
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
                        <p className="muted">{supportSummary}</p>
                        <p className="muted">{profileSummary}</p>
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
                  <dd>{releaseMetadata ? formatEditionKind(releaseMetadata.active_release_variant.edition_kind, locale) : "Loading"}</dd>
                </div>
                <div>
                  <dt>Market profile</dt>
                  <dd>{releaseMetadata?.selected_market_profile.display_name ?? "Loading"}</dd>
                </div>
                <div>
                  <dt>Verification</dt>
                  <dd>{formatCatalogVerification(releaseMetadata?.discovery_catalog ?? null, locale)}</dd>
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
              <p className="section-kicker">Diagnostics</p>
              <h2>Report a problem</h2>
            </div>
            <span className={`status-chip ${diagnosticsSummary?.telemetryEnabled ? "status-enabled" : "status-disabled"}`}>
              {diagnosticsSummary?.telemetryEnabled ? "Error reporting on" : "Error reporting off"}
            </span>
          </div>
          <p className="muted">
            Create a redacted diagnostics zip when you want to attach local context to a GitHub bug report. Receipt
            contents, credentials, tokens, and database files are not included.
          </p>
          <div className="key-value-grid">
            <div>
              <span className="label">Release</span>
              <strong>{diagnosticsSummary?.appVersion ?? t("common.loading")}</strong>
            </div>
            <div>
              <span className="label">Channel</span>
              <strong>{diagnosticsSummary?.releaseChannel ?? t("common.loading")}</strong>
            </div>
            <div>
              <span className="label">System</span>
              <strong>
                {diagnosticsSummary
                  ? `${diagnosticsSummary.platform} / ${diagnosticsSummary.arch}`
                  : t("common.loading")}
              </strong>
            </div>
            <div>
              <span className="label">Telemetry</span>
              <strong>{diagnosticsSummary?.telemetryMode ?? "off"}</strong>
            </div>
          </div>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleCreateDiagnosticsBundle()}>
              Create diagnostics bundle
            </button>
            <button type="button" className="secondary" disabled={busy} onClick={() => void handleOpenBugReport()}>
              Open bug report
            </button>
          </div>
          {diagnosticsBundleResult ? (
            <p className="muted">
              Created {diagnosticsBundleResult.fileName} with {diagnosticsBundleResult.includedFiles.length} files.
            </p>
          ) : null}
          <details>
            <summary>Diagnostics summary</summary>
            <pre>{diagnosticsSummary ? prettyJson(diagnosticsSummary) : t("common.loading")}</pre>
          </details>
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
