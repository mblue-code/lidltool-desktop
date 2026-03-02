import { contextBridge, ipcRenderer } from "electron";
import type { BackendConfig, BackendStatus, CommandLogEvent, CommandResult, SyncRequest } from "@shared/contracts";

const api = {
  getConfig: async (): Promise<BackendConfig> => await ipcRenderer.invoke("desktop:get-config"),
  getBootError: async (): Promise<string | null> => await ipcRenderer.invoke("desktop:boot-error:get"),
  getBackendStatus: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:status"),
  startBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:start"),
  stopBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:stop"),
  openFullApp: async (): Promise<string> => await ipcRenderer.invoke("desktop:app:url"),
  runSync: async (payload: SyncRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:sync:run", payload),
  onLog: (handler: (event: CommandLogEvent) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, payload: CommandLogEvent): void => {
      handler(payload);
    };
    ipcRenderer.on("desktop:log", listener);
    return () => {
      ipcRenderer.removeListener("desktop:log", listener);
    };
  },
  onBootError: (handler: (message: string) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, message: string): void => {
      handler(message);
    };
    ipcRenderer.on("desktop:boot-error", listener);
    return () => {
      ipcRenderer.removeListener("desktop:boot-error", listener);
    };
  }
};

contextBridge.exposeInMainWorld("desktopApi", api);
