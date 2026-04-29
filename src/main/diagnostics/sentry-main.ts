import * as Sentry from "@sentry/electron/main";
import { app } from "electron";
import { homedir } from "node:os";
import { redactSensitiveText, sanitizeDiagnosticValue } from "./sanitization";
import { resolveDesktopTelemetryConfig, type DesktopTelemetryConfig } from "./telemetry-config";

let activeConfig: DesktopTelemetryConfig | null = null;

export function getDesktopTelemetryConfig(): DesktopTelemetryConfig {
  activeConfig ??= resolveDesktopTelemetryConfig();
  return activeConfig;
}

export function initDesktopTelemetry(): DesktopTelemetryConfig {
  const config = getDesktopTelemetryConfig();
  if (!config.enabled || !config.dsn) {
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

  Sentry.setTag("app", "lidltool-desktop");
  Sentry.setTag("process", "main");
  Sentry.setTag("packaged", String(app.isPackaged));
  return config;
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
