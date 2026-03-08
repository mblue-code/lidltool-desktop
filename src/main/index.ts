import { app, BrowserWindow, shell } from "electron";
import { join } from "node:path";
import type { DesktopLocale } from "@shared/contracts";
import { registerIpc } from "./ipc";
import { applyDesktopMenu, loadDesktopLocale, persistDesktopLocale } from "./i18n";
import { DesktopRuntime } from "./runtime";

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

async function bootIntoFullApp(window: BrowserWindow): Promise<void> {
  try {
    await runtime.startBackend({ strictOverride: true });
    latestBootError = null;
    await window.loadURL(runtime.getFullAppUrl());
  } catch (err) {
    const message = String(err);
    await loadControlCenter(window, message);
  }
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
        await bootIntoFullApp(mainWindow);
      }
    },
    reloadControlCenter: async () => {
      if (mainWindow) {
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

  void bootIntoFullApp(window);

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
    (locale) => updateDesktopLocale(locale)
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
