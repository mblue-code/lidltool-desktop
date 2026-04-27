import { expect, test, type Page } from "@playwright/test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ReceiptPluginPackManager,
  type ValidatedManifestSnapshot
} from "../../src/main/plugins/receipt-plugin-packs";
import { launchDesktopApp } from "./helpers/desktop-app";

type AuthChromeProcess = {
  pid: number;
  port: number;
  userDataDir: string;
};

function readDevToolsPort(userDataDir: string): number | null {
  const portFile = join(userDataDir, "DevToolsActivePort");
  if (!existsSync(portFile)) {
    return null;
  }
  const lines = readFileSync(portFile, "utf-8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) {
    return null;
  }
  const port = Number(lines[0]);
  return Number.isFinite(port) && port > 0 ? port : null;
}

function readJson(path: string): Record<string, any> {
  return JSON.parse(readFileSync(path, "utf-8")) as Record<string, any>;
}

async function validateManifestFixture(manifestPath: string): Promise<ValidatedManifestSnapshot> {
  const manifest = readJson(manifestPath);
  const supportedHostKinds = Array.isArray(manifest.compatibility?.supported_host_kinds)
    ? manifest.compatibility.supported_host_kinds.map((item: unknown) => String(item))
    : [];
  return {
    pluginId: String(manifest.plugin_id),
    sourceId: String(manifest.source_id),
    displayName: String(manifest.display_name),
    pluginVersion: String(manifest.plugin_version),
    pluginFamily: "receipt",
    runtimeKind: String(manifest.runtime_kind),
    pluginOrigin: String(manifest.plugin_origin),
    trustClass: String(manifest.trust_class) as ValidatedManifestSnapshot["trustClass"],
    entrypoint: typeof manifest.entrypoint === "string" ? manifest.entrypoint : null,
    supportedHostKinds,
    minCoreVersion:
      typeof manifest.compatibility?.min_core_version === "string" ? manifest.compatibility.min_core_version : null,
    maxCoreVersion:
      typeof manifest.compatibility?.max_core_version === "string" ? manifest.compatibility.max_core_version : null,
    compatibilityStatus: supportedHostKinds.includes("electron") ? "compatible" : "incompatible",
    compatibilityReason: supportedHostKinds.includes("electron") ? null : "host_kind_not_supported",
    onboarding:
      manifest.onboarding && typeof manifest.onboarding === "object"
        ? {
            title: typeof manifest.onboarding.title === "string" ? manifest.onboarding.title : null,
            summary: typeof manifest.onboarding.summary === "string" ? manifest.onboarding.summary : null,
            expectedSpeed:
              typeof manifest.onboarding.expected_speed === "string"
                ? manifest.onboarding.expected_speed
                : null,
            caution: typeof manifest.onboarding.caution === "string" ? manifest.onboarding.caution : null,
            steps: Array.isArray(manifest.onboarding.steps)
              ? manifest.onboarding.steps.flatMap((step: unknown) => {
                  if (!step || typeof step !== "object") {
                    return [];
                  }
                  const candidate = step as Record<string, unknown>;
                  if (typeof candidate.title !== "string" || typeof candidate.description !== "string") {
                    return [];
                  }
                  return [{ title: candidate.title, description: candidate.description }];
                })
              : []
          }
        : null
  };
}

function apiFetch(
  origin: string,
  cookieJar: string,
  path: string,
  init: {
    method?: "GET" | "POST";
    body?: string;
  } = {}
): { ok: boolean; status: number; data: any } {
  const args = ["-sS", "-b", cookieJar, "-c", cookieJar, "-w", "\n%{http_code}"];
  const method = init.method ?? "GET";
  if (method !== "GET") {
    args.push("-X", method);
  }
  if (typeof init.body === "string") {
    args.push("-H", "Content-Type: application/json", "--data", init.body);
  }
  args.push(new URL(path, origin).toString());
  const result = spawnSync("curl", args, { encoding: "utf-8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const lines = result.stdout.trimEnd().split(/\r?\n/);
  const status = Number(lines.pop() || "0");
  const body = lines.join("\n");
  let data: any = null;
  try {
    data = JSON.parse(body);
  } catch {
    data = body;
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    data
  };
}

function fetchConnectorBySource(origin: string, cookieJar: string, sourceId: string): any | null {
  const result = apiFetch(origin, cookieJar, "/api/v1/connectors");
  const connectors = result.data?.result?.connectors;
  if (!result.ok || !Array.isArray(connectors)) {
    return null;
  }
  return connectors.find((connector: any) => connector.source_id === sourceId) ?? null;
}

function fetchBootstrapStatus(origin: string, cookieJar: string, sourceId: string): any | null {
  const result = apiFetch(origin, cookieJar, `/api/v1/connectors/${sourceId}/bootstrap/status`);
  return result.ok ? result.data : null;
}

async function waitForBackendAuth(origin: string): Promise<{ required: boolean }> {
  return await expect
    .poll(() => {
      const result = apiFetch(origin, "/dev/null", "/api/v1/auth/setup-required");
      return result.ok && typeof result.data?.result?.required === "boolean" ? result.data.result : null;
    }, { timeout: 120_000, intervals: [1_000, 2_000, 3_000] })
    .not.toBeNull() as { required: boolean };
}

function ensureAuthenticatedViaApi(origin: string, cookieJar: string, username: string, password: string): void {
  const setupStatus = apiFetch(origin, cookieJar, "/api/v1/auth/setup-required");
  assert.equal(setupStatus.ok, true, JSON.stringify(setupStatus.data));
  const required = Boolean(setupStatus.data?.result?.required);
  const payload = JSON.stringify({
    username,
    password,
    display_name: null,
    bootstrap_token: null
  });
  if (required) {
    const result = apiFetch(origin, cookieJar, "/api/v1/auth/setup", {
      method: "POST",
      body: payload
    });
    assert.equal(result.ok, true, JSON.stringify(result.data));
  } else {
    const result = apiFetch(origin, cookieJar, "/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    });
    assert.equal(result.ok, true, JSON.stringify(result.data));
  }
}

function queryPennySyncState(dbPath: string): { txCount: number; grossSum: number; discountSum: number; itemCount: number } {
  const script = [
    "import json, sqlite3, sys",
    "db = sqlite3.connect(sys.argv[1])",
    "tx = db.execute(\"select count(*), coalesce(sum(total_gross_cents),0), coalesce(sum(discount_total_cents),0) from transactions where source_id = ?\", (\"penny_de\",)).fetchone()",
    "items = db.execute(\"select count(*) from transaction_items where transaction_id in (select id from transactions where source_id = ?)\", (\"penny_de\",)).fetchone()",
    "print(json.dumps({'txCount': tx[0], 'grossSum': tx[1], 'discountSum': tx[2], 'itemCount': items[0]}))"
  ].join(";");
  const result = spawnSync("python3", ["-c", script, dbPath], { encoding: "utf-8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout.trim()) as { txCount: number; grossSum: number; discountSum: number; itemCount: number };
}

function findAuthChromeProcess(): AuthChromeProcess | null {
  const candidateRoots = Array.from(
    new Set([tmpdir(), "/tmp", "/private/tmp"].filter((value) => value && existsSync(value)))
  );
  const result = spawnSync("ps", ["-axo", "pid=,args="], { encoding: "utf-8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  const lines = result.stdout.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

  for (const line of lines) {
    if (!line.includes("lidltool-auth-browser-") || !line.includes("--user-data-dir=")) {
      continue;
    }
    const pidMatch = line.match(/^(\d+)\s+/);
    const userDataDirMatch = line.match(/--user-data-dir=([^\s]+)/);
    if (!pidMatch || !userDataDirMatch) {
      continue;
    }
    const port = readDevToolsPort(userDataDirMatch[1]);
    if (!port) {
      continue;
    }
    return {
      pid: Number(pidMatch[1]),
      port,
      userDataDir: userDataDirMatch[1]
    };
  }

  const profileDirs: string[] = [];
  for (const root of candidateRoots) {
    for (const entry of readdirSync(root, { withFileTypes: true })) {
      if (!entry.isDirectory() || !entry.name.startsWith("lidltool-auth-browser-")) {
        continue;
      }
      profileDirs.push(join(root, entry.name));
    }
  }
  profileDirs.sort((left, right) => statSync(right).mtimeMs - statSync(left).mtimeMs);

  for (const userDataDir of profileDirs) {
    const port = readDevToolsPort(userDataDir);
    if (!port) {
      continue;
    }
    const processLine = lines.find((line) => line.includes(`--user-data-dir=${userDataDir}`));
    const pidMatch = processLine?.match(/^(\d+)\s+/) ?? null;
    return {
      pid: pidMatch ? Number(pidMatch[1]) : -1,
      port,
      userDataDir
    };
  }
  return null;
}

async function waitForAuthChromeProcess(
  origin: string,
  cookieJar: string,
  sourceId: string,
  timeoutMs = 60_000
): Promise<AuthChromeProcess> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const process = findAuthChromeProcess();
    if (process !== null) {
      return process;
    }
    const bootstrapStatus = fetchBootstrapStatus(origin, cookieJar, sourceId);
    const status = bootstrapStatus?.result?.status;
    if (typeof status === "string" && status !== "running") {
      throw new Error(`Penny bootstrap ended before Chrome attach: ${JSON.stringify(bootstrapStatus)}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("Timed out waiting for the host-launched Penny auth Chrome process.");
}

async function waitForBootstrapCompletion(origin: string, cookieJar: string, sourceId: string, timeoutMs = 180_000): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  let lastSnapshot: any = null;
  while (Date.now() < deadline) {
    lastSnapshot = fetchBootstrapStatus(origin, cookieJar, sourceId);
    const status = lastSnapshot?.result?.status;
    if (typeof status === "string" && status !== "running") {
      return lastSnapshot;
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`Timed out waiting for Penny bootstrap completion: ${JSON.stringify(lastSnapshot)}`);
}

function runAppleScript(lines: string[]): string {
  const args = lines.flatMap((line) => ["-e", line]);
  const result = spawnSync("osascript", args, { encoding: "utf-8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

function appleScriptString(value: string): string {
  return JSON.stringify(value);
}

function chromeExecuteJavascript(urlNeedle: string, javascript: string): { ok: boolean; value: string } {
  const script = [
    "tell application \"Google Chrome\"",
    "repeat with w in windows",
    "repeat with i from 1 to (count of tabs of w)",
    `if URL of tab i of w contains ${appleScriptString(urlNeedle)} then`,
    "set active tab index of w to i",
    "set index of w to 1",
    "activate",
    `set jsResult to execute active tab of w javascript ${appleScriptString(javascript)}`,
    "return jsResult",
    "end if",
    "end repeat",
    "end repeat",
    "return \"\"",
    "end tell"
  ];
  const result = spawnSync("osascript", script.flatMap((line) => ["-e", line]), { encoding: "utf-8" });
  if (result.status === 0) {
    return { ok: true, value: result.stdout.trim() };
  }
  return { ok: false, value: `${result.stderr || result.stdout}`.trim() };
}

function chromeEnsureAppleEventJavascriptEnabled(): void {
  const probe = chromeExecuteJavascript("account.penny.de", "document.readyState");
  if (probe.ok) {
    return;
  }
  if (!probe.value.includes("JavaScript") || !probe.value.includes("Apple Events")) {
    throw new Error(`Chrome AppleScript bridge failed before login automation: ${probe.value}`);
  }

  runAppleScript([
    "tell application \"Google Chrome\" to activate",
    "delay 0.5",
    "tell application \"System Events\"",
    "tell process \"Google Chrome\"",
    "try",
    "click menu item \"JavaScript from Apple Events\" of menu \"Developer\" of menu item \"Developer\" of menu \"View\" of menu bar item \"View\" of menu bar 1",
    "on error",
    "click menu item \"JavaScript von Apple Events erlauben\" of menu \"Entwickler\" of menu item \"Entwickler\" of menu \"Darstellung\" of menu bar item \"Darstellung\" of menu bar 1",
    "end try",
    "end tell",
    "end tell"
  ]);
}

function parseChromeProbe(raw: string): { challenge: boolean; fields: boolean } {
  const payload = JSON.parse(raw || "{}") as { challenge?: boolean; fields?: boolean };
  return {
    challenge: Boolean(payload.challenge),
    fields: Boolean(payload.fields)
  };
}

async function automatePennyLogin(email: string, password: string): Promise<void> {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const urls = runAppleScript([
      "tell application \"Google Chrome\"",
      "set foundUrls to {}",
      "repeat with w in windows",
      "repeat with t in tabs of w",
      "copy (URL of t) to end of foundUrls",
      "end repeat",
      "end repeat",
      "return foundUrls as string",
      "end tell"
    ]);
    if (urls.includes("account.penny.de")) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  chromeEnsureAppleEventJavascriptEnabled();

  const probeScript = `
    (() => {
      const text = (document.body?.innerText || "").toLowerCase();
      const challenge =
        !!document.querySelector('iframe[src*="turnstile"], .cf-turnstile') ||
        text.includes('verify you are human') ||
        text.includes('bestaetige, dass du ein mensch bist') ||
        text.includes('bestätige, dass du ein mensch bist');
      const cookieButton = Array.from(document.querySelectorAll('button')).find((button) =>
        /accept all|alle akzeptieren|accept|akzeptieren/i.test(button.textContent || '')
      );
      if (cookieButton) cookieButton.click();
      const username = document.querySelector('#username, input[name="username"], input[type="email"]');
      const password = document.querySelector('#password, input[name="password"], input[type="password"]');
      return JSON.stringify({ challenge, fields: !!username && !!password });
    })();
  `;

  while (Date.now() < deadline) {
    const probe = chromeExecuteJavascript("account.penny.de", probeScript);
    if (!probe.ok) {
      throw new Error(`Chrome login probe failed: ${probe.value}`);
    }
    const parsed = parseChromeProbe(probe.value);
    if (parsed.challenge) {
      throw new Error("Penny login presented a Turnstile or verification challenge in the fresh host-browser flow.");
    }
    if (parsed.fields) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  const submitScript = `
    (() => {
      const username = document.querySelector('#username, input[name="username"], input[type="email"]');
      const password = document.querySelector('#password, input[name="password"], input[type="password"]');
      const submit = document.querySelector('#kc-login, button[type="submit"], input[type="submit"]');
      if (!username || !password || !submit) {
        return JSON.stringify({ ok: false, reason: 'missing-fields' });
      }
      const applyValue = (element, value) => {
        element.focus();
        element.value = value;
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
      };
      applyValue(username, ${JSON.stringify(email)});
      applyValue(password, ${JSON.stringify(password)});
      submit.click();
      return JSON.stringify({ ok: true });
    })();
  `;

  const submit = chromeExecuteJavascript("account.penny.de", submitScript);
  if (!submit.ok) {
    throw new Error(`Chrome login submit failed: ${submit.value}`);
  }
  const parsedSubmit = JSON.parse(submit.value || "{}") as { ok?: boolean; reason?: string };
  if (!parsedSubmit.ok) {
    throw new Error(`Chrome login submit did not complete: ${JSON.stringify(parsedSubmit)}`);
  }
}

test("fresh packaged desktop profile completes Penny auth through host-launched Chrome and syncs into a clean DB", async () => {
  test.setTimeout(420_000);

  const packagedExecutable = process.env.LIDLTOOL_DESKTOP_EXECUTABLE?.trim();
  const pennyEmail = process.env.PENNY_TEST_EMAIL?.trim();
  const pennyPassword = process.env.PENNY_TEST_PASSWORD?.trim();
  const chromePath =
    process.env.PENNY_TEST_CHROME_PATH?.trim() ??
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

  test.skip(!packagedExecutable, "Set LIDLTOOL_DESKTOP_EXECUTABLE to the packaged desktop binary.");
  test.skip(!pennyEmail || !pennyPassword, "Set PENNY_TEST_EMAIL and PENNY_TEST_PASSWORD.");
  test.skip(!existsSync(chromePath), `Expected a Chromium browser at ${chromePath}.`);

  const explicitProfileRoot = fileURLToPath(new URL("../../.tmp/penny-live-fresh/", import.meta.url));
  const userDataDir = join(explicitProfileRoot, "electron-user-data");
  const homeDir = join(explicitProfileRoot, "home");
  const tmpPath = join(explicitProfileRoot, "tmp");
  const cookieJar = join(explicitProfileRoot, "api-cookies.txt");
  const pluginStorageDir = join(userDataDir, "plugins", "receipt-packs");
  const packOutputDir = join(explicitProfileRoot, "pack-output");
  const dbPath = join(userDataDir, "lidltool.sqlite");
  const stateFile = join(explicitProfileRoot, "penny-state.json");
  const pluginDir = fileURLToPath(new URL("../../fixtures/plugin-sources/penny_de/", import.meta.url));

  rmSync(explicitProfileRoot, { recursive: true, force: true });

  const manager = new ReceiptPluginPackManager({
    rootDir: pluginStorageDir,
    validateManifest: validateManifestFixture
  });

  const build = spawnSync(
    "python3",
    [join(pluginDir, "build_desktop_pack.py"), "--output-dir", packOutputDir],
    { encoding: "utf-8" }
  );
  assert.equal(build.status, 0, build.stderr || build.stdout);
  const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
  assert.ok(packPath);

  const install = await manager.installFromFile(packPath);
  assert.equal(install.pack.sourceId, "penny_de");
  const enabledPack = await manager.setEnabled("local.penny_de", true);
  assert.equal(enabledPack.status, "enabled");
  const installPath = join(pluginStorageDir, "installs", "local.penny_de", "0.1.0");

  const session = await launchDesktopApp({
    executablePath: packagedExecutable,
    userDataDir,
    homeDir,
    tmpPath,
    envOverrides: {
      LIDLTOOL_PLAYWRIGHT_BROWSER_EXECUTABLE_PATH: chromePath,
      LIDLTOOL_AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM: "true",
      LIDLTOOL_CONNECTOR_PLUGIN_PATHS: installPath,
      LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED: "true",
      LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED: "true",
      LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES: "local_custom"
    }
  });
  const { page, close } = session;

  try {
      await page.waitForURL(/127\.0\.0\.1|localhost/, { timeout: 120_000 });
      const origin = new URL(page.url()).origin;
      await waitForBackendAuth(origin);

      ensureAuthenticatedViaApi(origin, cookieJar, "penny-fresh-admin", "penny-fresh-pass");

      await expect
        .poll(() => {
          const connector = fetchConnectorBySource(origin, cookieJar, "penny_de");
          return connector?.source_id ?? null;
        }, { timeout: 90_000, intervals: [1_000, 2_000, 3_000] })
        .toBe("penny_de");

      const configResult = apiFetch(origin, cookieJar, "/api/v1/connectors/penny_de/config", {
        method: "POST",
        body: JSON.stringify({
          values: {
            chrome_cookie_export: false,
            state_file: stateFile,
            force_reauth: true
          },
          clear_secret_keys: []
        })
      });
      assert.equal(configResult.ok, true, JSON.stringify(configResult.data));

      const enableResult = apiFetch(origin, cookieJar, "/api/v1/connectors/penny_de/enable", { method: "POST" });
      assert.equal(enableResult.ok, true, JSON.stringify(enableResult.data));

      await expect
        .poll(() => {
          const connector = fetchConnectorBySource(origin, cookieJar, "penny_de");
          return connector?.enable_state ?? null;
        }, { timeout: 90_000, intervals: [1_000, 2_000, 3_000] })
        .toBe("enabled");

      const bootstrapStart = apiFetch(origin, cookieJar, "/api/v1/connectors/penny_de/bootstrap/start", {
        method: "POST"
      });
      assert.equal(bootstrapStart.ok, true, JSON.stringify(bootstrapStart.data));

      const chromeProcess = await waitForAuthChromeProcess(origin, cookieJar, "penny_de");
      assert.ok(chromeProcess.userDataDir.includes("lidltool-auth-browser-"));

      await automatePennyLogin(pennyEmail!, pennyPassword!);

      const bootstrapStatus = await waitForBootstrapCompletion(origin, cookieJar, "penny_de");
      assert.equal(
        bootstrapStatus?.result?.status,
        "succeeded",
        `Penny bootstrap did not succeed: ${JSON.stringify(bootstrapStatus)}`
      );

      await expect
        .poll(() => {
          const connector = fetchConnectorBySource(origin, cookieJar, "penny_de");
          return connector?.advanced?.auth_state ?? null;
        }, { timeout: 90_000, intervals: [1_000, 2_000, 3_000] })
        .toBe("connected");

      const state = readJson(stateFile);
      assert.ok(state.oauth, "Expected plugin-local Penny OAuth state to be stored.");
      assert.equal(state.browser_session ?? null, null, "Fresh host-browser flow should not leave a Chrome cookie-import session behind.");

      const syncStart = apiFetch(origin, cookieJar, "/api/v1/connectors/penny_de/sync", { method: "POST" });
      assert.equal(syncStart.ok, true, JSON.stringify(syncStart.data));

      await expect
        .poll(() => queryPennySyncState(dbPath), {
          timeout: 180_000,
          intervals: [2_000, 3_000, 5_000]
        })
        .toMatchObject({
          txCount: 1,
          itemCount: 6,
          grossSum: 1102,
          discountSum: 24
        });

      const dbState = queryPennySyncState(dbPath);
      console.log("penny-fresh-sync", JSON.stringify(dbState));
      console.log(
        "penny-host-browser",
        JSON.stringify({
          chromePid: chromeProcess.pid,
          chromePort: chromeProcess.port,
          bootstrapStatus: bootstrapStatus.result.status
        })
      );
  } finally {
    await close();
  }
});
