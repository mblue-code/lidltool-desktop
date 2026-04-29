import { expect, type Page } from "@playwright/test";
import { _electron as electron, type ElectronApplication } from "playwright";
import { mkdtempSync, mkdirSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const DESKTOP_APP_DIR = resolve(__dirname, "../../..");
const require = createRequire(import.meta.url);
const electronBinary = require("electron") as string;

export type DesktopLaunchOptions = {
  frontendDistMode?: "default" | "missing";
  envOverrides?: Record<string, string>;
  executablePath?: string;
  homeDir?: string;
  userDataDir?: string;
  tmpPath?: string;
};

export type DesktopAppSession = {
  electronApp: ElectronApplication;
  page: Page;
  profileRoot: string;
  homeDir: string;
  close: () => Promise<void>;
};

function pathnamePattern(pathname: string): RegExp {
  return new RegExp(`${pathname.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:$|[?#])`);
}

async function allocateApiPort(): Promise<number> {
  await new Promise<void>((resolvePromise, reject) => {
    const probeServer = createServer();
    probeServer.once("error", reject);
    probeServer.listen(0, "127.0.0.1", () => {
      probeServer.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolvePromise();
      });
    });
  });

  const probeServer = createServer();
  return await new Promise<number>((resolvePromise, reject) => {
    probeServer.once("error", reject);
    probeServer.listen(0, "127.0.0.1", () => {
      const address = probeServer.address();
      if (!address || typeof address === "string") {
        probeServer.close((closeError) => reject(closeError ?? new Error("Failed to allocate API port.")));
        return;
      }
      const { port } = address;
      probeServer.close((closeError) => {
        if (closeError) {
          reject(closeError);
          return;
        }
        resolvePromise(port);
      });
    });
  });
}

export async function launchDesktopApp(options: DesktopLaunchOptions = {}): Promise<DesktopAppSession> {
  const explicitUserDataDir =
    options.userDataDir ??
    process.env.OUTLAYS_DESKTOP_TEST_USER_DATA_DIR?.trim() ??
    process.env.LIDLTOOL_DESKTOP_TEST_USER_DATA_DIR?.trim();
  const explicitHomeDir =
    options.homeDir ??
    process.env.OUTLAYS_DESKTOP_TEST_HOME_DIR?.trim() ??
    process.env.LIDLTOOL_DESKTOP_TEST_HOME_DIR?.trim();
  const explicitTmpPath =
    options.tmpPath ??
    process.env.OUTLAYS_DESKTOP_TEST_TMP_DIR?.trim() ??
    process.env.LIDLTOOL_DESKTOP_TEST_TMP_DIR?.trim();
  const profileRoot = explicitUserDataDir
    ? dirname(explicitUserDataDir)
    : mkdtempSync(join(tmpdir(), "outlays-desktop-e2e-"));
  const homeDir = explicitHomeDir || join(profileRoot, "home");
  const tmpPath = explicitTmpPath || join(profileRoot, "tmp");
  const userDataDir = explicitUserDataDir || join(profileRoot, "electron-user-data");
  const shouldCleanupProfileRoot = !explicitUserDataDir && !explicitHomeDir && !explicitTmpPath;
  const configDir = join(homeDir, ".config", "lidltool");
  const documentsDir = join(homeDir, ".local", "share", "lidltool", "documents");
  mkdirSync(homeDir, { recursive: true });
  mkdirSync(tmpPath, { recursive: true });
  mkdirSync(userDataDir, { recursive: true });
  mkdirSync(configDir, { recursive: true });
  mkdirSync(documentsDir, { recursive: true });
  const apiPort = await allocateApiPort();

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    CI: "1",
    HOME: homeDir,
    USERPROFILE: homeDir,
    APPDATA: join(homeDir, "AppData", "Roaming"),
    LOCALAPPDATA: join(homeDir, "AppData", "Local"),
    XDG_CONFIG_HOME: join(homeDir, ".config"),
    XDG_DATA_HOME: join(homeDir, ".local", "share"),
    TMPDIR: tmpPath,
    OUTLAYS_DESKTOP_API_PORT: String(apiPort),
    OUTLAYS_DESKTOP_USER_DATA_DIR: userDataDir,
    OUTLAYS_DESKTOP_CONFIG_DIR: configDir,
    OUTLAYS_DESKTOP_DOCUMENT_STORAGE_PATH: documentsDir
  };

  if (options.envOverrides) {
    Object.assign(env, options.envOverrides);
  }

  if (options.frontendDistMode === "missing") {
    const missingFrontendDist = join(profileRoot, "missing-frontend-dist");
    mkdirSync(missingFrontendDist, { recursive: true });
    env.OUTLAYS_DESKTOP_FRONTEND_DIST = missingFrontendDist;
  }

  const requestedExecutablePath =
    options.executablePath ??
    (process.env.OUTLAYS_DESKTOP_EXECUTABLE?.trim() || process.env.LIDLTOOL_DESKTOP_EXECUTABLE?.trim() || electronBinary);
  const isPackagedLaunch = requestedExecutablePath !== electronBinary;

  const electronApp = await electron.launch({
    executablePath: requestedExecutablePath,
    args: isPackagedLaunch ? [] : [DESKTOP_APP_DIR],
    cwd: isPackagedLaunch ? dirname(requestedExecutablePath) : DESKTOP_APP_DIR,
    env
  });

  const page = await electronApp.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => {
    try {
      window.localStorage.setItem("app.locale", "en");
      window.localStorage.setItem("desktop.shell.locale", "en");
    } catch {
      // Ignore storage access errors during bootstrap.
    }
  });
  await page.reload({ waitUntil: "domcontentloaded" });

  return {
    electronApp,
    page,
    profileRoot,
    homeDir,
    close: async () => {
      await electronApp.close();
      if (shouldCleanupProfileRoot) {
        rmSync(profileRoot, { recursive: true, force: true });
      }
    }
  };
}

export async function openMainApp(page: Page): Promise<void> {
  const openButton = page.getByRole("button", { name: "Open main app" }).first();
  await expect(openButton).toBeVisible();
  await openButton.click();
  await page.waitForURL(/:\/\/(?:127\.0\.0\.1|localhost):\d+(?:\/|$)/, { timeout: 90_000 });
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => {
    try {
      window.localStorage.setItem("app.locale", "en");
    } catch {
      // Ignore storage access errors during bootstrap.
    }
  });
  await page.reload({ waitUntil: "domcontentloaded" });
}

export async function ensureAuthenticated(
  page: Page,
  credentials = {
    username: "desktop-e2e",
    password: "desktop-e2e-pass"
  }
): Promise<void> {
  await page.waitForLoadState("domcontentloaded");

  async function readApiError(response: Awaited<ReturnType<Page["waitForResponse"]>>): Promise<string | null> {
    try {
      const payload = await response.json();
      return typeof payload?.error === "string" ? payload.error : null;
    } catch {
      return null;
    }
  }

  async function createAccount(): Promise<string | null> {
    await page.locator("#username").waitFor({ state: "visible" });
    await page.locator("#username").fill(credentials.username);
    await page.locator("#password").fill(credentials.password);
    await page.locator("#confirm").fill(credentials.password);
    const responsePromise = page.waitForResponse(
      (response) => response.request().method() === "POST" && response.url().includes("/api/v1/auth/setup")
    );
    await page.getByRole("button", { name: "Create account" }).click();
    const response = await responsePromise;
    return response.ok() ? null : await readApiError(response);
  }

  async function signIn(): Promise<string | null> {
    await page.locator("#username").waitFor({ state: "visible" });
    await page.locator("#username").fill(credentials.username);
    await page.locator("#password").fill(credentials.password);
    const responsePromise = page.waitForResponse(
      (response) => response.request().method() === "POST" && response.url().includes("/api/v1/auth/login")
    );
    await page.getByRole("button", { name: "Sign in" }).click();
    const response = await responsePromise;
    return response.ok() ? null : await readApiError(response);
  }

  for (let attempt = 0; attempt < 8; attempt += 1) {
    const currentPath = new URL(page.url()).pathname;

    if (
      await page
        .getByRole("button", { name: "Open main app" })
        .first()
        .isVisible()
        .catch(() => false)
    ) {
      await openMainApp(page);
      await page.waitForLoadState("domcontentloaded");
      continue;
    }

    if (
      currentPath === "/" &&
      (await page.getByRole("heading", { name: "Your finance overview" }).isVisible().catch(() => false))
    ) {
      return;
    }

    if (currentPath === "/setup") {
      const error = await createAccount();
      if (error?.includes("setup already completed")) {
        await page.goto(new URL("/login", page.url()).toString());
      } else if (error) {
        throw new Error(`Desktop setup failed: ${error}`);
      }
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(250);
      continue;
    }

    if (currentPath === "/login") {
      const error = await signIn();
      if (error?.includes("Invalid username or password")) {
        await page.goto(new URL("/setup", page.url()).toString());
      } else if (error && error !== "authentication required") {
        throw new Error(`Desktop sign-in failed: ${error}`);
      }
      await page.waitForLoadState("domcontentloaded");
      await page.waitForTimeout(250);
      continue;
    }

    await page.waitForTimeout(250);
  }

  await expect(page).toHaveURL(pathnamePattern("/"));
  await expect(page.locator("#main-content").getByRole("heading", { name: "Your finance overview" }).first()).toBeVisible();
}

export async function openAdvancedTools(page: Page): Promise<void> {
  const productsLink = page.getByRole("navigation", { name: "Primary navigation" }).getByRole("link", {
    name: "Products",
    exact: true
  });
  if (await productsLink.isVisible().catch(() => false)) {
    return;
  }
  const showButton = page.getByRole("button", { name: "Show advanced tools" });
  if (await showButton.isVisible()) {
    await showButton.click();
  }
  await expect(productsLink).toBeVisible();
}

export async function clickNavLink(page: Page, name: string, expectedPath: string, headingName?: string): Promise<void> {
  await page
    .getByRole("navigation", { name: "Primary navigation" })
    .getByRole("link", { name, exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(pathnamePattern(expectedPath));
  if (headingName) {
    await expect(page.locator("#main-content").getByRole("heading", { name: headingName }).first()).toBeVisible();
  }
}

export async function ensureVisibleWindowCount(
  electronApp: ElectronApplication,
  minimumVisibleWindows = 1
): Promise<void> {
  await expect
    .poll(async () => {
      const visibleWindowCount = await electronApp.evaluate(({ BrowserWindow }) => {
        return BrowserWindow.getAllWindows().filter((window) => !window.isDestroyed() && window.isVisible()).length;
      });
      return visibleWindowCount >= minimumVisibleWindows;
    })
    .toBe(true);
}
