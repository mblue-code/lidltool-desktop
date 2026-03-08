/// <reference types="vite/client" />

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

declare global {
  interface Window {
    desktopApi: {
      getConfig: () => Promise<BackendConfig>;
      getLocale: () => Promise<DesktopLocale>;
      getBootError: () => Promise<string | null>;
      getBackendStatus: () => Promise<BackendStatus>;
      setLocale: (locale: DesktopLocale) => Promise<DesktopLocale>;
      startBackend: () => Promise<BackendStatus>;
      stopBackend: () => Promise<BackendStatus>;
      openFullApp: () => Promise<string>;
      runSync: (payload: SyncRequest) => Promise<CommandResult>;
      runExport: (payload: ExportRequest) => Promise<CommandResult>;
      runBackup: (payload: BackupRequest) => Promise<CommandResult>;
      runImport: (payload: ImportRequest) => Promise<CommandResult>;
      onLog: (handler: (event: CommandLogEvent) => void) => () => void;
      onBootError: (handler: (message: string) => void) => () => void;
      onLocaleChanged: (handler: (locale: DesktopLocale) => void) => () => void;
    };
  }
}

export {};
