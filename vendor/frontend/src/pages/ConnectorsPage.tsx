import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchConnectorConfig,
  fetchConnectors,
  reloadConnectors,
  startConnectorBootstrap,
  startConnectorSync,
  submitConnectorConfig,
  type ConnectorConfig,
  type ConnectorConfigField,
  type ConnectorDiscoveryRow
} from "@/api/connectors";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  getDesktopConnectorBridge,
  type DesktopConnectorCatalogEntry,
  type DesktopReceiptPluginPackInfo
} from "@/lib/desktop-api";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { cn } from "@/lib/utils";
import { formatDateTime } from "@/utils/format";

type SetupState = {
  connector: ConnectorDiscoveryRow;
  mode: "setup" | "reconnect" | "configure";
};

type PackGuideState = {
  pack: DesktopReceiptPluginPackInfo;
  catalogEntry: DesktopConnectorCatalogEntry | null;
  showEnableAction: boolean;
};

type SetupValues = Record<string, string | boolean>;

type ConnectorGuide = {
  headline: string;
  summary: string;
  speedDescription: string;
  caution: string;
  steps: Array<{
    title: string;
    description: string;
  }>;
};

function compareVersions(left: string, right: string): number {
  const leftParts = left.split(/[\.-]/);
  const rightParts = right.split(/[\.-]/);
  const maxLength = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < maxLength; index += 1) {
    const leftPart = leftParts[index] ?? "0";
    const rightPart = rightParts[index] ?? "0";
    const leftNumber = Number(leftPart);
    const rightNumber = Number(rightPart);
    const bothNumeric = Number.isFinite(leftNumber) && Number.isFinite(rightNumber);
    const comparison = bothNumeric
      ? leftNumber - rightNumber
      : leftPart.localeCompare(rightPart, undefined, { numeric: true, sensitivity: "base" });
    if (comparison !== 0) {
      return comparison < 0 ? -1 : 1;
    }
  }
  return 0;
}

function initialSetupValues(config: ConnectorConfig): SetupValues {
  const nextValues: SetupValues = {};
  for (const field of config.fields) {
    if (field.sensitive) {
      nextValues[field.key] = "";
      continue;
    }
    if (typeof field.value === "boolean") {
      nextValues[field.key] = field.value;
    } else if (field.value === null || field.value === undefined) {
      nextValues[field.key] = "";
    } else {
      nextValues[field.key] = String(field.value);
    }
  }
  return nextValues;
}

function fieldsForSetupMode(
  fields: ConnectorConfigField[],
  mode: SetupState["mode"]
): ConnectorConfigField[] {
  if (mode === "configure") {
    return fields;
  }
  return fields.filter((field) => !field.operator_only);
}

function buildConfigPayload(
  config: ConnectorConfig,
  visibleFields: ConnectorConfigField[],
  values: SetupValues,
  clearSecretKeys: string[]
): {
  values: Record<string, string | number | boolean | null>;
  clear_secret_keys?: string[];
} {
  const payloadValues: Record<string, string | number | boolean | null> = {};
  const clearSet = new Set(clearSecretKeys);
  const visibleKeys = new Set(visibleFields.map((field) => field.key));

  for (const field of config.fields) {
    if (!visibleKeys.has(field.key)) {
      continue;
    }
    const rawValue = values[field.key];
    if (field.sensitive) {
      if (typeof rawValue === "string" && rawValue.trim()) {
        payloadValues[field.key] = rawValue.trim();
        clearSet.delete(field.key);
      } else if (!field.has_value) {
        payloadValues[field.key] = null;
      }
      continue;
    }
    if (field.input_kind === "boolean") {
      payloadValues[field.key] = Boolean(rawValue);
      continue;
    }
    if (typeof rawValue === "string") {
      const trimmed = rawValue.trim();
      payloadValues[field.key] = trimmed.length > 0 ? trimmed : null;
    }
  }

  return {
    values: payloadValues,
    clear_secret_keys: clearSet.size > 0 ? Array.from(clearSet) : undefined
  };
}

function trustLabel(trustClass: string | null | undefined): string {
  if (trustClass === "official") {
    return "Official";
  }
  if (trustClass === "community_verified") {
    return "Community verified";
  }
  if (trustClass === "local_custom") {
    return "Local custom";
  }
  if (trustClass === "community_unsigned") {
    return "Community unsigned";
  }
  return "Unknown trust";
}

function connectorStatusLabel(connector: ConnectorDiscoveryRow): string {
  switch (connector.ui.status) {
    case "setup_required":
      return "Setup required";
    case "connected":
      return "Connected";
    case "syncing":
      return "Syncing";
    case "ready":
      return "Ready";
    case "needs_attention":
      return "Needs attention";
    case "error":
      return "Error";
    case "preview":
      return "Preview";
    default:
      return "Unknown";
  }
}

function packStateLabel(pack: DesktopReceiptPluginPackInfo): string {
  if (pack.status === "enabled") {
    return "Enabled";
  }
  if (pack.status === "disabled") {
    return "Stored locally";
  }
  if (pack.status === "revoked") {
    return "Blocked";
  }
  if (pack.status === "incompatible") {
    return "Incompatible";
  }
  return "Needs attention";
}

function findCatalogEntry(
  catalogEntries: DesktopConnectorCatalogEntry[],
  connector: ConnectorDiscoveryRow,
  pack: DesktopReceiptPluginPackInfo | null
): DesktopConnectorCatalogEntry | null {
  const bySource = catalogEntries.find((entry) => entry.source_id === connector.source_id);
  if (bySource) {
    return bySource;
  }
  if (pack) {
    return (
      catalogEntries.find((entry) => entry.plugin_id === pack.pluginId) ??
      (pack.catalogEntryId
        ? catalogEntries.find((entry) => entry.entry_id === pack.catalogEntryId) ?? null
        : null)
    );
  }
  return null;
}

function findCatalogEntryForPack(
  catalogEntries: DesktopConnectorCatalogEntry[],
  pack: DesktopReceiptPluginPackInfo
): DesktopConnectorCatalogEntry | null {
  return (
    (pack.catalogEntryId
      ? catalogEntries.find((entry) => entry.entry_id === pack.catalogEntryId)
      : null) ??
    catalogEntries.find((entry) => entry.plugin_id === pack.pluginId) ??
    catalogEntries.find((entry) => entry.source_id === pack.sourceId) ??
    null
  );
}

function fallbackConnectorGuide(displayName: string): ConnectorGuide {
  return {
    headline: "Simple first-run setup",
    summary: `${displayName} needs a quick sign-in before it can import receipts on this computer.`,
    speedDescription: "Normal speed. Time can vary depending on the retailer and your account.",
    caution: "If something changes on the retailer site, you may need to reconnect later.",
    steps: [
      {
        title: "Turn it on",
        description: "Enable the connector first so this desktop app can load it."
      },
      {
        title: "Finish setup and import",
        description: "Use the connector card to sign in if needed, then start your first import."
      }
    ]
  };
}

function connectorGuideForPack(pack: DesktopReceiptPluginPackInfo | null, displayName: string): ConnectorGuide {
  const fallback = fallbackConnectorGuide(displayName);
  const onboarding = pack?.onboarding;
  if (!onboarding) {
    return fallback;
  }
  return {
    headline: onboarding.title ?? fallback.headline,
    summary: onboarding.summary ?? fallback.summary,
    speedDescription: onboarding.expectedSpeed ?? fallback.speedDescription,
    caution: onboarding.caution ?? fallback.caution,
    steps: onboarding.steps.length > 0 ? onboarding.steps : fallback.steps
  };
}

function connectorStatusSummary(
  connector: ConnectorDiscoveryRow,
  pack: DesktopReceiptPluginPackInfo | null
): string {
  if (pack?.status === "disabled") {
    return "Imported on this computer, but still turned off.";
  }
  if (connector.ui.status === "syncing") {
    return "Import is running right now.";
  }
  if (connector.ui.status === "setup_required") {
    return "Needs a first sign-in before it can import receipts.";
  }
  if (connector.actions.primary.kind === "reconnect") {
    return "Your sign-in needs attention before the next import.";
  }
  if (connector.ui.status === "error" || connector.ui.status === "needs_attention") {
    return connector.status_detail ?? "This connector needs attention before it can be used normally.";
  }
  if (connector.last_synced_at) {
    return "Ready for the next import.";
  }
  return connector.ui.description;
}

function primaryActionLabel(connector: ConnectorDiscoveryRow): string {
  if (connector.actions.primary.kind === "reconnect") {
    return "Fix sign-in";
  }
  if (connector.actions.primary.kind === "sync_now") {
    return "Import receipts";
  }
  return "Set up";
}

export function ConnectorsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [setupState, setSetupState] = useState<SetupState | null>(null);
  const [setupValues, setSetupValues] = useState<SetupValues>({});
  const [clearSecretKeys, setClearSecretKeys] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [packGuideState, setPackGuideState] = useState<PackGuideState | null>(null);
  const [highlightedPackId, setHighlightedPackId] = useState<string | null>(null);

  const connectorsQuery = useQuery({
    queryKey: ["connectors"],
    queryFn: fetchConnectors,
    refetchInterval: (query) =>
      query.state.data?.connectors.some((connector) => connector.ui.status === "syncing") ? 2000 : false
  });

  const desktopContextQuery = useQuery({
    queryKey: ["desktop", "connectors", "context"],
    queryFn: async () => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        return {
          available: false,
          releaseMetadata: null,
          receiptPlugins: null
        };
      }
      const [releaseMetadata, receiptPlugins] = await Promise.all([
        bridge.getReleaseMetadata(),
        bridge.listReceiptPlugins()
      ]);
      return {
        available: true,
        releaseMetadata,
        receiptPlugins
      };
    }
  });

  const setupConfigQuery = useQuery({
    queryKey: ["connectors", "config", setupState?.connector.source_id],
    queryFn: () => fetchConnectorConfig(setupState!.connector.source_id),
    enabled:
      setupState !== null &&
      (setupState.connector.actions.operator.configure || setupState.connector.config_state !== "not_required")
  });

  useEffect(() => {
    if (!setupConfigQuery.data) {
      setSetupValues({});
      setClearSecretKeys([]);
      return;
    }
    setSetupValues(initialSetupValues(setupConfigQuery.data));
    setClearSecretKeys([]);
  }, [setupConfigQuery.data]);

  const bootstrapMutation = useMutation({
    mutationFn: (sourceId: string) => startConnectorBootstrap(sourceId),
    onSuccess: async (_result, sourceId) => {
      setFeedback(t("pages.connectors.feedback.setupStarted", { name: sourceId }));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.startBootstrapErrorTitle")));
    }
  });

  const syncMutation = useMutation({
    mutationFn: ({ sourceId, full }: { sourceId: string; full: boolean }) =>
      startConnectorSync(sourceId, full),
    onSuccess: async (_result, { sourceId, full }) => {
      setFeedback(
        full
          ? t("pages.connectors.feedback.fullSyncStarted", { name: sourceId })
          : t("pages.connectors.feedback.syncStarted", { name: sourceId })
      );
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.startSyncErrorTitle")));
    }
  });

  const reloadMutation = useMutation({
    mutationFn: reloadConnectors,
    onSuccess: async () => {
      setFeedback(t("pages.connectors.feedback.registryReloaded"));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.loadSourceErrorTitle")));
    }
  });

  const installLocalPackMutation = useMutation({
    mutationFn: async () => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.installReceiptPluginFromDialog();
    },
    onSuccess: async (result) => {
      if (!result) {
        return;
      }
      setHighlightedPackId(result.pack.pluginId);
      setFeedback(`Imported ${result.pack.displayName}. One more step: turn it on to use it in this app.`);
      if (result.pack.status === "disabled") {
        setPackGuideState({
          pack: result.pack,
          catalogEntry: findCatalogEntryForPack(catalogEntries, result.pack),
          showEnableAction: true
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(`Could not import the local receipt pack. ${String(error)}`);
    }
  });

  const installCatalogPackMutation = useMutation({
    mutationFn: async (entryId: string) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.installReceiptPluginFromCatalogEntry({ entryId });
    },
    onSuccess: async (result) => {
      setHighlightedPackId(result.pack.pluginId);
      setFeedback(
        result.pack.status === "disabled"
          ? `Installed ${result.pack.displayName}. Turn it on to finish adding it to this desktop app.`
          : `Installed ${result.pack.displayName} from the trusted catalog.`
      );
      if (result.pack.status === "disabled") {
        setPackGuideState({
          pack: result.pack,
          catalogEntry: findCatalogEntryForPack(catalogEntries, result.pack),
          showEnableAction: true
        });
      }
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(`Could not install the trusted receipt pack. ${String(error)}`);
    }
  });

  const togglePackMutation = useMutation({
    mutationFn: async ({ pluginId, enabled }: { pluginId: string; enabled: boolean }) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return enabled ? await bridge.enableReceiptPlugin(pluginId) : await bridge.disableReceiptPlugin(pluginId);
    },
    onSuccess: async (result, variables) => {
      setFeedback(
        variables.enabled
          ? `${result.pack.displayName} is turned on. Next, use Set up to sign in if the connector asks for it.`
          : `${result.pack.displayName} is turned off on this computer.`
      );
      if (variables.enabled) {
        setHighlightedPackId(result.pack.pluginId);
      }
      setPackGuideState((current) => (current?.pack.pluginId === result.pack.pluginId ? null : current));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(`Could not update the receipt pack state. ${String(error)}`);
    }
  });

  const uninstallPackMutation = useMutation({
    mutationFn: async (pluginId: string) => {
      const bridge = getDesktopConnectorBridge();
      if (!bridge) {
        throw new Error("Desktop pack management is unavailable in this build.");
      }
      return await bridge.uninstallReceiptPlugin(pluginId);
    },
    onSuccess: async (_result, pluginId) => {
      setFeedback(`Removed ${pluginId} from desktop storage.`);
      setHighlightedPackId((current) => (current === pluginId ? null : current));
      setPackGuideState((current) => (current?.pack.pluginId === pluginId ? null : current));
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(`Could not remove the receipt pack. ${String(error)}`);
    }
  });

  const configMutation = useMutation({
    mutationFn: ({
      sourceId,
      payload
    }: {
      sourceId: string;
      payload: {
        values: Record<string, string | number | boolean | null>;
        clear_secret_keys?: string[];
      };
    }) => submitConnectorConfig(sourceId, payload),
    onSuccess: async (_result, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["connectors", "config", variables.sourceId] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.loadSourceErrorTitle")));
    }
  });

  const connectors = connectorsQuery.data?.connectors ?? [];
  const viewerIsAdmin = Boolean(connectorsQuery.data?.viewer.is_admin);
  const visibleConnectors = useMemo(
    () => connectors.filter((connector) => connector.ui.visibility === "default"),
    [connectors]
  );
  const catalogEntries = desktopContextQuery.data?.releaseMetadata?.discovery_catalog.entries ?? [];
  const receiptPlugins = desktopContextQuery.data?.receiptPlugins?.packs ?? [];
  const desktopBridgeAvailable = desktopContextQuery.data?.available ?? false;
  const curatedDesktopPackEntries = useMemo(
    () => catalogEntries.filter((entry) => entry.entry_type === "desktop_pack"),
    [catalogEntries]
  );

  const packBySourceId = useMemo(
    () => new Map(receiptPlugins.map((pack) => [pack.sourceId, pack])),
    [receiptPlugins]
  );
  const connectorCards = useMemo(
    () =>
      visibleConnectors.map((connector) => {
        const pack = packBySourceId.get(connector.source_id) ?? null;
        const catalogEntry = findCatalogEntry(catalogEntries, connector, pack);
        return { connector, pack, catalogEntry };
      }),
    [catalogEntries, packBySourceId, visibleConnectors]
  );

  const pendingActivationPacks = useMemo(
    () => receiptPlugins.filter((pack) => pack.status === "disabled"),
    [receiptPlugins]
  );

  const pendingActivationPluginIds = useMemo(
    () => new Set(pendingActivationPacks.map((pack) => pack.pluginId)),
    [pendingActivationPacks]
  );

  const visibleConnectorCards = useMemo(
    () =>
      connectorCards.filter(
        ({ pack }) => !(pack && pendingActivationPluginIds.has(pack.pluginId))
      ),
    [connectorCards, pendingActivationPluginIds]
  );

  const attentionPacks = useMemo(
    () =>
      receiptPlugins.filter(
        (pack) =>
          pack.status !== "enabled" &&
          pack.status !== "disabled" &&
          connectorCards.some((item) => item.pack?.pluginId === pack.pluginId) === false
      ),
    [connectorCards, receiptPlugins]
  );

  const setupDialogFields = useMemo(() => {
    if (!setupConfigQuery.data || !setupState) {
      return [];
    }
    return fieldsForSetupMode(setupConfigQuery.data.fields, setupState.mode);
  }, [setupConfigQuery.data, setupState]);

  const connectorsError = connectorsQuery.error
    ? resolveApiErrorMessage(connectorsQuery.error, t, t("pages.connectors.loadSourceErrorTitle"))
    : null;

  async function openSetup(connector: ConnectorDiscoveryRow, mode: SetupState["mode"]): Promise<void> {
    setFeedback(null);
    if (mode !== "configure" && connector.config_state === "not_required" && !connector.actions.operator.configure) {
      await bootstrapMutation.mutateAsync(connector.source_id);
      return;
    }
    setSetupState({ connector, mode });
  }

  function closeSetup(): void {
    setSetupState(null);
    setSetupValues({});
    setClearSecretKeys([]);
  }

  function openPackGuide(pack: DesktopReceiptPluginPackInfo, showEnableAction: boolean): void {
    setPackGuideState({
      pack,
      catalogEntry: findCatalogEntryForPack(catalogEntries, pack),
      showEnableAction
    });
  }

  async function handlePrimaryAction(connector: ConnectorDiscoveryRow): Promise<void> {
    const kind = connector.actions.primary.kind;
    if (!kind || !connector.actions.primary.enabled) {
      return;
    }
    if (kind === "set_up") {
      await openSetup(connector, "setup");
      return;
    }
    if (kind === "reconnect") {
      await openSetup(connector, "reconnect");
      return;
    }
    if (kind === "sync_now") {
      await syncMutation.mutateAsync({ sourceId: connector.source_id, full: false });
    }
  }

  async function handleSaveSetup(): Promise<void> {
    if (!setupState) {
      return;
    }
    const config = setupConfigQuery.data;
    const connector = setupState.connector;
    if (config) {
      const payload = buildConfigPayload(config, setupDialogFields, setupValues, clearSecretKeys);
      await configMutation.mutateAsync({
        sourceId: connector.source_id,
        payload
      });
    }

    if (setupState.mode !== "configure") {
      await bootstrapMutation.mutateAsync(connector.source_id);
    } else {
      setFeedback(t("pages.connectors.feedback.settingsSaved", { name: connector.display_name }));
    }
    closeSetup();
  }

  async function handleGuidePrimaryAction(): Promise<void> {
    if (!packGuideState?.showEnableAction) {
      setPackGuideState(null);
      return;
    }
    await togglePackMutation.mutateAsync({ pluginId: packGuideState.pack.pluginId, enabled: true });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Connectors"
        description="Add store connectors, turn them on, and import receipts from one place."
      >
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => void installLocalPackMutation.mutateAsync()}
            disabled={installLocalPackMutation.isPending || !desktopBridgeAvailable}
          >
            {installLocalPackMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Import .zip connector
          </Button>
          <Button
            variant="outline"
            onClick={() => void reloadMutation.mutateAsync()}
            disabled={reloadMutation.isPending}
          >
            {reloadMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </PageHeader>

      <Card className="border-border/60 bg-card/85 shadow-sm">
        <CardHeader className="space-y-2">
          <CardTitle>Start here</CardTitle>
          <CardDescription>
            Most connector imports only need three simple steps. If you already downloaded a plugin file, start with
            the import button above.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-border/60 bg-background/60 p-4">
            <p className="text-sm font-medium text-foreground">1. Import your connector</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Choose the plugin `.zip` file you downloaded, or install a trusted connector below.
            </p>
          </div>
          <div className="rounded-xl border border-border/60 bg-background/60 p-4">
            <p className="text-sm font-medium text-foreground">2. Turn it on</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Newly imported connectors stay off until you confirm that you want to use them on this computer.
            </p>
          </div>
          <div className="rounded-xl border border-border/60 bg-background/60 p-4">
            <p className="text-sm font-medium text-foreground">3. Sign in and import</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Use the connector card to finish setup, then start your first receipt import.
            </p>
          </div>
        </CardContent>
      </Card>

      {desktopContextQuery.data?.releaseMetadata ? (
        <div className="app-section-divider grid gap-4 md:grid-cols-3">
          <div>
            <p className="text-xs uppercase text-muted-foreground">Edition</p>
            <p className="font-medium">
              {desktopContextQuery.data.releaseMetadata.active_release_variant.display_name}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase text-muted-foreground">Market profile</p>
            <p className="font-medium">
              {desktopContextQuery.data.releaseMetadata.selected_market_profile.display_name}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase text-muted-foreground">Installed connector plugins</p>
            <p className="font-medium">{receiptPlugins.length}</p>
          </div>
        </div>
      ) : null}

      {feedback ? (
        <Alert>
          <AlertTitle>Connector status</AlertTitle>
          <AlertDescription>{feedback}</AlertDescription>
        </Alert>
      ) : null}

      {connectorsError ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load connectors</AlertTitle>
          <AlertDescription>{connectorsError}</AlertDescription>
        </Alert>
      ) : null}

      {pendingActivationPacks.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">Turn on imported connectors</h2>
            <p className="text-sm text-muted-foreground">
              These connectors are already on your computer. They need one more confirmation before they show up as
              active connectors.
            </p>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            {pendingActivationPacks.map((pack) => {
              const catalogEntry = findCatalogEntryForPack(catalogEntries, pack);
              const guide = connectorGuideForPack(pack, pack.displayName);
              return (
                <Card
                  key={pack.pluginId}
                  className={cn(
                    "border-border/60 bg-card/85 shadow-sm",
                    highlightedPackId === pack.pluginId ? "ring-2 ring-primary/20" : ""
                  )}
                >
                  <CardHeader className="space-y-3 border-b border-border/50 bg-background/40">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <CardTitle className="text-lg">{pack.displayName}</CardTitle>
                        <CardDescription>Imported and ready to be turned on.</CardDescription>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Badge>Needs one more step</Badge>
                        <Badge variant="secondary">{trustLabel(pack.trustClass)}</Badge>
                        <Badge variant="outline">{pack.version}</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4 bg-card/70 pt-6">
                    <p className="text-sm text-muted-foreground">
                      {guide.summary} {guide.speedDescription}
                    </p>
                    <Alert>
                      <AlertTitle>{guide.headline}</AlertTitle>
                      <AlertDescription>{guide.caution}</AlertDescription>
                    </Alert>
                    {catalogEntry?.support_policy ? (
                      <p className="text-sm text-muted-foreground">
                        {catalogEntry.support_policy.maintainer_support} {catalogEntry.support_policy.update_expectations}
                      </p>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      <Button
                        onClick={() => openPackGuide(pack, true)}
                        disabled={togglePackMutation.isPending}
                      >
                        Review and enable
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => void uninstallPackMutation.mutateAsync(pack.pluginId)}
                        disabled={uninstallPackMutation.isPending}
                      >
                        {uninstallPackMutation.isPending && uninstallPackMutation.variables === pack.pluginId ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        Remove connector
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      ) : null}

      <div className="space-y-1.5">
        <h2 className="font-semibold leading-none tracking-tight">Your connectors</h2>
        <p className="text-sm text-muted-foreground">
          Active and built-in connectors live here. Use them to sign in, reconnect, and run imports.
        </p>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {visibleConnectorCards.map(({ connector, pack, catalogEntry }) => {
          const updateAvailable =
            pack !== null &&
            catalogEntry?.current_version &&
            compareVersions(pack.version, catalogEntry.current_version) < 0;
          const guide = connectorGuideForPack(pack, connector.display_name);

          return (
          <Card key={connector.source_id} className="border-border/60 bg-card/85 shadow-sm">
            <CardHeader className="space-y-3 border-b border-border/50 bg-background/40">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <CardTitle className="text-lg">{connector.display_name}</CardTitle>
                    <CardDescription>{connectorStatusSummary(connector, pack)}</CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge>{connectorStatusLabel(connector)}</Badge>
                    <Badge variant="secondary">{trustLabel(pack?.trustClass ?? connector.trust_class)}</Badge>
                  </div>
                </div>
                {connector.status_detail ? <p className="text-sm text-muted-foreground">{connector.status_detail}</p> : null}
                {updateAvailable ? (
                  <Alert>
                    <AlertTitle>Trusted pack update available</AlertTitle>
                    <AlertDescription>
                      {connector.display_name} is running {pack.version}, while the catalog entry lists{" "}
                      {catalogEntry?.current_version}. Install the trusted update from this page when you want the newer pack.
                    </AlertDescription>
                  </Alert>
                ) : null}
              </CardHeader>
              <CardContent className="space-y-4 bg-card/70">
                <div className="grid gap-2 text-sm text-muted-foreground">
                  <p>
                    <strong className="text-foreground">What to expect:</strong> {guide.speedDescription}
                  </p>
                  {connector.last_synced_at ? (
                    <p>
                      <strong className="text-foreground">Last import:</strong> {formatDateTime(connector.last_synced_at)}
                    </p>
                  ) : null}
                  {connector.last_sync_summary ? (
                    <p>
                      <strong className="text-foreground">Last result:</strong> {connector.last_sync_summary}
                    </p>
                  ) : null}
                  {pack ? (
                    <p>
                      <strong className="text-foreground">Installed on this computer:</strong> {packStateLabel(pack)} via{" "}
                      {pack.installedVia === "catalog_url" ? "trusted catalog download" : ".zip import"}.
                    </p>
                  ) : null}
                </div>

                {pack ? (
                  <Alert>
                    <AlertTitle>Before your first import</AlertTitle>
                    <AlertDescription>
                      {guide.summary} {guide.caution}
                    </AlertDescription>
                  </Alert>
                ) : null}

                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => void handlePrimaryAction(connector)}
                    disabled={
                      bootstrapMutation.isPending ||
                      syncMutation.isPending ||
                      !connector.actions.primary.enabled ||
                      connector.actions.primary.kind === null
                    }
                  >
                    {(bootstrapMutation.isPending || syncMutation.isPending) &&
                    (bootstrapMutation.variables === connector.source_id ||
                      syncMutation.variables?.sourceId === connector.source_id) ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    {primaryActionLabel(connector)}
                  </Button>

                  {connector.supports_sync ? (
                    <Button
                      variant="outline"
                      onClick={() => void syncMutation.mutateAsync({ sourceId: connector.source_id, full: true })}
                      disabled={syncMutation.isPending || connector.enable_state !== "enabled"}
                    >
                      Full import
                    </Button>
                  ) : null}

                  {viewerIsAdmin &&
                  (connector.actions.operator.configure || connector.config_state !== "not_required") ? (
                    <Button
                      variant="outline"
                      onClick={() => void openSetup(connector, "configure")}
                    >
                      Connector settings
                    </Button>
                  ) : null}

                  {pack ? (
                    <Button
                      variant="outline"
                      onClick={() => openPackGuide(pack, false)}
                    >
                      What to expect
                    </Button>
                  ) : null}

                  {connector.actions.secondary.href ? (
                    <Button asChild variant="ghost">
                      <Link to={connector.actions.secondary.href}>
                        <ExternalLink className="mr-2 h-4 w-4" />
                        {connector.actions.secondary.kind === "view_receipts" ? "View receipts" : "Open source"}
                      </Link>
                    </Button>
                  ) : null}

                  {updateAvailable && catalogEntry?.entry_type === "desktop_pack" ? (
                    <Button
                      variant="outline"
                      onClick={() => void installCatalogPackMutation.mutateAsync(catalogEntry.entry_id)}
                      disabled={installCatalogPackMutation.isPending || !desktopBridgeAvailable}
                    >
                      {installCatalogPackMutation.isPending && installCatalogPackMutation.variables === catalogEntry.entry_id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Install trusted update
                    </Button>
                  ) : null}
                </div>

                {viewerIsAdmin && connector.advanced.manual_commands.sync ? (
                  <p className="text-xs text-muted-foreground">
                    Manual fallback: <code>{connector.advanced.manual_commands.sync}</code>
                  </p>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {attentionPacks.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">Stored connectors needing attention</h2>
            <p className="text-sm text-muted-foreground">
              These connectors are stored locally, but they cannot be turned on until the reported issue is resolved.
            </p>
          </div>
          <div className="divide-y divide-border/60">
            {attentionPacks.map((pack) => {
              const catalogEntry = findCatalogEntryForPack(catalogEntries, pack);
              return (
                <div key={pack.pluginId} className="space-y-3 py-4 first:pt-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="font-medium">{pack.displayName}</p>
                      <p className="text-sm text-muted-foreground">
                        {packStateLabel(pack)}.{" "}
                        {pack.trustReason ?? pack.compatibilityReason ?? "Review the connector details before trying again."}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{trustLabel(pack.trustClass)}</Badge>
                      <Badge variant="outline">{pack.version}</Badge>
                    </div>
                  </div>
                  {catalogEntry?.support_policy ? (
                    <p className="text-sm text-muted-foreground">
                      {catalogEntry.support_policy.maintainer_support} {catalogEntry.support_policy.update_expectations}
                    </p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => openPackGuide(pack, false)}
                    >
                      Review connector
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => void togglePackMutation.mutateAsync({ pluginId: pack.pluginId, enabled: true })}
                      disabled={
                        togglePackMutation.isPending ||
                        pack.status === "revoked" ||
                        pack.status === "invalid" ||
                        pack.status === "incompatible"
                      }
                    >
                      {togglePackMutation.isPending &&
                      togglePackMutation.variables?.pluginId === pack.pluginId &&
                      togglePackMutation.variables.enabled ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Enable pack
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => void uninstallPackMutation.mutateAsync(pack.pluginId)}
                      disabled={uninstallPackMutation.isPending}
                    >
                      {uninstallPackMutation.isPending && uninstallPackMutation.variables === pack.pluginId ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      Remove pack
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {curatedDesktopPackEntries.length > 0 ? (
        <div className="app-section-divider space-y-4">
          <div className="space-y-1.5">
            <h2 className="font-semibold leading-none tracking-tight">Trusted connectors you can add</h2>
            <p className="text-sm text-muted-foreground">
              Signed optional connectors for this desktop build can be installed directly from this page.
            </p>
          </div>
          <div className="divide-y divide-border/60">
            {curatedDesktopPackEntries.map((entry) => {
              const installedPack = entry.plugin_id
                ? receiptPlugins.find((pack) => pack.pluginId === entry.plugin_id) ?? null
                : null;
              const updateAvailable =
                installedPack !== null &&
                entry.current_version !== null &&
                compareVersions(installedPack.version, entry.current_version) < 0;
              const installLabel = installedPack
                ? updateAvailable
                  ? "Install trusted update"
                  : "Reinstall trusted pack"
                : "Install trusted pack";
              return (
                <div key={entry.entry_id} className="space-y-3 py-4 first:pt-0">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="font-medium">{entry.display_name}</p>
                      <p className="text-sm text-muted-foreground">{entry.summary}</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{trustLabel(entry.trust_class)}</Badge>
                      {entry.current_version ? <Badge variant="outline">{entry.current_version}</Badge> : null}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => void installCatalogPackMutation.mutateAsync(entry.entry_id)}
                      disabled={installCatalogPackMutation.isPending || !desktopBridgeAvailable}
                    >
                      {installCatalogPackMutation.isPending && installCatalogPackMutation.variables === entry.entry_id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : null}
                      {installLabel}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      <Dialog open={packGuideState !== null} onOpenChange={(open) => (!open ? setPackGuideState(null) : undefined)}>
        <DialogContent className="max-w-xl">
          {packGuideState ? (
            <>
              <DialogHeader>
                <DialogTitle>
                  {packGuideState.showEnableAction
                    ? `Before you turn on ${packGuideState.pack.displayName}`
                    : `${packGuideState.pack.displayName}: what to expect`}
                </DialogTitle>
                <DialogDescription>
                  {packGuideState.showEnableAction
                    ? "This quick note explains how the connector behaves before you enable it."
                    : "Use this as a quick reminder for the first import and future reconnects."}
                </DialogDescription>
              </DialogHeader>

              {(() => {
                const guide = connectorGuideForPack(packGuideState.pack, packGuideState.pack.displayName);
                return (
                  <div className="space-y-4">
                    <Alert>
                      <AlertTitle>{guide.headline}</AlertTitle>
                      <AlertDescription>{guide.summary}</AlertDescription>
                    </Alert>

                    <div className="grid gap-3">
                      <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                        <p className="text-sm font-medium text-foreground">Expected speed</p>
                        <p className="mt-1 text-sm text-muted-foreground">{guide.speedDescription}</p>
                      </div>
                      {guide.steps.map((step, index) => (
                        <div
                          key={`${step.title}-${index}`}
                          className="rounded-lg border border-border/60 bg-background/60 p-4"
                        >
                          <p className="text-sm font-medium text-foreground">{step.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{step.description}</p>
                        </div>
                      ))}
                      <div className="rounded-lg border border-border/60 bg-background/60 p-4">
                        <p className="text-sm font-medium text-foreground">Good to know</p>
                        <p className="mt-1 text-sm text-muted-foreground">{guide.caution}</p>
                      </div>
                    </div>

                    {packGuideState.catalogEntry?.support_policy ? (
                      <p className="text-sm text-muted-foreground">
                        {packGuideState.catalogEntry.support_policy.maintainer_support}{" "}
                        {packGuideState.catalogEntry.support_policy.update_expectations}
                      </p>
                    ) : null}
                  </div>
                );
              })()}

              <DialogFooter>
                <Button variant="outline" onClick={() => setPackGuideState(null)}>
                  {packGuideState.showEnableAction ? "Not now" : "Close"}
                </Button>
                {packGuideState.showEnableAction ? (
                  <Button
                    onClick={() => void handleGuidePrimaryAction()}
                    disabled={togglePackMutation.isPending}
                  >
                    {togglePackMutation.isPending &&
                    togglePackMutation.variables?.pluginId === packGuideState.pack.pluginId &&
                    togglePackMutation.variables.enabled ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : null}
                    Enable connector
                  </Button>
                ) : null}
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={setupState !== null} onOpenChange={(open) => (!open ? closeSetup() : undefined)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {setupState?.mode === "configure"
                ? t("pages.connectors.dialog.settingsTitle", { name: setupState.connector.display_name })
                : t("pages.connectors.dialog.setupTitle", { name: setupState?.connector.display_name ?? "connector" })}
            </DialogTitle>
            <DialogDescription>
              {setupState?.mode === "configure"
                ? t("pages.connectors.dialog.settingsDescription")
                : t("pages.connectors.dialog.setupDescription")}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {setupConfigQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("pages.connectors.loadingSettings")}
              </div>
            ) : null}

            {!setupConfigQuery.isLoading && setupDialogFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("pages.connectors.noExtraSettings")}</p>
            ) : null}

            {setupDialogFields.map((field) => (
              <div key={field.key} className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label htmlFor={`connector-field-${field.key}`}>{field.label}</Label>
                  {field.sensitive && field.has_value ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setClearSecretKeys((current) =>
                          current.includes(field.key)
                            ? current.filter((item) => item !== field.key)
                            : [...current, field.key]
                        )
                      }
                      >
                      {clearSecretKeys.includes(field.key)
                        ? t("pages.connectors.keepSavedValue")
                        : t("pages.connectors.clearSavedValue")}
                    </Button>
                  ) : null}
                </div>

                {field.input_kind === "boolean" ? (
                  <div className="flex items-center gap-3 rounded-md border px-3 py-2">
                    <Switch
                      id={`connector-field-${field.key}`}
                      checked={Boolean(setupValues[field.key])}
                      onCheckedChange={(checked) =>
                        setSetupValues((current) => ({ ...current, [field.key]: checked }))
                      }
                    />
                    <span className="text-sm text-muted-foreground">
                      {field.description ?? t("pages.connectors.toggleRuntimeSetting")}
                    </span>
                  </div>
                ) : (
                  <Input
                    id={`connector-field-${field.key}`}
                    type={field.input_kind === "password" ? "password" : field.input_kind}
                    value={typeof setupValues[field.key] === "string" ? String(setupValues[field.key]) : ""}
                    placeholder={field.placeholder ?? ""}
                    onChange={(event) =>
                      setSetupValues((current) => ({ ...current, [field.key]: event.target.value }))
                    }
                  />
                )}

                {field.description ? <p className="text-xs text-muted-foreground">{field.description}</p> : null}
              </div>
            ))}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeSetup}>
              Cancel
            </Button>
            <Button
              onClick={() => void handleSaveSetup()}
              disabled={configMutation.isPending || bootstrapMutation.isPending}
            >
              {configMutation.isPending || bootstrapMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              {setupState?.mode === "configure" ? t("pages.connectors.saveSettings") : t("pages.connectors.saveAndContinue")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
