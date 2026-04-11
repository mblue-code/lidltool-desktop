import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { fetchAutomationRules, type AutomationRule } from "@/api/automations";
import {
  deleteOfferSource,
  deleteOfferWatchlist,
  fetchOfferAlerts,
  fetchOfferMatches,
  fetchOfferRefreshRuns,
  fetchOfferSources,
  fetchOffersOverview,
  fetchOfferWatchlists,
  patchOfferAlert,
  postOfferRefresh,
  updateOfferWatchlist,
  type OfferRefreshRun
} from "@/api/offers";
import { fetchAISettings } from "@/api/aiSettings";
import { PageHeader } from "@/components/shared/PageHeader";
import { OfferAgentCard } from "@/components/offers/OfferAgentCard";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { formatDateTime, formatEurFromCents } from "@/utils/format";

export function OffersPage() {
  const queryClient = useQueryClient();
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);

  const overviewQuery = useQuery({
    queryKey: ["offers", "overview"],
    queryFn: fetchOffersOverview
  });
  const aiSettingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });
  const automationRulesQuery = useQuery({
    queryKey: ["automation-rules"],
    queryFn: () => fetchAutomationRules(200, 0)
  });
  const sourcesQuery = useQuery({
    queryKey: ["offers", "sources"],
    queryFn: fetchOfferSources
  });
  const watchlistsQuery = useQuery({
    queryKey: ["offers", "watchlists"],
    queryFn: fetchOfferWatchlists
  });
  const matchesQuery = useQuery({
    queryKey: ["offers", "matches"],
    queryFn: () => fetchOfferMatches(100)
  });
  const alertsQuery = useQuery({
    queryKey: ["offers", "alerts"],
    queryFn: () => fetchOfferAlerts({ limit: 100 })
  });
  const refreshRunsQuery = useQuery({
    queryKey: ["offers", "refresh-runs"],
    queryFn: () => fetchOfferRefreshRuns(10)
  });

  const sources = sourcesQuery.data?.items ?? [];
  const watchlists = watchlistsQuery.data?.items ?? [];
  const matches = matchesQuery.data?.items ?? [];
  const alerts = alertsQuery.data?.items ?? [];
  const refreshRuns = refreshRunsQuery.data?.items ?? [];
  const aiEnabled = aiSettingsQuery.data?.enabled === true;
  const offerRefreshRules = useMemo(
    () => (automationRulesQuery.data?.items ?? []).filter((rule) => rule.rule_type === "offer_refresh"),
    [automationRulesQuery.data?.items]
  );
  const sourceNameById = useMemo(
    () => Object.fromEntries(sources.map((source) => [source.source_id, source.display_name])),
    [sources]
  );
  const currentSourceIds = useMemo(() => new Set(sources.map((source) => source.source_id)), [sources]);
  const latestRelevantRefreshSummary = useMemo(
    () => refreshRuns.find((run) => refreshRunTouchesSources(run, currentSourceIds)) ?? null,
    [currentSourceIds, refreshRuns]
  );
  const latestRunBySourceId = useMemo(() => {
    const entries = new Map<string, { run: OfferRefreshRun; result: OfferRefreshRun["source_results"][number] }>();
    for (const run of refreshRuns) {
      for (const result of run.source_results) {
        if (!currentSourceIds.has(result.source_id) || entries.has(result.source_id)) {
          continue;
        }
        entries.set(result.source_id, { run, result });
      }
    }
    return entries;
  }, [currentSourceIds, refreshRuns]);
  const automationBySourceId = useMemo(() => {
    const entries = new Map<string, AutomationRule>();
    for (const source of sources) {
      const matches = offerRefreshRules.filter((rule) => extractAutomationSourceIds(rule).includes(source.source_id));
      const preferred = pickPreferredAutomation(matches);
      if (preferred) {
        entries.set(source.source_id, preferred);
      }
    }
    return entries;
  }, [offerRefreshRules, sources]);

  useEffect(() => {
    if (sources.length === 0) {
      setSelectedSourceIds((current) => (current.length === 0 ? current : []));
      return;
    }
    setSelectedSourceIds((current) => {
      const valid = current.filter((sourceEntry) =>
        sources.some((source) => source.source_id === sourceEntry)
      );
      if (valid.length > 0) {
        return valid.length === current.length &&
          valid.every((sourceId, index) => sourceId === current[index])
          ? current
          : valid;
      }
      const allSourceIds = sources.map((sourceEntry) => sourceEntry.source_id);
      return allSourceIds.length === current.length &&
        allSourceIds.every((sourceId, index) => sourceId === current[index])
        ? current
        : allSourceIds;
    });
  }, [sources]);

  const refreshMutation = useMutation({
    mutationFn: () =>
      postOfferRefresh({
        source_ids: selectedSourceIds.length === sources.length ? undefined : selectedSourceIds
      }),
    onSuccess: (result) => {
      toast.success(`Offer refresh finished with status: ${result.status}`);
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "sources"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "matches"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "refresh-runs"] })
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Offer refresh failed");
    }
  });

  const toggleWatchlistMutation = useMutation({
    mutationFn: (payload: { id: string; active: boolean }) =>
      updateOfferWatchlist(payload.id, { active: payload.active }),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] })
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to update watchlist");
    }
  });

  const deleteWatchlistMutation = useMutation({
    mutationFn: (watchlistId: string) => deleteOfferWatchlist(watchlistId),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] })
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to delete watchlist");
    }
  });

  const deleteSourceMutation = useMutation({
    mutationFn: (sourceId: string) => deleteOfferSource(sourceId),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "sources"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "matches"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "refresh-runs"] })
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to delete offer source");
    }
  });

  const readAlertMutation = useMutation({
    mutationFn: (alertId: string) => patchOfferAlert(alertId, true),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["offers", "matches"] })
      ]);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to update alert");
    }
  });

  const counts = overviewQuery.data?.counts ?? {
    watchlists: watchlists.length,
    active_matches: matches.length,
    unread_alerts: alerts.filter((alert) => alert.read_at === null).length
  };

  return (
    <section className="space-y-4">
      <PageHeader title="Offer Intelligence" />
      <section className="rounded-xl border border-border/60 app-dashboard-surface grid divide-y md:divide-y-0 md:divide-x divide-border/40 md:grid-cols-4">
        <Metric label="Watchlists" value={counts.watchlists} />
        <Metric label="Active Matches" value={counts.active_matches} />
        <Metric label="Unread Alerts" value={counts.unread_alerts} />
        <Metric
          label="Last Refresh"
          value={latestRelevantRefreshSummary ? latestRelevantRefreshSummary.status.replace(/_/g, " ") : "Never"}
          detail={
            latestRelevantRefreshSummary
              ? formatDateTime(latestRelevantRefreshSummary.finished_at ?? latestRelevantRefreshSummary.started_at)
              : sources.length > 0
                ? "No refresh run yet for current sources"
                : "No refresh run yet"
          }
        />
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Offer Sources</CardTitle>
            <Button
              onClick={() => void refreshMutation.mutateAsync()}
              disabled={!aiEnabled || refreshMutation.isPending || selectedSourceIds.length === 0}
            >
              Refresh selected
            </Button>
          </CardHeader>
          <CardContent className="space-y-4">
            {!aiEnabled ? (
              <Alert variant="destructive">
                <AlertTitle>AI assistant required</AlertTitle>
                <AlertDescription>
                  Connect a capable model in AI Settings before running URL-based offer discovery from this page.
                </AlertDescription>
              </Alert>
            ) : null}
            {sources.length === 0 ? (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                No offer sources yet. Add a merchant offer URL in the assistant card to create the first source.
              </div>
            ) : null}
            <div className="divide-y divide-border/40">
              {sources.map((sourceEntry) => {
                const selected = selectedSourceIds.includes(sourceEntry.source_id);
                const sourceRun = latestRunBySourceId.get(sourceEntry.source_id) ?? null;
                const sourceAutomation = automationBySourceId.get(sourceEntry.source_id) ?? null;
                const sourceErrorSummary = summarizeOfferRefreshError(sourceRun?.result.error ?? null);
                return (
                  <div
                    key={sourceEntry.source_id}
                    className="py-4 first:pt-0 last:pb-0 text-sm"
                  >
                    <div className="flex items-start gap-3">
                      <Checkbox
                        checked={selected}
                        onCheckedChange={(checked) => {
                          setSelectedSourceIds((current) => {
                            if (checked) {
                              return current.includes(sourceEntry.source_id)
                                ? current
                                : [...current, sourceEntry.source_id];
                            }
                            return current.filter((value) => value !== sourceEntry.source_id);
                          });
                        }}
                      />
                      <div className="min-w-0 flex-1 space-y-2">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-medium leading-5">{sourceEntry.display_name}</span>
                              <Badge variant="outline">{sourceEntry.active_offer_count} active</Badge>
                              {sourceAutomation?.enabled ? <Badge variant="secondary">Scheduled</Badge> : null}
                            </div>
                            {sourceEntry.merchant_url ? (
                              <a
                                className="block break-all text-xs leading-5 text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                                href={sourceEntry.merchant_url}
                                rel="noreferrer"
                                target="_blank"
                              >
                                {sourceEntry.merchant_url}
                              </a>
                            ) : (
                              <p className="text-xs text-muted-foreground">No URL stored</p>
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => void deleteSourceMutation.mutateAsync(sourceEntry.source_id)}
                            disabled={deleteSourceMutation.isPending}
                          >
                            Delete
                          </Button>
                        </div>
                        <div className="grid gap-3 lg:grid-cols-2">
                          <div className="min-w-0 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                              Refresh
                            </p>
                            <p className="mt-1 text-sm font-medium text-foreground">
                              {sourceRun ? sourceRun.result.status.replace(/_/g, " ") : "No run yet"}
                            </p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                              {sourceRun
                                ? formatDateTime(sourceRun.run.finished_at ?? sourceRun.run.started_at)
                                : "Not refreshed yet"}
                            </p>
                            {sourceErrorSummary ? (
                              <p className="mt-2 text-xs leading-5 text-destructive break-words">
                                {sourceErrorSummary}
                              </p>
                            ) : null}
                          </div>
                          <div className="min-w-0 rounded-lg border border-border/50 bg-background/40 px-3 py-2">
                            <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                              Schedule
                            </p>
                            <p className="mt-1 text-sm font-medium text-foreground break-words">
                              {sourceAutomation ? sourceAutomation.name : "None"}
                            </p>
                            <p className="mt-1 text-xs leading-5 text-muted-foreground">
                              {sourceAutomation?.next_run_at
                                ? `Next ${formatDateTime(sourceAutomation.next_run_at)}`
                                : sourceAutomation
                                  ? "Waiting for next time"
                                  : "No recurring refresh"}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {latestRelevantRefreshSummary ? (
              <div className="app-section-divider pt-4 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">Latest run</span>
                  <Badge>{latestRelevantRefreshSummary.status}</Badge>
                </div>
                <p className="mt-1 text-muted-foreground">
                  {formatDateTime(
                    latestRelevantRefreshSummary.finished_at ?? latestRelevantRefreshSummary.started_at
                  )}
                </p>
                <div className="mt-3 flex flex-wrap gap-4 text-sm">
                  <StatLine label="Inserted" value={Number(latestRelevantRefreshSummary.totals.inserted ?? 0)} />
                  <StatLine label="Updated" value={Number(latestRelevantRefreshSummary.totals.updated ?? 0)} />
                  <StatLine label="Alerts" value={Number(latestRelevantRefreshSummary.totals.alerts_created ?? 0)} />
                </div>
                {latestRelevantRefreshSummary.error ? (
                  <p className="mt-3 text-xs text-destructive">{latestRelevantRefreshSummary.error}</p>
                ) : null}
              </div>
            ) : sources.length > 0 ? (
              <p className="app-section-divider pt-4 text-sm text-muted-foreground">
                No refresh run has completed for the current offer sources yet.
              </p>
            ) : null}
          </CardContent>
        </Card>

        <OfferAgentCard aiEnabled={aiEnabled} sources={sources} watchlists={watchlists} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Watchlists</CardTitle>
        </CardHeader>
        <CardContent>
          {watchlists.length === 0 ? (
            <p className="text-sm text-muted-foreground">No watchlists yet.</p>
          ) : (
            <div className="divide-y divide-border/40">
            {watchlists.map((watchlist) => (
              <div key={watchlist.id} className="py-3 first:pt-0 last:pb-0 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {watchlist.product_name ?? watchlist.query_text ?? "Untitled watchlist"}
                      </span>
                      <Badge variant={watchlist.active ? "default" : "secondary"}>
                        {watchlist.active ? "Active" : "Paused"}
                      </Badge>
                      {watchlist.source_id ? (
                        <Badge variant="outline">
                          {sourceNameById[watchlist.source_id] ?? watchlist.source_id}
                        </Badge>
                      ) : null}
                    </div>
                    <p className="text-muted-foreground">
                      {watchlist.min_discount_percent !== null
                        ? `Minimum discount ${watchlist.min_discount_percent}%`
                        : "No discount threshold"}
                      {" · "}
                      {watchlist.source_id
                        ? "Watching one source"
                        : "Watching all sources"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        void toggleWatchlistMutation.mutateAsync({
                          id: watchlist.id,
                          active: !watchlist.active
                        })
                      }
                    >
                      {watchlist.active ? "Pause" : "Resume"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void deleteWatchlistMutation.mutateAsync(watchlist.id)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Matched Offers</CardTitle>
          </CardHeader>
          <CardContent>
            {matches.length === 0 ? (
              <p className="text-sm text-muted-foreground">No current matches.</p>
            ) : (
              <div className="divide-y divide-border/40">
              {matches.map((match) => (
                <div key={match.id} className="py-3 first:pt-0 last:pb-0 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{match.offer.item_title ?? match.offer.title}</p>
                      <p className="text-muted-foreground">
                        {match.offer.merchant_name} · valid until {formatDateTime(match.offer.validity_end)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">
                        {match.offer.price_cents !== null ? formatEurFromCents(match.offer.price_cents) : "n/a"}
                      </p>
                      {match.offer.discount_percent !== null ? (
                        <Badge variant="secondary">{match.offer.discount_percent.toFixed(1)}%</Badge>
                      ) : null}
                    </div>
                  </div>
                  {(match.reason.explanations ?? []).length > 0 ? (
                    <ul className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                      {(match.reason.explanations ?? []).map((explanation) => (
                        <li key={explanation}>• {explanation}</li>
                      ))}
                    </ul>
                  ) : null}
                  {match.offer.offer_url ? (
                    <a className="mt-2 inline-block text-xs text-primary underline" href={match.offer.offer_url} target="_blank" rel="noreferrer">
                      Open offer
                    </a>
                  ) : null}
                </div>
              ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Alert Inbox</CardTitle>
          </CardHeader>
          <CardContent>
            {alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No offer alerts yet.</p>
            ) : (
              <div className="divide-y divide-border/40">
              {alerts.map((alert) => (
                <div key={alert.id} className="py-3 first:pt-0 last:pb-0 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-medium">{alert.title}</p>
                      <p className="text-xs text-muted-foreground">{formatDateTime(alert.created_at)}</p>
                    </div>
                    <Badge variant={alert.read_at ? "secondary" : "default"}>
                      {alert.read_at ? "Read" : "Unread"}
                    </Badge>
                  </div>
                  {alert.body ? <p className="mt-1 text-muted-foreground">{alert.body}</p> : null}
                  {(alert.match.reason.explanations ?? []).length > 0 ? (
                    <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                      {(alert.match.reason.explanations ?? []).map((explanation) => (
                        <li key={explanation}>• {explanation}</li>
                      ))}
                    </ul>
                  ) : null}
                  {!alert.read_at ? (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      onClick={() => void readAlertMutation.mutateAsync(alert.id)}
                    >
                      Mark read
                    </Button>
                  ) : null}
                </div>
              ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function refreshRunTouchesSources(run: OfferRefreshRun, sourceIds: Set<string>): boolean {
  return run.source_ids.some((sourceId) => sourceIds.has(sourceId)) ||
    run.source_results.some((result) => sourceIds.has(result.source_id));
}

function extractAutomationSourceIds(rule: AutomationRule): string[] {
  const sourceIds = rule.action_config.source_ids;
  if (!Array.isArray(sourceIds)) {
    return [];
  }
  return sourceIds
    .filter((value): value is string => typeof value === "string")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function pickPreferredAutomation(rules: AutomationRule[]): AutomationRule | null {
  if (rules.length === 0) {
    return null;
  }
  return [...rules].sort((left, right) => {
    if (left.enabled !== right.enabled) {
      return left.enabled ? -1 : 1;
    }
    if (left.next_run_at && right.next_run_at) {
      return left.next_run_at.localeCompare(right.next_run_at);
    }
    if (left.next_run_at) {
      return -1;
    }
    if (right.next_run_at) {
      return 1;
    }
    return right.created_at.localeCompare(left.created_at);
  })[0] ?? null;
}

function summarizeOfferRefreshError(error: string | null | undefined): string | null {
  const normalized = (error ?? "").trim();
  if (!normalized) {
    return null;
  }
  const singleLine = normalized.replace(/\s+/g, " ").trim();
  if (singleLine.includes("BrowserType.launch_persistent_context: Executable doesn't exist")) {
    return "Offer browser is not available in this deployment yet. Rebuild the app image so Playwright browser binaries are installed for the runtime user.";
  }
  if (singleLine.includes("Client error '403 Forbidden'")) {
    return "Merchant page blocked the old direct HTTP fetch with 403. Retry after the browser-backed refresh runtime is available.";
  }
  if (singleLine.includes("For more information check:")) {
    return singleLine.split("For more information check:")[0]?.trim() ?? singleLine;
  }
  return singleLine;
}

function Metric(props: { label: string; value: number | string; detail?: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{props.label}</p>
      <p className="mt-2 text-2xl font-semibold">{props.value}</p>
      {props.detail ? <p className="mt-1 text-xs text-muted-foreground">{props.detail}</p> : null}
    </div>
  );
}

function StatLine(props: { label: string; value: number }) {
  return (
    <div>
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{props.label}</span>
      <span className="ml-1.5 text-sm font-semibold">{props.value}</span>
    </div>
  );
}
