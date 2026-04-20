import { app, BrowserWindow, dialog } from "electron";
import { randomBytes } from "node:crypto";
import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { homedir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import type {
  BackendConfig,
  BackendStatus,
  BackupRequest,
  CommandLogEvent,
  CommandResult,
  DesktopRuntimeDiagnostics,
  ConnectorCatalogEntry,
  ConnectorSourceId,
  DesktopReleaseMetadata,
  ExportRequest,
  ImportRequest,
  OcrWorkerWakeResult,
  ReceiptPluginCatalogInstallRequest,
  ReceiptPluginPackInfo,
  ReceiptPluginPackInstallResult,
  ReceiptPluginPackListResult,
  ReceiptPluginPackToggleResult,
  ReceiptPluginPackUninstallResult,
  SyncRequest
} from "@shared/contracts";
import { OcrWorkerSupervisor } from "./ocr-worker-supervisor";
import {
  ReceiptPluginPackManager,
  type ValidatedManifestSnapshot,
} from "./plugins/receipt-plugin-packs";
import { resolveDesktopReleaseContext, resolveDesktopReleaseMetadata } from "./release-metadata";
import { buildBackendServeArgs, normalizeDesktopOcrProvider } from "./runtime-contract";

const DEFAULT_PORT = 18765;

function resolveApiPort(defaultPort = DEFAULT_PORT): number {
  const rawPort = process.env.LIDLTOOL_DESKTOP_API_PORT?.trim();
  if (!rawPort) {
    return defaultPort;
  }

  const parsedPort = Number.parseInt(rawPort, 10);
  if (!Number.isInteger(parsedPort) || parsedPort <= 0 || parsedPort > 65535) {
    return defaultPort;
  }

  return parsedPort;
}

function nowIso(): string {
  return new Date().toISOString();
}

function splitLines(chunk: string): string[] {
  return chunk
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0);
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

interface StartBackendOptions {
  strictOverride?: boolean;
}

interface BackendEnvOptions {
  includePluginRuntimePolicy?: boolean;
}

interface BackendInvocation {
  command: string;
  argsPrefix: string[];
}

export class DesktopRuntime {
  private backendProcess: ChildProcessWithoutNullStreams | null = null;
  private backendStartedAt: string | null = null;
  private readonly apiPort: number;
  private readonly ocrWorkerSupervisor: OcrWorkerSupervisor;
  private readonly receiptPluginPackManager = new ReceiptPluginPackManager({
    rootDir: this.receiptPluginStorageDir(),
    validateManifest: async (manifestPath) => await this.validateReceiptPluginManifest(manifestPath)
  });

  constructor(port = resolveApiPort()) {
    this.apiPort = port;
    this.ocrWorkerSupervisor = new OcrWorkerSupervisor({
      buildLaunchSpec: async () => {
        const cfg = this.getConfig();
        const command = this.resolvePythonExecutable();
        const idleTimeoutSeconds = this.resolveOcrIdleTimeoutSeconds();
        return {
          command,
          args: [
            "-m",
            "lidltool.ingest.jobs",
            "--db",
            cfg.dbPath,
            "--config",
            this.resolveConfigFilePath(),
            "--poll-interval-s",
            "1.0",
            "--idle-exit-after-s",
            String(idleTimeoutSeconds),
          ],
          env: await this.backendProcessEnv(command),
          idleTimeoutSeconds,
        };
      },
      emitLog: (payload) => this.emitLog(payload),
    });
  }

  getConfig(): BackendConfig {
    const userDataDir = app.getPath("userData");
    mkdirSync(userDataDir, { recursive: true });

    return {
      apiBaseUrl: `http://127.0.0.1:${this.apiPort}`,
      dbPath: join(userDataDir, "lidltool.sqlite"),
      userDataDir,
      receiptPluginStorageDir: this.receiptPluginStorageDir()
    };
  }

  getBackendStatus(): BackendStatus {
    const invocation = this.resolveBackendInvocation(false);
    return {
      running: this.backendProcess !== null,
      pid: this.backendProcess?.pid ?? null,
      startedAt: this.backendStartedAt,
      command: [invocation.command, ...invocation.argsPrefix].join(" ")
    };
  }

  getRuntimeDiagnostics(): DesktopRuntimeDiagnostics {
    const frontendDistPath = this.resolveFrontendDist();
    const backendSourcePath = this.resolveRepoRootHint();
    const backendCommandSummary = this.inspectBackendCommand();
    const frontendReady = existsSync(frontendDistPath) && existsSync(join(frontendDistPath, "index.html"));

    return {
      environment: app.isPackaged ? "packaged" : "development",
      fullAppReady: frontendReady,
      frontendDistPath,
      frontendDistStatus: frontendReady ? "ready" : "missing",
      backendSourcePath,
      backendSourceStatus: existsSync(backendSourcePath) ? "ready" : "missing",
      backendCommand: backendCommandSummary.command,
      backendCommandSource: backendCommandSummary.source,
      backendCommandStatus: backendCommandSummary.status
    };
  }

  getFullAppUrl(): string {
    return this.getConfig().apiBaseUrl;
  }

  async getReleaseMetadata(): Promise<DesktopReleaseMetadata> {
    return await resolveDesktopReleaseMetadata({
      repoRootHint: this.resolveRepoRootHint(),
      requestedReleaseVariantId: process.env.LIDLTOOL_DESKTOP_RELEASE_VARIANT?.trim() || null,
      remoteCatalogUrl: this.resolveRemoteCatalogUrl(),
      trustedCatalogOverride: this.resolveTrustedCatalogOverride(),
      trustRootsOverride: this.resolveTrustRootsOverride()
    });
  }

  async startBackend(options: StartBackendOptions = {}): Promise<BackendStatus> {
    if (this.backendProcess !== null && this.backendProcess.pid === undefined) {
      this.backendProcess = null;
      this.backendStartedAt = null;
    }

    if (this.backendProcess !== null) {
      return this.getBackendStatus();
    }

    const cfg = this.getConfig();
    const invocation = this.resolveBackendInvocation(options.strictOverride ?? false);
    const command = invocation.command;
    const args = [...invocation.argsPrefix, ...buildBackendServeArgs(cfg.dbPath, this.apiPort)];
    const env = await this.backendProcessEnv(command);

    this.backendProcess = spawn(command, args, {
      env,
      stdio: "pipe"
    });
    this.backendStartedAt = nowIso();

    let spawnError: Error | null = null;
    this.backendProcess.on("error", (err) => {
      spawnError = err;
      this.backendProcess = null;
      this.backendStartedAt = null;
      this.emitLog({
        stream: "stderr",
        line: `backend spawn failed: ${String(err)}`,
        source: "backend"
      });
    });

    this.backendProcess.stdout.on("data", (chunk) => {
      for (const line of splitLines(chunk.toString("utf-8"))) {
        this.emitLog({ stream: "stdout", line, source: "backend" });
      }
    });

    this.backendProcess.stderr.on("data", (chunk) => {
      for (const line of splitLines(chunk.toString("utf-8"))) {
        this.emitLog({ stream: "stderr", line, source: "backend" });
      }
    });

    this.backendProcess.on("exit", () => {
      this.backendProcess = null;
      this.backendStartedAt = null;
    });

    try {
      // Surface invalid executable overrides quickly instead of waiting for health timeout.
      for (let attempts = 0; attempts < 10; attempts += 1) {
        if (spawnError) {
          break;
        }
        await sleep(50);
      }
      if (spawnError) {
        throw spawnError;
      }
      await this.waitUntilHealthy(cfg.apiBaseUrl, 20_000);
      return this.getBackendStatus();
    } catch (err) {
      if (spawnError) {
        if (app.isPackaged) {
          throw new Error(
            `Desktop could not start its local service from '${command}'. ${String(spawnError)}. ` +
              "This installation looks incomplete. Reinstall the app or use a build that includes the local runtime."
          );
        }
        throw new Error(
          `Failed to launch backend executable '${command}'. ${String(spawnError)}. ` +
            "Run `npm run backend:prepare` in apps/desktop or set LIDLTOOL_EXECUTABLE."
        );
      }
      throw err;
    }
  }

  async stopBackend(): Promise<BackendStatus> {
    await this.ocrWorkerSupervisor.stop();
    if (this.backendProcess === null) {
      return this.getBackendStatus();
    }

    const proc = this.backendProcess;
    proc.kill("SIGTERM");
    await sleep(500);
    if (this.backendProcess !== null) {
      this.backendProcess.kill("SIGKILL");
      this.backendProcess = null;
      this.backendStartedAt = null;
    }

    return this.getBackendStatus();
  }

  async wakeOcrWorker(): Promise<OcrWorkerWakeResult> {
    return await this.ocrWorkerSupervisor.ensureRunning();
  }

  async runSyncJob(payload: SyncRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const invocation = this.resolveBackendInvocation(false);
    const command = invocation.command;
    const args = [...invocation.argsPrefix, ...this.mapSyncArgs(payload, cfg.dbPath)];
    return await this.runCommand(command, args, "sync");
  }

  async runExportJob(payload: ExportRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const outPath = payload.outPath.trim();
    if (!outPath) {
      throw new Error("Export output path is required.");
    }
    const invocation = this.resolveBackendInvocation(false);
    const command = invocation.command;
    const args = [...invocation.argsPrefix, ...this.mapExportArgs(payload, cfg.dbPath)];
    return await this.runCommand(command, args, "export");
  }

  async runBackupJob(payload: BackupRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const outDirRaw = payload.outDir.trim();
    if (!outDirRaw) {
      throw new Error("Backup output directory is required.");
    }

    const backupDir = this.resolveUserPath(outDirRaw);
    mkdirSync(backupDir, { recursive: true });
    if (readdirSync(backupDir).length > 0) {
      throw new Error(`Backup output directory is not empty: ${backupDir}`);
    }

    const includeDocuments = payload.includeDocuments ?? true;
    const includeExportJson = payload.includeExportJson ?? true;
    const copied: string[] = [];
    const skipped: string[] = [];
    const now = nowIso();

    if (!existsSync(cfg.dbPath)) {
      throw new Error(`Database file was not found at ${cfg.dbPath}`);
    }

    const dbBackupPath = join(backupDir, "lidltool.sqlite");
    copyFileSync(cfg.dbPath, dbBackupPath);
    copied.push(dbBackupPath);
    this.emitLog({ stream: "stdout", source: "backup", line: `Copied DB -> ${dbBackupPath}` });

    const keyFile = join(cfg.userDataDir, "credential_encryption_key.txt");
    if (existsSync(keyFile)) {
      const keyBackupPath = join(backupDir, "credential_encryption_key.txt");
      copyFileSync(keyFile, keyBackupPath);
      copied.push(keyBackupPath);
      this.emitLog({ stream: "stdout", source: "backup", line: `Copied credential key -> ${keyBackupPath}` });
    } else {
      skipped.push("credential_encryption_key.txt (not found)");
    }

    const tokenFile = this.resolveTokenFilePath();
    if (existsSync(tokenFile)) {
      const tokenBackupPath = join(backupDir, "token.json");
      copyFileSync(tokenFile, tokenBackupPath);
      copied.push(tokenBackupPath);
      this.emitLog({ stream: "stdout", source: "backup", line: `Copied token file -> ${tokenBackupPath}` });
    } else {
      skipped.push(`token file (${tokenFile}) not found`);
    }

    if (includeDocuments) {
      const documentsSource = this.resolveDocumentsPath();
      if (existsSync(documentsSource)) {
        const documentsBackupPath = join(backupDir, "documents");
        cpSync(documentsSource, documentsBackupPath, { recursive: true });
        copied.push(documentsBackupPath);
        this.emitLog({ stream: "stdout", source: "backup", line: `Copied documents -> ${documentsBackupPath}` });
      } else {
        skipped.push(`documents (${documentsSource}) not found`);
      }
    }

    let exportResult: CommandResult | null = null;
    if (includeExportJson) {
      const invocation = this.resolveBackendInvocation(false);
      const command = invocation.command;
      const exportPath = join(backupDir, "receipts-export.json");
      const exportArgs = [...invocation.argsPrefix, ...this.mapExportArgs({ outPath: exportPath, format: "json" }, cfg.dbPath)];
      exportResult = await this.runCommand(command, exportArgs, "backup");
      if (exportResult.ok) {
        copied.push(exportPath);
      }
    }

    const manifestPath = join(backupDir, "backup-manifest.json");
    const manifest = {
      createdAt: now,
      backupDir,
      dbPath: cfg.dbPath,
      includeDocuments,
      includeExportJson,
      copied,
      skipped,
      exportResult: exportResult
        ? {
            ok: exportResult.ok,
            exitCode: exportResult.exitCode,
            stdout: exportResult.stdout,
            stderr: exportResult.stderr
          }
        : null
    };
    writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), "utf-8");
    copied.push(manifestPath);
    this.emitLog({ stream: "stdout", source: "backup", line: `Wrote backup manifest -> ${manifestPath}` });

    return {
      ok: exportResult ? exportResult.ok : true,
      command: "desktop:backup",
      args: [backupDir],
      exitCode: exportResult?.exitCode ?? 0,
      stdout: JSON.stringify({ backupDir, manifestPath, copied, skipped }, null, 2),
      stderr: exportResult?.stderr ?? ""
    };
  }

  async runImportJob(payload: ImportRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const backupDirRaw = payload.backupDir.trim();
    if (!backupDirRaw) {
      throw new Error("Backup directory is required.");
    }

    const backupDir = this.resolveUserPath(backupDirRaw);
    if (!existsSync(backupDir) || !statSync(backupDir).isDirectory()) {
      throw new Error(`Backup directory was not found: ${backupDir}`);
    }

    const includeDocuments = payload.includeDocuments ?? true;
    const includeToken = payload.includeToken ?? true;
    const includeCredentialKey = payload.includeCredentialKey ?? true;
    const restartBackend = payload.restartBackend ?? true;
    const copied: string[] = [];
    const skipped: string[] = [];
    const wasRunning = this.backendProcess !== null;

    if (wasRunning) {
      this.emitLog({ stream: "stdout", source: "restore", line: "Stopping backend before restore." });
      await this.stopBackend();
    }

    const dbSource = this.resolveDbArtifact(backupDir);
    if (!dbSource) {
      throw new Error(
        `No database artifact found in backup directory '${backupDir}'. Expected 'lidltool.sqlite' or 'db-backup-*.sqlite'.`
      );
    }
    mkdirSync(dirname(cfg.dbPath), { recursive: true });
    copyFileSync(dbSource, cfg.dbPath);
    copied.push(cfg.dbPath);
    this.emitLog({ stream: "stdout", source: "restore", line: `Restored DB <- ${dbSource}` });

    if (includeCredentialKey) {
      const keySource = this.resolveCredentialKeyArtifact(backupDir);
      const keyTarget = join(cfg.userDataDir, "credential_encryption_key.txt");
      if (keySource) {
        copyFileSync(keySource, keyTarget);
        copied.push(keyTarget);
        this.emitLog({ stream: "stdout", source: "restore", line: `Restored credential key <- ${keySource}` });
      } else {
        skipped.push("credential_encryption_key.txt not found in backup");
      }
    }

    if (includeToken) {
      const tokenSource = this.resolveTokenArtifact(backupDir);
      const tokenTarget = this.resolveTokenFilePath();
      if (tokenSource) {
        mkdirSync(dirname(tokenTarget), { recursive: true });
        copyFileSync(tokenSource, tokenTarget);
        copied.push(tokenTarget);
        this.emitLog({ stream: "stdout", source: "restore", line: `Restored token <- ${tokenSource}` });
      } else {
        skipped.push("token artifact not found in backup");
      }
    }

    if (includeDocuments) {
      const docsSource = this.resolveDocumentsArtifact(backupDir);
      const docsTarget = this.resolveDocumentsPath();
      if (docsSource) {
        rmSync(docsTarget, { recursive: true, force: true });
        mkdirSync(dirname(docsTarget), { recursive: true });
        cpSync(docsSource, docsTarget, { recursive: true });
        copied.push(docsTarget);
        this.emitLog({ stream: "stdout", source: "restore", line: `Restored documents <- ${docsSource}` });
      } else {
        skipped.push("documents artifact not found in backup");
      }
    }

    let backendStatus: BackendStatus | null = null;
    if (restartBackend) {
      backendStatus = await this.startBackend();
      this.emitLog({ stream: "stdout", source: "restore", line: "Backend restarted after restore." });
    }

    return {
      ok: true,
      command: "desktop:import",
      args: [backupDir],
      exitCode: 0,
      stdout: JSON.stringify(
        {
          backupDir,
          dbSource,
          copied,
          skipped,
          restartedBackend: restartBackend,
          backendRunning: backendStatus?.running ?? false
        },
        null,
        2
      ),
      stderr: ""
    };
  }

  async listReceiptPluginPacks(): Promise<ReceiptPluginPackListResult> {
    const releaseContext = await this.resolveReleaseContext();
    return await this.receiptPluginPackManager.listPacks({
      trustPolicy: releaseContext.trustPolicy,
      catalogEntries: releaseContext.metadata.discovery_catalog.entries
    });
  }

  async installReceiptPluginPackFromDialog(): Promise<ReceiptPluginPackInstallResult | null> {
    const result = await dialog.showOpenDialog({
      properties: ["openFile"],
      filters: [
        { name: "Receipt Plugin Packs", extensions: ["zip", "lidltool-plugin"] },
        { name: "All Files", extensions: ["*"] }
      ]
    });
    const filePath = result.filePaths[0];
    if (result.canceled || !filePath) {
      return null;
    }
    return await this.installReceiptPluginPackFromFile(filePath);
  }

  async installReceiptPluginPackFromFile(filePath: string): Promise<ReceiptPluginPackInstallResult> {
    const releaseContext = await this.resolveReleaseContext();
    const installResult = await this.receiptPluginPackManager.installFromFile(filePath, {
      installSource: "manual_file",
      trustPolicy: releaseContext.trustPolicy,
      catalogEntries: releaseContext.metadata.discovery_catalog.entries
    });
    const restart = installResult.pack.enabled;
    const backendStatus = restart ? await this.restartBackendForPluginChange() : null;
    return {
      action: installResult.action,
      pack: installResult.pack,
      restartedBackend: restart,
      backendStatus
    };
  }

  async installReceiptPluginPackFromCatalogEntry(
    payload: ReceiptPluginCatalogInstallRequest
  ): Promise<ReceiptPluginPackInstallResult> {
    const releaseContext = await this.resolveReleaseContext();
    const entry = this.findCatalogDesktopPackEntry(releaseContext.metadata.discovery_catalog.entries, payload.entryId);
    const installResult = await this.receiptPluginPackManager.installFromUrl(entry, {
      trustPolicy: releaseContext.trustPolicy,
      catalogEntries: releaseContext.metadata.discovery_catalog.entries
    });
    const restart = installResult.pack.enabled;
    const backendStatus = restart ? await this.restartBackendForPluginChange() : null;
    return {
      action: installResult.action,
      pack: installResult.pack,
      restartedBackend: restart,
      backendStatus
    };
  }

  async setReceiptPluginPackEnabled(
    pluginId: string,
    enabled: boolean
  ): Promise<ReceiptPluginPackToggleResult> {
    const releaseContext = await this.resolveReleaseContext();
    const pack = await this.receiptPluginPackManager.setEnabled(pluginId, enabled, {
      trustPolicy: releaseContext.trustPolicy,
      catalogEntries: releaseContext.metadata.discovery_catalog.entries
    });
    const backendStatus = await this.restartBackendForPluginChange();
    const refreshed = await this.findReceiptPluginPack(pack.pluginId);
    return {
      pack: refreshed ?? pack,
      restartedBackend: backendStatus !== null,
      backendStatus
    };
  }

  async uninstallReceiptPluginPack(pluginId: string): Promise<ReceiptPluginPackUninstallResult> {
    const { removedPath } = await this.receiptPluginPackManager.uninstall(pluginId);
    const backendStatus = await this.restartBackendForPluginChange();
    return {
      pluginId,
      removedPath,
      restartedBackend: backendStatus !== null,
      backendStatus
    };
  }

  async shutdown(): Promise<void> {
    await this.ocrWorkerSupervisor.stop();
    await this.stopBackend();
  }

  private mapSyncArgs(payload: SyncRequest, dbPath: string): string[] {
    const globalOptions: string[] = ["--db", dbPath, "--json", "connectors", "sync", "--source-id", payload.source];
    return [...globalOptions, ...this.connectorArgs(payload.source, payload)];
  }

  private connectorArgs(source: ConnectorSourceId, payload: SyncRequest): string[] {
    const args: string[] = [];

    if (source.startsWith("lidl_plus_")) {
      if (payload.full) {
        args.push("--full");
      }
      return args;
    }

    const headless = payload.headless ?? true;
    args.push("--option", `headless=${headless ? "true" : "false"}`);

    if (payload.domain?.trim()) {
      args.push("--option", `domain=${payload.domain.trim()}`);
    }

    if (source.startsWith("amazon_")) {
      if (payload.years && payload.years > 0) {
        args.push("--option", `years=${String(payload.years)}`);
      }
      if (payload.maxPages && payload.maxPages > 0) {
        args.push("--option", `max_pages_per_year=${String(payload.maxPages)}`);
      }
      return args;
    }

    if (payload.maxPages && payload.maxPages > 0) {
      args.push("--option", `max_pages=${String(payload.maxPages)}`);
    }

    return args;
  }

  private mapExportArgs(payload: ExportRequest, dbPath: string): string[] {
    const formatName = payload.format ?? "json";
    return ["--db", dbPath, "--json", "export", "--out", payload.outPath.trim(), "--format", formatName];
  }

  private resolveDesktopConfigDir(): string {
    return join(this.getConfig().userDataDir, "config");
  }

  private resolveConfigDirPath(): string {
    const configDirRaw = process.env.LIDLTOOL_CONFIG_DIR?.trim();
    if (configDirRaw) {
      return this.resolveUserPath(configDirRaw);
    }
    return this.resolveDesktopConfigDir();
  }

  private resolveConfigFilePath(): string {
    return join(this.resolveConfigDirPath(), "config.toml");
  }

  private resolveTokenFilePath(): string {
    return join(this.resolveConfigDirPath(), "token.json");
  }

  private resolveDocumentsPath(): string {
    const documentsPathRaw = process.env.LIDLTOOL_DOCUMENT_STORAGE_PATH?.trim();
    if (documentsPathRaw) {
      return this.resolveUserPath(documentsPathRaw);
    }
    return join(this.getConfig().userDataDir, "documents");
  }

  private resolveUserPath(value: string): string {
    if (value === "~") {
      return homedir();
    }
    if (value.startsWith("~/") || value.startsWith("~\\")) {
      return resolve(homedir(), value.slice(2));
    }
    return resolve(value);
  }

  private resolveDbArtifact(backupDir: string): string | null {
    const manifest = this.readBackupManifest(backupDir);
    const manifestCandidate = this.resolveManifestArtifactCandidate(backupDir, manifest, [
      "db_artifact",
      "dbArtifact"
    ]);
    if (manifestCandidate) {
      return manifestCandidate;
    }
    const direct = this.resolveBackupArtifact(backupDir, "lidltool.sqlite");
    if (direct) {
      return direct;
    }
    const timestamped = this.resolveLatestPatternMatch(backupDir, /^db-backup-.*\.sqlite$/);
    if (timestamped) {
      return timestamped;
    }
    return this.resolveLatestPatternMatch(backupDir, /\.sqlite$/);
  }

  private resolveTokenArtifact(backupDir: string): string | null {
    const manifest = this.readBackupManifest(backupDir);
    const manifestCandidate = this.resolveManifestArtifactCandidate(backupDir, manifest, [
      "token_artifact",
      "tokenArtifact"
    ]);
    if (manifestCandidate) {
      return manifestCandidate;
    }
    const direct = this.resolveBackupArtifact(backupDir, "token.json");
    if (direct) {
      return direct;
    }
    return this.resolveLatestPatternMatch(backupDir, /^token-backup-.*\.json$/);
  }

  private resolveDocumentsArtifact(backupDir: string): string | null {
    const manifest = this.readBackupManifest(backupDir);
    const manifestCandidate = this.resolveManifestArtifactCandidate(backupDir, manifest, [
      "documents_artifact",
      "documentsArtifact"
    ]);
    if (manifestCandidate && statSync(manifestCandidate).isDirectory()) {
      return manifestCandidate;
    }
    const direct = this.resolveBackupArtifact(backupDir, "documents");
    if (direct && statSync(direct).isDirectory()) {
      return direct;
    }
    const pattern = this.resolveLatestPatternMatch(backupDir, /^documents-backup-.*/);
    if (pattern && statSync(pattern).isDirectory()) {
      return pattern;
    }
    return null;
  }

  private resolveCredentialKeyArtifact(backupDir: string): string | null {
    const manifest = this.readBackupManifest(backupDir);
    const manifestCandidate = this.resolveManifestArtifactCandidate(backupDir, manifest, [
      "credential_key_artifact",
      "credentialKeyArtifact"
    ]);
    if (manifestCandidate) {
      return manifestCandidate;
    }
    return this.resolveBackupArtifact(backupDir, "credential_encryption_key.txt");
  }

  private readBackupManifest(backupDir: string): Record<string, unknown> | null {
    const manifestPath = join(backupDir, "backup-manifest.json");
    if (!existsSync(manifestPath)) {
      return null;
    }
    try {
      const parsed = JSON.parse(readFileSync(manifestPath, "utf-8"));
      if (parsed && typeof parsed === "object") {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return null;
    }
    return null;
  }

  private resolveManifestArtifactCandidate(
    backupDir: string,
    manifest: Record<string, unknown> | null,
    keys: string[]
  ): string | null {
    if (!manifest) {
      return null;
    }
    for (const key of keys) {
      const value = manifest[key];
      if (typeof value !== "string" || !value.trim()) {
        continue;
      }
      const direct = this.resolveUserPath(value.trim());
      if (existsSync(direct)) {
        return direct;
      }
      const moved = join(backupDir, basename(value.trim()));
      if (existsSync(moved)) {
        return moved;
      }
    }
    return null;
  }

  private resolveBackupArtifact(backupDir: string, fileName: string): string | null {
    const candidate = join(backupDir, fileName);
    return existsSync(candidate) ? candidate : null;
  }

  private resolveLatestPatternMatch(backupDir: string, pattern: RegExp): string | null {
    const matches = readdirSync(backupDir)
      .filter((entry) => pattern.test(entry))
      .sort()
      .reverse();
    for (const entry of matches) {
      const candidate = join(backupDir, entry);
      if (existsSync(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  private async runCommand(
    command: string,
    args: string[],
    source: CommandLogEvent["source"]
  ): Promise<CommandResult> {
    const env = await this.backendProcessEnv(command);

    return await new Promise<CommandResult>((resolve, reject) => {
      const proc = spawn(command, args, {
        env,
        stdio: "pipe"
      });

      let stdout = "";
      let stderr = "";

      proc.on("error", (err) => {
        reject(err);
      });

      proc.stdout.on("data", (chunk) => {
        const text = chunk.toString("utf-8");
        stdout += text;
        for (const line of splitLines(text)) {
          this.emitLog({ stream: "stdout", line, source });
        }
      });

      proc.stderr.on("data", (chunk) => {
        const text = chunk.toString("utf-8");
        stderr += text;
        for (const line of splitLines(text)) {
          this.emitLog({ stream: "stderr", line, source });
        }
      });

      proc.on("close", (code) => {
        resolve({
          ok: code === 0,
          command,
          args,
          exitCode: code,
          stdout: stdout.trim(),
          stderr: stderr.trim()
        });
      });
    });
  }

  private async runCommandCapture(
    command: string,
    args: string[],
    options: BackendEnvOptions = {}
  ): Promise<CommandResult> {
    const env = await this.backendProcessEnv(command, options);

    return await new Promise<CommandResult>((resolve, reject) => {
      const proc = spawn(command, args, {
        env,
        stdio: "pipe"
      });

      let stdout = "";
      let stderr = "";

      proc.on("error", (err) => {
        reject(err);
      });

      proc.stdout.on("data", (chunk) => {
        stdout += chunk.toString("utf-8");
      });

      proc.stderr.on("data", (chunk) => {
        stderr += chunk.toString("utf-8");
      });

      proc.on("close", (code) => {
        resolve({
          ok: code === 0,
          command,
          args,
          exitCode: code,
          stdout: stdout.trim(),
          stderr: stderr.trim()
        });
      });
    });
  }

  private async waitUntilHealthy(baseUrl: string, timeoutMs: number): Promise<void> {
    const deadline = Date.now() + timeoutMs;
    let lastErr: unknown;

    while (Date.now() < deadline) {
      try {
        const response = await fetch(`${baseUrl}/api/v1/health`);
        if (response.ok) {
          return;
        }
      } catch (err) {
        lastErr = err;
      }
      await sleep(350);
    }

    throw new Error(`Backend did not become healthy in ${timeoutMs}ms. Last error: ${String(lastErr)}`);
  }

  private emitLog(payload: Omit<CommandLogEvent, "timestamp">): void {
    const eventPayload = {
      ...payload,
      timestamp: nowIso()
    } satisfies CommandLogEvent;

    for (const window of BrowserWindow.getAllWindows()) {
      window.webContents.send("desktop:log", eventPayload);
    }
  }

  private async backendProcessEnv(command: string, options: BackendEnvOptions = {}): Promise<NodeJS.ProcessEnv> {
    const cfg = this.getConfig();
    const env: NodeJS.ProcessEnv = { ...process.env };
    const repoRootHint = this.resolveRepoRootHint();
    const configDir = this.resolveConfigDirPath();
    const documentsPath = this.resolveDocumentsPath();
    env.LIDLTOOL_FRONTEND_DIST = this.resolveFrontendDist();
    env.LIDLTOOL_REPO_ROOT = repoRootHint;
    env.LIDLTOOL_DB = cfg.dbPath;
    env.LIDLTOOL_CONFIG_DIR = configDir;
    env.LIDLTOOL_DOCUMENT_STORAGE_PATH = documentsPath;
    env.LIDLTOOL_DESKTOP_MODE = "true";
    env.LIDLTOOL_CONNECTOR_HOST_KIND = "electron";
    env.LIDLTOOL_OCR_DEFAULT_PROVIDER = normalizeDesktopOcrProvider(env.LIDLTOOL_OCR_DEFAULT_PROVIDER);
    env.LIDLTOOL_OCR_FALLBACK_ENABLED = env.LIDLTOOL_OCR_FALLBACK_ENABLED || "false";
    env.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY =
      env.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY || this.resolveCredentialEncryptionKey(cfg.userDataDir);
    if (!env.LIDLTOOL_AUTH_BROWSER_MODE && app.isPackaged && (process.platform === "darwin" || process.platform === "win32")) {
      env.LIDLTOOL_AUTH_BROWSER_MODE = "local_display";
    }
    if (app.isPackaged) {
      const packagedSrc = join(repoRootHint, "src");
      env.PYTHONPATH = env.PYTHONPATH?.trim() ? `${packagedSrc}:${env.PYTHONPATH}` : packagedSrc;
    }
    if (options.includePluginRuntimePolicy === false) {
      env.LIDLTOOL_CONNECTOR_PLUGIN_PATHS = "";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED = "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED = "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED = "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES = "";
    } else {
      const releaseContext = await this.resolveReleaseContext();
      const runtimePolicy = await this.receiptPluginPackManager.getRuntimePolicy({
        trustPolicy: releaseContext.trustPolicy,
        catalogEntries: releaseContext.metadata.discovery_catalog.entries
      });
      env.LIDLTOOL_CONNECTOR_PLUGIN_PATHS = runtimePolicy.activePluginSearchPaths.join(",");
      env.LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED = runtimePolicy.activePluginSearchPaths.length > 0 ? "true" : "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED =
        runtimePolicy.activePluginSearchPaths.length > 0 ? "true" : "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED = "false";
      env.LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES = runtimePolicy.allowedTrustClasses.join(",");
    }
    if (!env.PLAYWRIGHT_BROWSERS_PATH && this.shouldUseInVenvPlaywrightBrowsers(command)) {
      env.PLAYWRIGHT_BROWSERS_PATH = "0";
    }
    return env;
  }

  private shouldUseInVenvPlaywrightBrowsers(command: string): boolean {
    const normalized = command.replaceAll("\\", "/");
    return normalized.includes("/backend-venv/") || normalized.includes("/.backend/venv/");
  }

  private resolveCredentialEncryptionKey(userDataDir: string): string {
    const keyFile = join(userDataDir, "credential_encryption_key.txt");
    if (existsSync(keyFile)) {
      const existing = readFileSync(keyFile, "utf-8").trim();
      if (existing.length >= 32) {
        return existing;
      }
    }

    const generated = randomBytes(32).toString("hex");
    writeFileSync(keyFile, `${generated}\n`, { encoding: "utf-8", mode: 0o600 });
    return generated;
  }

  private receiptPluginStorageDir(): string {
    return join(app.getPath("userData"), "plugins", "receipt-packs");
  }

  private async restartBackendForPluginChange(): Promise<BackendStatus | null> {
    const wasRunning = this.backendProcess !== null;
    if (!wasRunning) {
      return null;
    }
    await this.stopBackend();
    return await this.startBackend();
  }

  private async findReceiptPluginPack(pluginId: string): Promise<ReceiptPluginPackInfo | null> {
    const releaseContext = await this.resolveReleaseContext();
    const packs = await this.receiptPluginPackManager.listPacks({
      trustPolicy: releaseContext.trustPolicy,
      catalogEntries: releaseContext.metadata.discovery_catalog.entries
    });
    return packs.packs.find((pack) => pack.pluginId === pluginId) ?? null;
  }

  private async resolveReleaseContext() {
    return await resolveDesktopReleaseContext({
      repoRootHint: this.resolveRepoRootHint(),
      requestedReleaseVariantId: process.env.LIDLTOOL_DESKTOP_RELEASE_VARIANT?.trim() || null,
      remoteCatalogUrl: this.resolveRemoteCatalogUrl(),
      trustedCatalogOverride: this.resolveTrustedCatalogOverride(),
      trustRootsOverride: this.resolveTrustRootsOverride()
    });
  }

  private async validateReceiptPluginManifest(manifestPath: string): Promise<ValidatedManifestSnapshot> {
    const command = this.resolvePythonExecutable();
    const script = `
import json
import sys
from pathlib import Path

import lidltool
from lidltool.connectors.plugin_policy import evaluate_plugin_compatibility
from lidltool.connectors.sdk.manifest import ConnectorManifest

manifest = ConnectorManifest.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
compatibility = evaluate_plugin_compatibility(manifest, host_kind="electron", core_version=lidltool.__version__)
print(json.dumps({
    "pluginId": manifest.plugin_id,
    "sourceId": manifest.source_id,
    "displayName": manifest.display_name,
    "pluginVersion": manifest.plugin_version,
    "pluginFamily": manifest.plugin_family,
    "runtimeKind": manifest.runtime_kind,
    "pluginOrigin": manifest.plugin_origin,
    "trustClass": manifest.trust_class,
    "entrypoint": manifest.entrypoint,
    "supportedHostKinds": list(manifest.compatibility.supported_host_kinds),
    "minCoreVersion": manifest.compatibility.min_core_version,
    "maxCoreVersion": manifest.compatibility.max_core_version,
    "compatibilityStatus": "compatible" if compatibility.compatible else "incompatible",
    "compatibilityReason": compatibility.reason,
    "onboarding": {
        "title": manifest.onboarding.title if manifest.onboarding else None,
        "summary": manifest.onboarding.summary if manifest.onboarding else None,
        "expectedSpeed": manifest.onboarding.expected_speed if manifest.onboarding else None,
        "caution": manifest.onboarding.caution if manifest.onboarding else None,
        "steps": [
            {
                "title": step.title,
                "description": step.description,
            }
            for step in (manifest.onboarding.steps if manifest.onboarding else [])
        ],
    } if manifest.onboarding else None,
}))
`.trim();
    const result = await this.runCommandCapture(command, ["-c", script, manifestPath], {
      includePluginRuntimePolicy: false
    });
    if (!result.ok) {
      throw new Error(result.stderr || result.stdout || "Manifest validation failed.");
    }
    try {
      return JSON.parse(result.stdout) as ValidatedManifestSnapshot;
    } catch (error) {
      throw new Error(`Manifest validation returned invalid JSON: ${String(error)}`);
    }
  }

  private resolveRepoRootHint(): string {
    const override = process.env.LIDLTOOL_REPO_ROOT?.trim();
    if (override) {
      return override;
    }

    if (app.isPackaged) {
      return join(process.resourcesPath, "backend-src");
    }

    return resolve(app.getAppPath(), "vendor", "backend");
  }

  private resolveRemoteCatalogUrl(): string | null {
    const raw = process.env.LIDLTOOL_DESKTOP_CATALOG_URL?.trim();
    return raw ? raw : null;
  }

  private resolveTrustRootsOverride(): unknown | undefined {
    return this.readJsonOverrideFromPath("LIDLTOOL_DESKTOP_TRUST_ROOTS_PATH", "Desktop trust roots override");
  }

  private resolveTrustedCatalogOverride(): unknown | undefined {
    return this.readJsonOverrideFromPath("LIDLTOOL_DESKTOP_TRUSTED_CATALOG_PATH", "Desktop trusted catalog override");
  }

  private readJsonOverrideFromPath(envName: string, label: string): unknown | undefined {
    const overridePath = process.env[envName]?.trim();
    if (!overridePath) {
      return undefined;
    }
    try {
      return JSON.parse(readFileSync(overridePath, "utf-8"));
    } catch (error) {
      throw new Error(`${label} could not be loaded from ${overridePath}. ${String(error)}`);
    }
  }

  private findCatalogDesktopPackEntry(
    entries: DesktopReleaseMetadata["discovery_catalog"]["entries"],
    entryId: string
  ): ConnectorCatalogEntry {
    const entry = entries.find((candidate) => candidate.entry_id === entryId);
    if (!entry || entry.entry_type !== "desktop_pack") {
      throw new Error(`Trusted desktop pack catalog entry was not found: ${entryId}`);
    }
    if (entry.availability.blocked_by_policy) {
      throw new Error(entry.availability.block_reason ?? `Catalog entry ${entryId} is blocked.`);
    }
    if (entry.install_methods.includes("download_url") === false || !entry.download_url) {
      throw new Error(`Catalog entry ${entryId} does not support trusted URL install.`);
    }
    return entry;
  }

  private resolveFrontendDist(): string {
    const override = process.env.LIDLTOOL_FRONTEND_DIST?.trim();
    if (override) {
      return override;
    }

    if (app.isPackaged) {
      return join(process.resourcesPath, "frontend-dist");
    }

    return resolve(app.getAppPath(), "vendor", "frontend", "dist");
  }

  private inspectBackendCommand(): {
    command: string;
    source: DesktopRuntimeDiagnostics["backendCommandSource"];
    status: DesktopRuntimeDiagnostics["backendCommandStatus"];
  } {
    const override = process.env.LIDLTOOL_EXECUTABLE?.trim();
    if (override) {
      if (this.isPathLike(override)) {
        return {
          command: override,
          source: "env_override",
          status: existsSync(override) ? "ready" : "missing"
        };
      }
      return {
        command: override,
        source: "env_override",
        status: "lookup"
      };
    }

    if (app.isPackaged) {
      const bundledPython = this.resolvePythonExecutable();
      if (this.isPathLike(bundledPython) && existsSync(bundledPython)) {
        return {
          command: `${bundledPython} -m lidltool.cli`,
          source: "bundled",
          status: "ready"
        };
      }
    }

    const bundledExecutable = this.resolveBundledExecutable();
    if (bundledExecutable) {
      return {
        command: bundledExecutable,
        source: "bundled",
        status: "ready"
      };
    }

    const managedDevExecutable = this.resolveManagedDevExecutable();
    if (managedDevExecutable) {
      return {
        command: managedDevExecutable,
        source: "managed_dev",
        status: "ready"
      };
    }

    return {
      command: process.platform === "win32" ? "lidltool.exe" : "lidltool",
      source: "path_lookup",
      status: "lookup"
    };
  }

  private resolveBackendInvocation(strictOverride: boolean): BackendInvocation {
    const override = process.env.LIDLTOOL_EXECUTABLE?.trim();
    if (override) {
      if (strictOverride || !this.isPathLike(override) || existsSync(override)) {
        return { command: override, argsPrefix: [] };
      }
    }

    if (app.isPackaged) {
      const bundledPython = this.resolvePythonExecutable();
      if (this.isPathLike(bundledPython) && existsSync(bundledPython)) {
        return {
          command: bundledPython,
          argsPrefix: ["-m", "lidltool.cli"]
        };
      }
    }

    const bundledExecutable = this.resolveBundledExecutable();
    if (bundledExecutable) {
      return { command: bundledExecutable, argsPrefix: [] };
    }

    const managedDevExecutable = this.resolveManagedDevExecutable();
    if (managedDevExecutable) {
      return { command: managedDevExecutable, argsPrefix: [] };
    }

    return {
      command: process.platform === "win32" ? "lidltool.exe" : "lidltool",
      argsPrefix: []
    };
  }

  private resolveLidltoolExecutable(strictOverride: boolean): string {
    return this.resolveBackendInvocation(strictOverride).command;
  }

  private resolvePythonExecutable(): string {
    if (app.isPackaged) {
      const bundled =
        process.platform === "win32"
          ? join(process.resourcesPath, "backend-venv", "Scripts", "python.exe")
          : join(process.resourcesPath, "backend-venv", "bin", "python");
      if (existsSync(bundled)) {
        return bundled;
      }
    }

    const managedDev =
      process.platform === "win32"
        ? join(app.getAppPath(), ".backend", "venv", "Scripts", "python.exe")
        : join(app.getAppPath(), ".backend", "venv", "bin", "python");
    if (existsSync(managedDev)) {
      return managedDev;
    }

    return process.platform === "win32" ? "python" : "python3";
  }

  private isPathLike(command: string): boolean {
    return command.startsWith(".") || command.startsWith("/") || command.includes("\\") || command.includes("/");
  }

  private resolveBundledExecutable(): string | null {
    if (!app.isPackaged) {
      return null;
    }

    const candidate =
      process.platform === "win32"
        ? join(process.resourcesPath, "backend-venv", "Scripts", "lidltool.exe")
        : join(process.resourcesPath, "backend-venv", "bin", "lidltool");

    return existsSync(candidate) ? candidate : null;
  }

  private resolveManagedDevExecutable(): string | null {
    if (app.isPackaged) {
      return null;
    }

    const candidate =
      process.platform === "win32"
        ? join(app.getAppPath(), ".backend", "venv", "Scripts", "lidltool.exe")
        : join(app.getAppPath(), ".backend", "venv", "bin", "lidltool");

    return existsSync(candidate) ? candidate : null;
  }

  private resolveOcrIdleTimeoutSeconds(): number {
    const raw = process.env.LIDLTOOL_DESKTOP_OCR_IDLE_TIMEOUT_S?.trim();
    if (!raw) {
      return 600;
    }
    const parsed = Number.parseInt(raw, 10);
    if (!Number.isFinite(parsed) || parsed < 60) {
      return 600;
    }
    return parsed;
  }
}
