import { app, BrowserWindow, dialog } from "electron";
import { copyFileSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { basename, dirname, join, resolve } from "node:path";
import type {
  BackendConfig,
  BackendStatus,
  BackupRequest,
  CommandLogEvent,
  CommandResult,
  DesktopRuntimeDiagnostics,
  ConnectorCatalogEntry,
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
import { buildBackendServeArgs } from "./runtime-contract";
import { buildExportArgs, buildSyncArgs } from "./runtime-cli-args";
import {
  resolveCredentialKeyArtifact,
  resolveDbArtifact,
  resolveDocumentsArtifact,
  resolveTokenArtifact
} from "./runtime-backup-artifacts";
import {
  applyPluginRuntimePolicyToEnv,
  buildDesktopBackendEnv,
  ensureManagedPlaywrightBrowsers,
  resolveCredentialEncryptionKey
} from "./runtime-backend-env";
import {
  nowIso,
  runCommandCapture,
  runCommandWithLogs,
  splitLines,
  waitUntilHealthy
} from "./runtime-command-runner";
import {
  findCatalogDesktopPackEntry,
  inspectBackendCommand,
  isPathLike,
  readJsonOverrideFromPath,
  resolveBackendInvocation,
  resolveConfigDirPath,
  resolveConfigFilePath,
  resolveDesktopConfigDir,
  resolveBundledExecutable,
  resolveDocumentsPath,
  resolveFrontendDist,
  resolveManagedDevExecutable,
  resolveOcrIdleTimeoutSeconds,
  resolvePythonExecutable,
  resolveRemoteCatalogUrl,
  resolveRepoRootHint,
  resolveTokenFilePath,
  resolveTrustedCatalogOverride,
  resolveTrustRootsOverride,
  resolveUserPath,
  type BackendInvocation,
  type RuntimePathContext
} from "./runtime-paths";
import {
  copySqliteArtifact,
  describeSqliteSnapshotMismatch,
  snapshotSqliteArtifact,
  type SqliteArtifactSnapshot
} from "./sqlite-artifacts";

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

interface StartBackendOptions {
  strictOverride?: boolean;
}

interface BackendEnvOptions {
  includePluginRuntimePolicy?: boolean;
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

  private runtimePathContext(): RuntimePathContext {
    return {
      appPath: app.getAppPath(),
      resourcesPath: process.resourcesPath,
      isPackaged: app.isPackaged,
      homeDir: app.getPath("home"),
      platform: process.platform
    };
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
        await new Promise((resolvePromise) => setTimeout(resolvePromise, 50));
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
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 500));
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
    const args = [...invocation.argsPrefix, ...buildSyncArgs(payload, cfg.dbPath)];
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
    const args = [...invocation.argsPrefix, ...buildExportArgs(payload, cfg.dbPath)];
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
    const sqliteHelper = await this.sqliteHelperContext();
    const liveSnapshot = await snapshotSqliteArtifact(cfg.dbPath, sqliteHelper);
    await copySqliteArtifact(cfg.dbPath, dbBackupPath, sqliteHelper);
    const backupSnapshot = await snapshotSqliteArtifact(dbBackupPath, sqliteHelper);
    this.assertMatchingSqliteSnapshots({
      expected: liveSnapshot,
      actual: backupSnapshot,
      action: "backup verification",
      expectedLabel: "live database",
      actualLabel: "backup artifact"
    });
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
      const exportArgs = [...invocation.argsPrefix, ...buildExportArgs({ outPath: exportPath, format: "json" }, cfg.dbPath)];
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
      stdout: JSON.stringify(
        {
          backupDir,
          manifestPath,
          copied,
          skipped,
          verification: {
            liveDbPath: cfg.dbPath,
            liveDbSnapshot: liveSnapshot,
            backupDbSnapshot: backupSnapshot
          }
        },
        null,
        2
      ),
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

    const dbSource = resolveDbArtifact(backupDir, (value) => this.resolveUserPath(value));
    if (!dbSource) {
      throw new Error(
        `No database artifact found in backup directory '${backupDir}'. Expected 'lidltool.sqlite' or 'db-backup-*.sqlite'.`
      );
    }
    const sqliteHelper = await this.sqliteHelperContext();
    const sourceSnapshot = await snapshotSqliteArtifact(dbSource, sqliteHelper);
    const tempRestorePath = join(
      dirname(cfg.dbPath),
      `.restore-${Date.now()}-${basename(cfg.dbPath)}`
    );
    mkdirSync(dirname(cfg.dbPath), { recursive: true });
    await copySqliteArtifact(dbSource, tempRestorePath, sqliteHelper);
    const stagedSnapshot = await snapshotSqliteArtifact(tempRestorePath, sqliteHelper);
    this.assertMatchingSqliteSnapshots({
      expected: sourceSnapshot,
      actual: stagedSnapshot,
      action: "restore staging verification",
      expectedLabel: "backup artifact",
      actualLabel: "staged restore"
    });
    this.removeSqliteSidecars(cfg.dbPath);
    rmSync(cfg.dbPath, { force: true });
    renameSync(tempRestorePath, cfg.dbPath);
    rmSync(tempRestorePath, { force: true });
    const liveSnapshot = await snapshotSqliteArtifact(cfg.dbPath, sqliteHelper);
    this.assertMatchingSqliteSnapshots({
      expected: sourceSnapshot,
      actual: liveSnapshot,
      action: "restore verification",
      expectedLabel: "backup artifact",
      actualLabel: "live database"
    });
    copied.push(cfg.dbPath);
    this.emitLog({ stream: "stdout", source: "restore", line: `Restored DB <- ${dbSource}` });

    if (includeCredentialKey) {
      const keySource = resolveCredentialKeyArtifact(backupDir, (value) => this.resolveUserPath(value));
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
      const tokenSource = resolveTokenArtifact(backupDir, (value) => this.resolveUserPath(value));
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
      const docsSource = resolveDocumentsArtifact(backupDir, (value) => this.resolveUserPath(value));
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
          liveDbPath: cfg.dbPath,
          copied,
          skipped,
          restartedBackend: restartBackend,
          backendRunning: backendStatus?.running ?? false,
          verification: {
            backupDbSnapshot: sourceSnapshot,
            liveDbSnapshot: liveSnapshot
          }
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
    if (installResult.pack.status === "disabled") {
      installResult.pack = await this.receiptPluginPackManager.setEnabled(installResult.pack.pluginId, true, {
        trustPolicy: releaseContext.trustPolicy,
        catalogEntries: releaseContext.metadata.discovery_catalog.entries
      });
    }
    const backendStatus = await this.restartBackendForPluginChange();
    return {
      action: installResult.action,
      pack: installResult.pack,
      restartedBackend: backendStatus !== null,
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
    if (installResult.pack.status === "disabled") {
      installResult.pack = await this.receiptPluginPackManager.setEnabled(installResult.pack.pluginId, true, {
        trustPolicy: releaseContext.trustPolicy,
        catalogEntries: releaseContext.metadata.discovery_catalog.entries
      });
    }
    const backendStatus = await this.restartBackendForPluginChange();
    return {
      action: installResult.action,
      pack: installResult.pack,
      restartedBackend: backendStatus !== null,
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

  private resolveDesktopConfigDir(): string {
    return resolveDesktopConfigDir(this.getConfig().userDataDir);
  }

  private resolveConfigDirPath(): string {
    return resolveConfigDirPath(this.getConfig().userDataDir, process.env, this.runtimePathContext().homeDir);
  }

  private resolveConfigFilePath(): string {
    return resolveConfigFilePath(this.getConfig().userDataDir, process.env, this.runtimePathContext().homeDir);
  }

  private resolveTokenFilePath(): string {
    return resolveTokenFilePath(this.getConfig().userDataDir, process.env, this.runtimePathContext().homeDir);
  }

  private resolveDocumentsPath(): string {
    return resolveDocumentsPath(this.getConfig().userDataDir, process.env, this.runtimePathContext().homeDir);
  }

  private resolveUserPath(value: string): string {
    return resolveUserPath(value, this.runtimePathContext().homeDir);
  }

  private async sqliteHelperContext(): Promise<{
    pythonExecutable: string;
    env: NodeJS.ProcessEnv;
  }> {
    const pythonExecutable = this.resolvePythonExecutable();
    const env = await this.backendProcessEnv(pythonExecutable, {
      includePluginRuntimePolicy: false
    });
    return { pythonExecutable, env };
  }

  private assertMatchingSqliteSnapshots(args: {
    expected: SqliteArtifactSnapshot;
    actual: SqliteArtifactSnapshot;
    action: string;
    expectedLabel: string;
    actualLabel: string;
  }): void {
    const mismatches = describeSqliteSnapshotMismatch(args.expected, args.actual);
    if (mismatches.length === 0) {
      return;
    }
    throw new Error(
      `${args.action} failed: ${mismatches.join("; ")}. ` +
        `${args.expectedLabel}: ${args.expected.path}. ${args.actualLabel}: ${args.actual.path}.`
    );
  }

  private removeSqliteSidecars(dbPath: string): void {
    rmSync(`${dbPath}-shm`, { force: true });
    rmSync(`${dbPath}-wal`, { force: true });
  }

  private async runCommand(
    command: string,
    args: string[],
    source: CommandLogEvent["source"]
  ): Promise<CommandResult> {
    const env = await this.backendProcessEnv(command);
    return await runCommandWithLogs({
      command,
      args,
      env,
      source,
      emitLog: (payload) => this.emitLog(payload)
    });
  }

  private async runCommandCapture(
    command: string,
    args: string[],
    options: BackendEnvOptions = {}
  ): Promise<CommandResult> {
    const env = await this.backendProcessEnv(command, options);
    return await runCommandCapture({ command, args, env });
  }

  private async waitUntilHealthy(baseUrl: string, timeoutMs: number): Promise<void> {
    await waitUntilHealthy(baseUrl, timeoutMs);
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
    const repoRootHint = this.resolveRepoRootHint();
    const configDir = this.resolveConfigDirPath();
    const documentsPath = this.resolveDocumentsPath();
    const env = buildDesktopBackendEnv({
      env: process.env,
      userDataDir: cfg.userDataDir,
      dbPath: cfg.dbPath,
      repoRootHint,
      configDir,
      documentsPath,
      frontendDist: this.resolveFrontendDist(),
      isPackaged: app.isPackaged,
      platform: process.platform,
      credentialEncryptionKey: resolveCredentialEncryptionKey(cfg.userDataDir)
    });
    if (options.includePluginRuntimePolicy === false) {
      applyPluginRuntimePolicyToEnv({
        env,
        includePluginRuntimePolicy: false
      });
    } else {
      const releaseContext = await this.resolveReleaseContext();
      const runtimePolicy = await this.receiptPluginPackManager.getRuntimePolicy({
        trustPolicy: releaseContext.trustPolicy,
        catalogEntries: releaseContext.metadata.discovery_catalog.entries
      });
      applyPluginRuntimePolicyToEnv({
        env,
        runtimePolicy
      });
    }
    await ensureManagedPlaywrightBrowsers({
      command,
      userDataDir: cfg.userDataDir,
      env,
      pythonExecutable: this.resolvePythonExecutable(),
      isPathLike: (candidate) => this.isPathLike(candidate),
      emitLog: (payload) => this.emitLog(payload),
      runRawCommandCapture: async (captureCommand, captureArgs, captureEnv) =>
        await this.runRawCommandCapture(captureCommand, captureArgs, captureEnv)
    });
    return env;
  }

  private async runRawCommandCapture(
    command: string,
    args: string[],
    env: NodeJS.ProcessEnv
  ): Promise<CommandResult> {
    return await runCommandCapture({ command, args, env });
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
    return resolveRepoRootHint(this.runtimePathContext(), process.env);
  }

  private resolveRemoteCatalogUrl(): string | null {
    return resolveRemoteCatalogUrl(process.env);
  }

  private resolveTrustRootsOverride(): unknown | undefined {
    return resolveTrustRootsOverride(process.env);
  }

  private resolveTrustedCatalogOverride(): unknown | undefined {
    return resolveTrustedCatalogOverride(process.env);
  }

  private readJsonOverrideFromPath(envName: string, label: string): unknown | undefined {
    return readJsonOverrideFromPath(process.env, envName, label);
  }

  private findCatalogDesktopPackEntry(
    entries: DesktopReleaseMetadata["discovery_catalog"]["entries"],
    entryId: string
  ): ConnectorCatalogEntry {
    return findCatalogDesktopPackEntry(entries, entryId);
  }

  private resolveFrontendDist(): string {
    return resolveFrontendDist(this.runtimePathContext(), process.env);
  }

  private inspectBackendCommand(): {
    command: string;
    source: DesktopRuntimeDiagnostics["backendCommandSource"];
    status: DesktopRuntimeDiagnostics["backendCommandStatus"];
  } {
    return inspectBackendCommand(this.runtimePathContext(), process.env);
  }

  private resolveBackendInvocation(strictOverride: boolean): BackendInvocation {
    return resolveBackendInvocation(this.runtimePathContext(), process.env, strictOverride);
  }

  private resolveLidltoolExecutable(strictOverride: boolean): string {
    return this.resolveBackendInvocation(strictOverride).command;
  }

  private resolvePythonExecutable(): string {
    return resolvePythonExecutable(this.runtimePathContext());
  }

  private isPathLike(command: string): boolean {
    return isPathLike(command);
  }

  private resolveBundledExecutable(): string | null {
    return resolveBundledExecutable(this.runtimePathContext());
  }

  private resolveManagedDevExecutable(): string | null {
    return resolveManagedDevExecutable(this.runtimePathContext());
  }

  private resolveOcrIdleTimeoutSeconds(): number {
    return resolveOcrIdleTimeoutSeconds(process.env);
  }
}
