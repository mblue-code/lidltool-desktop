/// <reference types="vite/client" />

import type {
  BackendConfig,
  BackendStatus,
  BackupRequest,
  CommandLogEvent,
  CommandResult,
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

declare global {
  interface Window {
    desktopApi: {
      getConfig: () => Promise<BackendConfig>;
      getLocale: () => Promise<DesktopLocale>;
      getBootError: () => Promise<string | null>;
      getBackendStatus: () => Promise<BackendStatus>;
      getRuntimeDiagnostics: () => Promise<DesktopRuntimeDiagnostics>;
      getReleaseMetadata: () => Promise<DesktopReleaseMetadata>;
      setLocale: (locale: DesktopLocale) => Promise<DesktopLocale>;
      startBackend: () => Promise<BackendStatus>;
      stopBackend: () => Promise<BackendStatus>;
      openFullApp: () => Promise<string>;
      runSync: (payload: SyncRequest) => Promise<CommandResult>;
      runExport: (payload: ExportRequest) => Promise<CommandResult>;
      runBackup: (payload: BackupRequest) => Promise<CommandResult>;
      runImport: (payload: ImportRequest) => Promise<CommandResult>;
      listReceiptPlugins: () => Promise<ReceiptPluginPackListResult>;
      installReceiptPluginFromDialog: () => Promise<ReceiptPluginPackInstallResult | null>;
      installReceiptPluginFromCatalogEntry: (
        payload: ReceiptPluginCatalogInstallRequest
      ) => Promise<ReceiptPluginPackInstallResult>;
      enableReceiptPlugin: (pluginId: string) => Promise<ReceiptPluginPackToggleResult>;
      disableReceiptPlugin: (pluginId: string) => Promise<ReceiptPluginPackToggleResult>;
      uninstallReceiptPlugin: (pluginId: string) => Promise<ReceiptPluginPackUninstallResult>;
      onLog: (handler: (event: CommandLogEvent) => void) => () => void;
      onBootError: (handler: (message: string) => void) => () => void;
      onLocaleChanged: (handler: (locale: DesktopLocale) => void) => () => void;
    };
  }
}

export {};
