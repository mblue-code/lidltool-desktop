import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const DEFAULT_SCAN_INTERVAL_MS = 10 * 60 * 1000;
const DEFAULT_STALE_AFTER_MS = 60 * 60 * 1000;
const DEFAULT_CONNECTOR_STALE_AFTER_MS = 12 * 60 * 60 * 1000;

export type ProcessSnapshot = {
  pid: number;
  ageSeconds: number | null;
  command: string;
};

export type StalePlaywrightCleanerOptions = {
  userDataDir: string;
  platform?: NodeJS.Platform;
  scanIntervalMs?: number;
  staleAfterMs?: number;
  connectorStaleAfterMs?: number;
  log?: (event: string, details?: Record<string, unknown>) => void;
  killProcess?: (pid: number, signal?: NodeJS.Signals) => boolean;
};

export type StalePlaywrightProcessMatch = ProcessSnapshot & {
  reason: string;
};

function normalizePathForMatch(value: string): string {
  return value.replace(/\\/g, "/").toLowerCase();
}

function normalizeCommand(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function processAgeMs(processInfo: ProcessSnapshot): number | null {
  return processInfo.ageSeconds === null ? null : processInfo.ageSeconds * 1000;
}

export function isOutlaysOwnedPlaywrightProcess(
  processInfo: ProcessSnapshot,
  options: {
    userDataDir: string;
    staleAfterMs?: number;
    connectorStaleAfterMs?: number;
  }
): StalePlaywrightProcessMatch | null {
  const staleAfterMs = options.staleAfterMs ?? DEFAULT_STALE_AFTER_MS;
  const connectorStaleAfterMs = options.connectorStaleAfterMs ?? DEFAULT_CONNECTOR_STALE_AFTER_MS;
  if (!Number.isInteger(processInfo.pid) || processInfo.pid <= 0 || processInfo.pid === process.pid) {
    return null;
  }

  const command = normalizeCommand(processInfo.command);
  const normalizedCommand = normalizePathForMatch(command);
  const normalizedUserDataDir = normalizePathForMatch(options.userDataDir);
  const connectorProfileMarkers = [
    `${normalizedUserDataDir}/config/amazon_browser_profile`,
    `${normalizedUserDataDir}/config/lidl_plus_browser_profile`
  ];
  const appControlledMarkers = [
    `${normalizedUserDataDir}/playwright-browsers`,
    `${normalizedUserDataDir}/config/amazon_storage_state.json`,
    `${normalizedUserDataDir}/config/lidl_plus_storage_state.json`,
    "playwright_chromiumdev_profile-"
  ];
  const browserMarkers = [
    "chromium",
    "chrome",
    "google chrome",
    "msedge",
    "playwright",
    "clidaemon.js"
  ];

  const hasAppControlledMarker = appControlledMarkers.some((marker) => normalizedCommand.includes(marker));
  const hasConnectorProfileMarker = connectorProfileMarkers.some((marker) => normalizedCommand.includes(marker));
  const hasBrowserMarker = browserMarkers.some((marker) => normalizedCommand.includes(marker));
  if ((!hasAppControlledMarker && !hasConnectorProfileMarker) || !hasBrowserMarker) {
    return null;
  }

  const ageMs = processAgeMs(processInfo);
  const requiredStaleAfterMs = hasConnectorProfileMarker ? connectorStaleAfterMs : staleAfterMs;
  if (ageMs === null || ageMs < requiredStaleAfterMs) {
    return null;
  }

  return {
    ...processInfo,
    command,
    reason: hasConnectorProfileMarker
      ? "outlays_connector_browser_profile_stale"
      : "outlays_playwright_browser_stale"
  };
}

export function parseDarwinLinuxProcessList(output: string): ProcessSnapshot[] {
  const nowMs = Date.now();
  return output
    .split(/\r?\n/)
    .map((line): ProcessSnapshot | null => {
      const match = line.match(
        /^\s*(\d+)\s+([A-Z][a-z]{2}\s+[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+(.+?)\s*$/
      );
      if (!match) {
        return null;
      }
      const startedAtMs = Date.parse(match[2]);
      return {
        pid: Number(match[1]),
        ageSeconds: Number.isFinite(startedAtMs)
          ? Math.max(Math.floor((nowMs - startedAtMs) / 1000), 0)
          : null,
        command: match[3]
      };
    })
    .filter((entry): entry is ProcessSnapshot => entry !== null);
}

async function listDarwinLinuxProcesses(): Promise<ProcessSnapshot[]> {
  const { stdout } = await execFileAsync("ps", ["-axo", "pid=,lstart=,command="], {
    maxBuffer: 8 * 1024 * 1024
  });
  return parseDarwinLinuxProcessList(stdout);
}

export class StalePlaywrightProcessCleaner {
  private readonly userDataDir: string;
  private readonly platform: NodeJS.Platform;
  private readonly scanIntervalMs: number;
  private readonly staleAfterMs: number;
  private readonly connectorStaleAfterMs: number;
  private readonly log: (event: string, details?: Record<string, unknown>) => void;
  private readonly killProcess: (pid: number, signal?: NodeJS.Signals) => boolean;
  private timer: NodeJS.Timeout | null = null;
  private scanRunning = false;

  constructor(options: StalePlaywrightCleanerOptions) {
    this.userDataDir = options.userDataDir;
    this.platform = options.platform ?? process.platform;
    this.scanIntervalMs = options.scanIntervalMs ?? DEFAULT_SCAN_INTERVAL_MS;
    this.staleAfterMs = options.staleAfterMs ?? DEFAULT_STALE_AFTER_MS;
    this.connectorStaleAfterMs = options.connectorStaleAfterMs ?? DEFAULT_CONNECTOR_STALE_AFTER_MS;
    this.log = options.log ?? (() => {});
    this.killProcess = options.killProcess ?? process.kill;
  }

  start(): void {
    if (this.timer !== null) {
      return;
    }
    void this.scan("startup");
    this.timer = setInterval(() => {
      void this.scan("interval");
    }, this.scanIntervalMs);
    this.timer.unref?.();
  }

  stop(): void {
    if (this.timer === null) {
      return;
    }
    clearInterval(this.timer);
    this.timer = null;
  }

  async scan(reason = "manual"): Promise<StalePlaywrightProcessMatch[]> {
    if (this.scanRunning) {
      return [];
    }
    this.scanRunning = true;
    try {
      const processes = await this.listProcesses();
      const matches = processes
        .map((processInfo) =>
          isOutlaysOwnedPlaywrightProcess(processInfo, {
            userDataDir: this.userDataDir,
            staleAfterMs: this.staleAfterMs,
            connectorStaleAfterMs: this.connectorStaleAfterMs
          })
        )
        .filter((match): match is StalePlaywrightProcessMatch => match !== null);

      for (const match of matches) {
        this.terminate(match, reason);
      }
      if (matches.length > 0) {
        this.log("playwright_stale_cleanup.completed", {
          reason,
          count: matches.length,
          pids: matches.map((match) => match.pid)
        });
      }
      return matches;
    } catch (error) {
      this.log("playwright_stale_cleanup.failed", {
        reason,
        error: error instanceof Error ? error.message : String(error)
      });
      return [];
    } finally {
      this.scanRunning = false;
    }
  }

  private async listProcesses(): Promise<ProcessSnapshot[]> {
    if (this.platform === "darwin" || this.platform === "linux") {
      return await listDarwinLinuxProcesses();
    }
    return [];
  }

  private terminate(match: StalePlaywrightProcessMatch, scanReason: string): void {
    try {
      const terminated = this.killProcess(match.pid, "SIGTERM");
      this.log("playwright_stale_cleanup.terminated", {
        scanReason,
        pid: match.pid,
        ageSeconds: match.ageSeconds,
        reason: match.reason,
        terminated,
        command: match.command.slice(0, 500)
      });
    } catch (error) {
      this.log("playwright_stale_cleanup.terminate_failed", {
        scanReason,
        pid: match.pid,
        ageSeconds: match.ageSeconds,
        reason: match.reason,
        error: error instanceof Error ? error.message : String(error)
      });
    }
  }
}
