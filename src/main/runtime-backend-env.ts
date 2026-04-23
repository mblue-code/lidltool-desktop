import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import type { CommandLogEvent, CommandResult } from "@shared/contracts";
import {
  normalizeDesktopOcrProvider,
  resolveManagedPlaywrightBrowsersPath,
  shouldManagePlaywrightBrowsers
} from "./runtime-contract";
import { splitLines } from "./runtime-command-runner";

export function resolveCredentialEncryptionKey(userDataDir: string): string {
  const keyFile = join(userDataDir, "credential_encryption_key.txt");
  if (existsSync(keyFile)) {
    const existing = readFileSync(keyFile, "utf-8").trim();
    if (existing.length >= 32) {
      return existing;
    }
  }

  const generated = randomBytes(32).toString("hex");
  writeFileSync(keyFile, `${generated}\n`, { encoding: "utf-8", mode: 0o600 });
  return generated;
}

export function buildDesktopBackendEnv(args: {
  env: NodeJS.ProcessEnv;
  userDataDir: string;
  dbPath: string;
  repoRootHint: string;
  configDir: string;
  documentsPath: string;
  frontendDist: string;
  isPackaged: boolean;
  platform: NodeJS.Platform;
  credentialEncryptionKey: string;
}): NodeJS.ProcessEnv {
  const nextEnv: NodeJS.ProcessEnv = { ...args.env };
  nextEnv.LIDLTOOL_FRONTEND_DIST = args.frontendDist;
  nextEnv.LIDLTOOL_REPO_ROOT = args.repoRootHint;
  nextEnv.LIDLTOOL_DB = args.dbPath;
  nextEnv.LIDLTOOL_CONFIG_DIR = args.configDir;
  nextEnv.LIDLTOOL_DOCUMENT_STORAGE_PATH = args.documentsPath;
  nextEnv.LIDLTOOL_DESKTOP_MODE = "true";
  nextEnv.LIDLTOOL_CONNECTOR_HOST_KIND = "electron";
  nextEnv.LIDLTOOL_OCR_DEFAULT_PROVIDER = normalizeDesktopOcrProvider(nextEnv.LIDLTOOL_OCR_DEFAULT_PROVIDER);
  nextEnv.LIDLTOOL_OCR_FALLBACK_ENABLED = nextEnv.LIDLTOOL_OCR_FALLBACK_ENABLED || "false";
  nextEnv.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY =
    nextEnv.LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY || args.credentialEncryptionKey;

  if (!nextEnv.LIDLTOOL_AUTH_BROWSER_MODE && args.isPackaged && (args.platform === "darwin" || args.platform === "win32")) {
    nextEnv.LIDLTOOL_AUTH_BROWSER_MODE = "local_display";
  }

  if (args.isPackaged) {
    const packagedSrc = join(args.repoRootHint, "src");
    nextEnv.PYTHONPATH = nextEnv.PYTHONPATH?.trim() ? `${packagedSrc}:${nextEnv.PYTHONPATH}` : packagedSrc;
  }

  return nextEnv;
}

export function applyPluginRuntimePolicyToEnv(args: {
  env: NodeJS.ProcessEnv;
  includePluginRuntimePolicy?: boolean;
  runtimePolicy?: {
    activePluginSearchPaths: string[];
    allowedTrustClasses: string[];
  };
}): void {
  if (args.includePluginRuntimePolicy === false) {
    args.env.LIDLTOOL_CONNECTOR_PLUGIN_PATHS = "";
    args.env.LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED = "false";
    args.env.LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED = "false";
    args.env.LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED = "false";
    args.env.LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES = "";
    return;
  }

  const runtimePolicy = args.runtimePolicy ?? {
    activePluginSearchPaths: [],
    allowedTrustClasses: []
  };
  args.env.LIDLTOOL_CONNECTOR_PLUGIN_PATHS = runtimePolicy.activePluginSearchPaths.join(",");
  args.env.LIDLTOOL_CONNECTOR_EXTERNAL_RUNTIME_ENABLED =
    runtimePolicy.activePluginSearchPaths.length > 0 ? "true" : "false";
  args.env.LIDLTOOL_CONNECTOR_EXTERNAL_RECEIPT_PLUGINS_ENABLED =
    runtimePolicy.activePluginSearchPaths.length > 0 ? "true" : "false";
  args.env.LIDLTOOL_CONNECTOR_EXTERNAL_OFFER_PLUGINS_ENABLED = "false";
  args.env.LIDLTOOL_CONNECTOR_EXTERNAL_ALLOWED_TRUST_CLASSES =
    runtimePolicy.allowedTrustClasses.join(",");
}

export async function ensureManagedPlaywrightBrowsers(args: {
  command: string;
  userDataDir: string;
  env: NodeJS.ProcessEnv;
  pythonExecutable: string;
  isPathLike: (command: string) => boolean;
  emitLog: (payload: Omit<CommandLogEvent, "timestamp">) => void;
  runRawCommandCapture: (
    command: string,
    commandArgs: string[],
    env: NodeJS.ProcessEnv
  ) => Promise<CommandResult>;
}): Promise<void> {
  const browsersPath = resolveManagedPlaywrightBrowsersPath(
    args.userDataDir,
    args.command,
    args.env.PLAYWRIGHT_BROWSERS_PATH
  );
  if (!browsersPath || !shouldManagePlaywrightBrowsers(args.command)) {
    return;
  }

  args.env.PLAYWRIGHT_BROWSERS_PATH = browsersPath;
  mkdirSync(browsersPath, { recursive: true });
  if (hasInstalledPlaywrightBrowsers(browsersPath)) {
    return;
  }

  if (!args.isPathLike(args.pythonExecutable) || !existsSync(args.pythonExecutable)) {
    args.emitLog({
      stream: "stderr",
      source: "backend",
      line:
        "Skipping Playwright browser install because no managed Python runtime was found. " +
        "Set PLAYWRIGHT_BROWSERS_PATH manually if you are using an external backend."
    });
    return;
  }

  args.emitLog({
    stream: "stdout",
    source: "backend",
    line: `Installing Playwright Chromium into ${browsersPath}`
  });

  const result = await args.runRawCommandCapture(
    args.pythonExecutable,
    ["-m", "playwright", "install", "chromium"],
    {
      ...args.env,
      PLAYWRIGHT_BROWSERS_PATH: browsersPath
    }
  );

  for (const line of splitLines(result.stdout)) {
    args.emitLog({ stream: "stdout", source: "backend", line });
  }
  for (const line of splitLines(result.stderr)) {
    args.emitLog({ stream: "stderr", source: "backend", line });
  }

  if (!result.ok || !hasInstalledPlaywrightBrowsers(browsersPath)) {
    throw new Error(
      `Failed to install managed Playwright browsers into '${browsersPath}'. ${result.stderr || result.stdout}`.trim()
    );
  }
}

function hasInstalledPlaywrightBrowsers(browsersPath: string): boolean {
  if (!existsSync(browsersPath)) {
    return false;
  }
  return readdirSync(browsersPath).some((entry) => /^chromium-|^chromium_headless_shell-/.test(entry));
}
