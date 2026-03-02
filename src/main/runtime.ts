import { app, BrowserWindow } from "electron";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { join, resolve } from "node:path";
import type {
  BackendConfig,
  BackendStatus,
  CommandLogEvent,
  CommandResult,
  ConnectorSourceId,
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
