import { useEffect, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import type {
  BackendConfig,
  BackendStatus,
  CommandLogEvent,
  CommandResult,
  DesktopRuntimeDiagnostics,
  ReceiptPluginPackInfo,
  SyncSourceId
} from "@shared/contracts";
import type { DesktopMessageKey, DesktopTranslationVariables } from "../i18n";
import {
  defaultBackupDir,
  defaultExportPath,
  defaultImportDir,
  defaultYearMonth
} from "./control-center-helpers";

export interface ControlCenterState {
  year: number;
  month: number;
  config: BackendConfig | null;
  setConfig: Dispatch<SetStateAction<BackendConfig | null>>;
  backend: BackendStatus | null;
  setBackend: Dispatch<SetStateAction<BackendStatus | null>>;
  runtimeDiagnostics: DesktopRuntimeDiagnostics | null;
  setRuntimeDiagnostics: Dispatch<SetStateAction<DesktopRuntimeDiagnostics | null>>;
  releaseMetadata: Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>> | null;
  setReleaseMetadata: Dispatch<
    SetStateAction<Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>> | null>
  >;
  releaseMetadataError: string | null;
  setReleaseMetadataError: Dispatch<SetStateAction<string | null>>;
  pluginLoadError: string | null;
  setPluginLoadError: Dispatch<SetStateAction<string | null>>;
  source: SyncSourceId;
  setSource: Dispatch<SetStateAction<SyncSourceId>>;
  fullSync: boolean;
  setFullSync: Dispatch<SetStateAction<boolean>>;
  headless: boolean;
  setHeadless: Dispatch<SetStateAction<boolean>>;
  domain: string;
  setDomain: Dispatch<SetStateAction<string>>;
  years: number;
  setYears: Dispatch<SetStateAction<number>>;
  maxPages: number;
  setMaxPages: Dispatch<SetStateAction<number>>;
  busy: boolean;
  setBusy: Dispatch<SetStateAction<boolean>>;
  syncResult: CommandResult | null;
  setSyncResult: Dispatch<SetStateAction<CommandResult | null>>;
  exportResult: CommandResult | null;
  setExportResult: Dispatch<SetStateAction<CommandResult | null>>;
  exportOutPath: string;
  setExportOutPath: Dispatch<SetStateAction<string>>;
  backupResult: CommandResult | null;
  setBackupResult: Dispatch<SetStateAction<CommandResult | null>>;
  backupOutDir: string;
  setBackupOutDir: Dispatch<SetStateAction<string>>;
  backupIncludeExportJson: boolean;
  setBackupIncludeExportJson: Dispatch<SetStateAction<boolean>>;
  backupIncludeDocuments: boolean;
  setBackupIncludeDocuments: Dispatch<SetStateAction<boolean>>;
  importResult: CommandResult | null;
  setImportResult: Dispatch<SetStateAction<CommandResult | null>>;
  importBackupDir: string;
  setImportBackupDir: Dispatch<SetStateAction<string>>;
  importIncludeDocuments: boolean;
  setImportIncludeDocuments: Dispatch<SetStateAction<boolean>>;
  importIncludeToken: boolean;
  setImportIncludeToken: Dispatch<SetStateAction<boolean>>;
  importIncludeCredentialKey: boolean;
  setImportIncludeCredentialKey: Dispatch<SetStateAction<boolean>>;
  importRestartBackend: boolean;
  setImportRestartBackend: Dispatch<SetStateAction<boolean>>;
  pluginPacks: ReceiptPluginPackInfo[];
  setPluginPacks: Dispatch<SetStateAction<ReceiptPluginPackInfo[]>>;
  pluginSearchPaths: string[];
  setPluginSearchPaths: Dispatch<SetStateAction<string[]>>;
  pluginStatusMessage: string | null;
  setPluginStatusMessage: Dispatch<SetStateAction<string | null>>;
  cardsResult: unknown;
  setCardsResult: Dispatch<SetStateAction<unknown>>;
  logs: CommandLogEvent[];
  setLogs: Dispatch<SetStateAction<CommandLogEvent[]>>;
  error: string | null;
  setError: Dispatch<SetStateAction<string | null>>;
  bootError: string | null;
  setBootError: Dispatch<SetStateAction<string | null>>;
  refreshReleaseMetadata: () => Promise<void>;
  refreshReceiptPlugins: () => Promise<void>;
}

export function useControlCenterState(args: {
  t: (key: DesktopMessageKey, vars?: DesktopTranslationVariables) => string;
}): ControlCenterState {
  const [{ year, month }] = useState(defaultYearMonth);
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [backend, setBackend] = useState<BackendStatus | null>(null);
  const [runtimeDiagnostics, setRuntimeDiagnostics] = useState<DesktopRuntimeDiagnostics | null>(null);
  const [releaseMetadata, setReleaseMetadata] = useState<Awaited<ReturnType<typeof window.desktopApi.getReleaseMetadata>> | null>(null);
  const [releaseMetadataError, setReleaseMetadataError] = useState<string | null>(null);
  const [pluginLoadError, setPluginLoadError] = useState<string | null>(null);
  const [source, setSource] = useState<SyncSourceId>("lidl_plus_de");
  const [fullSync, setFullSync] = useState(false);
  const [headless, setHeadless] = useState(true);
  const [domain, setDomain] = useState("");
  const [years, setYears] = useState(2);
  const [maxPages, setMaxPages] = useState(8);
  const [busy, setBusy] = useState(false);
  const [syncResult, setSyncResult] = useState<CommandResult | null>(null);
  const [exportResult, setExportResult] = useState<CommandResult | null>(null);
  const [exportOutPath, setExportOutPath] = useState("");
  const [backupResult, setBackupResult] = useState<CommandResult | null>(null);
  const [backupOutDir, setBackupOutDir] = useState("");
  const [backupIncludeExportJson, setBackupIncludeExportJson] = useState(true);
  const [backupIncludeDocuments, setBackupIncludeDocuments] = useState(true);
  const [importResult, setImportResult] = useState<CommandResult | null>(null);
  const [importBackupDir, setImportBackupDir] = useState("");
  const [importIncludeDocuments, setImportIncludeDocuments] = useState(true);
  const [importIncludeToken, setImportIncludeToken] = useState(true);
  const [importIncludeCredentialKey, setImportIncludeCredentialKey] = useState(true);
  const [importRestartBackend, setImportRestartBackend] = useState(true);
  const [pluginPacks, setPluginPacks] = useState<ReceiptPluginPackInfo[]>([]);
  const [pluginSearchPaths, setPluginSearchPaths] = useState<string[]>([]);
  const [pluginStatusMessage, setPluginStatusMessage] = useState<string | null>(null);
  const [cardsResult, setCardsResult] = useState<unknown>(null);
  const [logs, setLogs] = useState<CommandLogEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    let disposeLogs: (() => void) | null = null;
    let disposeBootError: (() => void) | null = null;

    async function boot(): Promise<void> {
      const results = await Promise.allSettled([
        window.desktopApi.getConfig(),
        window.desktopApi.getBootError(),
        window.desktopApi.getBackendStatus(),
        window.desktopApi.getRuntimeDiagnostics(),
        window.desktopApi.listReceiptPlugins(),
        window.desktopApi.getReleaseMetadata()
      ]);

      const [cfgResult, bootErrorResult, statusResult, runtimeResult, receiptPluginsResult, metadataResult] = results;

      if (cfgResult.status === "fulfilled") {
        setConfig(cfgResult.value);
      } else {
        setError(args.t("shell.error.desktopApiInit", { detail: String(cfgResult.reason) }));
      }

      if (bootErrorResult.status === "fulfilled") {
        setBootError(bootErrorResult.value);
      }

      if (statusResult.status === "fulfilled") {
        setBackend(statusResult.value);
      }

      if (runtimeResult.status === "fulfilled") {
        setRuntimeDiagnostics(runtimeResult.value);
      }

      if (receiptPluginsResult.status === "fulfilled") {
        setPluginPacks(receiptPluginsResult.value.packs);
        setPluginSearchPaths(receiptPluginsResult.value.activePluginSearchPaths);
        setPluginLoadError(null);
      } else {
        setPluginLoadError(String(receiptPluginsResult.reason));
      }

      if (metadataResult.status === "fulfilled") {
        setReleaseMetadata(metadataResult.value);
        setReleaseMetadataError(null);
      } else {
        setReleaseMetadataError(String(metadataResult.reason));
      }

      disposeLogs = window.desktopApi.onLog((event) => {
        setLogs((prev) => [...prev.slice(-399), event]);
      });
      disposeBootError = window.desktopApi.onBootError((message) => {
        setBootError(message);
      });
    }

    void boot();

    return () => {
      disposeLogs?.();
      disposeBootError?.();
    };
  }, [args.t]);

  useEffect(() => {
    if (config && !exportOutPath) {
      setExportOutPath(defaultExportPath(config.userDataDir));
    }
  }, [config, exportOutPath]);

  useEffect(() => {
    if (config && !backupOutDir) {
      setBackupOutDir(defaultBackupDir(config.userDataDir));
    }
  }, [config, backupOutDir]);

  useEffect(() => {
    if (config && !importBackupDir) {
      setImportBackupDir(defaultImportDir(config.userDataDir));
    }
  }, [config, importBackupDir]);

  async function refreshReleaseMetadata(): Promise<void> {
    try {
      const nextMetadata = await window.desktopApi.getReleaseMetadata();
      setReleaseMetadata(nextMetadata);
      setReleaseMetadataError(null);
    } catch (err) {
      setReleaseMetadataError(String(err));
    }
  }

  async function refreshReceiptPlugins(): Promise<void> {
    try {
      const result = await window.desktopApi.listReceiptPlugins();
      setPluginPacks(result.packs);
      setPluginSearchPaths(result.activePluginSearchPaths);
      setPluginLoadError(null);
    } catch (err) {
      setPluginLoadError(String(err));
    }
  }

  return {
    year,
    month,
    config,
    setConfig,
    backend,
    setBackend,
    runtimeDiagnostics,
    setRuntimeDiagnostics,
    releaseMetadata,
    setReleaseMetadata,
    releaseMetadataError,
    setReleaseMetadataError,
    pluginLoadError,
    setPluginLoadError,
    source,
    setSource,
    fullSync,
    setFullSync,
    headless,
    setHeadless,
    domain,
    setDomain,
    years,
    setYears,
    maxPages,
    setMaxPages,
    busy,
    setBusy,
    syncResult,
    setSyncResult,
    exportResult,
    setExportResult,
    exportOutPath,
    setExportOutPath,
    backupResult,
    setBackupResult,
    backupOutDir,
    setBackupOutDir,
    backupIncludeExportJson,
    setBackupIncludeExportJson,
    backupIncludeDocuments,
    setBackupIncludeDocuments,
    importResult,
    setImportResult,
    importBackupDir,
    setImportBackupDir,
    importIncludeDocuments,
    setImportIncludeDocuments,
    importIncludeToken,
    setImportIncludeToken,
    importIncludeCredentialKey,
    setImportIncludeCredentialKey,
    importRestartBackend,
    setImportRestartBackend,
    pluginPacks,
    setPluginPacks,
    pluginSearchPaths,
    setPluginSearchPaths,
    pluginStatusMessage,
    setPluginStatusMessage,
    cardsResult,
    setCardsResult,
    logs,
    setLogs,
    error,
    setError,
    bootError,
    setBootError,
    refreshReleaseMetadata,
    refreshReceiptPlugins
  };
}
