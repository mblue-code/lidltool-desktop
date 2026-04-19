import { ipcMain } from "electron";
import type {
  BackupRequest,
  DesktopLocale,
  ExportRequest,
  ImportRequest,
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
  openControlCenter: () => Promise<void>
): void {
  ipcMain.handle("desktop:get-config", () => runtime.getConfig());
  ipcMain.handle("desktop:capabilities:get", () => DESKTOP_CAPABILITIES);
  ipcMain.handle("desktop:locale:get", () => getLocale());
  ipcMain.handle("desktop:boot-error:get", () => getBootError());
  ipcMain.handle("desktop:backend:status", () => runtime.getBackendStatus());
  ipcMain.handle("desktop:runtime:diagnostics", () => runtime.getRuntimeDiagnostics());
  ipcMain.handle("desktop:release-metadata:get", async () => await runtime.getReleaseMetadata());
  ipcMain.handle("desktop:locale:set", (_event, locale: DesktopLocale) => setLocale(locale));
  ipcMain.handle("desktop:backend:start", async () => await runtime.startBackend());
  ipcMain.handle("desktop:backend:stop", async () => await runtime.stopBackend());
  ipcMain.handle("desktop:ocr:wake", async () => await runtime.wakeOcrWorker());
  ipcMain.handle("desktop:app:url", async () => {
    await runtime.startBackend();
    return runtime.getFullAppUrl();
  });
  ipcMain.handle("desktop:control-center:open", async () => {
    await openControlCenter();
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
}
