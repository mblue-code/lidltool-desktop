import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink, Loader2, Play, RefreshCw, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  cancelConnectorBootstrap,
  cancelConnectorCascade,
  fetchConnectorBootstrapStatus,
  fetchConnectorCascadeStatus,
  fetchConnectorSyncStatus,
  retryConnectorCascade,
  startConnectorBootstrap,
  startConnectorCascade,
  startConnectorSync,
  type ConnectorBootstrapStatus,
  type ConnectorCascadeStatus,
  type ConnectorSyncStatus
} from "@/api/connectors";
import { fetchSources } from "@/api/sources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { type TranslationKey, useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";

type ConnectorCatalogEntry = {
  id: string;
  displayName: string;
  status: "live" | "stub";
  connectCommand: string;
  noteKey: TranslationKey;
};

const CONNECTOR_CATALOG: ConnectorCatalogEntry[] = [
  {
    id: "lidl_plus_de",
    displayName: "Lidl",
    status: "live",
    connectCommand: "lidltool auth bootstrap",
    noteKey: "pages.connectors.catalog.lidl.note"
  },
  {
    id: "amazon_de",
    displayName: "Amazon",
    status: "stub",
    connectCommand: "lidltool amazon auth bootstrap --domain amazon.de",
    noteKey: "pages.connectors.catalog.amazon.note"
  },
  {
    id: "rewe_de",
    displayName: "REWE",
    status: "stub",
    connectCommand: "lidltool rewe auth bootstrap --domain shop.rewe.de",
    noteKey: "pages.connectors.catalog.rewe.note"
  },
  {
    id: "kaufland_de",
    displayName: "Kaufland",
    status: "stub",
    connectCommand: "lidltool kaufland auth bootstrap --domain www.kaufland.de",
    noteKey: "pages.connectors.catalog.kaufland.note"
  },
  {
    id: "dm_de",
    displayName: "dm",
    status: "stub",
    connectCommand: "lidltool dm auth bootstrap --domain www.dm.de",
    noteKey: "pages.connectors.catalog.dm.note"
  },
  {
    id: "rossmann_de",
    displayName: "Rossmann",
    status: "stub",
    connectCommand: "lidltool rossmann auth bootstrap --domain www.rossmann.de",
    noteKey: "pages.connectors.catalog.rossmann.note"
  }
];

const CASCADE_SELECTION_STORAGE_KEY = "connector-cascade-selected-sources";

const IDLE_BOOTSTRAP: ConnectorBootstrapStatus = {
  source_id: "",
  status: "idle",
  command: null,
  pid: null,
  started_at: null,
  finished_at: null,
  return_code: null,
  output_tail: [],
  can_cancel: false,
  remote_login_url: null
};

const IDLE_SYNC: ConnectorSyncStatus = {
  source_id: "",
  status: "idle",
  command: null,
  pid: null,
  started_at: null,
  finished_at: null,
  return_code: null,
  output_tail: [],
  can_cancel: false
};

const IDLE_CASCADE: ConnectorCascadeStatus = {
  status: "idle",
  source_ids: [],
  full: false,
  started_at: null,
  finished_at: null,
  current_source_id: null,
  current_step: null,
  can_cancel: false,
  remote_login_url: null,
  summary: {
    total_sources: 0,
    completed: 0,
    failed: 0,
    canceled: 0,
    pending: 0,
    skipped: 0
  },
  sources: []
};

export function ConnectorsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>(() => {
    const defaultSelection = ["lidl_plus_de", "rewe_de", "amazon_de"];
    if (typeof window === "undefined") {
      return defaultSelection;
    }
    try {
      const raw = window.localStorage.getItem(CASCADE_SELECTION_STORAGE_KEY);
      if (!raw) {
        return defaultSelection;
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return defaultSelection;
      }
      const validIds = new Set(CONNECTOR_CATALOG.map((connector) => connector.id));
      const filtered = parsed.filter((value): value is string => typeof value === "string" && validIds.has(value));
      return filtered.length > 0 ? filtered : defaultSelection;
    } catch {
      return defaultSelection;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(CASCADE_SELECTION_STORAGE_KEY, JSON.stringify(selectedSourceIds));
    } catch {
      // Ignore storage write failures and keep in-memory selection.
    }
  }, [selectedSourceIds]);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources
  });

  const cascadeQuery = useQuery({
    queryKey: ["connector-cascade-status"],
    queryFn: fetchConnectorCascadeStatus,
    refetchInterval: (query: { state: { data?: ConnectorCascadeStatus } }) => {
      const status = query.state.data?.status;
      return status === "running" || status === "canceling" ? 1500 : false;
    }
  });

  const cascadeStatus = cascadeQuery.data ?? IDLE_CASCADE;
  const cascadeBusy = cascadeStatus.status === "running" || cascadeStatus.status === "canceling";

  const startCascadeMutation = useMutation({
    mutationFn: ({ sourceIds, full }: { sourceIds: string[]; full: boolean }) =>
      startConnectorCascade(sourceIds, full),
    onSuccess: async (result, { sourceIds, full }) => {
      setActionFeedback(
        result.reused
          ? t("pages.connectors.action.guidedAlreadyRunning")
          : full
            ? t("pages.connectors.action.guidedFullStarted", { count: sourceIds.length })
            : t("pages.connectors.action.guidedStarted", { count: sourceIds.length })
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-cascade-status"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const cancelCascadeMutation = useMutation({
    mutationFn: cancelConnectorCascade,
    onSuccess: async (result) => {
      setActionFeedback(
        result.canceled
          ? t("pages.connectors.action.guidedCanceled")
          : t("pages.connectors.action.noActiveCascade")
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-cascade-status"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const retryCascadeMutation = useMutation({
    mutationFn: ({ full }: { full?: boolean }) => retryConnectorCascade(full, true),
    onSuccess: async (result) => {
      setActionFeedback(
        result.reused
          ? t("pages.connectors.action.guidedAlreadyRunning")
          : t("pages.connectors.action.retryStarted")
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-cascade-status"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const bootstrapQueries = useQueries({
    queries: CONNECTOR_CATALOG.map((connector) => ({
      queryKey: ["connector-bootstrap-status", connector.id],
      queryFn: () => fetchConnectorBootstrapStatus(connector.id),
      refetchInterval: (query: { state: { data?: ConnectorBootstrapStatus } }) =>
        query.state.data?.status === "running" ? 2000 : false
    }))
  });

  const startBootstrapMutation = useMutation({
    mutationFn: startConnectorBootstrap,
    onSuccess: async (result, sourceId) => {
      setActionFeedback(
        result.reused
          ? t("pages.connectors.action.bootstrapAlreadyRunning", { sourceId })
          : result.remote_login_url
            ? t("pages.connectors.action.bootstrapStartedRemote", { sourceId })
            : t("pages.connectors.action.bootstrapStartedBrowser", { sourceId })
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-bootstrap-status", sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const cancelBootstrapMutation = useMutation({
    mutationFn: cancelConnectorBootstrap,
    onSuccess: async (_result, sourceId) => {
      setActionFeedback(t("pages.connectors.action.bootstrapCanceled", { sourceId }));
      await queryClient.invalidateQueries({ queryKey: ["connector-bootstrap-status", sourceId] });
    }
  });

  const syncQueries = useQueries({
    queries: CONNECTOR_CATALOG.map((connector) => ({
      queryKey: ["connector-sync-status", connector.id],
      queryFn: () => fetchConnectorSyncStatus(connector.id),
      refetchInterval: (query: { state: { data?: ConnectorSyncStatus } }) =>
        query.state.data?.status === "running" ? 3000 : false
    }))
  });

  const syncMutation = useMutation({
    mutationFn: ({ sourceId, full }: { sourceId: string; full: boolean }) =>
      startConnectorSync(sourceId, full),
    onSuccess: async (result, { sourceId, full }) => {
      setActionFeedback(
        result.reused
          ? t("pages.connectors.action.syncAlreadyRunning", { sourceId })
          : full
            ? t("pages.connectors.action.syncFullStarted", { sourceId })
            : t("pages.connectors.action.syncStarted", { sourceId })
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-sync-status", sourceId] });
    },
    onSettled: async (_data, _error, { sourceId }) => {
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      await queryClient.invalidateQueries({ queryKey: ["connector-sync-status", sourceId] });
    }
  });

  const sourceById = new Map((sourcesQuery.data?.sources ?? []).map((source) => [source.id, source]));
  const connectorById = new Map(CONNECTOR_CATALOG.map((connector) => [connector.id, connector]));

  const bootstrapById = useMemo(
    () =>
      new Map(
        CONNECTOR_CATALOG.map((connector, index) => [
          connector.id,
          bootstrapQueries[index]?.data ?? { ...IDLE_BOOTSTRAP, source_id: connector.id }
        ])
      ),
    [bootstrapQueries]
  );

  const syncById = useMemo(
    () =>
      new Map(
        CONNECTOR_CATALOG.map((connector, index) => [
          connector.id,
          syncQueries[index]?.data ?? { ...IDLE_SYNC, source_id: connector.id }
        ])
      ),
    [syncQueries]
  );

  const errorMessage = sourcesQuery.error
    ? resolveApiErrorMessage(sourcesQuery.error, t, t("pages.connectors.loadSourceErrorTitle"))
    : null;
  const cascadeError = cascadeQuery.error
    ? resolveApiErrorMessage(cascadeQuery.error, t, t("pages.connectors.loadCascadeErrorTitle"))
    : null;
  const cascadeStartError = startCascadeMutation.error
    ? resolveApiErrorMessage(startCascadeMutation.error, t, t("pages.connectors.startCascadeErrorTitle"))
    : null;
  const cascadeCancelError = cancelCascadeMutation.error
    ? resolveApiErrorMessage(cancelCascadeMutation.error, t, t("pages.connectors.cancelCascadeErrorTitle"))
    : null;
  const cascadeRetryError = retryCascadeMutation.error
    ? resolveApiErrorMessage(retryCascadeMutation.error, t, t("pages.connectors.retryCascadeErrorTitle"))
    : null;
  const bootstrapError = startBootstrapMutation.error
    ? resolveApiErrorMessage(startBootstrapMutation.error, t, t("pages.connectors.startBootstrapErrorTitle"))
    : null;
  const cancelError = cancelBootstrapMutation.error
    ? resolveApiErrorMessage(cancelBootstrapMutation.error, t, t("pages.connectors.cancelBootstrapErrorTitle"))
    : null;
  const syncError = syncMutation.error
    ? resolveApiErrorMessage(syncMutation.error, t, t("pages.connectors.startSyncErrorTitle"))
    : null;

  const selectedSourcesInOrder = CONNECTOR_CATALOG.filter((connector) =>
    selectedSourceIds.includes(connector.id)
  ).map((connector) => connector.id);

  const currentCascadeSourceLabel = cascadeStatus.current_source_id
    ? connectorById.get(cascadeStatus.current_source_id)?.displayName ?? cascadeStatus.current_source_id
    : null;
  const retryableSourceCount = cascadeStatus.sources.filter((sourceState) =>
    ["bootstrap_failed", "sync_failed", "canceled", "skipped", "pending"].includes(sourceState.state)
  ).length;
  const cascadeTerminal = ["completed", "partial_success", "failed", "canceled"].includes(
    cascadeStatus.status
  );

  const sourceStatusBadge = (status: string | undefined): JSX.Element => {
    if (!status) {
      return <Badge variant="secondary">{t("pages.connectors.sourceStatus.notConfigured")}</Badge>;
    }
    if (status === "healthy") {
      return <Badge>{t("pages.connectors.sourceStatus.healthy")}</Badge>;
    }
    if (status === "connected") {
      return <Badge>{t("pages.connectors.sourceStatus.connected")}</Badge>;
    }
    return <Badge variant="secondary">{status}</Badge>;
  };

  const bootstrapStatusBadge = (status: ConnectorBootstrapStatus["status"]): JSX.Element => {
    if (status === "running") {
      return <Badge className="bg-blue-500/15 text-blue-700">{t("pages.connectors.bootstrapStatus.running")}</Badge>;
    }
    if (status === "succeeded") {
      return (
        <Badge className="bg-emerald-500/15 text-emerald-700">
          {t("pages.connectors.bootstrapStatus.succeeded")}
        </Badge>
      );
    }
    if (status === "failed") {
      return <Badge variant="destructive">{t("pages.connectors.bootstrapStatus.failed")}</Badge>;
    }
    return <Badge variant="secondary">{t("common.idle")}</Badge>;
  };

  const syncStatusBadge = (status: ConnectorSyncStatus["status"]): JSX.Element | null => {
    if (status === "idle") return null;
    if (status === "running") {
      return <Badge className="bg-blue-500/15 text-blue-700">{t("pages.connectors.syncStatus.running")}</Badge>;
    }
    if (status === "succeeded") {
      return (
        <Badge className="bg-emerald-500/15 text-emerald-700">{t("pages.connectors.syncStatus.succeeded")}</Badge>
      );
    }
    return <Badge variant="destructive">{t("pages.connectors.syncStatus.failed")}</Badge>;
  };

  const cascadeStateBadge = (state: ConnectorCascadeStatus["sources"][number]["state"]): JSX.Element => {
    if (state === "completed") {
      return <Badge className="bg-emerald-500/15 text-emerald-700">{t("pages.connectors.cascadeState.completed")}</Badge>;
    }
    if (state === "bootstrapping") {
      return <Badge className="bg-blue-500/15 text-blue-700">{t("pages.connectors.cascadeState.bootstrapping")}</Badge>;
    }
    if (state === "syncing") {
      return <Badge className="bg-blue-500/15 text-blue-700">{t("pages.connectors.cascadeState.syncing")}</Badge>;
    }
    if (state === "bootstrap_failed") {
      return <Badge variant="destructive">{t("pages.connectors.cascadeState.bootstrapFailed")}</Badge>;
    }
    if (state === "sync_failed") {
      return <Badge variant="destructive">{t("pages.connectors.cascadeState.syncFailed")}</Badge>;
    }
    if (state === "canceled") {
      return <Badge variant="secondary">{t("pages.connectors.cascadeState.canceled")}</Badge>;
    }
    if (state === "skipped") {
      return <Badge variant="secondary">{t("pages.connectors.cascadeState.skipped")}</Badge>;
    }
    return <Badge variant="secondary">{t("pages.connectors.cascadeState.pending")}</Badge>;
  };

  const cascadeStatusLabel = (status: ConnectorCascadeStatus["status"]): string => {
    switch (status) {
      case "running":
        return t("pages.connectors.cascadeStatus.running");
      case "canceling":
        return t("pages.connectors.cascadeStatus.canceling");
      case "completed":
        return t("pages.connectors.cascadeStatus.completed");
      case "partial_success":
        return t("pages.connectors.cascadeStatus.partialSuccess");
      case "failed":
        return t("pages.connectors.cascadeStatus.failed");
      case "canceled":
        return t("pages.connectors.cascadeStatus.canceled");
      default:
        return status;
    }
  };

  async function copyCommand(command: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(command);
      setCopyFeedback(t("pages.connectors.copyFeedbackSuccess", { command }));
    } catch {
      setCopyFeedback(t("pages.connectors.copyFeedbackFailed", { command }));
    }
  }

  function toggleSourceSelection(sourceId: string, checked: boolean): void {
    setSelectedSourceIds((current) => {
      if (checked) {
        return current.includes(sourceId) ? current : [...current, sourceId];
      }
      return current.filter((id) => id !== sourceId);
    });
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("pages.connectors.title")}</CardTitle>
          <CardDescription>{t("pages.connectors.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle>{t("pages.connectors.fallbackTitle")}</AlertTitle>
            <AlertDescription>
              <span>
                {t("pages.connectors.fallback.beforeManual")}{" "}
                <Link to="/imports/manual" className="underline">
                  {t("nav.item.manualImport")}
                </Link>{" "}
                {t("pages.connectors.fallback.between")}{" "}
                <Link to="/imports/ocr" className="underline">
                  {t("nav.item.ocrImport")}
                </Link>{" "}
                {t("pages.connectors.fallback.afterOcr")}
              </span>
            </AlertDescription>
          </Alert>

          {errorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.loadSourceErrorTitle")}</AlertTitle>
              <AlertDescription>
                {errorMessage}. {t("pages.connectors.loadSourceErrorDescription")}
              </AlertDescription>
            </Alert>
          ) : null}

          {cascadeError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.loadCascadeErrorTitle")}</AlertTitle>
              <AlertDescription>{cascadeError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeStartError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.startCascadeErrorTitle")}</AlertTitle>
              <AlertDescription>{cascadeStartError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeCancelError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.cancelCascadeErrorTitle")}</AlertTitle>
              <AlertDescription>{cascadeCancelError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeRetryError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.retryCascadeErrorTitle")}</AlertTitle>
              <AlertDescription>{cascadeRetryError}</AlertDescription>
            </Alert>
          ) : null}

          {bootstrapError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.startBootstrapErrorTitle")}</AlertTitle>
              <AlertDescription>{bootstrapError}</AlertDescription>
            </Alert>
          ) : null}

          {cancelError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.cancelBootstrapErrorTitle")}</AlertTitle>
              <AlertDescription>{cancelError}</AlertDescription>
            </Alert>
          ) : null}

          {syncError ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.connectors.startSyncErrorTitle")}</AlertTitle>
              <AlertDescription>{syncError}</AlertDescription>
            </Alert>
          ) : null}

          {copyFeedback ? <p className="text-sm text-muted-foreground">{copyFeedback}</p> : null}
          {actionFeedback ? <p className="text-sm text-muted-foreground">{actionFeedback}</p> : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("pages.connectors.guidedTitle")}</CardTitle>
              <CardDescription>{t("pages.connectors.guidedDescription")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 md:grid-cols-3">
                {CONNECTOR_CATALOG.map((connector) => (
                  <label key={connector.id} className="flex items-center gap-2 rounded-md border p-2 text-sm">
                    <Checkbox
                      checked={selectedSourceIds.includes(connector.id)}
                      disabled={cascadeBusy || startCascadeMutation.isPending}
                      onCheckedChange={(checked) =>
                        toggleSourceSelection(connector.id, checked === true)
                      }
                    />
                    <span>{connector.displayName}</span>
                  </label>
                ))}
              </div>

              {cascadeStatus.status !== "idle" ? (
                <div className="space-y-2 rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={cascadeBusy ? "secondary" : "default"}>
                      {cascadeStatusLabel(cascadeStatus.status)}
                    </Badge>
                    {currentCascadeSourceLabel ? (
                      <span className="text-sm text-muted-foreground">
                        {t("pages.connectors.currentSource", {
                          label: currentCascadeSourceLabel,
                          step: cascadeStatus.current_step
                            ? ` (${t(`pages.connectors.currentStep.${cascadeStatus.current_step}` as TranslationKey)})`
                            : ""
                        })}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {t("pages.connectors.summary", {
                      completed: cascadeStatus.summary.completed,
                      total: cascadeStatus.summary.total_sources,
                      failed: cascadeStatus.summary.failed,
                      skipped: cascadeStatus.summary.skipped
                    })}
                  </p>
                  {cascadeStatus.sources.length > 0 ? (
                    <div className="space-y-2">
                      {cascadeStatus.sources.map((sourceState) => {
                        const label = connectorById.get(sourceState.source_id)?.displayName ?? sourceState.source_id;
                        const outputTail =
                          sourceState.state === "bootstrapping"
                            ? sourceState.bootstrap?.output_tail
                            : sourceState.state === "syncing"
                              ? sourceState.sync?.output_tail
                              : undefined;
                        return (
                          <div key={sourceState.source_id} className="rounded-md border bg-muted/20 p-2">
                            <div className="mb-1 flex items-center justify-between gap-2">
                              <span className="text-sm font-medium">{label}</span>
                              {cascadeStateBadge(sourceState.state)}
                            </div>
                            {sourceState.error ? (
                              <p className="text-xs text-destructive">{sourceState.error}</p>
                            ) : null}
                            {outputTail && outputTail.length > 0 ? (
                              <pre className="mt-1 max-h-20 overflow-auto whitespace-pre-wrap text-xs">
                                {outputTail.join("\n")}
                              </pre>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() =>
                    startCascadeMutation.mutate({
                      sourceIds: selectedSourcesInOrder,
                      full: false
                    })
                  }
                      disabled={
                        cascadeBusy || startCascadeMutation.isPending || selectedSourcesInOrder.length === 0
                      }
                    >
                      {startCascadeMutation.isPending ? (
                        <>
                          <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                          {t("pages.connectors.starting")}
                        </>
                      ) : (
                        <>
                          <Play className="mr-1.5 h-3.5 w-3.5" />
                          {t("pages.connectors.startGuidedSync")}
                        </>
                      )}
                    </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    startCascadeMutation.mutate({
                      sourceIds: selectedSourcesInOrder,
                      full: true
                    })
                  }
                  disabled={
                    cascadeBusy || startCascadeMutation.isPending || selectedSourcesInOrder.length === 0
                  }
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  {t("pages.connectors.startGuidedFullSync")}
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => cancelCascadeMutation.mutate()}
                  disabled={!cascadeBusy || cancelCascadeMutation.isPending}
                >
                  {cancelCascadeMutation.isPending ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      {t("pages.connectors.canceling")}
                    </>
                  ) : (
                    <>
                      <Square className="mr-1.5 h-3.5 w-3.5" />
                      {t("pages.connectors.cancelGuidedSync")}
                    </>
                  )}
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => retryCascadeMutation.mutate({ full: cascadeStatus.full })}
                  disabled={
                    cascadeBusy
                    || retryCascadeMutation.isPending
                    || !cascadeTerminal
                    || retryableSourceCount === 0
                  }
                >
                  {retryCascadeMutation.isPending ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      {t("pages.connectors.retrying")}
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                      {t("pages.connectors.retryFailedRemaining", { count: retryableSourceCount })}
                    </>
                  )}
                </Button>

                {cascadeStatus.remote_login_url && cascadeBusy ? (
                  <Button asChild type="button" variant="outline" size="sm">
                    <a href={cascadeStatus.remote_login_url} target="_blank" rel="noreferrer">
                      {t("pages.connectors.openCurrentLogin")}
                      <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                    </a>
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-3 md:grid-cols-2">
            {CONNECTOR_CATALOG.map((connector) => {
              const source = sourceById.get(connector.id);
              const bootstrap = bootstrapById.get(connector.id) ?? { ...IDLE_BOOTSTRAP, source_id: connector.id };
              const sync = syncById.get(connector.id) ?? { ...IDLE_SYNC, source_id: connector.id };
              const isRunning = bootstrap.status === "running";
              const isSyncing = sync.status === "running";
              const remoteLoginUrl = bootstrap.remote_login_url ?? null;
              const isStartPending =
                startBootstrapMutation.isPending && startBootstrapMutation.variables === connector.id;
              const isCancelPending =
                cancelBootstrapMutation.isPending && cancelBootstrapMutation.variables === connector.id;
              const isSyncPending = syncMutation.isPending && syncMutation.variables?.sourceId === connector.id;
              const canSync = bootstrap.status === "succeeded" || source !== undefined;

              return (
                <Card key={connector.id}>
                  <CardHeader className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle className="text-base">{connector.displayName}</CardTitle>
                      {connector.status === "live" ? (
                        <Badge className="bg-emerald-500/15 text-emerald-700">
                          {t("pages.connectors.connector.liveTested")}
                        </Badge>
                      ) : (
                        <Badge variant="secondary">{t("pages.connectors.connector.previewStub")}</Badge>
                      )}
                      {sourceStatusBadge(source?.status)}
                      {bootstrapStatusBadge(bootstrap.status)}
                      {syncStatusBadge(sync.status)}
                    </div>
                    <CardDescription>{t(connector.noteKey)}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="rounded-md border bg-muted/40 p-3">
                      <p className="mb-1 text-xs text-muted-foreground">{t("pages.connectors.cliCommandLabel")}</p>
                      <code className="block whitespace-pre-wrap text-xs">{connector.connectCommand}</code>
                    </div>

                    {bootstrap.status !== "idle" ? (
                      <div className="rounded-md border bg-muted/30 p-3">
                        <p className="mb-2 text-xs text-muted-foreground">{t("pages.connectors.bootstrapOutputLabel")}</p>
                        {bootstrap.output_tail.length === 0 ? (
                          <p className="text-xs text-muted-foreground">{t("pages.connectors.noOutputYet")}</p>
                        ) : (
                          <pre className="max-h-36 overflow-auto whitespace-pre-wrap text-xs">
                            {bootstrap.output_tail.join("\n")}
                          </pre>
                        )}
                      </div>
                    ) : null}

                    {sync.status !== "idle" ? (
                      <div className="rounded-md border bg-muted/30 p-3">
                        <p className="mb-2 text-xs text-muted-foreground">{t("pages.connectors.syncOutputLabel")}</p>
                        {sync.output_tail.length === 0 ? (
                          <p className="text-xs text-muted-foreground">{t("pages.connectors.noOutputYet")}</p>
                        ) : (
                          <pre className="max-h-36 overflow-auto whitespace-pre-wrap text-xs">
                            {sync.output_tail.join("\n")}
                          </pre>
                        )}
                      </div>
                    ) : null}

                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => startBootstrapMutation.mutate(connector.id)}
                        disabled={isRunning || isStartPending || isCancelPending || cascadeBusy}
                      >
                        {isStartPending ? (
                          <>
                            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                            {t("pages.connectors.starting")}
                          </>
                        ) : (
                          <>
                            <Play className="mr-1.5 h-3.5 w-3.5" />
                            {t("pages.connectors.startFromFrontend")}
                          </>
                        )}
                      </Button>

                      {isRunning ? (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => cancelBootstrapMutation.mutate(connector.id)}
                          disabled={isCancelPending || cascadeBusy}
                        >
                          {isCancelPending ? (
                            <>
                              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                              {t("pages.connectors.stopping")}
                            </>
                          ) : (
                            <>
                              <Square className="mr-1.5 h-3.5 w-3.5" />
                              {t("pages.connectors.stop")}
                            </>
                          )}
                        </Button>
                      ) : null}

                      {remoteLoginUrl && isRunning ? (
                        <Button asChild type="button" variant="outline" size="sm">
                          <a href={remoteLoginUrl} target="_blank" rel="noreferrer">
                            {t("pages.connectors.openRemoteLogin")}
                            <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                          </a>
                        </Button>
                      ) : null}

                      {canSync ? (
                        <>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => syncMutation.mutate({ sourceId: connector.id, full: false })}
                            disabled={isSyncing || isSyncPending || cascadeBusy}
                          >
                            {isSyncPending || isSyncing ? (
                              <>
                                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                                {t("pages.connectors.syncing")}
                              </>
                            ) : (
                              <>
                                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                                {t("pages.connectors.syncNow")}
                              </>
                            )}
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => syncMutation.mutate({ sourceId: connector.id, full: true })}
                            disabled={isSyncing || isSyncPending || cascadeBusy}
                          >
                            <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                            {t("pages.connectors.fullSync")}
                          </Button>
                        </>
                      ) : null}

                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void copyCommand(connector.connectCommand)}
                      >
                        <Copy className="mr-1.5 h-3.5 w-3.5" />
                        {t("pages.connectors.copyCommand")}
                      </Button>

                      <Button asChild type="button" variant="secondary" size="sm">
                        <Link to="/sources">
                          {t("pages.connectors.openSources")}
                          <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
