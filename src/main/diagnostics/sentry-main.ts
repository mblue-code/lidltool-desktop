import * as Sentry from "@sentry/electron/main";
import { app } from "electron";
import { homedir } from "node:os";
import { redactSensitiveText, sanitizeDiagnosticValue } from "./sanitization";
import { resolveDesktopTelemetryConfig, type DesktopTelemetryConfig } from "./telemetry-config";
import { PACKAGE_SLUG } from "../product-identity.ts";

let activeConfig: DesktopTelemetryConfig | null = null;
let sentryInitialized = false;

export function getDesktopTelemetryConfig(): DesktopTelemetryConfig {
  activeConfig ??= resolveDesktopTelemetryConfig();
  return activeConfig;
}

export function initDesktopTelemetry(): DesktopTelemetryConfig {
  const config = getDesktopTelemetryConfig();
  if (!config.enabled || !config.dsn || sentryInitialized) {
    return config;
  }

  Sentry.init({
    dsn: config.dsn,
    release: config.release,
    environment: config.environment,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event) {
      const home = homedir();
      event.message = event.message ? redactSensitiveText(event.message, home) : event.message;
      event.extra = sanitizeDiagnosticValue(event.extra, home) as typeof event.extra;
      event.tags = {
        ...event.tags,
        packaged: String(app.isPackaged),
        process: "main"
      };
      if (event.request) {
        delete event.request.cookies;
        delete event.request.headers;
        event.request.url = event.request.url ? redactSensitiveText(event.request.url, home) : event.request.url;
      }
      return event;
    }
  });

  Sentry.setTag("app", PACKAGE_SLUG);
  Sentry.setTag("process", "main");
  Sentry.setTag("packaged", String(app.isPackaged));
  sentryInitialized = true;
  return config;
}

export function reloadDesktopTelemetryConfig(): DesktopTelemetryConfig {
  activeConfig = resolveDesktopTelemetryConfig();
  if (activeConfig.enabled && activeConfig.dsn && !sentryInitialized) {
    return initDesktopTelemetry();
  }
  return activeConfig;
}

export function captureDesktopException(error: unknown, context: Record<string, unknown> = {}): void {
  const config = getDesktopTelemetryConfig();
  if (!config.enabled) {
    return;
  }
  Sentry.withScope((scope) => {
    for (const [key, value] of Object.entries(context)) {
      scope.setExtra(key, sanitizeDiagnosticValue(value, homedir()));
    }
    Sentry.captureException(error);
  });
}

export function addDesktopBreadcrumb(message: string, data: Record<string, unknown> = {}): void {
  const config = getDesktopTelemetryConfig();
  if (!config.enabled) {
    return;
  }
  Sentry.addBreadcrumb({
    category: "desktop",
    level: "info",
    message,
    data: sanitizeDiagnosticValue(data, homedir()) as Record<string, unknown>
  });
}
