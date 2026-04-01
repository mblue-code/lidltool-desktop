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
import { formatDateTime } from "@/utils/format";

type SetupState = {
  connector: ConnectorDiscoveryRow;
  mode: "setup" | "reconnect" | "configure";
};

type SetupValues = Record<string, string | boolean>;

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

export function ConnectorsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [setupState, setSetupState] = useState<SetupState | null>(null);
  const [setupValues, setSetupValues] = useState<SetupValues>({});
  const [clearSecretKeys, setClearSecretKeys] = useState<string[]>([]);
  const [feedback, setFeedback] = useState<string | null>(null);

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
      setFeedback(`Setup started for ${sourceId}.`);
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
      setFeedback(full ? `Full sync started for ${sourceId}.` : `Sync started for ${sourceId}.`);
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.startSyncErrorTitle")));
    }
  });

  const reloadMutation = useMutation({
    mutationFn: reloadConnectors,
    onSuccess: async () => {
      setFeedback("Connector registry refreshed.");
      await queryClient.invalidateQueries({ queryKey: ["connectors"] });
      await queryClient.invalidateQueries({ queryKey: ["desktop", "connectors", "context"] });
    },
    onError: (error) => {
      setFeedback(resolveApiErrorMessage(error, t, t("pages.connectors.loadSourceErrorTitle")));
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
  const activePluginSearchPaths = desktopContextQuery.data?.receiptPlugins?.activePluginSearchPaths ?? [];

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

  const inactivePacks = useMemo(
    () =>
      receiptPlugins.filter(
        (pack) => connectorCards.some((item) => item.pack?.pluginId === pack.pluginId) === false
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
      setFeedback(`Saved settings for ${connector.display_name}.`);
    }
    closeSetup();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Connectors"
        description="Use the shared lifecycle model for one-off setup and sync, while pack install and trust management stay in the desktop control center."
      >
        <Button
          variant="outline"
          onClick={() => void reloadMutation.mutateAsync()}
          disabled={reloadMutation.isPending}
        >
          {reloadMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          Refresh
        </Button>
      </PageHeader>

      <Alert>
        <AlertTitle>Desktop pack management stays native</AlertTitle>
        <AlertDescription>
          Install, update, disable, and remove receipt packs in the desktop control center. If you need that surface from the
          full app, use the desktop app menu and choose <strong>Reload control center</strong>.
        </AlertDescription>
      </Alert>

      {desktopContextQuery.data?.releaseMetadata ? (
        <Card>
          <CardContent className="grid gap-4 pt-6 md:grid-cols-3">
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
              <p className="text-xs uppercase text-muted-foreground">Active pack paths</p>
              <p className="font-medium">{activePluginSearchPaths.length}</p>
            </div>
          </CardContent>
        </Card>
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

      <div className="grid gap-4 xl:grid-cols-2">
        {connectorCards.map(({ connector, pack, catalogEntry }) => {
          const updateAvailable =
            pack !== null &&
            catalogEntry?.current_version &&
            compareVersions(pack.version, catalogEntry.current_version) < 0;

          return (
            <Card key={connector.source_id}>
              <CardHeader className="space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <CardTitle className="text-lg">{connector.display_name}</CardTitle>
                    <CardDescription>{connector.ui.description}</CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge>{connectorStatusLabel(connector)}</Badge>
                    <Badge variant="secondary">{trustLabel(pack?.trustClass ?? connector.trust_class)}</Badge>
                    <Badge variant="outline">{connector.maturity_label}</Badge>
                    <Badge variant="outline">{connector.origin_label}</Badge>
                  </div>
                </div>
                {connector.status_detail ? <p className="text-sm text-muted-foreground">{connector.status_detail}</p> : null}
                {updateAvailable ? (
                  <Alert>
                    <AlertTitle>Update available in control center</AlertTitle>
                    <AlertDescription>
                      {connector.display_name} is running {pack.version}, while the catalog entry lists{" "}
                      {catalogEntry?.current_version}. Use the desktop control center to update the stored pack.
                    </AlertDescription>
                  </Alert>
                ) : null}
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-2 text-sm text-muted-foreground">
                  <p>
                    <strong className="text-foreground">Install state:</strong> {connector.install_state}
                  </p>
                  <p>
                    <strong className="text-foreground">Enabled:</strong> {connector.enable_state}
                  </p>
                  <p>
                    <strong className="text-foreground">Config:</strong> {connector.config_state}
                  </p>
                  {connector.last_synced_at ? (
                    <p>
                      <strong className="text-foreground">Last sync:</strong> {formatDateTime(connector.last_synced_at)}
                    </p>
                  ) : null}
                  {connector.last_sync_summary ? (
                    <p>
                      <strong className="text-foreground">Last result:</strong> {connector.last_sync_summary}
                    </p>
                  ) : null}
                  {pack ? (
                    <p>
                      <strong className="text-foreground">Desktop pack:</strong> {packStateLabel(pack)} via{" "}
                      {pack.installedVia === "catalog_url" ? "trusted catalog download" : "manual file import"}.
                    </p>
                  ) : null}
                  {catalogEntry?.support_policy ? (
                    <p>{catalogEntry.support_policy.maintainer_support} {catalogEntry.support_policy.update_expectations}</p>
                  ) : null}
                </div>

                {pack && connector.origin !== "builtin" ? (
                  <Alert>
                    <AlertTitle>Electron-managed connector</AlertTitle>
                    <AlertDescription>
                      This connector is backed by a local receipt pack. Setup, sync, and config work here, but pack
                      install, disable, remove, and trusted updates stay in the desktop control center.
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
                    {connector.actions.primary.kind === "reconnect"
                      ? "Reconnect"
                      : connector.actions.primary.kind === "sync_now"
                        ? "Sync now"
                        : "Set up"}
                  </Button>

                  {connector.supports_sync ? (
                    <Button
                      variant="outline"
                      onClick={() => void syncMutation.mutateAsync({ sourceId: connector.source_id, full: true })}
                      disabled={syncMutation.isPending || connector.enable_state !== "enabled"}
                    >
                      Full sync
                    </Button>
                  ) : null}

                  {viewerIsAdmin &&
                  (connector.actions.operator.configure || connector.config_state !== "not_required") ? (
                    <Button
                      variant="outline"
                      onClick={() => void openSetup(connector, "configure")}
                    >
                      Settings
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

      {inactivePacks.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Stored receipt packs</CardTitle>
            <CardDescription>
              These packs are installed in desktop storage but are not active in the current full-app runtime.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {inactivePacks.map((pack) => {
              const catalogEntry =
                (pack.catalogEntryId
                  ? catalogEntries.find((entry) => entry.entry_id === pack.catalogEntryId)
                  : null) ??
                catalogEntries.find((entry) => entry.plugin_id === pack.pluginId) ??
                null;
              return (
                <div key={pack.pluginId} className="rounded-lg border p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <p className="font-medium">{pack.displayName}</p>
                      <p className="text-sm text-muted-foreground">
                        {packStateLabel(pack)}. {pack.trustReason ?? pack.compatibilityReason ?? "Manage this pack in the control center."}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge variant="secondary">{trustLabel(pack.trustClass)}</Badge>
                      <Badge variant="outline">{pack.version}</Badge>
                    </div>
                  </div>
                  {catalogEntry?.support_policy ? (
                    <p className="mt-3 text-sm text-muted-foreground">
                      {catalogEntry.support_policy.maintainer_support} {catalogEntry.support_policy.update_expectations}
                    </p>
                  ) : null}
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : null}

      <Dialog open={setupState !== null} onOpenChange={(open) => (!open ? closeSetup() : undefined)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>
              {setupState?.mode === "configure"
                ? `Settings for ${setupState.connector.display_name}`
                : `Set up ${setupState?.connector.display_name ?? "connector"}`}
            </DialogTitle>
            <DialogDescription>
              {setupState?.mode === "configure"
                ? "Update saved connector settings for this desktop profile."
                : "Save any required settings, then continue into the connector bootstrap flow."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {setupConfigQuery.isLoading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading connector settings…
              </div>
            ) : null}

            {!setupConfigQuery.isLoading && setupDialogFields.length === 0 ? (
              <p className="text-sm text-muted-foreground">No extra settings are required for this connector.</p>
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
                      {clearSecretKeys.includes(field.key) ? "Keep saved value" : "Clear saved value"}
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
                      {field.description ?? "Toggle this setting for the local connector runtime."}
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
              {setupState?.mode === "configure" ? "Save settings" : "Save and continue"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
