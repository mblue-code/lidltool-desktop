import { BrowserWindow } from "electron";
import electronUpdater from "electron-updater";
import type { ProgressInfo, UpdateInfo } from "electron-updater";
import type { DesktopUpdateState } from "@shared/contracts";
import { captureDesktopException } from "../diagnostics/sentry-main";
import { redactSensitiveText } from "../diagnostics/sanitization";
import { resolveDesktopUpdateConfig, type DesktopUpdateConfig } from "./update-config";

type Logger = (event: string, details?: Record<string, unknown>) => void;
const { autoUpdater } = electronUpdater;

export class DesktopUpdateManager {
  private readonly config: DesktopUpdateConfig;
  private readonly log: Logger;
  private initialized = false;
  private state: DesktopUpdateState;

  constructor(config: DesktopUpdateConfig = resolveDesktopUpdateConfig(), log: Logger = () => undefined) {
    this.config = config;
    this.log = log;
    this.state = {
      enabled: config.enabled,
      channel: config.channel,
      status: config.enabled ? "idle" : "disabled",
      currentVersion: config.currentVersion,
      availableVersion: null,
      updateBaseUrl: config.updateBaseUrl,
      downloaded: false,
      error: config.enabled ? null : config.reason,
      lastCheckedAt: null,
      downloadProgress: null
    };
  }

  initialize(): DesktopUpdateState {
    if (this.initialized || !this.config.enabled || !this.config.updateBaseUrl) {
      return this.getState();
    }
    this.initialized = true;
    autoUpdater.autoDownload = false;
    autoUpdater.channel = this.config.channel;
    autoUpdater.setFeedURL({
      provider: "generic",
      url: this.config.updateBaseUrl,
      channel: this.config.channel
    });

    autoUpdater.on("checking-for-update", () => {
      this.updateState({ status: "checking", error: null, lastCheckedAt: new Date().toISOString() });
    });
    autoUpdater.on("update-available", (info) => {
      this.updateState({ status: "available", availableVersion: this.versionFromInfo(info), error: null });
    });
    autoUpdater.on("update-not-available", (info) => {
      this.updateState({
        status: "not_available",
        availableVersion: this.versionFromInfo(info),
        error: null,
        downloadProgress: null
      });
    });
    autoUpdater.on("download-progress", (progress) => {
      this.updateState({
        status: "downloading",
        downloadProgress: this.progressFromInfo(progress),
        error: null
      });
    });
    autoUpdater.on("update-downloaded", (info) => {
      this.updateState({
        status: "downloaded",
        availableVersion: this.versionFromInfo(info),
        downloaded: true,
        error: null,
        downloadProgress: null
      });
    });
    autoUpdater.on("error", (error) => {
      this.handleError(error, "autoUpdater.error");
    });

    this.log("updates.initialized", {
      channel: this.config.channel,
      updateBaseUrl: this.config.updateBaseUrl,
      autoCheck: this.config.autoCheck
    });
    this.broadcast();
    if (this.config.autoCheck) {
      void this.checkForUpdates();
    }
    return this.getState();
  }

  getState(): DesktopUpdateState {
    return { ...this.state, downloadProgress: this.state.downloadProgress ? { ...this.state.downloadProgress } : null };
  }

  async checkForUpdates(): Promise<DesktopUpdateState> {
    if (!this.config.enabled) {
      return this.getState();
    }
    this.initialize();
    try {
      this.updateState({ status: "checking", error: null, lastCheckedAt: new Date().toISOString() });
      await autoUpdater.checkForUpdates();
    } catch (error) {
      this.handleError(error, "updates.check");
    }
    return this.getState();
  }

  async downloadUpdate(): Promise<DesktopUpdateState> {
    if (!this.config.enabled) {
      return this.getState();
    }
    this.initialize();
    try {
      this.updateState({ status: "downloading", error: null });
      await autoUpdater.downloadUpdate();
    } catch (error) {
      this.handleError(error, "updates.download");
    }
    return this.getState();
  }

  installUpdate(): void {
    if (!this.config.enabled || !this.state.downloaded) {
      return;
    }
    this.log("updates.install_requested", { channel: this.config.channel });
    autoUpdater.quitAndInstall(false, true);
  }

  private updateState(next: Partial<DesktopUpdateState>): void {
    this.state = {
      ...this.state,
      ...next
    };
    this.log("updates.state", {
      status: this.state.status,
      channel: this.state.channel,
      availableVersion: this.state.availableVersion,
      error: this.state.error
    });
    this.broadcast();
  }

  private broadcast(): void {
    const payload = this.getState();
    for (const window of BrowserWindow.getAllWindows()) {
      if (!window.isDestroyed()) {
        window.webContents.send("desktop:updates:state-changed", payload);
      }
    }
  }

  private handleError(error: unknown, source: string): void {
    const message = this.sanitizeError(error);
    this.updateState({ status: "error", error: message, downloadProgress: null });
    captureDesktopException(error, {
      source,
      updateChannel: this.config.channel,
      updateBaseUrlConfigured: Boolean(this.config.updateBaseUrl)
    });
  }

  private sanitizeError(error: unknown): string {
    const text = error instanceof Error ? error.message : String(error);
    return redactSensitiveText(text, process.env.HOME ?? "").replace(/[A-Za-z0-9_=-]{24,}/g, "[redacted]");
  }

  private versionFromInfo(info: UpdateInfo | null | undefined): string | null {
    const version = info?.version?.trim();
    return version ? version : null;
  }

  private progressFromInfo(progress: ProgressInfo) {
    return {
      percent: Number.isFinite(progress.percent) ? progress.percent : 0,
      transferred: Number.isFinite(progress.transferred) ? progress.transferred : 0,
      total: Number.isFinite(progress.total) ? progress.total : 0,
      bytesPerSecond: Number.isFinite(progress.bytesPerSecond) ? progress.bytesPerSecond : 0
    };
  }
}
