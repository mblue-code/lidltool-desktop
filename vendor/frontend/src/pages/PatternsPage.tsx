import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toPng } from "html-to-image";
import { useNavigate } from "react-router-dom";

import {
  fetchHourHeatmap,
  fetchPatterns,
  fetchPriceIndex,
  fetchTimingMatrix,
  fetchWeekdayHeatmap,
  type HeatmapResponse,
  type HourHeatmapResponse,
  type TimingMatrixResponse,
  type TimingValueMode
} from "@/api/analytics";
import { fetchSources } from "@/api/sources";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeader } from "@/components/shared/PageHeader";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";
import { formatEurFromCents } from "@/utils/format";

type TimingView = "yearly" | "hourly" | "matrix";

type SourceOption = {
  kind: string;
  label: string;
};

const ALL_SOURCES_VALUE = "__all_sources__";
const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

type TimingDrilldownSelection = {
  weekday?: number;
  hour?: number;
};

type TimingCsvContext = {
  view: TimingView;
  sourceLabel: string;
  valueMode: TimingValueMode;
  fromDate?: string;
  toDate?: string;
  tzOffsetMinutes: number;
};

function toDateInputValue(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateDaysAgo(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() - days);
  return toDateInputValue(value);
}

function intensityClass(value: number, maxValue: number): string {
  if (maxValue <= 0 || value <= 0) {
    return "bg-muted";
  }
  const ratio = value / maxValue;
  if (ratio > 0.75) {
    return "bg-primary";
  }
  if (ratio > 0.5) {
    return "bg-primary/70";
  }
  if (ratio > 0.25) {
    return "bg-primary/45";
  }
  return "bg-primary/25";
}

function formatTimingMetric(
  mode: TimingValueMode,
  point: { value_cents: number; count: number }
): string {
  if (mode === "count") {
    return `${point.count} orders`;
  }
  return formatEurFromCents(point.value_cents);
}

function csvEscape(value: string): string {
  if (!value.includes(",") && !value.includes('"') && !value.includes("\n")) {
    return value;
  }
  return `"${value.replace(/"/g, '""')}"`;
}

function downloadBlob(filename: string, type: string, content: string): boolean {
  if (typeof URL.createObjectURL !== "function") {
    return false;
  }
  const blob = new Blob([content], { type });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(href);
  return true;
}

function downloadDataUrl(filename: string, dataUrl: string): boolean {
  const anchor = document.createElement("a");
  anchor.href = dataUrl;
  anchor.download = filename;
  anchor.click();
  return true;
}

function buildTimingCsvRows(
  view: TimingView,
  data: HeatmapResponse | HourHeatmapResponse | TimingMatrixResponse
): string[] {
  if (view === "yearly") {
    const yearly = data as HeatmapResponse;
    return [
      "date,weekday,week,value_cents,count,value",
      ...yearly.points.map((point) =>
        [
          point.date,
          String(point.weekday),
          String(point.week),
          String(point.value_cents),
          String(point.count),
          String(point.value)
        ].join(",")
      )
    ];
  }
  if (view === "hourly") {
    const hourly = data as HourHeatmapResponse;
    return [
      "hour,value_cents,count,value",
      ...hourly.points.map((point) =>
        [String(point.hour), String(point.value_cents), String(point.count), String(point.value)].join(",")
      )
    ];
  }
  const matrix = data as TimingMatrixResponse;
  return [
    "weekday,hour,value_cents,count,value",
    ...matrix.grid.map((cell) =>
      [String(cell.weekday), String(cell.hour), String(cell.value_cents), String(cell.count), String(cell.value)].join(",")
    )
  ];
}

function buildTimingCsv(
  context: TimingCsvContext,
  data: HeatmapResponse | HourHeatmapResponse | TimingMatrixResponse
): string {
  const metadataLine = [
    "meta",
    csvEscape(`view=${context.view}`),
    csvEscape(`source=${context.sourceLabel}`),
    csvEscape(`metric=${context.valueMode}`),
    csvEscape(`date_from=${context.fromDate ?? ""}`),
    csvEscape(`date_to=${context.toDate ?? ""}`),
    csvEscape(`tz_offset_minutes=${context.tzOffsetMinutes}`)
  ].join(",");
  return [metadataLine, ...buildTimingCsvRows(context.view, data)].join("\n");
}

function buildTimingFilenameBase(context: TimingCsvContext): string {
  const safeView = context.view.replace(/[^a-z0-9_-]/gi, "_");
  const safeSource = context.sourceLabel.replace(/[^a-z0-9_-]/gi, "_").toLowerCase();
  const fromPart = context.fromDate ?? "open";
  const toPart = context.toDate ?? "open";
  return `timing_${safeView}_${safeSource}_${fromPart}_${toPart}`;
}

function HeatmapLegend({ maxValue, metricLabel }: { maxValue: number; metricLabel: string }) {
  const mid = Math.round(maxValue / 2);
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground" aria-label={`Legend for ${metricLabel}`}>
      <span>{metricLabel}</span>
      <div className="flex items-center gap-1">
        <span className="text-xs">0</span>
        <span className="h-3 w-3 rounded-sm bg-muted" />
        <span className="h-3 w-3 rounded-sm bg-primary/25" />
        <span className="h-3 w-3 rounded-sm bg-primary/45" />
        <span className="text-xs">{mid.toLocaleString()}</span>
        <span className="h-3 w-3 rounded-sm bg-primary/70" />
        <span className="h-3 w-3 rounded-sm bg-primary" />
        <span className="text-xs">{maxValue.toLocaleString()}+</span>
      </div>
    </div>
  );
}

function YearlyHeatmapPanel({
  data,
  sourceLabel,
  onCellClick
}: {
  data: HeatmapResponse;
  sourceLabel: string;
  onCellClick: (selection: TimingDrilldownSelection) => void;
}) {
  const maxValue = Math.max(...data.points.map((point) => point.value), 0);
  if (maxValue <= 0) {
    return <p className="text-sm text-muted-foreground">No timing data for this date range.</p>;
  }

  const byWeek = new Map<string, { week: number; values: Map<number, HeatmapResponse["points"][number]> }>();
  for (const point of data.points) {
    const key = `${point.date.slice(0, 4)}-W${String(point.week).padStart(2, "0")}`;
    const existing = byWeek.get(key) ?? { week: point.week, values: new Map() };
    existing.values.set(point.weekday, point);
    byWeek.set(key, existing);
  }
  const sortedRows = Array.from(byWeek.entries()).sort(([left], [right]) => left.localeCompare(right));

  return (
    <div className="space-y-3">
      <HeatmapLegend maxValue={maxValue} metricLabel="Lower activity to higher activity" />
      <div className="space-y-1 overflow-x-auto">
        {sortedRows.map(([weekKey, row]) => (
          <div key={weekKey} className="flex items-center gap-1">
            <span className="w-12 text-xs text-muted-foreground">{weekKey}</span>
            {Array.from({ length: 7 }, (_, weekday) => {
              const point = row.values.get(weekday);
              const value = point?.value ?? 0;
              const count = point?.count ?? 0;
              const valueCents = point?.value_cents ?? 0;
              return (
                <button
                  key={`${weekKey}-${weekday}`}
                  type="button"
                  className={cn("h-4 w-4 rounded-sm border-0 p-0", intensityClass(value, maxValue))}
                  aria-label={`${sourceLabel} ${WEEKDAY_LABELS[weekday]} value ${value} count ${count}`}
                  title={`${sourceLabel} • ${point?.date ?? "n/a"} • ${WEEKDAY_LABELS[weekday]} • ${formatTimingMetric(data.value, {
                    value_cents: valueCents,
                    count
                  })} • ${count} order(s) • Click to open matching transactions`}
                  onClick={() => onCellClick({ weekday })}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function HourlyHeatmapPanel({
  data,
  sourceLabel,
  onBarClick
}: {
  data: HourHeatmapResponse;
  sourceLabel: string;
  onBarClick: (selection: TimingDrilldownSelection) => void;
}) {
  const maxValue = Math.max(...data.points.map((point) => point.value), 0);
  if (maxValue <= 0) {
    return <p className="text-sm text-muted-foreground">No timing data for this date range.</p>;
  }

  return (
    <div className="space-y-3">
      <HeatmapLegend maxValue={maxValue} metricLabel="Lower activity to higher activity" />
      <div className="overflow-x-auto pb-1">
        <div className="grid min-w-[38rem] gap-1" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
          {data.points.map((point) => (
            <button
              key={point.hour}
              type="button"
              className={cn("h-8 rounded-sm border-0 p-0", intensityClass(point.value, maxValue))}
              aria-label={`${sourceLabel} hour ${point.hour} value ${point.value} count ${point.count}`}
              title={`${sourceLabel} • ${String(point.hour).padStart(2, "0")}:00 • ${formatTimingMetric(data.value, point)} • ${point.count} order(s) • Click to open matching transactions`}
              onClick={() => onBarClick({ hour: point.hour })}
            />
          ))}
        </div>
        <div className="mt-1 grid min-w-[38rem] text-xs text-muted-foreground" style={{ gridTemplateColumns: "repeat(24, minmax(0, 1fr))" }}>
          {data.points.map((point) => (
            <span key={`label-${point.hour}`} className="text-center">
              {point.hour % 3 === 0 ? String(point.hour).padStart(2, "0") : ""}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function TimingMatrixPanel({
  data,
  sourceLabel,
  onCellClick
}: {
  data: TimingMatrixResponse;
  sourceLabel: string;
  onCellClick: (selection: TimingDrilldownSelection) => void;
}) {
  const maxValue = Math.max(...data.grid.map((cell) => cell.value), 0);
  if (maxValue <= 0) {
    return <p className="text-sm text-muted-foreground">No timing data for this date range.</p>;
  }

  const byCell = new Map<string, TimingMatrixResponse["grid"][number]>();
  for (const cell of data.grid) {
    byCell.set(`${cell.weekday}-${cell.hour}`, cell);
  }

  return (
    <div className="space-y-3">
      <HeatmapLegend maxValue={maxValue} metricLabel="Lower activity to higher activity" />
      <div className="overflow-x-auto">
        <table className="border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="px-1 text-left text-muted-foreground">Day</th>
              {Array.from({ length: 24 }, (_, hour) => (
                <th key={`hour-header-${hour}`} className="w-5 px-0 text-center text-xs text-muted-foreground">
                  {hour % 3 === 0 ? String(hour).padStart(2, "0") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 7 }, (_, weekday) => (
              <tr key={`weekday-${weekday}`}>
                <td className="pr-2 text-xs text-muted-foreground">{WEEKDAY_LABELS[weekday]}</td>
                {Array.from({ length: 24 }, (_, hour) => {
                  const cell = byCell.get(`${weekday}-${hour}`) ?? {
                    weekday,
                    hour,
                    value_cents: 0,
                    count: 0,
                    value: 0
                  };
                  return (
                    <td key={`${weekday}-${hour}`}>
                      <button
                        type="button"
                        className={cn("h-4 w-4 rounded-sm border-0 p-0", intensityClass(cell.value, maxValue))}
                        aria-label={`${sourceLabel} ${WEEKDAY_LABELS[weekday]} hour ${hour} value ${cell.value} count ${cell.count}`}
                        title={`${sourceLabel} • ${WEEKDAY_LABELS[weekday]} ${String(hour).padStart(2, "0")}:00 • ${formatTimingMetric(data.value, cell)} • ${cell.count} order(s) • Click to open matching transactions`}
                        onClick={() => onCellClick({ weekday, hour })}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LoadingPanel() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-44" />
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-4 w-32" />
    </div>
  );
}

function PanelError({ message }: { message: string }) {
  return <p className="text-sm text-destructive">{message}</p>;
}

function MobileSummary({ data }: { data: HeatmapResponse | HourHeatmapResponse | TimingMatrixResponse | undefined }) {
  if (!data) {
    return null;
  }
  let totalCount = 0;
  let totalCents = 0;
  if ("points" in data) {
    for (const p of data.points) {
      totalCount += p.count;
      totalCents += p.value_cents;
    }
  } else if ("grid" in data) {
    for (const c of data.grid) {
      totalCount += c.count;
      totalCents += c.value_cents;
    }
  }
  return (
    <div className="space-y-2 text-sm">
      <p className="font-medium">{formatEurFromCents(totalCents)}</p>
      <p className="text-muted-foreground">{totalCount} orders</p>
    </div>
  );
}

export function PatternsPage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [timingView, setTimingView] = useState<TimingView>("yearly");
  const [valueMode, setValueMode] = useState<TimingValueMode>("gross");
  const [fromDate, setFromDate] = useState<string>(() => dateDaysAgo(90));
  const [toDate, setToDate] = useState<string>(() => toDateInputValue(new Date()));
  const [sourceKind, setSourceKind] = useState<string>(ALL_SOURCES_VALUE);
  const [compareMode, setCompareMode] = useState<boolean>(false);
  const [compareSourceKind, setCompareSourceKind] = useState<string>(ALL_SOURCES_VALUE);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const primaryPanelRef = useRef<HTMLDivElement | null>(null);
  const secondaryPanelRef = useRef<HTMLDivElement | null>(null);

  const tzOffsetMinutes = useMemo(() => -new Date().getTimezoneOffset(), []);

  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: () => fetchSources()
  });

  const sourceOptions = useMemo<SourceOption[]>(() => {
    const labels = new Map<string, string>();
    for (const source of sourcesQuery.data?.sources ?? []) {
      if (!labels.has(source.kind)) {
        labels.set(source.kind, source.display_name || source.kind);
      }
    }
    return Array.from(labels.entries())
      .map(([kind, label]) => ({ kind, label }))
      .sort((left, right) => left.label.localeCompare(right.label));
  }, [sourcesQuery.data?.sources]);

  useEffect(() => {
    if (!compareMode) {
      return;
    }
    if (sourceOptions.length === 0) {
      return;
    }
    const currentPrimary = sourceKind === ALL_SOURCES_VALUE ? null : sourceKind;
    const candidate = sourceOptions.find((option) => option.kind !== currentPrimary)?.kind;
    if (candidate && (compareSourceKind === ALL_SOURCES_VALUE || compareSourceKind === sourceKind)) {
      setCompareSourceKind(candidate);
    }
  }, [compareMode, compareSourceKind, sourceKind, sourceOptions]);

  const primarySourceParam = sourceKind === ALL_SOURCES_VALUE ? undefined : sourceKind;
  const secondarySourceParam = compareSourceKind === ALL_SOURCES_VALUE ? undefined : compareSourceKind;
  const normalizedFromDate = fromDate.trim() || undefined;
  const normalizedToDate = toDate.trim() || undefined;

  const yearlyPrimaryQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "yearly",
      "primary",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      primarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchWeekdayHeatmap({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: primarySourceParam,
        tzOffsetMinutes
      }),
    enabled: timingView === "yearly"
  });

  const yearlyCompareQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "yearly",
      "compare",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      secondarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchWeekdayHeatmap({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: secondarySourceParam,
        tzOffsetMinutes
      }),
    enabled: compareMode && timingView === "yearly"
  });

  const hourlyPrimaryQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "hourly",
      "primary",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      primarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchHourHeatmap({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: primarySourceParam,
        tzOffsetMinutes
      }),
    enabled: timingView === "hourly"
  });

  const hourlyCompareQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "hourly",
      "compare",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      secondarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchHourHeatmap({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: secondarySourceParam,
        tzOffsetMinutes
      }),
    enabled: compareMode && timingView === "hourly"
  });

  const matrixPrimaryQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "matrix",
      "primary",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      primarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchTimingMatrix({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: primarySourceParam,
        tzOffsetMinutes
      }),
    enabled: timingView === "matrix"
  });

  const matrixCompareQuery = useQuery({
    queryKey: [
      "patterns",
      "timing",
      "matrix",
      "compare",
      normalizedFromDate,
      normalizedToDate,
      valueMode,
      secondarySourceParam,
      tzOffsetMinutes
    ],
    queryFn: () =>
      fetchTimingMatrix({
        fromDate: normalizedFromDate,
        toDate: normalizedToDate,
        value: valueMode,
        sourceKind: secondarySourceParam,
        tzOffsetMinutes
      }),
    enabled: compareMode && timingView === "matrix"
  });

  const patternsQuery = useQuery({
    queryKey: ["patterns-summary"],
    queryFn: () => fetchPatterns()
  });

  const priceIndexQuery = useQuery({
    queryKey: ["patterns-price-index"],
    queryFn: () => fetchPriceIndex()
  });

  const recentVelocity = (patternsQuery.data?.spend_velocity ?? []).slice(-10);
  const recentIndex = (priceIndexQuery.data?.points ?? []).slice(-12);

  const sourceLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const option of sourceOptions) {
      map.set(option.kind, `${option.label} (${option.kind})`);
    }
    return map;
  }, [sourceOptions]);

  const primarySourceLabel = primarySourceParam
    ? (sourceLabelMap.get(primarySourceParam) ?? primarySourceParam)
    : "All sources";
  const secondarySourceLabel = secondarySourceParam
    ? (sourceLabelMap.get(secondarySourceParam) ?? secondarySourceParam)
    : "All sources";

  function openDrilldownTransactions(sourceParam: string | undefined, selection: TimingDrilldownSelection): void {
    const params = new URLSearchParams();
    if (normalizedFromDate) {
      params.set("purchased_from", normalizedFromDate);
    }
    if (normalizedToDate) {
      params.set("purchased_to", normalizedToDate);
    }
    if (sourceParam) {
      params.set("source_kind", sourceParam);
    }
    if (selection.weekday !== undefined) {
      params.set("weekday", String(selection.weekday));
    }
    if (selection.hour !== undefined) {
      params.set("hour", String(selection.hour));
    }
    params.set("tz_offset_minutes", String(tzOffsetMinutes));
    params.set("offset", "0");
    navigate(`/transactions?${params.toString()}`);
  }

  async function exportPanelAsCsv(
    context: TimingCsvContext,
    data: HeatmapResponse | HourHeatmapResponse | TimingMatrixResponse
  ): Promise<void> {
    const content = `${buildTimingCsv(context, data)}\n`;
    const filename = `${buildTimingFilenameBase(context)}.csv`;
    const downloaded = downloadBlob(filename, "text/csv;charset=utf-8", content);
    setExportStatus(downloaded ? `Exported CSV (${filename}).` : "Download API unavailable in this browser.");
  }

  async function exportPanelAsPng(
    context: TimingCsvContext,
    node: HTMLDivElement | null
  ): Promise<void> {
    if (!node) {
      setExportStatus("Panel not ready for PNG export.");
      return;
    }
    try {
      const bg = getComputedStyle(document.documentElement).getPropertyValue("--background").trim() || "#ffffff";
      const dataUrl = await toPng(node, { cacheBust: true, backgroundColor: bg.startsWith("#") ? bg : `hsl(${bg})` });
      const filename = `${buildTimingFilenameBase(context)}.png`;
      downloadDataUrl(filename, dataUrl);
      setExportStatus(`Exported PNG (${filename}).`);
    } catch (error) {
      setExportStatus(error instanceof Error ? error.message : "Failed to export PNG.");
    }
  }

  function renderYearlyPanel(
    query: { isPending: boolean; error: unknown; data: HeatmapResponse | undefined },
    sourceLabel: string,
    sourceParam: string | undefined
  ) {
    if (query.isPending) {
      return <LoadingPanel />;
    }
    if (query.error) {
      const message = query.error instanceof Error ? query.error.message : "Failed to load yearly timing data.";
      return <PanelError message={message} />;
    }
    if (!query.data) {
      return <PanelError message="No yearly timing data available." />;
    }
    return (
      <YearlyHeatmapPanel
        data={query.data}
        sourceLabel={sourceLabel}
        onCellClick={(selection) => openDrilldownTransactions(sourceParam, selection)}
      />
    );
  }

  function renderHourlyPanel(
    query: { isPending: boolean; error: unknown; data: HourHeatmapResponse | undefined },
    sourceLabel: string,
    sourceParam: string | undefined
  ) {
    if (query.isPending) {
      return <LoadingPanel />;
    }
    if (query.error) {
      const message = query.error instanceof Error ? query.error.message : "Failed to load hourly timing data.";
      return <PanelError message={message} />;
    }
    if (!query.data) {
      return <PanelError message="No hourly timing data available." />;
    }
    return (
      <HourlyHeatmapPanel
        data={query.data}
        sourceLabel={sourceLabel}
        onBarClick={(selection) => openDrilldownTransactions(sourceParam, selection)}
      />
    );
  }

  function renderMatrixPanel(
    query: { isPending: boolean; error: unknown; data: TimingMatrixResponse | undefined },
    sourceLabel: string,
    sourceParam: string | undefined
  ) {
    if (query.isPending) {
      return <LoadingPanel />;
    }
    if (query.error) {
      const message = query.error instanceof Error ? query.error.message : "Failed to load timing matrix data.";
      return <PanelError message={message} />;
    }
    if (!query.data) {
      return <PanelError message="No timing matrix data available." />;
    }
    return (
      <TimingMatrixPanel
        data={query.data}
        sourceLabel={sourceLabel}
        onCellClick={(selection) => openDrilldownTransactions(sourceParam, selection)}
      />
    );
  }

  const primaryTimingData =
    timingView === "yearly"
      ? yearlyPrimaryQuery.data
      : timingView === "hourly"
        ? hourlyPrimaryQuery.data
        : matrixPrimaryQuery.data;
  const secondaryTimingData =
    timingView === "yearly"
      ? yearlyCompareQuery.data
      : timingView === "hourly"
        ? hourlyCompareQuery.data
        : matrixCompareQuery.data;
  const primaryCsvContext: TimingCsvContext = {
    view: timingView,
    sourceLabel: primarySourceLabel,
    valueMode,
    fromDate: normalizedFromDate,
    toDate: normalizedToDate,
    tzOffsetMinutes
  };
  const secondaryCsvContext: TimingCsvContext = {
    view: timingView,
    sourceLabel: secondarySourceLabel,
    valueMode,
    fromDate: normalizedFromDate,
    toDate: normalizedToDate,
    tzOffsetMinutes
  };

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.patterns")} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div className="space-y-2 xl:col-span-3">
          <Label htmlFor="patterns-timing-view">View</Label>
          <div
            id="patterns-timing-view"
            role="tablist"
            aria-label="Timing view"
            className="grid w-full grid-cols-3 gap-1 rounded-lg bg-muted p-1 md:w-auto"
          >
            <button
              type="button"
              role="tab"
              aria-selected={timingView === "yearly"}
              className={cn(
                "rounded-md px-3 py-1 text-sm transition",
                timingView === "yearly" ? "bg-card text-foreground shadow backdrop-blur-xl" : "text-muted-foreground"
              )}
              onClick={() => setTimingView("yearly")}
            >
              Yearly
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={timingView === "hourly"}
              className={cn(
                "rounded-md px-3 py-1 text-sm transition",
                timingView === "hourly" ? "bg-card text-foreground shadow backdrop-blur-xl" : "text-muted-foreground"
              )}
              onClick={() => setTimingView("hourly")}
            >
              Hourly
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={timingView === "matrix"}
              className={cn(
                "rounded-md px-3 py-1 text-sm transition",
                timingView === "matrix" ? "bg-card text-foreground shadow backdrop-blur-xl" : "text-muted-foreground"
              )}
              onClick={() => setTimingView("matrix")}
            >
              Weekday x Hour
            </button>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="patterns-value-mode">Metric</Label>
          <select
            id="patterns-value-mode"
            className="app-soft-surface h-9 w-full rounded-md border border-input px-3 text-sm"
            value={valueMode}
            onChange={(event) => setValueMode(event.target.value as TimingValueMode)}
          >
            <option value="net">Net spend</option>
            <option value="gross">Gross spend</option>
            <option value="count">Order count</option>
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="patterns-source-kind">Source</Label>
          <select
            id="patterns-source-kind"
            className="app-soft-surface h-9 w-full rounded-md border border-input px-3 text-sm"
            value={sourceKind}
            onChange={(event) => setSourceKind(event.target.value)}
          >
            <option value={ALL_SOURCES_VALUE}>All sources</option>
            {sourceOptions.map((option) => (
              <option key={option.kind} value={option.kind}>
                {option.label} ({option.kind})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 self-end pb-2">
          <Switch
            id="patterns-compare-mode"
            checked={compareMode}
            onCheckedChange={(checked) => setCompareMode(checked)}
            aria-label="Toggle compare mode"
          />
          <Label htmlFor="patterns-compare-mode">Compare mode</Label>
        </div>

        <div className="space-y-2">
          <Label htmlFor="patterns-date-from">From</Label>
          <Input
            id="patterns-date-from"
            type="date"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="patterns-date-to">To</Label>
          <Input
            id="patterns-date-to"
            type="date"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="patterns-source-kind-compare">Compare Source</Label>
          <select
            id="patterns-source-kind-compare"
            className="app-soft-surface h-9 w-full rounded-md border border-input px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60"
            value={compareSourceKind}
            disabled={!compareMode}
            onChange={(event) => setCompareSourceKind(event.target.value)}
          >
            {sourceOptions.length === 0 ? (
              <option value={ALL_SOURCES_VALUE}>No sources available</option>
            ) : (
              sourceOptions.map((option) => (
                <option key={`compare-${option.kind}`} value={option.kind}>
                  {option.label} ({option.kind})
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      <div className="md:hidden">
        <MobileSummary data={primaryTimingData} />
      </div>
      <div className={cn("hidden md:grid gap-4", compareMode && "md:grid-cols-2")}>
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">
                {compareMode ? `Source A: ${primarySourceLabel}` : primarySourceLabel}
              </CardTitle>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!primaryTimingData}
                  onClick={() =>
                    primaryTimingData ? void exportPanelAsCsv(primaryCsvContext, primaryTimingData) : undefined
                  }
                >
                  Export CSV
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!primaryTimingData}
                  onClick={() => void exportPanelAsPng(primaryCsvContext, primaryPanelRef.current)}
                >
                  Export PNG
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div ref={primaryPanelRef} className="space-y-2">
              {timingView === "yearly" && renderYearlyPanel(yearlyPrimaryQuery, primarySourceLabel, primarySourceParam)}
              {timingView === "hourly" && renderHourlyPanel(hourlyPrimaryQuery, primarySourceLabel, primarySourceParam)}
              {timingView === "matrix" && renderMatrixPanel(matrixPrimaryQuery, primarySourceLabel, primarySourceParam)}
            </div>
          </CardContent>
        </Card>

        {compareMode ? (
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">Source B: {secondarySourceLabel}</CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!secondaryTimingData}
                    onClick={() =>
                      secondaryTimingData ? void exportPanelAsCsv(secondaryCsvContext, secondaryTimingData) : undefined
                    }
                  >
                    Export CSV
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!secondaryTimingData}
                    onClick={() => void exportPanelAsPng(secondaryCsvContext, secondaryPanelRef.current)}
                  >
                    Export PNG
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div ref={secondaryPanelRef} className="space-y-2">
                {timingView === "yearly" && renderYearlyPanel(yearlyCompareQuery, secondarySourceLabel, secondarySourceParam)}
                {timingView === "hourly" && renderHourlyPanel(hourlyCompareQuery, secondarySourceLabel, secondarySourceParam)}
                {timingView === "matrix" && renderMatrixPanel(matrixCompareQuery, secondarySourceLabel, secondarySourceParam)}
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
      {exportStatus ? <p className="text-xs text-muted-foreground">{exportStatus}</p> : null}

      <Card>
        <CardHeader>
          <CardTitle>Spend Velocity (Recent)</CardTitle>
        </CardHeader>
        <CardContent>
          {recentVelocity.length === 0 ? (
            <p className="text-sm text-muted-foreground">No velocity data available.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Rolling 7d</TableHead>
                  <TableHead>Rolling 30d</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentVelocity.map((point) => (
                  <TableRow key={point.date}>
                    <TableCell>{point.date}</TableCell>
                    <TableCell>{formatEurFromCents(point.rolling_7d_cents)}</TableCell>
                    <TableCell>{formatEurFromCents(point.rolling_30d_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Retailer Price Index (Recent)</CardTitle>
        </CardHeader>
        <CardContent>
          {recentIndex.length === 0 ? (
            <p className="text-sm text-muted-foreground">No price index data available.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Index</TableHead>
                  <TableHead>Products</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentIndex.map((point) => (
                  <TableRow key={`${point.period}-${point.source_kind}`}>
                    <TableCell>{point.period}</TableCell>
                    <TableCell>{point.source_kind}</TableCell>
                    <TableCell>{point.index}</TableCell>
                    <TableCell>{point.product_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
