import type {
  BackupRequest,
  ExportRequest,
  ImportRequest,
  SyncRequest
} from "@shared/contracts";
import type { DesktopMessageKey, DesktopTranslationVariables } from "../i18n";
import type { SyncSourceOption } from "./control-center-view-model";
import type { ControlCenterState } from "./use-control-center-state";

interface UseControlCenterActionsArgs {
  locale: "en" | "de";
  t: (key: DesktopMessageKey, vars?: DesktopTranslationVariables) => string;
  selectedSourceMeta: SyncSourceOption;
  state: ControlCenterState;
}

export function useControlCenterActions(args: UseControlCenterActionsArgs) {
  const { locale, selectedSourceMeta, state, t } = args;

  async function handleStartBackend(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    try {
      const status = await window.desktopApi.startBackend();
      state.setBackend(status);
    } catch (err) {
      state.setError(t("shell.error.backendStart", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleStopBackend(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    try {
      const status = await window.desktopApi.stopBackend();
      state.setBackend(status);
    } catch (err) {
      state.setError(t("shell.error.backendStop", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleRunSync(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setSyncResult(null);

    const payload: SyncRequest = {
      source: state.source,
      full: selectedSourceMeta.syncFamily === "lidl_plus" ? state.fullSync : undefined,
      headless:
        selectedSourceMeta.syncFamily === "amazon" || selectedSourceMeta.syncFamily === "browser"
          ? state.headless
          : undefined,
      domain:
        selectedSourceMeta.syncFamily === "amazon" || selectedSourceMeta.syncFamily === "browser"
          ? state.domain || undefined
          : undefined,
      years: selectedSourceMeta.syncFamily === "amazon" ? state.years : undefined,
      maxPages:
        selectedSourceMeta.syncFamily === "amazon" || selectedSourceMeta.syncFamily === "browser"
          ? state.maxPages
          : undefined
    };

    try {
      const result = await window.desktopApi.runSync(payload);
      state.setSyncResult(result);
      state.setBackend(await window.desktopApi.getBackendStatus());
    } catch (err) {
      state.setError(t("shell.error.sync", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleLoadCards(): Promise<void> {
    if (!state.config) {
      state.setError(t("shell.error.configUnavailable"));
      return;
    }

    state.setBusy(true);
    state.setError(null);
    try {
      if (!state.backend?.running) {
        const status = await window.desktopApi.startBackend();
        state.setBackend(status);
      }
      const url = new URL("/api/v1/dashboard/cards", state.config.apiBaseUrl);
      url.searchParams.set("db", state.config.dbPath);
      url.searchParams.set("year", String(state.year));
      url.searchParams.set("month", String(state.month));
      const response = await fetch(url.toString());
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      state.setCardsResult(await response.json());
    } catch (err) {
      state.setError(t("shell.error.cards", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleOpenFullApp(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    try {
      const url = await window.desktopApi.openFullApp();
      window.location.assign(url);
    } catch (err) {
      state.setError(t("shell.error.openFullApp", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleRunExport(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setExportResult(null);

    const outPath = state.exportOutPath.trim();
    if (!outPath) {
      state.setBusy(false);
      state.setError(t("shell.error.exportRequired"));
      return;
    }

    const payload: ExportRequest = {
      outPath,
      format: "json"
    };

    try {
      const result = await window.desktopApi.runExport(payload);
      state.setExportResult(result);
    } catch (err) {
      state.setError(t("shell.error.export", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleRunBackup(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setBackupResult(null);

    const outDir = state.backupOutDir.trim();
    if (!outDir) {
      state.setBusy(false);
      state.setError(t("shell.error.backupRequired"));
      return;
    }

    const payload: BackupRequest = {
      outDir,
      includeExportJson: state.backupIncludeExportJson,
      includeDocuments: state.backupIncludeDocuments
    };

    try {
      const result = await window.desktopApi.runBackup(payload);
      state.setBackupResult(result);
    } catch (err) {
      state.setError(t("shell.error.backup", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleRunImport(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setImportResult(null);

    const backupDir = state.importBackupDir.trim();
    if (!backupDir) {
      state.setBusy(false);
      state.setError(t("shell.error.importRequired"));
      return;
    }

    const payload: ImportRequest = {
      backupDir,
      includeDocuments: state.importIncludeDocuments,
      includeToken: state.importIncludeToken,
      includeCredentialKey: state.importIncludeCredentialKey,
      restartBackend: state.importRestartBackend
    };

    try {
      const result = await window.desktopApi.runImport(payload);
      state.setImportResult(result);
      state.setBackend(await window.desktopApi.getBackendStatus());
    } catch (err) {
      state.setError(t("shell.error.import", { detail: String(err) }));
    } finally {
      state.setBusy(false);
    }
  }

  async function handleRefreshPluginState(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setPluginStatusMessage(null);
    try {
      await Promise.all([state.refreshReceiptPlugins(), state.refreshReleaseMetadata()]);
      state.setPluginStatusMessage(
        locale === "de"
          ? "Lokale Plugin-Pakete und Editionskatalogdetails wurden aktualisiert."
          : "Refreshed local plugin packs and edition catalog details."
      );
    } catch (err) {
      state.setError(
        locale === "de"
          ? `Belegpaket-Details konnten nicht aktualisiert werden. ${String(err)}`
          : `Could not refresh receipt pack details. ${String(err)}`
      );
    } finally {
      state.setBusy(false);
    }
  }

  async function handleInstallReceiptPlugin(): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.installReceiptPluginFromDialog();
      if (!result) {
        state.setPluginStatusMessage(
          locale === "de" ? "Es wurde kein lokales Paket ausgewählt." : "No local pack was selected."
        );
        return;
      }
      state.setPluginStatusMessage(
        result.action === "installed"
          ? locale === "de"
            ? `${result.pack.displayName} ${result.pack.version} importiert. Prüfen Sie die Vertrauenskennzeichnung und aktivieren Sie das Paket, wenn Sie bereit sind.`
            : `Imported ${result.pack.displayName} ${result.pack.version}. Review the trust label, then enable it when you are ready.`
          : result.action === "updated"
            ? locale === "de"
              ? `${result.pack.displayName} auf ${result.pack.version} aktualisiert.`
              : `Updated ${result.pack.displayName} to ${result.pack.version}.`
            : locale === "de"
              ? `${result.pack.displayName} ${result.pack.version} erneut installiert.`
              : `Reinstalled ${result.pack.displayName} ${result.pack.version}.`
      );
      if (result.backendStatus) {
        state.setBackend(result.backendStatus);
      }
      await state.refreshReceiptPlugins();
    } catch (err) {
      state.setError(
        locale === "de"
          ? `Das lokale Belegpaket konnte nicht importiert werden. ${String(err)}`
          : `Could not import the local receipt pack. ${String(err)}`
      );
    } finally {
      state.setBusy(false);
    }
  }

  async function handleInstallReceiptPluginFromCatalog(entryId: string): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.installReceiptPluginFromCatalogEntry({ entryId });
      state.setPluginStatusMessage(
        result.action === "installed"
          ? locale === "de"
            ? `Vertrauenswürdiges Paket ${result.pack.displayName} ${result.pack.version} installiert. Aktivieren Sie es, wenn es im nächsten Backend-Start aktiv sein soll.`
            : `Installed trusted pack ${result.pack.displayName} ${result.pack.version}. Enable it when you want it active in the next backend run.`
          : result.action === "updated"
            ? locale === "de"
              ? `Vertrauenswürdiges Paket ${result.pack.displayName} auf ${result.pack.version} aktualisiert.`
              : `Updated trusted pack ${result.pack.displayName} to ${result.pack.version}.`
            : locale === "de"
              ? `Vertrauenswürdiges Paket ${result.pack.displayName} ${result.pack.version} erneut installiert.`
              : `Reinstalled trusted pack ${result.pack.displayName} ${result.pack.version}.`
      );
      if (result.backendStatus) {
        state.setBackend(result.backendStatus);
      }
      await Promise.all([state.refreshReleaseMetadata(), state.refreshReceiptPlugins()]);
    } catch (err) {
      state.setError(
        locale === "de"
          ? `Das vertrauenswürdige Belegpaket konnte nicht installiert werden. ${String(err)}`
          : `Could not install the trusted receipt pack. ${String(err)}`
      );
    } finally {
      state.setBusy(false);
    }
  }

  async function handleToggleReceiptPlugin(pluginId: string, enabled: boolean): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setPluginStatusMessage(null);
    try {
      const result = enabled
        ? await window.desktopApi.enableReceiptPlugin(pluginId)
        : await window.desktopApi.disableReceiptPlugin(pluginId);
      state.setPluginStatusMessage(
        enabled
          ? locale === "de"
            ? `${result.pack.displayName} aktiviert.`
            : `Enabled ${result.pack.displayName}.`
          : locale === "de"
            ? `${result.pack.displayName} deaktiviert.`
            : `Disabled ${result.pack.displayName}.`
      );
      if (result.backendStatus) {
        state.setBackend(result.backendStatus);
      }
      await state.refreshReceiptPlugins();
    } catch (err) {
      state.setError(
        locale === "de"
          ? `Der Status des Belegpakets konnte nicht aktualisiert werden. ${String(err)}`
          : `Could not update the receipt pack state. ${String(err)}`
      );
    } finally {
      state.setBusy(false);
    }
  }

  async function handleUninstallReceiptPlugin(pluginId: string): Promise<void> {
    state.setBusy(true);
    state.setError(null);
    state.setPluginStatusMessage(null);
    try {
      const result = await window.desktopApi.uninstallReceiptPlugin(pluginId);
      state.setPluginStatusMessage(
        locale === "de"
          ? `${result.pluginId} aus dem lokalen Desktop-Speicher entfernt.`
          : `Removed ${result.pluginId} from local desktop storage.`
      );
      if (result.backendStatus) {
        state.setBackend(result.backendStatus);
      }
      await state.refreshReceiptPlugins();
    } catch (err) {
      state.setError(
        locale === "de"
          ? `Das Belegpaket konnte nicht entfernt werden. ${String(err)}`
          : `Could not remove the receipt pack. ${String(err)}`
      );
    } finally {
      state.setBusy(false);
    }
  }

  return {
    handleInstallReceiptPlugin,
    handleInstallReceiptPluginFromCatalog,
    handleLoadCards,
    handleOpenFullApp,
    handleRefreshPluginState,
    handleRunBackup,
    handleRunExport,
    handleRunImport,
    handleRunSync,
    handleStartBackend,
    handleStopBackend,
    handleToggleReceiptPlugin,
    handleUninstallReceiptPlugin
  };
}
