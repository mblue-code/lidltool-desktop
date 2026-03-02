import { ipcMain } from "electron";
import type { SyncRequest } from "@shared/contracts";
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
}
