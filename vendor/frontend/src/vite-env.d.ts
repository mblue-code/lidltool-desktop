/// <reference types="vite/client" />

import type {
  DesktopApiBridge,
  DesktopConnectorCallbackEvent,
  DesktopExternalBrowserId,
  DesktopExternalBrowserPreferenceState,
  DesktopLocale,
  DesktopReceiptPluginPackInstallResult,
  DesktopReceiptPluginPackListResult,
  DesktopReceiptPluginPackToggleResult,
  DesktopReceiptPluginPackUninstallResult,
  DesktopReleaseMetadata
} from "@/lib/desktop-api";

interface ImportMetaEnv {
  readonly VITE_DASHBOARD_API_BASE?: string;
  readonly VITE_DASHBOARD_DB?: string;
  readonly CI?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare global {
  interface Window {
    desktopApi?: DesktopApiBridge & {
      getLocale?: () => Promise<DesktopLocale>;
      setLocale?: (locale: DesktopLocale) => Promise<DesktopLocale>;
      onLocaleChanged?: (handler: (locale: DesktopLocale) => void) => (() => void);
      getCapabilities?: () => Promise<import("@/lib/desktop-api").DesktopCapabilities>;
      getReleaseMetadata?: () => Promise<DesktopReleaseMetadata>;
      wakeOcrWorker?: () => Promise<{ running: boolean; started: boolean; idleTimeoutSeconds: number }>;
      listReceiptPlugins?: () => Promise<DesktopReceiptPluginPackListResult>;
      installReceiptPluginFromDialog?: () => Promise<DesktopReceiptPluginPackInstallResult | null>;
      installReceiptPluginFromCatalogEntry?: (payload: { entryId: string }) => Promise<DesktopReceiptPluginPackInstallResult>;
      enableReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
      disableReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
      uninstallReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackUninstallResult>;
      getExternalBrowserPreference?: () => Promise<DesktopExternalBrowserPreferenceState>;
      setExternalBrowserPreference?: (
        preferredBrowser: DesktopExternalBrowserId
      ) => Promise<DesktopExternalBrowserPreferenceState>;
      openExternalUrl?: (url: string) => Promise<void>;
      consumePendingConnectorCallbacks?: () => Promise<DesktopConnectorCallbackEvent[]>;
      onConnectorCallback?: (handler: (event: DesktopConnectorCallbackEvent) => void) => (() => void);
    };
  }
}
