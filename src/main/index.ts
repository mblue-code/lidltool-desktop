import { app, BrowserWindow, shell } from "electron";
import { join } from "node:path";
import { registerIpc } from "./ipc";
import { DesktopRuntime } from "./runtime";

let mainWindow: BrowserWindow | null = null;
const runtime = new DesktopRuntime();
let latestBootError: string | null = null;

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

function createWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 980,
    minHeight: 680,
    show: false,
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

  mainWindow = createWindow();
  registerIpc(runtime, () => latestBootError);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow();
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
