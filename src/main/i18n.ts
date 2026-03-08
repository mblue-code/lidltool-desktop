import { app, Menu, type BrowserWindow, type MenuItemConstructorOptions } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type { DesktopLocale } from "@shared/contracts";
import { resolveDesktopLocale, translateDesktopMessage } from "../i18n";

const DESKTOP_LOCALE_FILE = "desktop-locale.json";

function localeFilePath(): string {
  const userDataDir = app.getPath("userData");
  mkdirSync(userDataDir, { recursive: true });
  return join(userDataDir, DESKTOP_LOCALE_FILE);
}

export function loadDesktopLocale(): DesktopLocale {
  const filePath = localeFilePath();
  if (existsSync(filePath)) {
    try {
      const parsed = JSON.parse(readFileSync(filePath, "utf-8")) as { locale?: string };
      return resolveDesktopLocale(parsed.locale);
    } catch {
      return resolveDesktopLocale(app.getLocale());
    }
  }
  return resolveDesktopLocale(app.getLocale());
}

export function persistDesktopLocale(locale: DesktopLocale): void {
  writeFileSync(localeFilePath(), JSON.stringify({ locale }, null, 2), "utf-8");
}

type MenuCallbacks = {
  openFullApp: () => Promise<void>;
  reloadControlCenter: () => Promise<void>;
  startBackend: () => Promise<void>;
  stopBackend: () => Promise<void>;
};

export function applyDesktopMenu(
  locale: DesktopLocale,
  mainWindow: BrowserWindow | null,
  callbacks: MenuCallbacks
): void {
  const appMenuLabel =
    process.platform === "darwin"
      ? translateDesktopMessage(locale, "app.brand.title")
      : translateDesktopMessage(locale, "shell.menu.application");

  const applicationSubmenu: MenuItemConstructorOptions[] = [
    {
      label: translateDesktopMessage(locale, "shell.menu.openFullApp"),
      click: () => {
        void callbacks.openFullApp();
      }
    },
    {
      label: translateDesktopMessage(locale, "shell.menu.reloadControlCenter"),
      click: () => {
        void callbacks.reloadControlCenter();
      }
    },
    { type: "separator" },
    {
      label: translateDesktopMessage(locale, "shell.menu.startBackend"),
      click: () => {
        void callbacks.startBackend();
      }
    },
    {
      label: translateDesktopMessage(locale, "shell.menu.stopBackend"),
      click: () => {
        void callbacks.stopBackend();
      }
    },
    { type: "separator" },
    {
      label: translateDesktopMessage(locale, "shell.menu.quit"),
      click: () => app.quit()
    }
  ];

  const template: MenuItemConstructorOptions[] = [
    {
      label: appMenuLabel,
      submenu: applicationSubmenu
    },
    {
      label: translateDesktopMessage(locale, "shell.menu.window"),
      submenu: [
        {
          label: translateDesktopMessage(locale, "shell.menu.minimize"),
          role: "minimize"
        }
      ]
    }
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
  mainWindow?.setTitle(translateDesktopMessage(locale, "shell.windowTitle"));
}
