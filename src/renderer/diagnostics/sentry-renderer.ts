import * as Sentry from "@sentry/electron/renderer";

let initialized = false;

export async function initRendererTelemetry(): Promise<void> {
  if (initialized) {
    return;
  }
  const config = await window.desktopApi.getTelemetryConfig();
  if (!config.enabled || !config.dsn) {
    return;
  }
  initialized = true;
  Sentry.init({
    dsn: config.dsn,
    release: config.release,
    environment: config.environment,
    tracesSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event) {
      event.tags = {
        ...event.tags,
        process: "renderer"
      };
      if (event.request) {
        delete event.request.cookies;
        delete event.request.headers;
      }
      return event;
    }
  });
  Sentry.setTag("app", "lidltool-desktop");
  Sentry.setTag("process", "renderer");
}
