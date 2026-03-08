import { useEffect, useMemo, useState } from "react";

import type {
  BackupRequest,
  BackendConfig,
  BackendStatus,
  CommandLogEvent,
  CommandResult,
  ExportRequest,
  ImportRequest,
  SyncRequest,
  SyncSourceId
} from "@shared/contracts";
import { useDesktopI18n } from "./i18n";

const SOURCE_OPTIONS: Array<{ id: SyncSourceId; label: string; defaultDomain?: string }> = [
  { id: "lidl", label: "Lidl" },
  { id: "amazon", label: "Amazon", defaultDomain: "amazon.de" },
  { id: "rewe", label: "REWE", defaultDomain: "shop.rewe.de" },
  { id: "kaufland", label: "Kaufland", defaultDomain: "www.kaufland.de" },
  { id: "dm", label: "dm", defaultDomain: "www.dm.de" },
  { id: "rossmann", label: "Rossmann", defaultDomain: "www.rossmann.de" }
];

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

export default function App(): JSX.Element {
  const { locale, setLocale, t } = useDesktopI18n();
  const [{ year, month }] = useState(defaultYearMonth);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [backend, setBackend] = useState<BackendStatus | null>(null);
  const [source, setSource] = useState<SyncSourceId>("lidl");
  const [fullSync, setFullSync] = useState(false);
  const [headless, setHeadless] = useState(true);
  const [domain, setDomain] = useState("amazon.de");
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
  const [cardsResult, setCardsResult] = useState<unknown>(null);
  const [logs, setLogs] = useState<CommandLogEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  const selectedSourceMeta = useMemo(
    () => SOURCE_OPTIONS.find((option) => option.id === source),
    [source]
  );

  const backendStatusText = useMemo(() => {
    if (!backend) {
      return t("shell.backend.status.loading");
    }
    if (backend.running) {
      return t("shell.backend.status.running", { pid: backend.pid ?? "n/a" });
    }
    return t("shell.backend.status.stopped");
  }, [backend, t]);

  useEffect(() => {
    let disposeLogs: (() => void) | null = null;
    let disposeBootError: (() => void) | null = null;

    async function boot(): Promise<void> {
      try {
        const [cfg, initialBootError, status] = await Promise.all([
          window.desktopApi.getConfig(),
          window.desktopApi.getBootError(),
          window.desktopApi.getBackendStatus()
        ]);
        setConfig(cfg);
        setBootError(initialBootError);
        setBackend(status);
        disposeLogs = window.desktopApi.onLog((event) => {
          setLogs((prev) => [...prev.slice(-399), event]);
        });
        disposeBootError = window.desktopApi.onBootError((message) => {
          setBootError(message);
        });
      } catch (err) {
        setError(t("shell.error.desktopApiInit", { detail: String(err) }));
      }
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
      full: source === "lidl" ? fullSync : undefined,
      headless: source === "lidl" ? undefined : headless,
      domain: source === "lidl" ? undefined : domain || undefined,
      years: source === "amazon" ? years : undefined,
      maxPages: source === "lidl" ? undefined : maxPages
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

  return (
    <main className="shell">
      <header className="shell-header">
        <div>
          <p className="eyebrow">{t("app.brand.title")}</p>
          <h1>{t("shell.header.title")}</h1>
          <p className="shell-subtitle">{t("shell.header.subtitle")}</p>
        </div>
        <label className="locale-switcher">
          <span>{t("app.header.language")}</span>
          <select value={locale} onChange={(event) => void setLocale(event.target.value as typeof locale)}>
            <option value="en">{t("app.language.english")}</option>
            <option value="de">{t("app.language.german")}</option>
          </select>
        </label>
      </header>

      {bootError ? <p className="error">{t("shell.bootError", { detail: bootError })}</p> : null}

      <section className="grid two-cols">
        <article className="card">
          <h2>{t("shell.backend.title")}</h2>
          <p>
            <strong>{t("shell.backend.api")}:</strong> {config?.apiBaseUrl ?? t("common.loading")}
          </p>
          <p>
            <strong>{t("shell.backend.db")}:</strong> {config?.dbPath ?? t("common.loading")}
          </p>
          <p>
            <strong>{t("common.status")}:</strong> {backendStatusText}
          </p>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleOpenFullApp()}>
              {t("shell.backend.action.openFullApp")}
            </button>
            <button type="button" disabled={busy} onClick={() => void handleStartBackend()}>
              {t("shell.backend.action.start")}
            </button>
            <button type="button" disabled={busy} onClick={() => void handleStopBackend()}>
              {t("shell.backend.action.stop")}
            </button>
          </div>
        </article>

        <article className="card">
          <h2>{t("shell.sync.title")}</h2>
          <p>{t("shell.sync.description")}</p>
          <label>
            {t("common.source")}
            <select value={source} onChange={(event) => setSource(event.target.value as SyncSourceId)}>
              {SOURCE_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {source === "lidl" ? (
            <label className="inline-checkbox">
              <input type="checkbox" checked={fullSync} onChange={(event) => setFullSync(event.target.checked)} />
              {t("shell.sync.fullHistory")}
            </label>
          ) : (
            <>
              <label className="inline-checkbox">
                <input type="checkbox" checked={headless} onChange={(event) => setHeadless(event.target.checked)} />
                {t("shell.sync.headless")}
              </label>
              <label>
                {t("shell.sync.domain")}
                <input value={domain} onChange={(event) => setDomain(event.target.value)} />
              </label>
              {source === "amazon" ? (
                <label>
                  {t("shell.sync.years")}
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={years}
                    onChange={(event) => setYears(Number(event.target.value) || 1)}
                  />
                </label>
              ) : null}
              <label>
                {t("shell.sync.maxPages")}
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={maxPages}
                  onChange={(event) => setMaxPages(Number(event.target.value) || 1)}
                />
              </label>
            </>
          )}

          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleRunSync()}>
              {t("shell.sync.action.run")}
            </button>
          </div>
        </article>

        <article className="card">
          <h2>{t("shell.backup.title")}</h2>
          <p>{t("shell.backup.description")}</p>
          <label>
            {t("shell.backup.outputDir")}
            <input value={backupOutDir} onChange={(event) => setBackupOutDir(event.target.value)} />
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={backupIncludeExportJson}
              onChange={(event) => setBackupIncludeExportJson(event.target.checked)}
            />
            {t("shell.backup.includeExport")}
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={backupIncludeDocuments}
              onChange={(event) => setBackupIncludeDocuments(event.target.checked)}
            />
            {t("shell.backup.includeDocuments")}
          </label>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleRunBackup()}>
              {t("shell.backup.action.run")}
            </button>
          </div>
        </article>

        <article className="card">
          <h2>{t("shell.export.title")}</h2>
          <p>{t("shell.export.description")}</p>
          <label>
            {t("shell.export.outputPath")}
            <input value={exportOutPath} onChange={(event) => setExportOutPath(event.target.value)} />
          </label>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleRunExport()}>
              {t("shell.export.action.run")}
            </button>
          </div>
        </article>

        <article className="card">
          <h2>{t("shell.restore.title")}</h2>
          <p>{t("shell.restore.description")}</p>
          <label>
            {t("shell.restore.backupDir")}
            <input value={importBackupDir} onChange={(event) => setImportBackupDir(event.target.value)} />
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeCredentialKey}
              onChange={(event) => setImportIncludeCredentialKey(event.target.checked)}
            />
            {t("shell.restore.includeCredentialKey")}
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeToken}
              onChange={(event) => setImportIncludeToken(event.target.checked)}
            />
            {t("shell.restore.includeToken")}
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeDocuments}
              onChange={(event) => setImportIncludeDocuments(event.target.checked)}
            />
            {t("shell.restore.includeDocuments")}
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importRestartBackend}
              onChange={(event) => setImportRestartBackend(event.target.checked)}
            />
            {t("shell.restore.restartBackend")}
          </label>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleRunImport()}>
              {t("shell.restore.action.run")}
            </button>
          </div>
        </article>
      </section>

      <section className="grid two-cols">
        <article className="card">
          <h2>{t("shell.analytics.title")}</h2>
          <p>{t("shell.analytics.description")}</p>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void handleLoadCards()}>
              {t("shell.analytics.action.load")}
            </button>
          </div>
          <pre>{cardsResult ? prettyJson(cardsResult) : t("shell.analytics.empty")}</pre>
        </article>

        <article className="card">
          <h2>{t("shell.results.title")}</h2>
          <p>
            <strong>{t("shell.results.sync")}</strong>
          </p>
          <pre>{syncResult ? prettyJson(syncResult) : t("shell.results.empty.sync")}</pre>
          <p>
            <strong>{t("shell.results.backup")}</strong>
          </p>
          <pre>{backupResult ? prettyJson(backupResult) : t("shell.results.empty.backup")}</pre>
          <p>
            <strong>{t("shell.results.export")}</strong>
          </p>
          <pre>{exportResult ? prettyJson(exportResult) : t("shell.results.empty.export")}</pre>
          <p>
            <strong>{t("shell.results.restore")}</strong>
          </p>
          <pre>{importResult ? prettyJson(importResult) : t("shell.results.empty.restore")}</pre>
        </article>
      </section>

      <section className="card">
        <h2>{t("shell.logs.title")}</h2>
        <div className="logbox">
          {logs.length === 0
            ? t("shell.logs.empty")
            : logs.map((entry, idx) => (
                <div key={`${entry.timestamp}-${idx}`} className={`logline ${entry.stream}`}>
                  [{entry.source}] [{entry.stream}] {entry.line}
                </div>
              ))}
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </main>
  );
}
