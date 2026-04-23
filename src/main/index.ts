import { app, BrowserWindow, Menu, shell } from "electron";
import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type { DesktopLocale } from "@shared/contracts";
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

function shouldGuardMainWindowClose(window: BrowserWindow): boolean {
  if (appIsQuitting || process.platform !== "darwin") {
    return false;
  }
  const surface = inferSurfaceFromUrl(window.webContents.getURL()) ?? lastRequestedSurface;
  return surface === "main_app";
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

app.on("second-instance", () => {
  logWindowLifecycle("app.second_instance", {
    surface: lastRequestedSurface
  });
  void recoverMainWindow("second-instance");
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
    if (shouldGuardMainWindowClose(window)) {
      event.preventDefault();
      logWindowLifecycle("window.close_guarded", details);
      lastCloseRequestHint = null;
      restoreWindowVisibility(window, "close-guard");
      scheduleVisibilityRecovery(window, "close-guard");
      return;
    }
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
    void shell.openExternal(details.url);
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
      if (shouldGuardMainWindowClose(window)) {
        event.preventDefault();
        restoreWindowVisibility(window, "close-accelerator-guard");
        scheduleVisibilityRecovery(window, "close-accelerator-guard");
      }
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
  currentLocale = loadDesktopLocale();

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
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  appIsQuitting = true;
  logWindowLifecycle("app.before_quit", {
    surface: lastRequestedSurface
  });
  await runtime.shutdown();
});
