/// <reference types="vite/client" />

import type { BackendConfig, BackendStatus, CommandLogEvent, CommandResult, SyncRequest } from "@shared/contracts";

declare global {
  interface Window {
    desktopApi: {
      getConfig: () => Promise<BackendConfig>;
      getBootError: () => Promise<string | null>;
      getBackendStatus: () => Promise<BackendStatus>;
      startBackend: () => Promise<BackendStatus>;
      stopBackend: () => Promise<BackendStatus>;
      openFullApp: () => Promise<string>;
      runSync: (payload: SyncRequest) => Promise<CommandResult>;
      onLog: (handler: (event: CommandLogEvent) => void) => () => void;
      onBootError: (handler: (message: string) => void) => () => void;
    };
  }
}

export {};
