import { app, dialog, shell } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, join } from "node:path";
import JSZip from "jszip";
import type {
  DesktopDiagnosticsBundleResult,
  DesktopDiagnosticsSummary,
  DesktopRuntimeDiagnostics
} from "@shared/contracts";
import { redactSensitiveText, sanitizeDiagnosticValue } from "./sanitization";
import { getDesktopTelemetryConfig } from "./sentry-main";
import { DIAGNOSTICS_PREFIX, readDesktopEnv } from "../product-identity.ts";

export interface DiagnosticsBundleContext {
  runtimeDiagnostics: () => DesktopRuntimeDiagnostics;
  bootError: () => string | null;
  surface: () => string;
}

function timestampForFile(): string {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function diagnosticsDir(): string {
  const dir = join(app.getPath("userData"), "diagnostics");
  mkdirSync(dir, { recursive: true });
  return dir;
}

function issueBaseUrl(): string {
  return (
    readDesktopEnv(process.env, "OUTLAYS_DESKTOP_ISSUES_URL", "LIDLTOOL_DESKTOP_ISSUES_URL") ||
    "https://github.com/mblue-code/outlays-desktop/issues/new"
  );
}

export function buildDesktopDiagnosticsSummary(context: DiagnosticsBundleContext): DesktopDiagnosticsSummary {
  const telemetry = getDesktopTelemetryConfig();
  return {
    appVersion: app.getVersion(),
    packaged: app.isPackaged,
    platform: process.platform,
    arch: process.arch,
    electronVersion: process.versions.electron ?? null,
    chromeVersion: process.versions.chrome ?? null,
    nodeVersion: process.versions.node,
    releaseChannel: telemetry.environment,
    telemetryMode: telemetry.mode,
    telemetryEnabled: telemetry.enabled,
    surface: context.surface(),
    bootError: context.bootError(),
    userDataDir: "<userData>",
    runtime: sanitizeDiagnosticValue(context.runtimeDiagnostics(), homedir()) as DesktopRuntimeDiagnostics
  };
}

function addRedactedFile(zip: JSZip, archiveName: string, path: string): string | null {
  if (!existsSync(path)) {
    return null;
  }
  const redacted = redactSensitiveText(readFileSync(path, "utf-8"), homedir());
  zip.file(archiveName, redacted);
  return archiveName;
}

export async function exportDesktopDiagnosticsBundle(
  context: DiagnosticsBundleContext,
  explicitPath?: string | null
): Promise<DesktopDiagnosticsBundleResult> {
  const summary = buildDesktopDiagnosticsSummary(context);
  const zip = new JSZip();
  const includedFiles: string[] = [];
  zip.file("diagnostics.json", JSON.stringify(summary, null, 2));
  includedFiles.push("diagnostics.json");

  const userDataDir = app.getPath("userData");
  const windowLog = addRedactedFile(zip, "logs/window-lifecycle.log", join(userDataDir, "window-lifecycle.log"));
  if (windowLog) {
    includedFiles.push(windowLog);
  }

  const defaultPath = join(diagnosticsDir(), `${DIAGNOSTICS_PREFIX}-${timestampForFile()}.zip`);
  const targetPath = explicitPath ?? defaultPath;
  const buffer = await zip.generateAsync({
    type: "nodebuffer",
    compression: "DEFLATE",
    compressionOptions: { level: 6 }
  });
  writeFileSync(targetPath, buffer);
  return {
    path: targetPath,
    fileName: basename(targetPath),
    includedFiles
  };
}

export async function exportDesktopDiagnosticsBundleWithDialog(
  context: DiagnosticsBundleContext
): Promise<DesktopDiagnosticsBundleResult | null> {
  const result = await dialog.showSaveDialog({
    title: "Create Diagnostics Bundle",
    defaultPath: join(diagnosticsDir(), `${DIAGNOSTICS_PREFIX}-${timestampForFile()}.zip`),
    filters: [{ name: "Zip archive", extensions: ["zip"] }]
  });
  if (result.canceled || !result.filePath) {
    return null;
  }
  return await exportDesktopDiagnosticsBundle(context, result.filePath);
}

export function buildBugReportUrl(context: DiagnosticsBundleContext): string {
  const summary = buildDesktopDiagnosticsSummary(context);
  const url = new URL(issueBaseUrl());
  url.searchParams.set("template", "bug_report.yml");
  url.searchParams.set("labels", "bug,desktop");
  url.searchParams.set("title", `[desktop] ${summary.appVersion} ${summary.platform}/${summary.arch}: `);
  return url.toString();
}

export async function openBugReportUrl(context: DiagnosticsBundleContext): Promise<string> {
  const url = buildBugReportUrl(context);
  await shell.openExternal(url);
  return url;
}
