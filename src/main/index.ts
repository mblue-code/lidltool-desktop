import { app, BrowserWindow, Menu, shell } from "electron";
import { join } from "node:path";
import type { DesktopLocale } from "@shared/contracts";
import { registerIpc } from "./ipc";
import { applyDesktopMenu, loadDesktopLocale, persistDesktopLocale } from "./i18n";
import { DesktopRuntime } from "./runtime";

const userDataOverride = process.env.LIDLTOOL_DESKTOP_USER_DATA_DIR?.trim();
if (userDataOverride) {
  app.setPath("userData", userDataOverride);
}

let mainWindow: BrowserWindow | null = null;
const runtime = new DesktopRuntime();
let latestBootError: string | null = null;
let currentLocale: DesktopLocale = "en";

async function loadControlCenter(window: BrowserWindow, bootError?: string): Promise<void> {
  latestBootError = bootError ?? null;

  if (process.env.ELECTRON_RENDERER_URL) {
    await window.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    await window.loadFile(join(__dirname, "../renderer/index.html"));
  }

  if (bootError) {
    window.webContents.send("desktop:boot-error", bootError);
  }
}

async function openMainApp(window: BrowserWindow): Promise<void> {
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
  } catch (err) {
    const message = String(err);
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
    await loadControlCenter(window);
  } catch (err) {
    await loadControlCenter(window, String(err));
  }
}

async function openControlCenter(window: BrowserWindow): Promise<void> {
  await runtime.stopBackend();
  await loadControlCenter(window, latestBootError ?? undefined);
}

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
    window.show();
  });

  window.webContents.setWindowOpenHandler((details) => {
    void shell.openExternal(details.url);
    return { action: "deny" };
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

  void loadStartupSurface(window);

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
      mainWindow = createWindow();
      updateDesktopLocale(currentLocale);
    }
  });
});

app.on("window-all-closed", async () => {
  await runtime.shutdown();
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  await runtime.shutdown();
});
