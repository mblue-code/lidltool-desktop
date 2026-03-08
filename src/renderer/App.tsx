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

const SOURCE_OPTIONS: Array<{ id: SyncSourceId; label: string; defaultDomain?: string }> = [
  { id: "lidl", label: "Lidl" },
  { id: "amazon", label: "Amazon", defaultDomain: "amazon.de" },
  { id: "rewe", label: "REWE", defaultDomain: "shop.rewe.de" },
  { id: "kaufland", label: "Kaufland", defaultDomain: "www.kaufland.de" },
  { id: "dm", label: "dm", defaultDomain: "www.dm.de" },
  { id: "rossmann", label: "Rossmann", defaultDomain: "www.rossmann.de" }
];

const monthFormatter = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit" });

function defaultYearMonth(): { year: number; month: number } {
  const parts = monthFormatter.formatToParts(new Date());
  const year = Number(parts.find((part) => part.type === "year")?.value ?? new Date().getFullYear());
  const month = Number(parts.find((part) => part.type === "month")?.value ?? new Date().getMonth() + 1);
  return { year, month };
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

export default function App() {
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
        setError(`Failed to initialize desktop API: ${String(err)}`);
      }
    }

    void boot();

    return () => {
      if (disposeLogs) {
        disposeLogs();
      }
      if (disposeBootError) {
        disposeBootError();
      }
    };
  }, []);

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
      setError(`Backend start failed: ${String(err)}`);
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
      setError(`Backend stop failed: ${String(err)}`);
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
      setError(`Sync failed: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadCards(): Promise<void> {
    if (!config) {
      setError("Desktop config is not ready yet.");
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
      setError(`Cards query failed: ${String(err)}. Start backend first.`);
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
      setError(`Could not open full app: ${String(err)}`);
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
      setError("Export output path is required.");
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
      setError(`Export failed: ${String(err)}`);
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
      setError("Backup output directory is required.");
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
      setError(`Backup failed: ${String(err)}`);
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
      setError("Backup directory is required.");
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
      setError(`Backup import failed: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header>
        <h1>LidlTool Desktop Scaffold</h1>
        <p>Control center fallback. The full self-hosted app should auto-open when backend startup succeeds.</p>
      </header>

      {bootError ? <p className="error">Automatic full-app boot failed: {bootError}</p> : null}

      <section className="grid two-cols">
        <article className="card">
          <h2>Backend</h2>
          <p><strong>API:</strong> {config?.apiBaseUrl ?? "loading"}</p>
          <p><strong>DB:</strong> {config?.dbPath ?? "loading"}</p>
          <p><strong>Status:</strong> {backend?.running ? `running (pid ${backend.pid ?? "n/a"})` : "stopped"}</p>
          <div className="actions">
            <button disabled={busy} onClick={() => void handleOpenFullApp()}>Open full app</button>
            <button disabled={busy} onClick={() => void handleStartBackend()}>Start backend</button>
            <button disabled={busy} onClick={() => void handleStopBackend()}>Stop backend</button>
          </div>
        </article>

        <article className="card">
          <h2>One-Time Scrape</h2>
          <label>
            Source
            <select value={source} onChange={(event) => setSource(event.target.value as SyncSourceId)}>
              {SOURCE_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </label>

          {source === "lidl" ? (
            <label className="inline-checkbox">
              <input type="checkbox" checked={fullSync} onChange={(event) => setFullSync(event.target.checked)} />
              Full historical sync
            </label>
          ) : (
            <>
              <label className="inline-checkbox">
                <input type="checkbox" checked={headless} onChange={(event) => setHeadless(event.target.checked)} />
                Headless browser
              </label>
              <label>
                Domain
                <input value={domain} onChange={(event) => setDomain(event.target.value)} />
              </label>
              {source === "amazon" ? (
                <label>
                  Years
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
                Max pages
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
            <button disabled={busy} onClick={() => void handleRunSync()}>Run one-time scrape</button>
          </div>
        </article>

        <article className="card">
          <h2>Backup Bundle</h2>
          <p>Creates a local backup directory with DB, credentials, and optional exports/documents.</p>
          <label>
            Backup directory
            <input value={backupOutDir} onChange={(event) => setBackupOutDir(event.target.value)} />
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={backupIncludeExportJson}
              onChange={(event) => setBackupIncludeExportJson(event.target.checked)}
            />
            Include JSON receipts export
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={backupIncludeDocuments}
              onChange={(event) => setBackupIncludeDocuments(event.target.checked)}
            />
            Include document storage
          </label>
          <div className="actions">
            <button disabled={busy} onClick={() => void handleRunBackup()}>Create backup</button>
          </div>
        </article>

        <article className="card">
          <h2>Data Export</h2>
          <p>Exports normalized receipts to a single local JSON file.</p>
          <label>
            Output path
            <input value={exportOutPath} onChange={(event) => setExportOutPath(event.target.value)} />
          </label>
          <div className="actions">
            <button disabled={busy} onClick={() => void handleRunExport()}>Export data</button>
          </div>
        </article>

        <article className="card">
          <h2>Restore Backup</h2>
          <p>Restores DB/auth artifacts from an existing backup directory.</p>
          <label>
            Backup directory
            <input value={importBackupDir} onChange={(event) => setImportBackupDir(event.target.value)} />
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeCredentialKey}
              onChange={(event) => setImportIncludeCredentialKey(event.target.checked)}
            />
            Restore credential key
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeToken}
              onChange={(event) => setImportIncludeToken(event.target.checked)}
            />
            Restore token file
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importIncludeDocuments}
              onChange={(event) => setImportIncludeDocuments(event.target.checked)}
            />
            Restore document storage
          </label>
          <label className="inline-checkbox">
            <input
              type="checkbox"
              checked={importRestartBackend}
              onChange={(event) => setImportRestartBackend(event.target.checked)}
            />
            Restart backend after restore
          </label>
          <div className="actions">
            <button disabled={busy} onClick={() => void handleRunImport()}>Restore backup</button>
          </div>
        </article>
      </section>

      <section className="grid two-cols">
        <article className="card">
          <h2>Analytics Hook</h2>
          <p>Fetches `/api/v1/dashboard/cards` from your local backend DB for quick post-sync checks.</p>
          <div className="actions">
            <button disabled={busy} onClick={() => void handleLoadCards()}>Load dashboard cards</button>
          </div>
          <pre>{cardsResult ? prettyJson(cardsResult) : "No analytics loaded yet."}</pre>
        </article>

        <article className="card">
          <h2>Command Results</h2>
          <p><strong>One-time scrape</strong></p>
          <pre>{syncResult ? prettyJson(syncResult) : "No scrape executed yet."}</pre>
          <p><strong>Backup</strong></p>
          <pre>{backupResult ? prettyJson(backupResult) : "No backup executed yet."}</pre>
          <p><strong>Data export</strong></p>
          <pre>{exportResult ? prettyJson(exportResult) : "No export executed yet."}</pre>
          <p><strong>Restore</strong></p>
          <pre>{importResult ? prettyJson(importResult) : "No restore executed yet."}</pre>
        </article>
      </section>

      <section className="card">
        <h2>Runtime Logs</h2>
        <div className="logbox">
          {logs.length === 0 ? "No logs yet." : logs.map((entry, idx) => (
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
