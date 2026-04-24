import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const sourceMessagesPath =
  process.env.LIDLTOOL_CANONICAL_MESSAGES_PATH ??
  resolve(desktopDir, "vendor", "frontend", "src", "i18n", "messages.ts");
const generatedOutputPath = resolve(desktopDir, "src", "i18n", "generated.ts");

const SHARED_KEYS = [
  "app.brand.title",
  "app.brand.subtitle",
  "app.header.language",
  "app.language.english",
  "app.language.german",
  "common.loading",
  "common.open",
  "common.status",
  "common.source",
  "common.retry"
];

const DESKTOP_ONLY_MESSAGES = {
  en: {
    "shell.windowTitle": "LidlTool Desktop",
    "shell.header.title": "Desktop Control Center",
    "shell.header.subtitle":
      "Fallback controls for backend boot, one-time sync runs, exports, and local backup tasks.",
    "shell.backend.title": "Backend",
    "shell.backend.api": "API",
    "shell.backend.db": "DB",
    "shell.backend.status.loading": "loading",
    "shell.backend.status.running": "running (pid {pid})",
    "shell.backend.status.stopped": "stopped",
    "shell.backend.action.openFullApp": "Open full app",
    "shell.backend.action.start": "Start backend",
    "shell.backend.action.stop": "Stop backend",
    "shell.sync.title": "One-Time Scrape",
    "shell.sync.description": "Run a guided sync directly from the desktop fallback shell.",
    "shell.sync.fullHistory": "Full historical sync",
    "shell.sync.headless": "Headless browser",
    "shell.sync.domain": "Domain",
    "shell.sync.years": "Years",
    "shell.sync.maxPages": "Max pages",
    "shell.sync.action.run": "Run one-time scrape",
    "shell.backup.title": "Backup Bundle",
    "shell.backup.description":
      "Create a local backup directory with the database, credentials, and optional exports/documents.",
    "shell.backup.outputDir": "Backup directory",
    "shell.backup.includeExport": "Include JSON receipts export",
    "shell.backup.includeDocuments": "Include document storage",
    "shell.backup.action.run": "Create backup",
    "shell.export.title": "Data Export",
    "shell.export.description": "Export normalized receipts to a single local JSON file.",
    "shell.export.outputPath": "Output path",
    "shell.export.action.run": "Export data",
    "shell.restore.title": "Restore Backup",
    "shell.restore.description": "Restore DB and auth artifacts from an existing backup directory.",
    "shell.restore.backupDir": "Backup directory",
    "shell.restore.includeCredentialKey": "Restore credential key",
    "shell.restore.includeToken": "Restore token file",
    "shell.restore.includeDocuments": "Restore document storage",
    "shell.restore.restartBackend": "Restart backend after restore",
    "shell.restore.action.run": "Restore backup",
    "shell.analytics.title": "Analytics Hook",
    "shell.analytics.description":
      "Fetch `/api/v1/dashboard/cards` from the local backend for quick post-sync checks.",
    "shell.analytics.action.load": "Load dashboard cards",
    "shell.analytics.empty": "No analytics loaded yet.",
    "shell.results.title": "Command Results",
    "shell.results.sync": "One-time scrape",
    "shell.results.backup": "Backup",
    "shell.results.export": "Data export",
    "shell.results.restore": "Restore",
    "shell.results.empty.sync": "No scrape executed yet.",
    "shell.results.empty.backup": "No backup executed yet.",
    "shell.results.empty.export": "No export executed yet.",
    "shell.results.empty.restore": "No restore executed yet.",
    "shell.logs.title": "Runtime Logs",
    "shell.logs.empty": "No logs yet.",
    "shell.bootError": "Automatic full-app boot failed: {detail}",
    "shell.error.desktopApiInit": "Failed to initialize desktop API: {detail}",
    "shell.error.configUnavailable": "Desktop config is not ready yet.",
    "shell.error.backendStart": "Backend start failed: {detail}",
    "shell.error.backendStop": "Backend stop failed: {detail}",
    "shell.error.sync": "Sync failed: {detail}",
    "shell.error.cards": "Cards query failed: {detail}. Start backend first.",
    "shell.error.openFullApp": "Could not open full app: {detail}",
    "shell.error.exportRequired": "Export output path is required.",
    "shell.error.export": "Export failed: {detail}",
    "shell.error.backupRequired": "Backup output directory is required.",
    "shell.error.backup": "Backup failed: {detail}",
    "shell.error.importRequired": "Backup directory is required.",
    "shell.error.import": "Backup import failed: {detail}",
    "shell.menu.application": "Application",
    "shell.menu.edit": "Edit",
    "shell.menu.openFullApp": "Open full app",
    "shell.menu.reloadControlCenter": "Reload control center",
    "shell.menu.startBackend": "Start backend",
    "shell.menu.stopBackend": "Stop backend",
    "shell.menu.undo": "Undo",
    "shell.menu.redo": "Redo",
    "shell.menu.cut": "Cut",
    "shell.menu.copy": "Copy",
    "shell.menu.paste": "Paste",
    "shell.menu.selectAll": "Select All",
    "shell.menu.quit": "Quit",
    "shell.menu.window": "Window",
    "shell.menu.minimize": "Minimize"
  },
  de: {
    "shell.windowTitle": "LidlTool Desktop",
    "shell.header.title": "Desktop-Kontrollzentrum",
    "shell.header.subtitle":
      "Fallback-Steuerung für Backend-Start, einmalige Sync-Läufe, Exporte und lokale Backup-Aufgaben.",
    "shell.backend.title": "Backend",
    "shell.backend.api": "API",
    "shell.backend.db": "DB",
    "shell.backend.status.loading": "lädt",
    "shell.backend.status.running": "aktiv (PID {pid})",
    "shell.backend.status.stopped": "gestoppt",
    "shell.backend.action.openFullApp": "Vollansicht öffnen",
    "shell.backend.action.start": "Backend starten",
    "shell.backend.action.stop": "Backend stoppen",
    "shell.sync.title": "Einmaliger Abruf",
    "shell.sync.description": "Einen geführten Sync direkt aus der Desktop-Fallback-Oberfläche starten.",
    "shell.sync.fullHistory": "Vollständige Historie synchronisieren",
    "shell.sync.headless": "Headless-Browser",
    "shell.sync.domain": "Domain",
    "shell.sync.years": "Jahre",
    "shell.sync.maxPages": "Maximale Seiten",
    "shell.sync.action.run": "Einmaligen Abruf starten",
    "shell.backup.title": "Backup-Paket",
    "shell.backup.description":
      "Ein lokales Backup-Verzeichnis mit Datenbank, Zugangsdaten und optionalen Exporten/Dokumenten erstellen.",
    "shell.backup.outputDir": "Backup-Verzeichnis",
    "shell.backup.includeExport": "JSON-Belegexport einschließen",
    "shell.backup.includeDocuments": "Dokumentspeicher einschließen",
    "shell.backup.action.run": "Backup erstellen",
    "shell.export.title": "Datenexport",
    "shell.export.description": "Normalisierte Belege in eine lokale JSON-Datei exportieren.",
    "shell.export.outputPath": "Ausgabepfad",
    "shell.export.action.run": "Daten exportieren",
    "shell.restore.title": "Backup wiederherstellen",
    "shell.restore.description": "Datenbank und Zugangsdaten aus einem vorhandenen Backup-Verzeichnis wiederherstellen.",
    "shell.restore.backupDir": "Backup-Verzeichnis",
    "shell.restore.includeCredentialKey": "Zugangsdaten-Schlüssel wiederherstellen",
    "shell.restore.includeToken": "Token-Datei wiederherstellen",
    "shell.restore.includeDocuments": "Dokumentspeicher wiederherstellen",
    "shell.restore.restartBackend": "Backend nach Wiederherstellung neu starten",
    "shell.restore.action.run": "Backup wiederherstellen",
    "shell.analytics.title": "Analytics-Schnellcheck",
    "shell.analytics.description":
      "`/api/v1/dashboard/cards` vom lokalen Backend für schnelle Nachkontrollen nach dem Sync abrufen.",
    "shell.analytics.action.load": "Dashboard-Karten laden",
    "shell.analytics.empty": "Noch keine Daten geladen.",
    "shell.results.title": "Befehlsergebnisse",
    "shell.results.sync": "Einmaliger Abruf",
    "shell.results.backup": "Backup",
    "shell.results.export": "Datenexport",
    "shell.results.restore": "Wiederherstellung",
    "shell.results.empty.sync": "Noch kein Abruf ausgeführt.",
    "shell.results.empty.backup": "Noch kein Backup ausgeführt.",
    "shell.results.empty.export": "Noch kein Export ausgeführt.",
    "shell.results.empty.restore": "Noch keine Wiederherstellung ausgeführt.",
    "shell.logs.title": "Laufzeitprotokolle",
    "shell.logs.empty": "Noch keine Protokolle.",
    "shell.bootError": "Automatischer Start der Vollansicht fehlgeschlagen: {detail}",
    "shell.error.desktopApiInit": "Desktop-API konnte nicht initialisiert werden: {detail}",
    "shell.error.configUnavailable": "Die Desktop-Konfiguration ist noch nicht bereit.",
    "shell.error.backendStart": "Backend-Start fehlgeschlagen: {detail}",
    "shell.error.backendStop": "Backend-Stopp fehlgeschlagen: {detail}",
    "shell.error.sync": "Sync fehlgeschlagen: {detail}",
    "shell.error.cards": "Dashboard-Karten konnten nicht geladen werden: {detail}. Starten Sie zuerst das Backend.",
    "shell.error.openFullApp": "Die Vollansicht konnte nicht geöffnet werden: {detail}",
    "shell.error.exportRequired": "Ein Ausgabepfad für den Export ist erforderlich.",
    "shell.error.export": "Export fehlgeschlagen: {detail}",
    "shell.error.backupRequired": "Ein Ausgabeverzeichnis für das Backup ist erforderlich.",
    "shell.error.backup": "Backup fehlgeschlagen: {detail}",
    "shell.error.importRequired": "Ein Backup-Verzeichnis ist erforderlich.",
    "shell.error.import": "Backup-Wiederherstellung fehlgeschlagen: {detail}",
    "shell.menu.application": "Anwendung",
    "shell.menu.edit": "Bearbeiten",
    "shell.menu.openFullApp": "Vollansicht öffnen",
    "shell.menu.reloadControlCenter": "Kontrollzentrum neu laden",
    "shell.menu.startBackend": "Backend starten",
    "shell.menu.stopBackend": "Backend stoppen",
    "shell.menu.undo": "Rückgängig",
    "shell.menu.redo": "Wiederholen",
    "shell.menu.cut": "Ausschneiden",
    "shell.menu.copy": "Kopieren",
    "shell.menu.paste": "Einfügen",
    "shell.menu.selectAll": "Alles auswählen",
    "shell.menu.quit": "Beenden",
    "shell.menu.window": "Fenster",
    "shell.menu.minimize": "Minimieren"
  }
};

async function loadCanonicalMessages() {
  const source = readFileSync(sourceMessagesPath, "utf-8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2020,
      target: ts.ScriptTarget.ES2020
    }
  }).outputText;
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(transpiled, "utf-8").toString("base64")}`;
  return await import(moduleUrl);
}

function pickMessages(messages, keys) {
  const picked = {};
  for (const key of keys) {
    if (!(key in messages)) {
      throw new Error(`Missing canonical shell key '${key}' in ${sourceMessagesPath}`);
    }
    picked[key] = messages[key];
  }
  return picked;
}

const { EN_MESSAGES, DE_MESSAGES } = await loadCanonicalMessages();

const desktopMessages = {
  en: {
    ...pickMessages(EN_MESSAGES, SHARED_KEYS),
    ...DESKTOP_ONLY_MESSAGES.en
  },
  de: {
    ...pickMessages(DE_MESSAGES, SHARED_KEYS),
    ...DESKTOP_ONLY_MESSAGES.de
  }
};

const output = `/* eslint-disable */
// Generated by scripts/sync-shell-i18n.mjs from the canonical frontend message source.
// Do not edit this file manually.

export const SUPPORTED_DESKTOP_LOCALES = ["en", "de"] as const;
export type DesktopLocale = (typeof SUPPORTED_DESKTOP_LOCALES)[number];
export const DEFAULT_DESKTOP_LOCALE: DesktopLocale = "en";

export const INTL_LOCALE_BY_DESKTOP_LOCALE: Record<DesktopLocale, string> = {
  en: "en-US",
  de: "de-DE"
};

export const DESKTOP_MESSAGES = ${JSON.stringify(desktopMessages, null, 2)} as const;

export type DesktopMessageKey = keyof typeof DESKTOP_MESSAGES.en;
`;

mkdirSync(resolve(desktopDir, "src", "i18n"), { recursive: true });
writeFileSync(generatedOutputPath, output, "utf-8");

console.log(`Generated desktop shell i18n artifact -> ${generatedOutputPath}`);
