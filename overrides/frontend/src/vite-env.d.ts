/// <reference types="vite/client" />

import type { DesktopApiBridge, DesktopReceiptPluginPackListResult, DesktopReleaseMetadata } from "@/lib/desktop-api";

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
    };
  }
}
