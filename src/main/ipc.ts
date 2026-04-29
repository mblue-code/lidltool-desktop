import { ipcMain } from "electron";
import type {
  BackupRequest,
  DesktopDiagnosticsBundleResult,
  DesktopDiagnosticsSummary,
  DesktopExternalBrowserId,
  DesktopExternalBrowserPreferenceState,
  DesktopPrivacyPreferences,
  DesktopUpdateState,
  DesktopLocale,
  DesktopTelemetryPublicConfig,
  DesktopConnectorCallbackEvent,
  ExportRequest,
  ImportRequest,
  StartMobileBridgeRequest,
  ReceiptPluginCatalogInstallRequest,
  SyncRequest
} from "@shared/contracts";
import { DESKTOP_CAPABILITIES } from "@shared/desktop-route-policy";
import { DesktopRuntime } from "./runtime";

export function registerIpc(
  runtime: DesktopRuntime,
  getBootError: () => string | null,
  getLocale: () => DesktopLocale,
  setLocale: (locale: DesktopLocale) => DesktopLocale,
  openControlCenter: () => Promise<void>,
  getDiagnosticsSummary: () => DesktopDiagnosticsSummary,
  getTelemetryConfig: () => DesktopTelemetryPublicConfig,
  exportDiagnosticsBundle: () => Promise<DesktopDiagnosticsBundleResult | null>,
  openLogsFolder: () => Promise<string>,
  openBugReport: () => Promise<string>,
  getPrivacyPreferences: () => DesktopPrivacyPreferences,
  setPrivacyPreferences: (preferences: Partial<DesktopPrivacyPreferences>) => DesktopPrivacyPreferences,
  getUpdateState: () => DesktopUpdateState,
  checkForUpdates: () => Promise<DesktopUpdateState>,
  downloadUpdate: () => Promise<DesktopUpdateState>,
  installUpdate: () => void,
  consumePendingConnectorCallbacks: () => DesktopConnectorCallbackEvent[],
  getExternalBrowserPreference: () => DesktopExternalBrowserPreferenceState,
  setExternalBrowserPreference: (preferredBrowser: DesktopExternalBrowserId) => DesktopExternalBrowserPreferenceState,
  openExternalUrl: (url: string) => Promise<void>
): void {
  ipcMain.handle("desktop:get-config", () => runtime.getConfig());
  ipcMain.handle("desktop:capabilities:get", () => DESKTOP_CAPABILITIES);
  ipcMain.handle("desktop:locale:get", () => getLocale());
  ipcMain.handle("desktop:boot-error:get", () => getBootError());
  ipcMain.handle("desktop:backend:status", () => runtime.getBackendStatus());
  ipcMain.handle("desktop:mobile-bridge:status", () => runtime.getMobileBridgeStatus());
  ipcMain.handle("desktop:runtime:diagnostics", () => runtime.getRuntimeDiagnostics());
  ipcMain.handle("desktop:release-metadata:get", async () => await runtime.getReleaseMetadata());
  ipcMain.handle("desktop:diagnostics:summary", () => getDiagnosticsSummary());
  ipcMain.handle("desktop:telemetry:config", () => getTelemetryConfig());
  ipcMain.handle("desktop:diagnostics:export-bundle", async () => await exportDiagnosticsBundle());
  ipcMain.handle("desktop:diagnostics:open-logs-folder", async () => await openLogsFolder());
  ipcMain.handle("desktop:diagnostics:open-bug-report", async () => await openBugReport());
  ipcMain.handle("desktop:privacy:get", () => getPrivacyPreferences());
  ipcMain.handle("desktop:privacy:set", (_event, preferences: Partial<DesktopPrivacyPreferences>) =>
    setPrivacyPreferences(preferences)
  );
  ipcMain.handle("desktop:updates:state", () => getUpdateState());
  ipcMain.handle("desktop:updates:check", async () => await checkForUpdates());
  ipcMain.handle("desktop:updates:download", async () => await downloadUpdate());
  ipcMain.handle("desktop:updates:install", () => installUpdate());
  ipcMain.handle("desktop:locale:set", (_event, locale: DesktopLocale) => setLocale(locale));
  ipcMain.handle("desktop:backend:start", async () => await runtime.startBackend());
  ipcMain.handle("desktop:backend:stop", async () => await runtime.stopBackend());
  ipcMain.handle("desktop:mobile-bridge:start", async (_event, payload: StartMobileBridgeRequest) =>
    await runtime.startMobileBridge(payload)
  );
  ipcMain.handle("desktop:mobile-bridge:stop", async () => await runtime.stopMobileBridge());
  ipcMain.handle("desktop:ocr:wake", async () => await runtime.wakeOcrWorker());
  ipcMain.handle("desktop:app:url", async () => {
    await runtime.startBackend();
    return runtime.getFullAppUrl();
  });
  ipcMain.handle("desktop:control-center:open", async () => {
    await openControlCenter();
  });
  ipcMain.handle("desktop:external-browser:get-preference", () => getExternalBrowserPreference());
  ipcMain.handle("desktop:external-browser:set-preference", (_event, preferredBrowser: DesktopExternalBrowserId) =>
    setExternalBrowserPreference(preferredBrowser)
  );
  ipcMain.handle("desktop:external-url:open", async (_event, url: string) => {
    await openExternalUrl(url);
  });
  ipcMain.handle("desktop:sync:run", async (_event, payload: SyncRequest) => await runtime.runSyncJob(payload));
  ipcMain.handle("desktop:export:run", async (_event, payload: ExportRequest) => await runtime.runExportJob(payload));
  ipcMain.handle("desktop:backup:run", async (_event, payload: BackupRequest) => await runtime.runBackupJob(payload));
  ipcMain.handle("desktop:import:run", async (_event, payload: ImportRequest) => await runtime.runImportJob(payload));
  ipcMain.handle("desktop:receipt-plugins:list", async () => await runtime.listReceiptPluginPacks());
  ipcMain.handle("desktop:receipt-plugins:install-dialog", async () => await runtime.installReceiptPluginPackFromDialog());
  ipcMain.handle("desktop:receipt-plugins:install-catalog-entry", async (_event, payload: ReceiptPluginCatalogInstallRequest) =>
    await runtime.installReceiptPluginPackFromCatalogEntry(payload)
  );
  ipcMain.handle("desktop:receipt-plugins:enable", async (_event, pluginId: string) =>
    await runtime.setReceiptPluginPackEnabled(pluginId, true)
  );
  ipcMain.handle("desktop:receipt-plugins:disable", async (_event, pluginId: string) =>
    await runtime.setReceiptPluginPackEnabled(pluginId, false)
  );
  ipcMain.handle("desktop:receipt-plugins:uninstall", async (_event, pluginId: string) =>
    await runtime.uninstallReceiptPluginPack(pluginId)
  );
  ipcMain.handle("desktop:connector-callbacks:consume", () => consumePendingConnectorCallbacks());
}
