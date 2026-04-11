/// <reference types="vite/client" />

import type {
  DesktopApiBridge,
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
      getCapabilities?: () => Promise<import("@/lib/desktop-api").DesktopCapabilities>;
      getReleaseMetadata?: () => Promise<DesktopReleaseMetadata>;
      listReceiptPlugins?: () => Promise<DesktopReceiptPluginPackListResult>;
      installReceiptPluginFromDialog?: () => Promise<DesktopReceiptPluginPackInstallResult | null>;
      installReceiptPluginFromCatalogEntry?: (payload: { entryId: string }) => Promise<DesktopReceiptPluginPackInstallResult>;
      enableReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
      disableReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
      uninstallReceiptPlugin?: (pluginId: string) => Promise<DesktopReceiptPluginPackUninstallResult>;
    };
  }
}
