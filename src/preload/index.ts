import { contextBridge, ipcRenderer } from "electron";
import type {
  BackendConfig,
  BackendStatus,
  BackupRequest,
  CommandLogEvent,
  CommandResult,
  DesktopLocale,
  ExportRequest,
  ImportRequest,
  SyncRequest
} from "@shared/contracts";

const api = {
  getConfig: async (): Promise<BackendConfig> => await ipcRenderer.invoke("desktop:get-config"),
  getLocale: async (): Promise<DesktopLocale> => await ipcRenderer.invoke("desktop:locale:get"),
  getBootError: async (): Promise<string | null> => await ipcRenderer.invoke("desktop:boot-error:get"),
  getBackendStatus: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:status"),
  setLocale: async (locale: DesktopLocale): Promise<DesktopLocale> => await ipcRenderer.invoke("desktop:locale:set", locale),
  startBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:start"),
  stopBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:stop"),
  openFullApp: async (): Promise<string> => await ipcRenderer.invoke("desktop:app:url"),
  runSync: async (payload: SyncRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:sync:run", payload),
  runExport: async (payload: ExportRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:export:run", payload),
  runBackup: async (payload: BackupRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:backup:run", payload),
  runImport: async (payload: ImportRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:import:run", payload),
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
  },
  onLocaleChanged: (handler: (locale: DesktopLocale) => void): (() => void) => {
    const listener = (_event: Electron.IpcRendererEvent, locale: DesktopLocale): void => {
      handler(locale);
    };
    ipcRenderer.on("desktop:locale-changed", listener);
    return () => {
      ipcRenderer.removeListener("desktop:locale-changed", listener);
    };
  }
};

contextBridge.exposeInMainWorld("desktopApi", api);
