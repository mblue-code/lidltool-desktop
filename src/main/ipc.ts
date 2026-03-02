import { ipcMain } from "electron";
import type { BackupRequest, ExportRequest, ImportRequest, SyncRequest } from "@shared/contracts";
import { DesktopRuntime } from "./runtime";

export function registerIpc(runtime: DesktopRuntime, getBootError: () => string | null): void {
  ipcMain.handle("desktop:get-config", () => runtime.getConfig());
  ipcMain.handle("desktop:boot-error:get", () => getBootError());
  ipcMain.handle("desktop:backend:status", () => runtime.getBackendStatus());
  ipcMain.handle("desktop:backend:start", async () => await runtime.startBackend());
  ipcMain.handle("desktop:backend:stop", async () => await runtime.stopBackend());
  ipcMain.handle("desktop:app:url", async () => {
    await runtime.startBackend();
    return runtime.getFullAppUrl();
  });
  ipcMain.handle("desktop:sync:run", async (_event, payload: SyncRequest) => await runtime.runSyncJob(payload));
  ipcMain.handle("desktop:export:run", async (_event, payload: ExportRequest) => await runtime.runExportJob(payload));
  ipcMain.handle("desktop:backup:run", async (_event, payload: BackupRequest) => await runtime.runBackupJob(payload));
  ipcMain.handle("desktop:import:run", async (_event, payload: ImportRequest) => await runtime.runImportJob(payload));
}
