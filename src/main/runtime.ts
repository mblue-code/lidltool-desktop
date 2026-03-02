import { app, BrowserWindow } from "electron";
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
  ConnectorSourceId,
  ExportRequest,
  ImportRequest,
  SyncRequest
} from "@shared/contracts";

const DEFAULT_PORT = 18765;

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

export class DesktopRuntime {
  private backendProcess: ChildProcessWithoutNullStreams | null = null;
  private backendStartedAt: string | null = null;
  private readonly apiPort: number;

  constructor(port = DEFAULT_PORT) {
    this.apiPort = port;
  }

  getConfig(): BackendConfig {
    const userDataDir = app.getPath("userData");
    mkdirSync(userDataDir, { recursive: true });

    return {
      apiBaseUrl: `http://127.0.0.1:${this.apiPort}`,
      dbPath: join(userDataDir, "lidltool.sqlite"),
      userDataDir
    };
  }

  getBackendStatus(): BackendStatus {
    return {
      running: this.backendProcess !== null,
      pid: this.backendProcess?.pid ?? null,
      startedAt: this.backendStartedAt,
      command: this.resolveLidltoolExecutable(false)
    };
  }

  getFullAppUrl(): string {
    return this.getConfig().apiBaseUrl;
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
    const command = this.resolveLidltoolExecutable(options.strictOverride ?? false);
    const args = ["--db", cfg.dbPath, "serve", "--host", "127.0.0.1", "--port", String(this.apiPort)];
    const env = this.backendProcessEnv(command);

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
        throw new Error(
          `Failed to launch backend executable '${command}'. ${String(spawnError)}. ` +
            "Run `npm run backend:prepare` in apps/desktop or set LIDLTOOL_EXECUTABLE."
        );
      }
      throw err;
    }
  }

  async stopBackend(): Promise<BackendStatus> {
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

  async runSyncJob(payload: SyncRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const command = this.resolveLidltoolExecutable(false);
    const args = this.mapSyncArgs(payload, cfg.dbPath);
    return await this.runCommand(command, args, "sync");
  }

  async runExportJob(payload: ExportRequest): Promise<CommandResult> {
    const cfg = this.getConfig();
    const outPath = payload.outPath.trim();
    if (!outPath) {
      throw new Error("Export output path is required.");
    }
    const command = this.resolveLidltoolExecutable(false);
    const args = this.mapExportArgs(payload, cfg.dbPath);
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
      const command = this.resolveLidltoolExecutable(false);
      const exportPath = join(backupDir, "receipts-export.json");
      const exportArgs = this.mapExportArgs({ outPath: exportPath, format: "json" }, cfg.dbPath);
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

  async shutdown(): Promise<void> {
    await this.stopBackend();
  }

  private mapSyncArgs(payload: SyncRequest, dbPath: string): string[] {
    const globalOptions: string[] = ["--db", dbPath, "--json"];

    if (payload.source === "lidl") {
      const syncArgs = payload.full ? ["--full"] : [];
      return [...globalOptions, "sync", ...syncArgs];
    }

    const connectorArgs = this.connectorArgs(payload.source, payload);
    return [...globalOptions, payload.source, "sync", ...connectorArgs];
  }

  private connectorArgs(source: ConnectorSourceId, payload: SyncRequest): string[] {
    const headless = payload.headless ?? true;
    const args: string[] = [headless ? "--headless" : "--no-headless"];

    if (payload.domain?.trim()) {
      args.push("--domain", payload.domain.trim());
    }

    if (source === "amazon") {
      if (payload.years && payload.years > 0) {
        args.push("--years", String(payload.years));
      }
      if (payload.maxPages && payload.maxPages > 0) {
        args.push("--max-pages-per-year", String(payload.maxPages));
      }
      return args;
    }

    if (payload.maxPages && payload.maxPages > 0) {
      args.push("--max-pages", String(payload.maxPages));
    }

    return args;
  }

  private mapExportArgs(payload: ExportRequest, dbPath: string): string[] {
    const formatName = payload.format ?? "json";
    return ["--db", dbPath, "--json", "export", "--out", payload.outPath.trim(), "--format", formatName];
  }

  private resolveTokenFilePath(): string {
    const configDirRaw = process.env.LIDLTOOL_CONFIG_DIR?.trim();
    if (configDirRaw) {
      return join(this.resolveUserPath(configDirRaw), "token.json");
    }
    return join(homedir(), ".config", "lidltool", "token.json");
  }

  private resolveDocumentsPath(): string {
    const documentsPathRaw = process.env.LIDLTOOL_DOCUMENT_STORAGE_PATH?.trim();
    if (documentsPathRaw) {
      return this.resolveUserPath(documentsPathRaw);
    }
    return join(homedir(), ".local", "share", "lidltool", "documents");
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
    const env = this.backendProcessEnv(command);

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

  private backendProcessEnv(command: string): NodeJS.ProcessEnv {
    const cfg = this.getConfig();
    const env: NodeJS.ProcessEnv = { ...process.env };
    env.LIDLTOOL_FRONTEND_DIST = this.resolveFrontendDist();
    env.LIDLTOOL_REPO_ROOT = this.resolveRepoRootHint();
    env.LIDLTOOL_DB = cfg.dbPath;
    env.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY =
      env.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY || this.resolveCredentialEncryptionKey(cfg.userDataDir);
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

  private resolveLidltoolExecutable(strictOverride: boolean): string {
    const override = process.env.LIDLTOOL_EXECUTABLE?.trim();
    if (override) {
      if (strictOverride || !this.isPathLike(override) || existsSync(override)) {
        return override;
      }
    }

    const bundledExecutable = this.resolveBundledExecutable();
    if (bundledExecutable) {
      return bundledExecutable;
    }

    const managedDevExecutable = this.resolveManagedDevExecutable();
    if (managedDevExecutable) {
      return managedDevExecutable;
    }

    return process.platform === "win32" ? "lidltool.exe" : "lidltool";
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
}
