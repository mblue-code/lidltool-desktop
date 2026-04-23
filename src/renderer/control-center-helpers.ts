import type { SyncSourceId } from "@shared/contracts";

export function defaultYearMonth(): { year: number; month: number } {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export function prettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function defaultExportPath(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  const stamp = new Date().toISOString().replaceAll(":", "-");
  return `${trimmed}${separator}exports${separator}receipts-${stamp}.json`;
}

export function defaultBackupDir(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  const stamp = new Date().toISOString().replaceAll(":", "-");
  return `${trimmed}${separator}backups${separator}backup-${stamp}`;
}

export function defaultImportDir(userDataDir: string): string {
  const separator = userDataDir.includes("\\") ? "\\" : "/";
  const trimmed = userDataDir.endsWith(separator) ? userDataDir.slice(0, -1) : userDataDir;
  return `${trimmed}${separator}backups`;
}

export function sourceJourneySummary(source: SyncSourceId, locale: "en" | "de"): string {
  if (source.startsWith("lidl_plus_")) {
    return locale === "de"
      ? "Verwenden Sie den integrierten Lidl-Pfad, wenn Sie nur eine einmalige lokale Aktualisierung des aktuellen oder vollständigen Belegverlaufs möchten."
      : "Use the built-in Lidl path when you just want a one-off local refresh of recent or full receipt history.";
  }
  if (source.startsWith("amazon_")) {
    return locale === "de"
      ? "Die Amazon-Synchronisierung verwendet die gespeicherte Desktop-Sitzung für den gewählten Markt und kann mehrere Jahre durchsuchen, wenn Sie einen breiteren lokalen Import benötigen."
      : "Amazon sync uses the saved desktop session for the selected market and can scan multiple years when you need a broader local import.";
  }
  return locale === "de"
    ? "Verwenden Sie ein Belegpaket, wenn Sie eine gelegentliche lokale Synchronisierung für einen anderen Händler möchten, und prüfen oder exportieren Sie die Ergebnisse anschließend auf diesem Computer."
    : "Use a receipt pack when you want an occasional local sync for another retailer, then review or export the results on this computer.";
}

export function sourceSyncNotice(source: SyncSourceId, locale: string): string | null {
  if (source !== "dm_de") {
    return null;
  }
  if (locale === "de") {
    return "dm-Syncs können sichtbar länger dauern. Die Desktop-App hält dabei absichtliche Wartephasen ein, damit Login, Session und Detailseiten stabil bleiben.";
  }
  return "dm sync can take noticeably longer. The desktop app keeps intentional wait phases so login, session refresh, and receipt detail pages stay stable.";
}
