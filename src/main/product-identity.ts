import type { DesktopUpdateChannel } from "@shared/contracts";

export const PRODUCT_NAME = "Outlays";
export const PRODUCT_SUBTITLE_EN = "Your Personal Spending Ledger";
export const PRODUCT_SUBTITLE_DE = "Dein Haushaltsbuch";
export const PRODUCT_DISPLAY_EN = `${PRODUCT_NAME} - ${PRODUCT_SUBTITLE_EN}`;
export const PRODUCT_DISPLAY_DE = `${PRODUCT_NAME} - ${PRODUCT_SUBTITLE_DE}`;
export const PACKAGE_SLUG = "outlays-desktop";
export const APP_ID = "com.gluecherlab.outlays.desktop";
export const DEFAULT_DB_FILENAME = "outlays.sqlite";
export const LEGACY_DB_FILENAME = "lidltool.sqlite";
export const DIAGNOSTICS_PREFIX = "outlays-diagnostics";

export function readDesktopEnv(
  env: NodeJS.ProcessEnv,
  preferredName: string,
  legacyName?: string
): string | undefined {
  const preferred = env[preferredName]?.trim();
  if (preferred) {
    return preferred;
  }
  if (!legacyName) {
    return undefined;
  }
  const legacy = env[legacyName]?.trim();
  return legacy || undefined;
}

export function readDesktopFlag(
  env: NodeJS.ProcessEnv,
  preferredName: string,
  legacyName?: string
): boolean {
  return readDesktopEnv(env, preferredName, legacyName) === "1";
}

export function updateFeedBaseUrl(channel: DesktopUpdateChannel): string {
  return `https://updates.invalid/${PACKAGE_SLUG}/${channel}`;
}
