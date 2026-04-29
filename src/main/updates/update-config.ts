import { createRequire } from "node:module";
import type { DesktopUpdateChannel } from "@shared/contracts";
import { readDesktopEnv, readDesktopFlag } from "../product-identity.ts";

const require = createRequire(import.meta.url);

function getElectronApp(): { isPackaged: boolean; getVersion: () => string } {
  try {
    return require("electron").app;
  } catch {
    return {
      isPackaged: false,
      getVersion: () => "0.0.0"
    };
  }
}

export interface DesktopUpdateConfig {
  enabled: boolean;
  channel: DesktopUpdateChannel;
  currentVersion: string;
  updateBaseUrl: string | null;
  allowDevUpdates: boolean;
  autoCheck: boolean;
  reason: string | null;
}

export interface ResolveDesktopUpdateConfigInput {
  env?: NodeJS.ProcessEnv;
  isPackaged?: boolean;
  version?: string;
}

function normalizeChannel(value: string | null | undefined, isPackaged: boolean): DesktopUpdateChannel {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "beta") {
    return "beta";
  }
  if (normalized === "stable" || normalized === "production") {
    return "stable";
  }
  return isPackaged ? "stable" : "development";
}

function normalizeBaseUrl(value: string | null | undefined, channel: DesktopUpdateChannel): string | null {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) {
    return null;
  }
  const withoutTrailingSlash = trimmed.replace(/\/+$/, "");
  if (channel === "development") {
    return withoutTrailingSlash;
  }
  return withoutTrailingSlash.endsWith(`/${channel}`) ? withoutTrailingSlash : `${withoutTrailingSlash}/${channel}`;
}

export function resolveDesktopUpdateConfig(input: ResolveDesktopUpdateConfigInput = {}): DesktopUpdateConfig {
  const env = input.env ?? process.env;
  const electronApp = getElectronApp();
  const isPackaged = input.isPackaged ?? electronApp.isPackaged;
  const channel = normalizeChannel(
    readDesktopEnv(env, "OUTLAYS_DESKTOP_RELEASE_CHANNEL", "LIDLTOOL_DESKTOP_RELEASE_CHANNEL"),
    isPackaged
  );
  const updateBaseUrl = normalizeBaseUrl(
    readDesktopEnv(env, "OUTLAYS_DESKTOP_UPDATE_BASE_URL", "LIDLTOOL_DESKTOP_UPDATE_BASE_URL"),
    channel
  );
  const allowDevUpdates = readDesktopFlag(
    env,
    "OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES",
    "LIDLTOOL_DESKTOP_ALLOW_DEV_UPDATES"
  );
  const autoCheck = readDesktopFlag(
    env,
    "OUTLAYS_DESKTOP_UPDATE_AUTO_CHECK",
    "LIDLTOOL_DESKTOP_UPDATE_AUTO_CHECK"
  );
  const currentVersion = input.version ?? electronApp.getVersion();

  if (!updateBaseUrl) {
    return {
      enabled: false,
      channel,
      currentVersion,
      updateBaseUrl,
      allowDevUpdates,
      autoCheck,
      reason: "missing_update_base_url"
    };
  }

  if (!isPackaged && !allowDevUpdates) {
    return {
      enabled: false,
      channel,
      currentVersion,
      updateBaseUrl,
      allowDevUpdates,
      autoCheck,
      reason: "dev_updates_disabled"
    };
  }

  return {
    enabled: true,
    channel,
    currentVersion,
    updateBaseUrl,
    allowDevUpdates,
    autoCheck,
    reason: null
  };
}
