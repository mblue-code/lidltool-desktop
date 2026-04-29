import { app } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { DesktopPrivacyPreferences } from "@shared/contracts";

const PRIVACY_PREFERENCES_FILE = "privacy-preferences.json";

const DEFAULT_PRIVACY_PREFERENCES: DesktopPrivacyPreferences = {
  errorReportingEnabled: false,
  diagnosticLogSharingEnabled: false
};

function privacyPreferencesPath(): string {
  const userDataDir = app.getPath("userData");
  mkdirSync(userDataDir, { recursive: true });
  return join(userDataDir, PRIVACY_PREFERENCES_FILE);
}

export function loadDesktopPrivacyPreferences(): DesktopPrivacyPreferences {
  const filePath = privacyPreferencesPath();
  if (!existsSync(filePath)) {
    return { ...DEFAULT_PRIVACY_PREFERENCES };
  }
  try {
    const parsed = JSON.parse(readFileSync(filePath, "utf-8")) as Partial<DesktopPrivacyPreferences>;
    return {
      errorReportingEnabled: parsed.errorReportingEnabled === true,
      diagnosticLogSharingEnabled: parsed.diagnosticLogSharingEnabled === true
    };
  } catch {
    return { ...DEFAULT_PRIVACY_PREFERENCES };
  }
}

export function persistDesktopPrivacyPreferences(
  next: Partial<DesktopPrivacyPreferences>
): DesktopPrivacyPreferences {
  const preferences = {
    ...loadDesktopPrivacyPreferences(),
    ...next
  };
  writeFileSync(privacyPreferencesPath(), JSON.stringify(preferences, null, 2), "utf-8");
  return preferences;
}
