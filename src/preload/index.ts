import { contextBridge, ipcRenderer } from "electron";
import type {
  BackendConfig,
  BackendStatus,
  BackupRequest,
  CommandLogEvent,
  CommandResult,
  DesktopCapabilities,
  DesktopReleaseMetadata,
  DesktopRuntimeDiagnostics,
  DesktopLocale,
  ExportRequest,
  ImportRequest,
  ReceiptPluginCatalogInstallRequest,
  ReceiptPluginPackInstallResult,
  ReceiptPluginPackListResult,
  ReceiptPluginPackToggleResult,
  ReceiptPluginPackUninstallResult,
  SyncRequest
} from "@shared/contracts";

const api = {
  getConfig: async (): Promise<BackendConfig> => await ipcRenderer.invoke("desktop:get-config"),
  getCapabilities: async (): Promise<DesktopCapabilities> => await ipcRenderer.invoke("desktop:capabilities:get"),
  getLocale: async (): Promise<DesktopLocale> => await ipcRenderer.invoke("desktop:locale:get"),
  getBootError: async (): Promise<string | null> => await ipcRenderer.invoke("desktop:boot-error:get"),
  getBackendStatus: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:status"),
  getRuntimeDiagnostics: async (): Promise<DesktopRuntimeDiagnostics> =>
    await ipcRenderer.invoke("desktop:runtime:diagnostics"),
  getReleaseMetadata: async (): Promise<DesktopReleaseMetadata> =>
    await ipcRenderer.invoke("desktop:release-metadata:get"),
  setLocale: async (locale: DesktopLocale): Promise<DesktopLocale> => await ipcRenderer.invoke("desktop:locale:set", locale),
  startBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:start"),
  stopBackend: async (): Promise<BackendStatus> => await ipcRenderer.invoke("desktop:backend:stop"),
  openFullApp: async (): Promise<string> => await ipcRenderer.invoke("desktop:app:url"),
  runSync: async (payload: SyncRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:sync:run", payload),
  runExport: async (payload: ExportRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:export:run", payload),
  runBackup: async (payload: BackupRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:backup:run", payload),
  runImport: async (payload: ImportRequest): Promise<CommandResult> => await ipcRenderer.invoke("desktop:import:run", payload),
  listReceiptPlugins: async (): Promise<ReceiptPluginPackListResult> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:list"),
  installReceiptPluginFromDialog: async (): Promise<ReceiptPluginPackInstallResult | null> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:install-dialog"),
  installReceiptPluginFromCatalogEntry: async (
    payload: ReceiptPluginCatalogInstallRequest
  ): Promise<ReceiptPluginPackInstallResult> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:install-catalog-entry", payload),
  enableReceiptPlugin: async (pluginId: string): Promise<ReceiptPluginPackToggleResult> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:enable", pluginId),
  disableReceiptPlugin: async (pluginId: string): Promise<ReceiptPluginPackToggleResult> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:disable", pluginId),
  uninstallReceiptPlugin: async (pluginId: string): Promise<ReceiptPluginPackUninstallResult> =>
    await ipcRenderer.invoke("desktop:receipt-plugins:uninstall", pluginId),
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
