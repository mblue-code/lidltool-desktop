import { execFile, execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { promisify } from "node:util";
import { join } from "node:path";
import { app, shell } from "electron";

import type { DesktopExternalBrowserId, DesktopExternalBrowserPreferenceState } from "@shared/contracts";

const execFileAsync = promisify(execFile);
const DESKTOP_EXTERNAL_BROWSER_FILE = "desktop-external-browser.json";

type DesktopExternalBrowserDefinition = {
  id: DesktopExternalBrowserId;
  appName: string | null;
  appBundleId: string | null;
};

const DESKTOP_EXTERNAL_BROWSERS: readonly DesktopExternalBrowserDefinition[] = [
  {
    id: "system_default",
    appName: null,
    appBundleId: null
  },
  {
    id: "arc",
    appName: "Arc",
    appBundleId: "company.thebrowser.Browser"
  },
  {
    id: "atlas",
    appName: "ChatGPT Atlas",
    appBundleId: "com.openai.atlas"
  },
  {
    id: "google_chrome",
    appName: "Google Chrome",
    appBundleId: "com.google.Chrome"
  }
] as const;

function externalBrowserFilePath(): string {
  const userDataDir = app.getPath("userData");
  mkdirSync(userDataDir, { recursive: true });
  return join(userDataDir, DESKTOP_EXTERNAL_BROWSER_FILE);
}

function isDesktopExternalBrowserId(value: string | null | undefined): value is DesktopExternalBrowserId {
  return DESKTOP_EXTERNAL_BROWSERS.some((browser) => browser.id === value);
}

function resolveDesktopExternalBrowserId(value: string | null | undefined): DesktopExternalBrowserId {
  if (isDesktopExternalBrowserId(value)) {
    return value;
  }
  return "system_default";
}

function browserAvailable(browser: DesktopExternalBrowserDefinition): boolean {
  if (browser.id === "system_default") {
    return true;
  }
  if (process.platform !== "darwin" || browser.appBundleId === null) {
    return false;
  }
  return macBundleIdInstalled(browser.appBundleId);
}

function macBundleIdInstalled(bundleId: string): boolean {
  try {
    const result = execFileSync("/usr/bin/mdfind", [`kMDItemCFBundleIdentifier == "${bundleId}"`], {
      encoding: "utf-8"
    });
    return result.trim().length > 0;
  } catch {
    return false;
  }
}

export function loadDesktopExternalBrowserPreference(): DesktopExternalBrowserPreferenceState {
  const filePath = externalBrowserFilePath();
  let preferredBrowser: DesktopExternalBrowserId = "system_default";
  if (existsSync(filePath)) {
    try {
      const parsed = JSON.parse(readFileSync(filePath, "utf-8")) as { preferredBrowser?: string };
      preferredBrowser = resolveDesktopExternalBrowserId(parsed.preferredBrowser);
    } catch {
      preferredBrowser = "system_default";
    }
  }

  return {
    preferredBrowser,
    options: DESKTOP_EXTERNAL_BROWSERS.map((browser) => ({
      id: browser.id,
      available: browserAvailable(browser)
    }))
  };
}

export function persistDesktopExternalBrowserPreference(
  preferredBrowser: DesktopExternalBrowserId
): DesktopExternalBrowserPreferenceState {
  const resolved = resolveDesktopExternalBrowserId(preferredBrowser);
  writeFileSync(externalBrowserFilePath(), JSON.stringify({ preferredBrowser: resolved }, null, 2), "utf-8");
  return loadDesktopExternalBrowserPreference();
}

export async function openUrlWithDesktopBrowserPreference(
  url: string,
  preferredBrowserOverride?: DesktopExternalBrowserId | null
): Promise<void> {
  const normalizedUrl = url.trim();
  if (!normalizedUrl) {
    return;
  }

  const preferredBrowser = resolveDesktopExternalBrowserId(
    preferredBrowserOverride ?? loadDesktopExternalBrowserPreference().preferredBrowser
  );
  const selected = DESKTOP_EXTERNAL_BROWSERS.find((browser) => browser.id === preferredBrowser) ?? DESKTOP_EXTERNAL_BROWSERS[0];

  if (
    process.platform !== "darwin" ||
    selected.id === "system_default" ||
    selected.appBundleId === null ||
    !browserAvailable(selected)
  ) {
    await shell.openExternal(normalizedUrl);
    return;
  }

  try {
    await execFileAsync("open", ["-b", selected.appBundleId, normalizedUrl]);
  } catch {
    await shell.openExternal(normalizedUrl);
  }
}
