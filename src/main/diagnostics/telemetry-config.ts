import { app } from "electron";
import { loadDesktopPrivacyPreferences } from "./privacy-preferences";

export type DesktopTelemetryMode = "off" | "errors" | "errors_with_logs";
export type DesktopReleaseChannel = "development" | "internal" | "beta" | "production";

export interface DesktopTelemetryConfig {
  enabled: boolean;
  mode: DesktopTelemetryMode;
  dsn: string | null;
  release: string;
  environment: DesktopReleaseChannel;
  sendLogs: boolean;
}

function normalizeTelemetryMode(value: string | null | undefined): DesktopTelemetryMode {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "errors" || normalized === "errors_with_logs") {
    return normalized;
  }
  return "off";
}

function normalizeReleaseChannel(value: string | null | undefined): DesktopReleaseChannel {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "internal" || normalized === "beta" || normalized === "production") {
    return normalized;
  }
  return app.isPackaged ? "production" : "development";
}

export function resolveDesktopTelemetryConfig(env: NodeJS.ProcessEnv = process.env): DesktopTelemetryConfig {
  const dsn = env.LIDLTOOL_DESKTOP_GLITCHTIP_DSN?.trim() || env.LIDLTOOL_DESKTOP_SENTRY_DSN?.trim() || null;
  const mode = normalizeTelemetryMode(env.LIDLTOOL_DESKTOP_TELEMETRY);
  const environment = normalizeReleaseChannel(env.LIDLTOOL_DESKTOP_RELEASE_CHANNEL);
  const release = `lidltool-desktop@${app.getVersion()}`;
  const preferences = loadDesktopPrivacyPreferences();
  return {
    enabled: Boolean(dsn) && mode !== "off" && preferences.errorReportingEnabled,
    mode,
    dsn,
    release,
    environment,
    sendLogs: mode === "errors_with_logs" && preferences.diagnosticLogSharingEnabled
  };
}
