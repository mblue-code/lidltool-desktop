import { app, BrowserWindow, Menu, nativeImage, session } from "electron";
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type { DesktopConnectorCallbackEvent } from "@shared/contracts";
import type { DesktopLocale } from "@shared/contracts";
import {
  loadDesktopExternalBrowserPreference,
  openUrlWithDesktopBrowserPreference,
  persistDesktopExternalBrowserPreference
} from "./browser-preferences";
import { registerIpc } from "./ipc";
import { applyDesktopMenu, loadDesktopLocale, persistDesktopLocale } from "./i18n";
import { DesktopRuntime } from "./runtime";

const userDataOverride = process.env.LIDLTOOL_DESKTOP_USER_DATA_DIR?.trim();
if (userDataOverride) {
  app.setPath("userData", userDataOverride);
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

let mainWindow: BrowserWindow | null = null;
const runtime = new DesktopRuntime();
let latestBootError: string | null = null;
let currentLocale: DesktopLocale = "en";
let lastRequestedSurface: "control_center" | "main_app" = "control_center";
let appIsQuitting = false;
let lastCloseRequestHint: { source: string; at: string } | null = null;
let windowLifecycleConsoleLoggingEnabled = true;
const LIDL_PROTOCOL_SCHEME = "com.lidlplus.app";
const LIDL_CALLBACK_PREFIX = `${LIDL_PROTOCOL_SCHEME}://callback`;
const DESKTOP_SESSION_COOKIE_NAME = "lidltool_session";
const pendingConnectorCallbacks: DesktopConnectorCallbackEvent[] = [];

type ConnectorCallbackConfirmationResult = {
  confirmed: boolean;
  detail: string | null;
};

function resolveDesktopIconPath(): string | null {
  const explicitIconPath = process.env.LIDLTOOL_DESKTOP_ICON_PATH?.trim();
  const candidates = [
    explicitIconPath || null,
    app.isPackaged ? join(process.resourcesPath, "icon.png") : null,
    join(app.getAppPath(), "build", "icon.png"),
    join(process.cwd(), "build", "icon.png")
  ].filter((candidate): candidate is string => Boolean(candidate));

  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

function applyDockIcon(): void {
  if (process.platform !== "darwin" || !app.dock) {
    return;
  }
  const iconPath = resolveDesktopIconPath();
  if (!iconPath) {
    logWindowLifecycle("app.dock_icon.missing");
    return;
  }
  const image = nativeImage.createFromPath(iconPath);
  if (image.isEmpty()) {
    logWindowLifecycle("app.dock_icon.empty", { iconPath });
    return;
  }
  app.dock.setIcon(image);
  logWindowLifecycle("app.dock_icon.applied", { iconPath });
}

function nowIso(): string {
  return new Date().toISOString();
}

function getWindowLifecycleLogPath(): string {
  return join(app.getPath("userData"), "window-lifecycle.log");
}

function logWindowLifecycle(
  event: string,
  details: Record<string, unknown> = {}
): void {
  const payload = {
    timestamp: nowIso(),
    event,
    pid: process.pid,
    windowCount: BrowserWindow.getAllWindows().length,
    ...details
  };

  try {
    mkdirSync(app.getPath("userData"), { recursive: true });
    appendFileSync(getWindowLifecycleLogPath(), `${JSON.stringify(payload)}\n`, "utf-8");
  } catch {
    // Best-effort instrumentation only.
  }

  if (!windowLifecycleConsoleLoggingEnabled) {
    return;
  }

  try {
    console.log(`[desktop-window] ${JSON.stringify(payload)}`);
  } catch (error) {
    windowLifecycleConsoleLoggingEnabled = false;
    try {
      appendFileSync(
        getWindowLifecycleLogPath(),
        `${JSON.stringify({
          timestamp: nowIso(),
          event: "window.lifecycle_console_logging_disabled",
          pid: process.pid,
          reason: error instanceof Error ? error.message : String(error)
        })}\n`,
        "utf-8"
      );
    } catch {
      // Best-effort instrumentation only.
    }
  }
}

function describeWindow(window: BrowserWindow | null): Record<string, unknown> {
  if (!window || window.isDestroyed()) {
    return {
      destroyed: true
    };
  }

  const bounds = window.getBounds();
  return {
    destroyed: false,
    visible: window.isVisible(),
    minimized: window.isMinimized(),
    focused: window.isFocused(),
    title: window.getTitle(),
    url: window.webContents.getURL(),
    bounds
  };
}

function noteCloseRequest(source: string): void {
  lastCloseRequestHint = {
    source,
    at: nowIso()
  };
}

function describeCloseRequestHint(): Record<string, unknown> {
  if (!lastCloseRequestHint) {
    return {};
  }
  return {
    closeRequestSource: lastCloseRequestHint.source,
    closeRequestAt: lastCloseRequestHint.at
  };
}

function inferSurfaceFromUrl(url: string): "control_center" | "main_app" | null {
  if (!url) {
    return null;
  }
  if (url.startsWith("http://127.0.0.1:") || url.startsWith("http://localhost:")) {
    return "main_app";
  }
  if (url.startsWith("file://")) {
    return "control_center";
  }
  return null;
}

function syncSurfaceFromWindow(window: BrowserWindow): void {
  if (window.isDestroyed()) {
    return;
  }
  const inferredSurface = inferSurfaceFromUrl(window.webContents.getURL());
  if (inferredSurface) {
    lastRequestedSurface = inferredSurface;
  }
}

function isConnectorCallbackUrl(url: string): boolean {
  const normalizedUrl = url.trim();
  return normalizedUrl.startsWith(LIDL_CALLBACK_PREFIX);
}

function consumePendingConnectorCallbacks(): DesktopConnectorCallbackEvent[] {
  const next = [...pendingConnectorCallbacks];
  pendingConnectorCallbacks.length = 0;
  return next;
}

function deliverConnectorCallbackToWindows(payload: DesktopConnectorCallbackEvent): void {
  const windows = BrowserWindow.getAllWindows().filter((window) => !window.isDestroyed());
  if (windows.length === 0) {
    pendingConnectorCallbacks.push(payload);
    return;
  }
  for (const window of windows) {
    window.webContents.send("desktop:connector-callback", payload);
  }
}

async function readDesktopSessionCookieValue(): Promise<string | null> {
  const cookies = await session.defaultSession.cookies.get({
    url: runtime.getFullAppUrl(),
    name: DESKTOP_SESSION_COOKIE_NAME
  });
  const cookieValue = cookies[0]?.value?.trim() ?? "";
  return cookieValue.length > 0 ? cookieValue : null;
}

async function confirmLidlConnectorCallback(callbackUrl: string): Promise<ConnectorCallbackConfirmationResult> {
  await runtime.startBackend();
  const sessionCookie = await readDesktopSessionCookieValue();
  if (!sessionCookie) {
    logWindowLifecycle("connector.callback.confirm_skipped", {
      sourceId: "lidl_plus_de",
      reason: "missing_session_cookie"
    });
    return {
      confirmed: false,
      detail: null
    };
  }

  const response = await fetch(
    `${runtime.getFullAppUrl()}/api/v1/connectors/lidl_plus_de/bootstrap/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: `${DESKTOP_SESSION_COOKIE_NAME}=${sessionCookie}`
      },
      body: JSON.stringify({ callback_url: callbackUrl })
    }
  );
  const responseText = await response.text();

  let payload: Record<string, unknown> | null = null;
  try {
    payload = JSON.parse(responseText) as Record<string, unknown>;
  } catch {
    payload = null;
  }

  const confirmed =
    response.ok &&
    payload?.ok === true &&
    typeof payload.result === "object" &&
    payload.result !== null &&
    (payload.result as { confirmed?: unknown }).confirmed === true;
  const detail =
    typeof payload?.result === "object" &&
    payload.result !== null &&
    typeof (payload.result as { auth_status?: { detail?: unknown } }).auth_status?.detail === "string"
      ? String((payload.result as { auth_status?: { detail?: unknown } }).auth_status?.detail)
      : null;

  logWindowLifecycle(confirmed ? "connector.callback.confirmed" : "connector.callback.confirm_failed", {
    sourceId: "lidl_plus_de",
    httpStatus: response.status,
    ok: payload?.ok ?? null,
    error: payload?.error ?? null,
    errorCode: payload?.error_code ?? null,
    responseSnippet: responseText.slice(0, 500)
  });

  return {
    confirmed,
    detail
  };
}

async function handleConnectorCallback(payload: DesktopConnectorCallbackEvent, reason: string): Promise<void> {
  logWindowLifecycle("connector.callback", {
    reason,
    callbackUrl: payload.url
  });

  let confirmation: ConnectorCallbackConfirmationResult = {
    confirmed: false,
    detail: null
  };
  try {
    confirmation = await confirmLidlConnectorCallback(payload.url);
  } catch (error) {
    logWindowLifecycle("connector.callback.confirm_exception", {
      sourceId: "lidl_plus_de",
      error: error instanceof Error ? error.message : String(error)
    });
  }

  if (!confirmation.confirmed) {
    deliverConnectorCallbackToWindows({
      ...payload,
      sourceId: payload.sourceId ?? "lidl_plus_de",
      confirmed: false,
      confirmedAt: null,
      detail: confirmation.detail
    });
    return;
  }

  const confirmedPayload: DesktopConnectorCallbackEvent = {
    url: payload.url,
    sourceId: payload.sourceId ?? "lidl_plus_de",
    confirmed: true,
    confirmedAt: nowIso(),
    detail: confirmation.detail
  };
  pendingConnectorCallbacks.push(confirmedPayload);

  await recoverMainWindow("connector-auth-confirmed");
  const targetUrl = new URL("/connectors", runtime.getFullAppUrl()).toString();
  const windows = BrowserWindow.getAllWindows().filter((window) => !window.isDestroyed());
  await Promise.all(
    windows.map(async (window) => {
      const currentUrl = window.webContents.getURL();
      if (currentUrl !== targetUrl) {
        await window.loadURL(targetUrl);
      }
    })
  );
  deliverConnectorCallbackToWindows(confirmedPayload);
}

function dispatchConnectorCallback(url: string, reason: string): void {
  const normalizedUrl = url.trim();
  if (!isConnectorCallbackUrl(normalizedUrl)) {
    return;
  }
  const payload: DesktopConnectorCallbackEvent = {
    url: normalizedUrl,
    sourceId: "lidl_plus_de"
  };
  void handleConnectorCallback(payload, reason);
}

function registerDesktopProtocolClient(): void {
  try {
    const registrationArgs =
      process.defaultApp || !app.isPackaged
        ? [app.getAppPath()]
        : [];
    const registered =
      registrationArgs.length > 0
        ? app.setAsDefaultProtocolClient(LIDL_PROTOCOL_SCHEME, process.execPath, registrationArgs)
        : app.setAsDefaultProtocolClient(LIDL_PROTOCOL_SCHEME);
    logWindowLifecycle("protocol.register", {
      scheme: LIDL_PROTOCOL_SCHEME,
      registered,
      execPath: process.execPath,
      registrationArgs
    });
  } catch (error) {
    logWindowLifecycle("protocol.register_failed", {
      scheme: LIDL_PROTOCOL_SCHEME,
      execPath: process.execPath,
      registrationArgs:
        process.defaultApp || !app.isPackaged
          ? [app.getAppPath()]
          : [],
      error: error instanceof Error ? error.message : String(error)
    });
  }
}

function extractConnectorCallbackFromArgv(argv: readonly string[]): string | null {
  for (const value of argv) {
    const candidate = String(value || "").trim();
    if (isConnectorCallbackUrl(candidate)) {
      return candidate;
    }
  }
  return null;
}

function restoreWindowVisibility(window: BrowserWindow, reason: string): void {
  if (window.isDestroyed()) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  if (!window.isVisible()) {
    window.show();
  }
  window.focus();
  logWindowLifecycle("window.visibility_restored", {
    reason,
    ...describeWindow(window)
  });
}

function scheduleVisibilityRecovery(window: BrowserWindow, reason: string): void {
  for (const delayMs of [200, 1_000, 3_000]) {
    setTimeout(() => {
      if (window !== mainWindow || window.isDestroyed() || appIsQuitting) {
        return;
      }
      if (!window.isVisible() || window.isMinimized()) {
        restoreWindowVisibility(window, `${reason}:${delayMs}ms`);
      }
    }, delayMs);
  }
}

async function loadControlCenter(window: BrowserWindow, bootError?: string): Promise<void> {
  lastRequestedSurface = "control_center";
  latestBootError = bootError ?? null;
  logWindowLifecycle("surface.load_control_center.start", {
    bootError: latestBootError,
    ...describeWindow(window)
  });

  if (process.env.ELECTRON_RENDERER_URL) {
    await window.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    await window.loadFile(join(__dirname, "../renderer/index.html"));
  }

  window.webContents.send("desktop:locale-changed", currentLocale);

  if (bootError) {
    window.webContents.send("desktop:boot-error", bootError);
  }
  restoreWindowVisibility(window, "control-center-loaded");
  scheduleVisibilityRecovery(window, "control-center-loaded");
  logWindowLifecycle("surface.load_control_center.success", {
    bootError: latestBootError,
    ...describeWindow(window)
  });
}

async function openMainApp(window: BrowserWindow): Promise<void> {
  lastRequestedSurface = "main_app";
  logWindowLifecycle("surface.open_main_app.start", describeWindow(window));
  try {
    const diagnostics = runtime.getRuntimeDiagnostics();
    if (!diagnostics.fullAppReady) {
      await loadControlCenter(
        window,
        `This build does not include the main app pages at '${diagnostics.frontendDistPath}'. ` +
          "You can still run local sync, plugin pack, export, and backup tasks from the control center."
      );
      return;
    }
    await runtime.startBackend({ strictOverride: true });
    latestBootError = null;
    await window.loadURL(runtime.getFullAppUrl());
    restoreWindowVisibility(window, "main-app-loaded");
    scheduleVisibilityRecovery(window, "main-app-loaded");
    logWindowLifecycle("surface.open_main_app.success", describeWindow(window));
  } catch (err) {
    const message = String(err);
    logWindowLifecycle("surface.open_main_app.failure", {
      error: message,
      ...describeWindow(window)
    });
    await loadControlCenter(window, message);
  }
}

async function loadStartupSurface(window: BrowserWindow): Promise<void> {
  try {
    const diagnostics = runtime.getRuntimeDiagnostics();
    if (!diagnostics.fullAppReady) {
      await loadControlCenter(
        window,
        `This build does not include the main app pages at '${diagnostics.frontendDistPath}'. ` +
          "You can still run local sync, plugin pack, export, and backup tasks from the control center."
      );
      return;
    }
    await openMainApp(window);
  } catch (err) {
    await loadControlCenter(window, String(err));
  }
}

async function openControlCenter(window: BrowserWindow): Promise<void> {
  await runtime.stopBackend();
  await loadControlCenter(window, latestBootError ?? undefined);
}

async function recoverMainWindow(reason: string): Promise<void> {
  if (appIsQuitting) {
    return;
  }

  const activeWindow =
    mainWindow && !mainWindow.isDestroyed() ? mainWindow : BrowserWindow.getAllWindows()[0] ?? null;

  if (activeWindow) {
    if (mainWindow !== activeWindow) {
      mainWindow = activeWindow;
    }
    restoreWindowVisibility(activeWindow, reason);
    scheduleVisibilityRecovery(activeWindow, reason);
    return;
  }

  logWindowLifecycle("window.recreate", {
    reason,
    surface: lastRequestedSurface
  });
  mainWindow = createWindow();
  updateDesktopLocale(currentLocale);
}

app.on("second-instance", (_event, argv) => {
  logWindowLifecycle("app.second_instance", {
    surface: lastRequestedSurface
  });
  const callbackUrl = extractConnectorCallbackFromArgv(argv);
  if (callbackUrl) {
    dispatchConnectorCallback(callbackUrl, "second-instance");
  }
  void recoverMainWindow("second-instance");
});

app.on("open-url", (event, url) => {
  event.preventDefault();
  dispatchConnectorCallback(url, "open-url");
  void recoverMainWindow("open-url");
});

function broadcastLocaleChanged(locale: DesktopLocale): void {
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("desktop:locale-changed", locale);
  }
}

function updateDesktopLocale(locale: DesktopLocale): DesktopLocale {
  currentLocale = locale;
  persistDesktopLocale(locale);
  applyDesktopMenu(locale, mainWindow, {
    openFullApp: async () => {
      if (mainWindow) {
        await openMainApp(mainWindow);
      }
    },
    reloadControlCenter: async () => {
      if (mainWindow) {
        await runtime.stopBackend();
        await loadControlCenter(mainWindow, latestBootError ?? undefined);
      }
    },
    startBackend: async () => {
      await runtime.startBackend();
    },
    stopBackend: async () => {
      await runtime.stopBackend();
    }
  });
  broadcastLocaleChanged(locale);
  return locale;
}

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 980,
    minHeight: 680,
    show: false,
    title: app.name,
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, "../preload/index.mjs"),
      sandbox: false
    }
  });

  window.on("ready-to-show", () => {
    restoreWindowVisibility(window, "ready-to-show");
  });

  window.on("show", () => {
    logWindowLifecycle("window.show", describeWindow(window));
  });

  window.on("hide", () => {
    logWindowLifecycle("window.hide", describeWindow(window));
  });

  window.on("minimize", () => {
    logWindowLifecycle("window.minimize", describeWindow(window));
  });

  window.on("restore", () => {
    logWindowLifecycle("window.restore", describeWindow(window));
  });

  window.on("close", (event) => {
    const details = {
      surface: inferSurfaceFromUrl(window.webContents.getURL()) ?? lastRequestedSurface,
      appIsQuitting,
      ...describeCloseRequestHint(),
      ...describeWindow(window)
    };
    logWindowLifecycle("window.close", details);
    lastCloseRequestHint = null;
  });

  window.on("closed", () => {
    logWindowLifecycle("window.closed", describeWindow(window));
    if (mainWindow === window) {
      mainWindow = null;
    }
  });

  window.webContents.setWindowOpenHandler((details) => {
    void openUrlWithDesktopBrowserPreference(details.url);
    return { action: "deny" };
  });

  window.webContents.on("render-process-gone", (_event, details) => {
    logWindowLifecycle("window.render_process_gone", {
      reason: details.reason,
      exitCode: details.exitCode,
      ...describeWindow(window)
    });
  });

  window.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    logWindowLifecycle("window.did_fail_load", {
      errorCode,
      errorDescription,
      validatedURL,
      isMainFrame,
      ...describeWindow(window)
    });
  });

  window.webContents.on("unresponsive", () => {
    logWindowLifecycle("window.unresponsive", describeWindow(window));
  });

  window.webContents.on("responsive", () => {
    logWindowLifecycle("window.responsive", describeWindow(window));
  });

  window.webContents.on("before-input-event", (event, input) => {
    const acceleratorPressed = input.meta || input.control;
    if (!acceleratorPressed || input.type !== "keyDown") {
      return;
    }
    const key = input.key.toLowerCase();
    if (key === "c") {
      event.preventDefault();
      window.webContents.copy();
      return;
    }
    if (key === "v") {
      event.preventDefault();
      window.webContents.paste();
      return;
    }
    if (key === "x") {
      event.preventDefault();
      window.webContents.cut();
      return;
    }
    if (key === "a") {
      event.preventDefault();
      window.webContents.selectAll();
      return;
    }
    if (key === "w") {
      noteCloseRequest(process.platform === "darwin" ? "accelerator:cmd+w" : "accelerator:ctrl+w");
      logWindowLifecycle("window.close_accelerator", {
        ...describeCloseRequestHint(),
        ...describeWindow(window)
      });
      return;
    }
    if (key === "z") {
      event.preventDefault();
      if (input.shift) {
        window.webContents.redo();
      } else {
        window.webContents.undo();
      }
    }
  });

  window.webContents.on("context-menu", (_event, params) => {
    const template = [];
    if (params.editFlags.canUndo) {
      template.push({ role: "undo" as const });
    }
    if (params.editFlags.canRedo) {
      template.push({ role: "redo" as const });
    }
    if (params.editFlags.canUndo || params.editFlags.canRedo) {
      template.push({ type: "separator" as const });
    }
    if (params.editFlags.canCut) {
      template.push({ role: "cut" as const });
    }
    if (params.editFlags.canCopy) {
      template.push({ role: "copy" as const });
    }
    if (params.editFlags.canPaste) {
      template.push({ role: "paste" as const });
    }
    if (params.editFlags.canCut || params.editFlags.canCopy || params.editFlags.canPaste) {
      template.push({ type: "separator" as const });
    }
    if (params.editFlags.canSelectAll) {
      template.push({ role: "selectAll" as const });
    }
    if (template.length > 0) {
      Menu.buildFromTemplate(template).popup({ window });
    }
  });

  window.webContents.on("did-start-loading", () => {
    logWindowLifecycle("web.did_start_loading", describeWindow(window));
  });

  window.webContents.on("did-finish-load", () => {
    syncSurfaceFromWindow(window);
    logWindowLifecycle("web.did_finish_load", describeWindow(window));
    scheduleVisibilityRecovery(window, "did-finish-load");
  });

  window.webContents.on("did-fail-load", (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
    logWindowLifecycle("web.did_fail_load", {
      errorCode,
      errorDescription,
      validatedURL,
      isMainFrame,
      ...describeWindow(window)
    });
    if (isMainFrame && errorCode !== -3) {
      scheduleVisibilityRecovery(window, "did-fail-load");
    }
  });

  window.webContents.on("render-process-gone", (_event, details) => {
    logWindowLifecycle("web.render_process_gone", {
      reason: details.reason,
      exitCode: details.exitCode,
      ...describeWindow(window)
    });
    if (window === mainWindow) {
      mainWindow = null;
    }
    void recoverMainWindow(`render-process-gone:${details.reason}`);
  });

  window.webContents.on("unresponsive", () => {
    logWindowLifecycle("web.unresponsive", describeWindow(window));
  });

  window.webContents.on("responsive", () => {
    logWindowLifecycle("web.responsive", describeWindow(window));
  });

  void loadStartupSurface(window);
  logWindowLifecycle("window.created", describeWindow(window));

  return window;
}

app.whenReady().then(() => {
  app.setAppUserModelId("com.lidltool.desktop");
  applyDockIcon();
  currentLocale = loadDesktopLocale();
  registerDesktopProtocolClient();
  const startupCallbackUrl = extractConnectorCallbackFromArgv(process.argv);
  if (startupCallbackUrl) {
    pendingConnectorCallbacks.push({ url: startupCallbackUrl });
  }

  mainWindow = createWindow();
  updateDesktopLocale(currentLocale);
  registerIpc(
    runtime,
    () => latestBootError,
    () => currentLocale,
    (locale) => updateDesktopLocale(locale),
    async () => {
      if (mainWindow) {
        await openControlCenter(mainWindow);
      }
    },
    () => consumePendingConnectorCallbacks(),
    () => loadDesktopExternalBrowserPreference(),
    (preferredBrowser) => persistDesktopExternalBrowserPreference(preferredBrowser),
    async (url) => {
      await openUrlWithDesktopBrowserPreference(url);
    }
  );

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      void recoverMainWindow("activate");
    }
  });
});

app.on("window-all-closed", async () => {
  logWindowLifecycle("app.window_all_closed", {
    surface: lastRequestedSurface
  });
  await runtime.shutdown();
  app.quit();
});

app.on("before-quit", async () => {
  appIsQuitting = true;
  logWindowLifecycle("app.before_quit", {
    surface: lastRequestedSurface
  });
  await runtime.shutdown();
});
