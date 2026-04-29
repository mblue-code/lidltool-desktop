export type DesktopRouteAvailability = "enabled" | "adapted" | "preview" | "unsupported";
export type DesktopRouteReason =
  | "desktop_override"
  | "desktop_preview"
  | "desktop_out_of_scope"
  | "scheduler_host_required"
  | "operator_surface";

export type DesktopRouteCapability = {
  route: string;
  availability: DesktopRouteAvailability;
  navVisible: boolean;
  redirectTo: string | null;
  reason: DesktopRouteReason | null;
};

export type DesktopCapabilities = {
  routes: DesktopRouteCapability[];
};

export type DesktopLocale = "en" | "de";
export type DesktopExternalBrowserId = "system_default" | "arc" | "atlas" | "google_chrome";
export type DesktopConnectorCallbackEvent = {
  url: string;
  sourceId?: string | null;
  confirmed?: boolean;
  confirmedAt?: string | null;
  detail?: string | null;
};
export type DesktopExternalBrowserOption = {
  id: DesktopExternalBrowserId;
  available: boolean;
};
export type DesktopExternalBrowserPreferenceState = {
  preferredBrowser: DesktopExternalBrowserId;
  options: DesktopExternalBrowserOption[];
};

export type DesktopMobileBridgeStatus = {
  running: boolean;
  endpointUrl: string | null;
  interface: {
    name: string;
    address: string;
    family: "IPv4";
    cidr: string | null;
    mac: string | null;
  } | null;
  startedAt: string | null;
  expiresAt: string | null;
  lastMobileRequestAt: string | null;
  lastMobileRequest: {
    method: string;
    path: string;
    remoteAddress: string;
    statusCode: number | null;
    at: string;
  } | null;
};

export type DesktopConnectorTrustClass =
  | "official"
  | "community_verified"
  | "community_unsigned"
  | "local_custom";

export type DesktopImportResult = {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
};

export type DesktopConnectorCatalogEntry = {
  entry_id: string;
  entry_type: "connector" | "bundle" | "desktop_pack";
  display_name: string;
  summary: string;
  description: string | null;
  trust_class: DesktopConnectorTrustClass;
  current_version: string | null;
  support_policy: {
    display_name: string;
    ui_label: string;
    diagnostics_expectation: string;
    update_expectations: string;
    maintainer_support: string;
  } | null;
  official_bundle_ids: string[];
  market_profile_ids: string[];
  release_variant_ids: string[];
  install_methods: Array<"built_in" | "manual_import" | "manual_mount" | "download_url">;
  plugin_id?: string;
  source_id?: string;
};

export type DesktopReleaseMetadata = {
  active_release_variant: {
    display_name: string;
  };
  selected_market_profile: {
    display_name: string;
  };
  discovery_catalog: {
    entries: DesktopConnectorCatalogEntry[];
  };
};

export type DesktopReceiptPluginPackInfo = {
  pluginId: string;
  sourceId: string;
  displayName: string;
  version: string;
  trustClass: DesktopConnectorTrustClass;
  enabled: boolean;
  status: "enabled" | "disabled" | "invalid" | "incompatible" | "revoked";
  trustStatus: "trusted" | "unsigned" | "signature_invalid" | "revoked" | "incompatible";
  trustReason: string | null;
  compatibilityReason: string | null;
  installedVia: "manual_file" | "catalog_url";
  catalogEntryId: string | null;
  onboarding: {
    title: string | null;
    summary: string | null;
    expectedSpeed: string | null;
    caution: string | null;
    steps: Array<{
      title: string;
      description: string;
    }>;
  } | null;
};

export type DesktopReceiptPluginPackListResult = {
  packs: DesktopReceiptPluginPackInfo[];
  activePluginSearchPaths: string[];
};

export type DesktopReceiptPluginPackInstallResult = {
  action: "installed" | "updated" | "reinstalled";
  pack: DesktopReceiptPluginPackInfo;
  restartedBackend: boolean;
  backendStatus: {
    running: boolean;
  } | null;
};

export type DesktopReceiptPluginPackToggleResult = {
  pack: DesktopReceiptPluginPackInfo;
  restartedBackend: boolean;
  backendStatus: {
    running: boolean;
  } | null;
};

export type DesktopReceiptPluginPackUninstallResult = {
  pluginId: string;
  removedPath: string | null;
  restartedBackend: boolean;
  backendStatus: {
    running: boolean;
  } | null;
};

type DesktopImportBridge = {
  runImport: (payload: {
    backupDir: string;
    includeDocuments?: boolean;
    includeToken?: boolean;
    includeCredentialKey?: boolean;
    restartBackend?: boolean;
  }) => Promise<DesktopImportResult>;
};

type DesktopLocaleBridge = {
  getLocale: () => Promise<DesktopLocale>;
  setLocale: (locale: DesktopLocale) => Promise<DesktopLocale>;
  onLocaleChanged: (handler: (locale: DesktopLocale) => void) => () => void;
};

type DesktopCapabilityBridge = {
  getCapabilities: () => Promise<DesktopCapabilities>;
};

type DesktopOcrBridge = {
  wakeOcrWorker: () => Promise<{ running: boolean; started: boolean; idleTimeoutSeconds: number }>;
};

type DesktopMobileBridge = {
  getMobileBridgeStatus: () => Promise<DesktopMobileBridgeStatus>;
  startMobileBridge: (payload?: { address?: string; expiresInSeconds?: number }) => Promise<DesktopMobileBridgeStatus>;
  stopMobileBridge: () => Promise<DesktopMobileBridgeStatus>;
};

type DesktopConnectorBridge = {
  getReleaseMetadata: () => Promise<DesktopReleaseMetadata>;
  listReceiptPlugins: () => Promise<DesktopReceiptPluginPackListResult>;
  installReceiptPluginFromDialog: () => Promise<DesktopReceiptPluginPackInstallResult | null>;
  installReceiptPluginFromCatalogEntry: (payload: { entryId: string }) => Promise<DesktopReceiptPluginPackInstallResult>;
  enableReceiptPlugin: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
  disableReceiptPlugin: (pluginId: string) => Promise<DesktopReceiptPluginPackToggleResult>;
  uninstallReceiptPlugin: (pluginId: string) => Promise<DesktopReceiptPluginPackUninstallResult>;
  getExternalBrowserPreference: () => Promise<DesktopExternalBrowserPreferenceState>;
  setExternalBrowserPreference: (
    preferredBrowser: DesktopExternalBrowserId
  ) => Promise<DesktopExternalBrowserPreferenceState>;
  openExternalUrl: (url: string) => Promise<void>;
  consumePendingConnectorCallbacks: () => Promise<DesktopConnectorCallbackEvent[]>;
  onConnectorCallback: (handler: (event: DesktopConnectorCallbackEvent) => void) => () => void;
};

export type DesktopApiBridge = (
  DesktopImportBridge &
  Partial<DesktopLocaleBridge> &
  Partial<DesktopCapabilityBridge> &
  Partial<DesktopOcrBridge> &
  Partial<DesktopMobileBridge>
) | null;

export function getDesktopApiBridge(): DesktopApiBridge {
  const desktopApi = (window as unknown as { desktopApi?: DesktopApiBridge }).desktopApi;
  if (!desktopApi || typeof desktopApi.runImport !== "function") {
    return null;
  }
  return desktopApi;
}

export function getDesktopCapabilityBridge(): DesktopCapabilityBridge | null {
  const desktopApi = (window as unknown as { desktopApi?: Partial<DesktopCapabilityBridge> }).desktopApi;
  if (!desktopApi || typeof desktopApi.getCapabilities !== "function") {
    return null;
  }
  return {
    getCapabilities: () => desktopApi.getCapabilities!()
  };
}

export function getDesktopOcrBridge(): DesktopOcrBridge | null {
  const desktopApi = (window as unknown as { desktopApi?: Partial<DesktopOcrBridge> }).desktopApi;
  if (!desktopApi || typeof desktopApi.wakeOcrWorker !== "function") {
    return null;
  }
  return {
    wakeOcrWorker: () => desktopApi.wakeOcrWorker!()
  };
}

export function getDesktopMobileBridge(): DesktopMobileBridge | null {
  const desktopApi = (window as unknown as { desktopApi?: Partial<DesktopMobileBridge> }).desktopApi;
  if (
    !desktopApi ||
    typeof desktopApi.getMobileBridgeStatus !== "function" ||
    typeof desktopApi.startMobileBridge !== "function" ||
    typeof desktopApi.stopMobileBridge !== "function"
  ) {
    return null;
  }
  return {
    getMobileBridgeStatus: () => desktopApi.getMobileBridgeStatus!(),
    startMobileBridge: (payload) => desktopApi.startMobileBridge!(payload),
    stopMobileBridge: () => desktopApi.stopMobileBridge!()
  };
}

export function getDesktopConnectorBridge(): DesktopConnectorBridge | null {
  const desktopApi = (window as unknown as { desktopApi?: Partial<DesktopConnectorBridge> }).desktopApi;
  if (
    !desktopApi ||
    typeof desktopApi.getReleaseMetadata !== "function" ||
    typeof desktopApi.listReceiptPlugins !== "function" ||
    typeof desktopApi.installReceiptPluginFromDialog !== "function" ||
    typeof desktopApi.installReceiptPluginFromCatalogEntry !== "function" ||
    typeof desktopApi.enableReceiptPlugin !== "function" ||
    typeof desktopApi.disableReceiptPlugin !== "function" ||
    typeof desktopApi.uninstallReceiptPlugin !== "function" ||
    typeof desktopApi.getExternalBrowserPreference !== "function" ||
    typeof desktopApi.setExternalBrowserPreference !== "function" ||
    typeof desktopApi.openExternalUrl !== "function" ||
    typeof desktopApi.consumePendingConnectorCallbacks !== "function" ||
    typeof desktopApi.onConnectorCallback !== "function"
  ) {
    return null;
  }
  return {
    getReleaseMetadata: () => desktopApi.getReleaseMetadata!(),
    listReceiptPlugins: () => desktopApi.listReceiptPlugins!(),
    installReceiptPluginFromDialog: () => desktopApi.installReceiptPluginFromDialog!(),
    installReceiptPluginFromCatalogEntry: (payload) => desktopApi.installReceiptPluginFromCatalogEntry!(payload),
    enableReceiptPlugin: (pluginId) => desktopApi.enableReceiptPlugin!(pluginId),
    disableReceiptPlugin: (pluginId) => desktopApi.disableReceiptPlugin!(pluginId),
    uninstallReceiptPlugin: (pluginId) => desktopApi.uninstallReceiptPlugin!(pluginId),
    getExternalBrowserPreference: () => desktopApi.getExternalBrowserPreference!(),
    setExternalBrowserPreference: (preferredBrowser) => desktopApi.setExternalBrowserPreference!(preferredBrowser),
    openExternalUrl: (url) => desktopApi.openExternalUrl!(url),
    consumePendingConnectorCallbacks: () => desktopApi.consumePendingConnectorCallbacks!(),
    onConnectorCallback: (handler) => desktopApi.onConnectorCallback!(handler)
  };
}
