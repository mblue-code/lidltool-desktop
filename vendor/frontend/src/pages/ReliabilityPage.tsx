import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { reliabilitySloQueryOptions } from "@/app/queries";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime, formatPercent } from "@/utils/format";

const DEFAULT_WINDOW_HOURS = 24;
const DEFAULT_SYNC_P95_TARGET_MS = 2500;
const DEFAULT_ANALYTICS_P95_TARGET_MS = 2000;
const DEFAULT_MIN_SUCCESS_RATE = 0.97;

function parseIntFilter(rawValue: string | null, fallback: number, min = 0): number {
  if (rawValue === null || rawValue.trim() === "") {
    return fallback;
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.max(min, Math.floor(parsed));
}

function parseFloatFilter(rawValue: string | null, fallback: number, min = 0, max = 1): number {
  if (rawValue === null || rawValue.trim() === "") {
    return fallback;
  }
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(max, Math.max(min, parsed));
}

function reliabilityFamilyFromRoute(route: string): "analytics" | "sync" | "other" {
  if (route.startsWith("/api/v1/dashboard")) {
    return "analytics";
  }
  if (route.startsWith("/api/v1/documents")) {
    return "sync";
  }
  return "other";
}

function familyDisplayName(family: string): string {
  if (family === "analytics") {
    return "Analytics";
  }
  if (family === "sync") {
    return "Sync";
  }
  return "Other";
}

function badgeVariantForHealth(isHealthy: boolean): "default" | "secondary" | "destructive" | "outline" {
  if (isHealthy) {
    return "default";
  }
  return "destructive";
}

export function ReliabilityPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const appliedWindowHours = parseIntFilter(searchParams.get("window_hours"), DEFAULT_WINDOW_HOURS, 1);
  const appliedSyncP95TargetMs = parseIntFilter(
    searchParams.get("sync_p95_target_ms"),
    DEFAULT_SYNC_P95_TARGET_MS,
    1
  );
  const appliedAnalyticsP95TargetMs = parseIntFilter(
    searchParams.get("analytics_p95_target_ms"),
    DEFAULT_ANALYTICS_P95_TARGET_MS,
    1
  );
  const appliedMinSuccessRate = parseFloatFilter(
    searchParams.get("min_success_rate"),
    DEFAULT_MIN_SUCCESS_RATE,
    0,
    1
  );

  const [windowHours, setWindowHours] = useState(String(appliedWindowHours));
  const [syncP95TargetMs, setSyncP95TargetMs] = useState(String(appliedSyncP95TargetMs));
  const [analyticsP95TargetMs, setAnalyticsP95TargetMs] = useState(String(appliedAnalyticsP95TargetMs));
  const [minSuccessRate, setMinSuccessRate] = useState(String(appliedMinSuccessRate));

  useEffect(() => {
    setWindowHours(String(appliedWindowHours));
    setSyncP95TargetMs(String(appliedSyncP95TargetMs));
    setAnalyticsP95TargetMs(String(appliedAnalyticsP95TargetMs));
    setMinSuccessRate(String(appliedMinSuccessRate));
  }, [appliedWindowHours, appliedSyncP95TargetMs, appliedAnalyticsP95TargetMs, appliedMinSuccessRate]);

  const { data, error, isPending, isFetching } = useQuery(
    reliabilitySloQueryOptions({
      windowHours: appliedWindowHours,
      syncP95TargetMs: appliedSyncP95TargetMs,
      analyticsP95TargetMs: appliedAnalyticsP95TargetMs,
      minSuccessRate: appliedMinSuccessRate
    })
  );

  const loading = isPending || isFetching;
  const errorMessage = error instanceof Error ? error.message : null;

  const families = useMemo(() => {
    if (!data) {
      return [];
    }
    const order = ["analytics", "sync", "other"];
    return Object.entries(data.families).sort(
      ([left], [right]) => order.indexOf(left) - order.indexOf(right)
    );
  }, [data]);

  function submitFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const next = new URLSearchParams(searchParams);
    next.set("window_hours", String(parseIntFilter(windowHours, DEFAULT_WINDOW_HOURS, 1)));
    next.set("sync_p95_target_ms", String(parseIntFilter(syncP95TargetMs, DEFAULT_SYNC_P95_TARGET_MS, 1)));
    next.set(
      "analytics_p95_target_ms",
      String(parseIntFilter(analyticsP95TargetMs, DEFAULT_ANALYTICS_P95_TARGET_MS, 1))
    );
    next.set(
      "min_success_rate",
      String(parseFloatFilter(minSuccessRate, DEFAULT_MIN_SUCCESS_RATE, 0, 1))
    );
    setSearchParams(next);
  }

  function resetFilters(): void {
    setWindowHours(String(DEFAULT_WINDOW_HOURS));
    setSyncP95TargetMs(String(DEFAULT_SYNC_P95_TARGET_MS));
    setAnalyticsP95TargetMs(String(DEFAULT_ANALYTICS_P95_TARGET_MS));
    setMinSuccessRate(String(DEFAULT_MIN_SUCCESS_RATE));
    const next = new URLSearchParams(searchParams);
    next.delete("window_hours");
    next.delete("sync_p95_target_ms");
    next.delete("analytics_p95_target_ms");
    next.delete("min_success_rate");
    setSearchParams(next);
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <h2 className="text-2xl font-semibold tracking-tight">Reliability Console</h2>
          <p className="text-sm text-muted-foreground">
            Track SLO performance for API endpoint families and inspect per-route health.
          </p>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-5" onSubmit={submitFilters}>
            <div className="space-y-2">
              <Label htmlFor="window-hours">Window (hours)</Label>
              <Input
                id="window-hours"
                type="number"
                min={1}
                step={1}
                value={windowHours}
                onChange={(event) => setWindowHours(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sync-p95-target">Sync p95 target (ms)</Label>
              <Input
                id="sync-p95-target"
                type="number"
                min={1}
                step={1}
                value={syncP95TargetMs}
                onChange={(event) => setSyncP95TargetMs(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="analytics-p95-target">Analytics p95 target (ms)</Label>
              <Input
                id="analytics-p95-target"
                type="number"
                min={1}
                step={1}
                value={analyticsP95TargetMs}
                onChange={(event) => setAnalyticsP95TargetMs(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="min-success-rate">Minimum success rate</Label>
              <Input
                id="min-success-rate"
                type="number"
                min={0}
                max={1}
                step={0.001}
                value={minSuccessRate}
                onChange={(event) => setMinSuccessRate(event.target.value)}
              />
            </div>
            <div className="flex gap-2 self-end">
              <Button type="submit">Apply</Button>
              <Button type="button" variant="outline" onClick={resetFilters}>
                Reset
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load reliability metrics</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        {loading ? (
          <>
            <Skeleton className="h-36 rounded-lg" />
            <Skeleton className="h-36 rounded-lg" />
            <Skeleton className="h-36 rounded-lg" />
          </>
        ) : null}
        {!loading && data ? (
          <>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Generated At</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-lg font-semibold">{formatDateTime(data.generated_at)}</p>
                <p className="text-xs text-muted-foreground">Window: {data.window_hours}h</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Thresholds</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p>Sync p95: {data.thresholds.sync_p95_target_ms}ms</p>
                <p>Analytics p95: {data.thresholds.analytics_p95_target_ms}ms</p>
                <p>Min success: {formatPercent(data.thresholds.min_success_rate)}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-muted-foreground">Endpoints</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-semibold">{data.endpoints.length}</p>
                <p className="text-xs text-muted-foreground">Active routes in selected window</p>
              </CardContent>
            </Card>
          </>
        ) : null}
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {!loading && families.length > 0
          ? families.map(([family, summary]) => (
              <Card key={family}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-base">
                    <span>{familyDisplayName(family)}</span>
                    <Badge variant={badgeVariantForHealth(summary.slo_pass)}>
                      {summary.slo_pass ? "SLO pass" : "SLO fail"}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-sm">
                  <p>Routes: {summary.routes}</p>
                  <p>p95 latency: {summary.p95_duration_ms === null ? "-" : `${summary.p95_duration_ms}ms`}</p>
                  <p>Target p95: {summary.p95_target_ms}ms</p>
                  <p>Avg success: {formatPercent(summary.avg_success_rate)}</p>
                </CardContent>
              </Card>
            ))
          : null}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Endpoint Health</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-sm text-muted-foreground">Loading endpoint metrics...</p> : null}
          {!loading && data && data.endpoints.length === 0 ? (
            <p className="text-sm text-muted-foreground">No endpoint metrics in the selected window.</p>
          ) : null}
          {!loading && data && data.endpoints.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Endpoint</TableHead>
                  <TableHead>Requests</TableHead>
                  <TableHead>Success</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead>p95</TableHead>
                  <TableHead>p99</TableHead>
                  <TableHead>Indicators</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.endpoints.map((endpoint) => {
                  const family = reliabilityFamilyFromRoute(endpoint.route);
                  const p95Target =
                    family === "analytics" ? data.thresholds.analytics_p95_target_ms : data.thresholds.sync_p95_target_ms;
                  const successHealthy = endpoint.success_rate >= data.thresholds.min_success_rate;
                  const latencyHealthy =
                    endpoint.p95_duration_ms === null || endpoint.p95_duration_ms <= p95Target;
                  return (
                    <TableRow key={endpoint.route}>
                      <TableCell className="font-mono text-xs">{endpoint.route}</TableCell>
                      <TableCell>{endpoint.count}</TableCell>
                      <TableCell>{formatPercent(endpoint.success_rate)}</TableCell>
                      <TableCell>{formatPercent(endpoint.error_rate)}</TableCell>
                      <TableCell>{endpoint.p95_duration_ms === null ? "-" : `${endpoint.p95_duration_ms}ms`}</TableCell>
                      <TableCell>{endpoint.p99_duration_ms === null ? "-" : `${endpoint.p99_duration_ms}ms`}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-2">
                          <Badge variant={badgeVariantForHealth(successHealthy)}>
                            Success {successHealthy ? "ok" : "low"}
                          </Badge>
                          <Badge variant={badgeVariantForHealth(latencyHealthy)}>
                            Latency {latencyHealthy ? "ok" : "high"}
                          </Badge>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
