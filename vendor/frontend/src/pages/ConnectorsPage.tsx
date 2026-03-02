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

type ConnectorCatalogEntry = {
  id: string;
  displayName: string;
  status: "live" | "stub";
  connectCommand: string;
  note: string;
};

const CONNECTOR_CATALOG: ConnectorCatalogEntry[] = [
  {
    id: "lidl_plus_de",
    displayName: "Lidl",
    status: "live",
    connectCommand: "lidltool auth bootstrap",
    note: "Live-tested via CLI. This is the production-ready connector today."
  },
  {
    id: "amazon_de",
    displayName: "Amazon",
    status: "stub",
    connectCommand: "lidltool amazon auth bootstrap --domain amazon.de",
    note: "Implemented but not yet fully live-validated end-to-end."
  },
  {
    id: "rewe_de",
    displayName: "REWE",
    status: "stub",
    connectCommand: "lidltool rewe auth bootstrap --domain shop.rewe.de",
    note: "Implemented but currently treated as preview/stub in real usage."
  },
  {
    id: "kaufland_de",
    displayName: "Kaufland",
    status: "stub",
    connectCommand: "lidltool kaufland auth bootstrap --domain www.kaufland.de",
    note: "Implemented but currently treated as preview/stub in real usage."
  },
  {
    id: "dm_de",
    displayName: "dm",
    status: "stub",
    connectCommand: "lidltool dm auth bootstrap --domain www.dm.de",
    note: "Implemented but currently treated as preview/stub in real usage."
  },
  {
    id: "rossmann_de",
    displayName: "Rossmann",
    status: "stub",
    connectCommand: "lidltool rossmann auth bootstrap --domain www.rossmann.de",
    note: "Implemented but currently treated as preview/stub in real usage."
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

function sourceStatusBadge(status: string | undefined): JSX.Element {
  if (!status) {
    return <Badge variant="secondary">not configured</Badge>;
  }
  if (status === "healthy") {
    return <Badge>healthy</Badge>;
  }
  if (status === "connected") {
    return <Badge>connected</Badge>;
  }
  return <Badge variant="secondary">{status}</Badge>;
}

function bootstrapStatusBadge(status: ConnectorBootstrapStatus["status"]): JSX.Element {
  if (status === "running") {
    return <Badge className="bg-blue-500/15 text-blue-700">bootstrap running</Badge>;
  }
  if (status === "succeeded") {
    return <Badge className="bg-emerald-500/15 text-emerald-700">bootstrap succeeded</Badge>;
  }
  if (status === "failed") {
    return <Badge variant="destructive">bootstrap failed</Badge>;
  }
  return <Badge variant="secondary">idle</Badge>;
}

function syncStatusBadge(status: ConnectorSyncStatus["status"]): JSX.Element | null {
  if (status === "idle") return null;
  if (status === "running") {
    return <Badge className="bg-blue-500/15 text-blue-700">syncing…</Badge>;
  }
  if (status === "succeeded") {
    return <Badge className="bg-emerald-500/15 text-emerald-700">sync succeeded</Badge>;
  }
  return <Badge variant="destructive">sync failed</Badge>;
}

function cascadeStateBadge(
  state: ConnectorCascadeStatus["sources"][number]["state"]
): JSX.Element {
  if (state === "completed") {
    return <Badge className="bg-emerald-500/15 text-emerald-700">completed</Badge>;
  }
  if (state === "bootstrapping" || state === "syncing") {
    return <Badge className="bg-blue-500/15 text-blue-700">{state}</Badge>;
  }
  if (state === "bootstrap_failed" || state === "sync_failed") {
    return <Badge variant="destructive">{state}</Badge>;
  }
  if (state === "canceled") {
    return <Badge variant="secondary">canceled</Badge>;
  }
  if (state === "skipped") {
    return <Badge variant="secondary">skipped</Badge>;
  }
  return <Badge variant="secondary">pending</Badge>;
}

export function ConnectorsPage(): JSX.Element {
  const queryClient = useQueryClient();
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
          ? "Guided sync cascade already running."
          : full
            ? `Guided full sync started for ${sourceIds.length} source(s).`
            : `Guided sync started for ${sourceIds.length} source(s).`
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-cascade-status"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const cancelCascadeMutation = useMutation({
    mutationFn: cancelConnectorCascade,
    onSuccess: async (result) => {
      setActionFeedback(result.canceled ? "Guided sync cascade canceled." : "No active cascade to cancel.");
      await queryClient.invalidateQueries({ queryKey: ["connector-cascade-status"] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const retryCascadeMutation = useMutation({
    mutationFn: ({ full }: { full?: boolean }) => retryConnectorCascade(full, true),
    onSuccess: async (result) => {
      setActionFeedback(
        result.reused
          ? "Guided sync cascade already running."
          : "Retry started for failed or remaining sources."
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
          ? `Bootstrap already running for ${sourceId}.`
          : result.remote_login_url
            ? `Bootstrap started for ${sourceId}. Open the remote login window from this card.`
            : `Bootstrap started for ${sourceId}. Complete login in the opened browser window.`
      );
      await queryClient.invalidateQueries({ queryKey: ["connector-bootstrap-status", sourceId] });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
    }
  });

  const cancelBootstrapMutation = useMutation({
    mutationFn: cancelConnectorBootstrap,
    onSuccess: async (_result, sourceId) => {
      setActionFeedback(`Bootstrap canceled for ${sourceId}.`);
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
          ? `Sync already running for ${sourceId}.`
          : full
            ? `Full sync started for ${sourceId}. This may take a few minutes.`
            : `Sync started for ${sourceId}.`
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

  const errorMessage = sourcesQuery.error instanceof Error ? sourcesQuery.error.message : null;
  const cascadeError = cascadeQuery.error instanceof Error ? cascadeQuery.error.message : null;
  const cascadeStartError =
    startCascadeMutation.error instanceof Error ? startCascadeMutation.error.message : null;
  const cascadeCancelError =
    cancelCascadeMutation.error instanceof Error ? cancelCascadeMutation.error.message : null;
  const cascadeRetryError =
    retryCascadeMutation.error instanceof Error ? retryCascadeMutation.error.message : null;
  const bootstrapError = startBootstrapMutation.error instanceof Error ? startBootstrapMutation.error.message : null;
  const cancelError = cancelBootstrapMutation.error instanceof Error ? cancelBootstrapMutation.error.message : null;
  const syncError = syncMutation.error instanceof Error ? syncMutation.error.message : null;

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

  async function copyCommand(command: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(command);
      setCopyFeedback(`Copied: ${command}`);
    } catch {
      setCopyFeedback(`Copy failed. Run manually: ${command}`);
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
          <CardTitle>Connector Setup</CardTitle>
          <CardDescription>
            Start merchant connection from here. Only Lidl is currently live-tested; all other merchants are shown as
            preview connectors so they never block app usability.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle>Usability-safe fallback paths stay available</AlertTitle>
            <AlertDescription>
              Even if preview connectors fail, you can keep using{" "}
              <Link to="/imports/manual" className="underline">
                manual import
              </Link>{" "}
              and{" "}
              <Link to="/imports/ocr" className="underline">
                OCR import
              </Link>{" "}
              without interruption.
            </AlertDescription>
          </Alert>

          {errorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to fetch source status</AlertTitle>
              <AlertDescription>{errorMessage}. Connector setup controls still work.</AlertDescription>
            </Alert>
          ) : null}

          {cascadeError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to load guided sync status</AlertTitle>
              <AlertDescription>{cascadeError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeStartError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to start guided sync</AlertTitle>
              <AlertDescription>{cascadeStartError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeCancelError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to cancel guided sync</AlertTitle>
              <AlertDescription>{cascadeCancelError}</AlertDescription>
            </Alert>
          ) : null}

          {cascadeRetryError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to retry guided sync</AlertTitle>
              <AlertDescription>{cascadeRetryError}</AlertDescription>
            </Alert>
          ) : null}

          {bootstrapError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to start connector bootstrap</AlertTitle>
              <AlertDescription>{bootstrapError}</AlertDescription>
            </Alert>
          ) : null}

          {cancelError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to cancel connector bootstrap</AlertTitle>
              <AlertDescription>{cancelError}</AlertDescription>
            </Alert>
          ) : null}

          {syncError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to start sync</AlertTitle>
              <AlertDescription>{syncError}</AlertDescription>
            </Alert>
          ) : null}

          {copyFeedback ? <p className="text-sm text-muted-foreground">{copyFeedback}</p> : null}
          {actionFeedback ? <p className="text-sm text-muted-foreground">{actionFeedback}</p> : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Guided Sync Cascade</CardTitle>
              <CardDescription>
                Select the retailers you want and run one guided login journey. The backend will do bootstrap and sync
                source-by-source in sequence.
              </CardDescription>
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
                    <Badge variant={cascadeBusy ? "secondary" : "default"}>{cascadeStatus.status}</Badge>
                    {currentCascadeSourceLabel ? (
                      <span className="text-sm text-muted-foreground">
                        Current: {currentCascadeSourceLabel}
                        {cascadeStatus.current_step ? ` (${cascadeStatus.current_step})` : ""}
                      </span>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Completed {cascadeStatus.summary.completed}/{cascadeStatus.summary.total_sources}, failed{" "}
                    {cascadeStatus.summary.failed}, skipped {cascadeStatus.summary.skipped}.
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
                      Starting...
                    </>
                  ) : (
                    <>
                      <Play className="mr-1.5 h-3.5 w-3.5" />
                      Start guided sync
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
                  Start guided full sync
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
                      Canceling...
                    </>
                  ) : (
                    <>
                      <Square className="mr-1.5 h-3.5 w-3.5" />
                      Cancel guided sync
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
                      Retrying...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                      Retry failed/remaining ({retryableSourceCount})
                    </>
                  )}
                </Button>

                {cascadeStatus.remote_login_url && cascadeBusy ? (
                  <Button asChild type="button" variant="outline" size="sm">
                    <a href={cascadeStatus.remote_login_url} target="_blank" rel="noreferrer">
                      Open current login window
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
                        <Badge className="bg-emerald-500/15 text-emerald-700">live-tested</Badge>
                      ) : (
                        <Badge variant="secondary">preview stub</Badge>
                      )}
                      {sourceStatusBadge(source?.status)}
                      {bootstrapStatusBadge(bootstrap.status)}
                      {syncStatusBadge(sync.status)}
                    </div>
                    <CardDescription>{connector.note}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="rounded-md border bg-muted/40 p-3">
                      <p className="mb-1 text-xs text-muted-foreground">CLI command (fallback/manual run):</p>
                      <code className="block whitespace-pre-wrap text-xs">{connector.connectCommand}</code>
                    </div>

                    {bootstrap.status !== "idle" ? (
                      <div className="rounded-md border bg-muted/30 p-3">
                        <p className="mb-2 text-xs text-muted-foreground">Bootstrap output (latest lines)</p>
                        {bootstrap.output_tail.length === 0 ? (
                          <p className="text-xs text-muted-foreground">No output yet.</p>
                        ) : (
                          <pre className="max-h-36 overflow-auto whitespace-pre-wrap text-xs">
                            {bootstrap.output_tail.join("\n")}
                          </pre>
                        )}
                      </div>
                    ) : null}

                    {sync.status !== "idle" ? (
                      <div className="rounded-md border bg-muted/30 p-3">
                        <p className="mb-2 text-xs text-muted-foreground">Sync output (latest lines)</p>
                        {sync.output_tail.length === 0 ? (
                          <p className="text-xs text-muted-foreground">No output yet.</p>
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
                            Starting...
                          </>
                        ) : (
                          <>
                            <Play className="mr-1.5 h-3.5 w-3.5" />
                            Start from frontend
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
                              Stopping...
                            </>
                          ) : (
                            <>
                              <Square className="mr-1.5 h-3.5 w-3.5" />
                              Stop
                            </>
                          )}
                        </Button>
                      ) : null}

                      {remoteLoginUrl && isRunning ? (
                        <Button asChild type="button" variant="outline" size="sm">
                          <a href={remoteLoginUrl} target="_blank" rel="noreferrer">
                            Open remote login
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
                                Syncing…
                              </>
                            ) : (
                              <>
                                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                                Sync now
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
                            Full sync
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
                        Copy command
                      </Button>

                      <Button asChild type="button" variant="secondary" size="sm">
                        <Link to="/sources">
                          Open sources
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
