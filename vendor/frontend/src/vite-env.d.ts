/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DASHBOARD_API_BASE?: string;
  readonly VITE_DASHBOARD_DB?: string;
  readonly CI?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
