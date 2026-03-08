import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Euro, Package, Percent, PiggyBank, TrendingDown } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { fetchRecurringCalendar, fetchRecurringForecast } from "@/api/recurringBills";
import { DashboardPeriodMode, dashboardPanelsQueryOptions } from "@/app/queries";
import { fetchDepositAnalytics } from "@/api/analytics";
import { fetchSources } from "@/api/sources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatEurFromCents, formatPercent } from "../utils/format";

type DiscountView = "native" | "normalized";
type BreakdownDisplay = "chart" | "table";
type SpendView = "net" | "gross";

type ExportRow = {
  table: "savings_breakdown" | "retailer_composition";
  label: string;
  saved_cents: number;
  events?: number;
  share?: number;
};

type RetailerOption = {
  id: string;
  label: string;
};

const YEAR_MIN = 2020;
const YEAR_MAX = 2100;
const MONTH_MIN = 1;
const MONTH_MAX = 12;
const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December"
] as const;

const RANGE_PRESETS: Array<{ label: string; startMonth: number; endMonth: number }> = [
  { label: "Q1", startMonth: 1, endMonth: 3 },
  { label: "Q2", startMonth: 4, endMonth: 6 },
  { label: "Q3", startMonth: 7, endMonth: 9 },
  { label: "Q4", startMonth: 10, endMonth: 12 },
  { label: "H1", startMonth: 1, endMonth: 6 },
  { label: "H2", startMonth: 7, endMonth: 12 },
  { label: "Full year", startMonth: 1, endMonth: 12 }
];

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function parseInteger(value: string | null): number | null {
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return null;
  }
  return Math.floor(parsed);
}

function readYearParam(raw: string | null, fallback: number): number {
  const parsed = parseInteger(raw);
  if (parsed === null) {
    return fallback;
  }
  return clampNumber(parsed, YEAR_MIN, YEAR_MAX);
}

function readMonthParam(raw: string | null, fallback: number): number {
  const parsed = parseInteger(raw);
  if (parsed === null) {
    return fallback;
  }
  return clampNumber(parsed, MONTH_MIN, MONTH_MAX);
}

function readPeriodMode(raw: string | null): DashboardPeriodMode {
  if (raw === "range" || raw === "year") {
    return raw;
  }
  return "month";
}

function readDiscountView(raw: string | null): DiscountView {
  return raw === "normalized" ? "normalized" : "native";
}

function readBreakdownDisplay(raw: string | null): BreakdownDisplay {
  return raw === "table" ? "table" : "chart";
}

function readSpendView(raw: string | null): SpendView {
  return raw === "net" ? "net" : "gross";
}

function readRetailerIds(raw: string | null): string[] {
  if (!raw) {
    return [];
  }
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean)
    )
  ).sort();
}

function monthName(month: number): string {
  return MONTH_NAMES[clampNumber(month, MONTH_MIN, MONTH_MAX) - 1];
}

function monthYearLabel(year: number, month: number): string {
  return `${monthName(month)} ${year}`;
}

function monthIsoStart(year: number, month: number): string {
  return `${year}-${String(month).padStart(2, "0")}-01T00:00:00Z`;
}

function monthIsoEnd(year: number, month: number): string {
  const nextMonth = month === 12 ? 1 : month + 1;
  const nextYear = month === 12 ? year + 1 : year;
  return `${nextYear}-${String(nextMonth).padStart(2, "0")}-01T00:00:00Z`;
}

function labelFromTrendPoint(point: { year: number; month: number; period_key: string }): string {
  if (point.month >= MONTH_MIN && point.month <= MONTH_MAX) {
    return monthYearLabel(point.year, point.month);
  }
  const [rawYear, rawMonth] = point.period_key.split("-");
  const parsedYear = Number(rawYear);
  const parsedMonth = Number(rawMonth);
  if (Number.isFinite(parsedYear) && Number.isFinite(parsedMonth)) {
    return monthYearLabel(parsedYear, parsedMonth);
  }
  return point.period_key;
}

function csvEscape(value: string): string {
  if (!value.includes(",") && !value.includes('"') && !value.includes("\n")) {
    return value;
  }
  return `"${value.replace(/"/g, '""')}"`;
}

function buildCsv(rows: ExportRow[]): string {
  const header = "table,label,saved_cents,events,share";
  const lines = rows.map((row) =>
    [
      row.table,
      csvEscape(row.label),
      String(row.saved_cents),
      row.events === undefined ? "" : String(row.events),
      row.share === undefined ? "" : String(row.share)
    ].join(",")
  );
  return [header, ...lines].join("\n");
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

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const today = new Date();
  const recurringToday = new Date();
  const defaultYear = today.getFullYear();
  const defaultMonth = today.getMonth() + 1;

  const year = readYearParam(searchParams.get("year"), defaultYear);
  const periodMode = readPeriodMode(searchParams.get("period"));
  const month = readMonthParam(searchParams.get("month"), defaultMonth);
  const parsedStartMonth = readMonthParam(searchParams.get("start_month"), Math.max(1, month - 2));
  const parsedEndMonth = readMonthParam(searchParams.get("end_month"), month);
  const startMonth = Math.min(parsedStartMonth, parsedEndMonth);
  const endMonth = Math.max(parsedStartMonth, parsedEndMonth);
  const view = readDiscountView(searchParams.get("view"));
  const breakdownDisplay = readBreakdownDisplay(searchParams.get("breakdown"));
  const spendView = readSpendView(searchParams.get("spend"));
  const selectedRetailerIds = readRetailerIds(searchParams.get("retailers"));

  const [exportStatus, setExportStatus] = useState<string | null>(null);

  function updateSearchParams(nextValues: Partial<{
    year: number;
    period: DashboardPeriodMode;
    month: number;
    startMonth: number;
    endMonth: number;
    view: DiscountView;
    breakdown: BreakdownDisplay;
    spend: SpendView;
    retailers: string[];
  }>): void {
    const next = new URLSearchParams(searchParams);
    const nextYear = nextValues.year ?? year;
    const nextPeriod = nextValues.period ?? periodMode;
    const nextMonth = nextValues.month ?? month;
    const nextStartMonth = nextValues.startMonth ?? startMonth;
    const nextEndMonth = nextValues.endMonth ?? endMonth;
    const normalizedStartMonth = Math.min(nextStartMonth, nextEndMonth);
    const normalizedEndMonth = Math.max(nextStartMonth, nextEndMonth);
    const nextView = nextValues.view ?? view;
    const nextBreakdown = nextValues.breakdown ?? breakdownDisplay;
    const nextSpend = nextValues.spend ?? spendView;
    const nextRetailers = nextValues.retailers ?? selectedRetailerIds;

    next.set("year", String(clampNumber(nextYear, YEAR_MIN, YEAR_MAX)));
    next.set("period", nextPeriod);
    next.set("month", String(clampNumber(nextMonth, MONTH_MIN, MONTH_MAX)));
    next.set("start_month", String(clampNumber(normalizedStartMonth, MONTH_MIN, MONTH_MAX)));
    next.set("end_month", String(clampNumber(normalizedEndMonth, MONTH_MIN, MONTH_MAX)));
    next.set("view", nextView);
    next.set("breakdown", nextBreakdown);
    next.set("spend", nextSpend);

    if (nextRetailers.length > 0) {
      next.set("retailers", Array.from(new Set(nextRetailers)).sort().join(","));
    } else {
      next.delete("retailers");
    }

    setSearchParams(next);
  }

  const sourcesQuery = useQuery({ queryKey: ["sources"], queryFn: fetchSources });

  const { data, error, isPending, isFetching } = useQuery(
    dashboardPanelsQueryOptions({
      year,
      periodMode,
      month,
      startMonth,
      endMonth,
      view,
      sourceIds: selectedRetailerIds
    })
  );
  const depositQuery = useQuery({ queryKey: ["deposit-analytics"], queryFn: fetchDepositAnalytics });
  const recurringCalendarQuery = useQuery({
    queryKey: [
      "dashboard-recurring-calendar",
      recurringToday.getFullYear(),
      recurringToday.getMonth() + 1
    ],
    queryFn: () =>
      fetchRecurringCalendar({
        year: recurringToday.getFullYear(),
        month: recurringToday.getMonth() + 1
      })
  });
  const recurringForecastQuery = useQuery({
    queryKey: ["dashboard-recurring-forecast", 3],
    queryFn: () => fetchRecurringForecast({ months: 3 })
  });

  const cards = data?.cards ?? null;
  const trends = data?.trends ?? null;
  const breakdown = data?.breakdown ?? null;
  const composition = data?.composition ?? null;
  const warnings = data?.warnings ?? [];
  const loading = isPending || isFetching;
  const errorMessage = error instanceof Error ? error.message : null;

  const trendPoints = trends?.points ?? [];
  const breakdownRows = breakdown?.by_type ?? [];
  const retailerRows = composition?.retailers ?? [];

  const retailerOptions = useMemo<RetailerOption[]>(() => {
    const options = new Map<string, string>();
    for (const source of sourcesQuery.data?.sources ?? []) {
      options.set(source.id, source.display_name || source.id);
    }
    for (const row of retailerRows) {
      if (!options.has(row.source_id)) {
        options.set(row.source_id, row.retailer);
      }
    }
    return Array.from(options.entries())
      .map(([id, label]) => ({ id, label }))
      .sort((left, right) => left.label.localeCompare(right.label));
  }, [retailerRows, sourcesQuery.data?.sources]);

  const retailerNameById = useMemo(
    () => new Map(retailerOptions.map((option) => [option.id, option.label])),
    [retailerOptions]
  );

  function selectedRetailerSummary(): string {
    if (selectedRetailerIds.length === 0) {
      return "All retailers";
    }
    if (selectedRetailerIds.length === 1) {
      return retailerNameById.get(selectedRetailerIds[0]) ?? selectedRetailerIds[0];
    }
    return `${selectedRetailerIds.length} retailers selected`;
  }

  function toggleRetailer(sourceId: string): void {
    const selected = new Set(selectedRetailerIds);
    if (selected.has(sourceId)) {
      selected.delete(sourceId);
    } else {
      selected.add(sourceId);
    }
    updateSearchParams({ retailers: Array.from(selected).sort() });
  }

  const maxTrendSpend = Math.max(
    ...trendPoints.map((point) => {
      const grossCents = point.gross_cents ?? point.paid_cents + point.saved_cents;
      const netCents = point.net_cents ?? point.paid_cents;
      return spendView === "gross" ? grossCents : netCents;
    }),
    1
  );
  const maxBreakdownSaved = Math.max(...breakdownRows.map((row) => row.saved_cents), 1);
  const spendColumnTitle = spendView === "gross" ? "Gross spend" : "Net spend";
  const recurringForecastMax = Math.max(
    ...(recurringForecastQuery.data?.points ?? []).map((point) => point.projected_cents),
    1
  );

  const savingsRatePct = useMemo(() => {
    if (!cards) {
      return "0.00%";
    }
    return formatPercent(cards.totals.savings_rate);
  }, [cards]);

  const netSpendCents = cards ? cards.totals.net_cents ?? cards.totals.paid_cents : null;
  const grossSpendCents = cards ? cards.totals.gross_cents : null;
  const savingsCents = cards ? cards.totals.discount_total_cents ?? cards.totals.saved_cents : null;

  const ledgerParams = new URLSearchParams();
  ledgerParams.set("year", String(year));
  if (periodMode === "month") {
    ledgerParams.set("month", String(month));
  } else if (periodMode === "range") {
    ledgerParams.set("purchased_from", monthIsoStart(year, startMonth));
    ledgerParams.set("purchased_to", monthIsoEnd(year, endMonth));
  } else {
    ledgerParams.set("purchased_from", `${year}-01-01T00:00:00Z`);
    ledgerParams.set("purchased_to", `${year + 1}-01-01T00:00:00Z`);
  }
  if (selectedRetailerIds.length === 1) {
    ledgerParams.set("source_id", selectedRetailerIds[0]);
  }
  const ledgerLink = `/transactions?${ledgerParams.toString()}`;

  const trendTitle =
    periodMode === "month"
      ? `Trend (last 6 months, ${spendView})`
      : periodMode === "range"
        ? `Trend (${monthName(startMonth)}-${monthName(endMonth)} ${year}, ${spendView})`
        : `Trend (${year}, ${spendView})`;

  const exportRows = useMemo<ExportRow[]>(() => {
    const rows: ExportRow[] = [];
    if (breakdownDisplay === "table") {
      for (const row of breakdownRows) {
        rows.push({
          table: "savings_breakdown",
          label: row.type,
          saved_cents: row.saved_cents,
          events: row.discount_events
        });
      }
    }
    for (const row of retailerRows) {
      rows.push({
        table: "retailer_composition",
        label: row.retailer,
        saved_cents: row.saved_cents,
        share: row.saved_share
      });
    }
    return rows;
  }, [breakdownDisplay, breakdownRows, retailerRows]);

  const periodExportLabel =
    periodMode === "month"
      ? `${year}_${String(month).padStart(2, "0")}`
      : periodMode === "range"
        ? `${year}_${String(startMonth).padStart(2, "0")}-${String(endMonth).padStart(2, "0")}`
        : `${year}_full_year`;

  function exportSnapshotAsJson(): void {
    const payload = {
      filters: {
        year,
        period: periodMode,
        month,
        start_month: startMonth,
        end_month: endMonth,
        view,
        breakdown: breakdownDisplay,
        source_ids: selectedRetailerIds
      },
      exported_at: new Date().toISOString(),
      rows: exportRows
    };
    const downloaded = downloadBlob(
      `dashboard_snapshot_${periodExportLabel}.json`,
      "application/json",
      `${JSON.stringify(payload, null, 2)}\n`
    );
    setExportStatus(downloaded ? "Exported JSON snapshot." : "Download API unavailable in this browser.");
  }

  function exportSnapshotAsCsv(): void {
    const downloaded = downloadBlob(
      `dashboard_snapshot_${periodExportLabel}.csv`,
      "text/csv;charset=utf-8",
      `${buildCsv(exportRows)}\n`
    );
    setExportStatus(downloaded ? "Exported CSV snapshot." : "Download API unavailable in this browser.");
  }

  return (
    <section className="space-y-4">
      <div className="space-y-4 rounded-lg border bg-card p-4">
        <div className="grid gap-3 md:grid-cols-6">
          <div className="space-y-2">
            <Label htmlFor="dashboard-period-mode">Period</Label>
            <Select
              value={periodMode}
              onValueChange={(nextMode) => updateSearchParams({ period: nextMode as DashboardPeriodMode })}
            >
              <SelectTrigger id="dashboard-period-mode">
                <SelectValue placeholder="Select period" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="month">Single month</SelectItem>
                <SelectItem value="range">Month range</SelectItem>
                <SelectItem value="year">Full year</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="dashboard-year">Year</Label>
            <Input
              id="dashboard-year"
              type="number"
              value={year}
              min={YEAR_MIN}
              max={YEAR_MAX}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                if (!Number.isFinite(parsed)) {
                  return;
                }
                updateSearchParams({ year: clampNumber(Math.floor(parsed), YEAR_MIN, YEAR_MAX) });
              }}
            />
          </div>

          {periodMode === "month" ? (
            <div className="space-y-2">
              <Label htmlFor="dashboard-month">Month</Label>
              <Select
                value={String(month)}
                onValueChange={(value) => updateSearchParams({ month: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })}
              >
                <SelectTrigger id="dashboard-month">
                  <SelectValue placeholder="Select month" />
                </SelectTrigger>
                <SelectContent>
                  {MONTH_NAMES.map((name, index) => (
                    <SelectItem key={name} value={String(index + 1)}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {periodMode === "range" ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="dashboard-start-month">From</Label>
                <Select
                  value={String(startMonth)}
                  onValueChange={(value) =>
                    updateSearchParams({ startMonth: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })
                  }
                >
                  <SelectTrigger id="dashboard-start-month">
                    <SelectValue placeholder="Start month" />
                  </SelectTrigger>
                  <SelectContent>
                    {MONTH_NAMES.map((name, index) => (
                      <SelectItem key={`start-${name}`} value={String(index + 1)}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dashboard-end-month">To</Label>
                <Select
                  value={String(endMonth)}
                  onValueChange={(value) =>
                    updateSearchParams({ endMonth: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })
                  }
                >
                  <SelectTrigger id="dashboard-end-month">
                    <SelectValue placeholder="End month" />
                  </SelectTrigger>
                  <SelectContent>
                    {MONTH_NAMES.map((name, index) => (
                      <SelectItem key={`end-${name}`} value={String(index + 1)}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          ) : null}

          {periodMode === "year" ? (
            <div className="space-y-2">
              <Label>Window</Label>
              <div className="flex h-10 items-center rounded-md border px-3 text-sm text-muted-foreground">
                January - December
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label>Retailers</Label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="outline" className="w-full justify-start text-left">
                  {selectedRetailerSummary()}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-72">
                <DropdownMenuLabel>Filter retailers</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="mx-1 mb-1 w-[calc(100%-0.5rem)] justify-start"
                  onClick={() => updateSearchParams({ retailers: [] })}
                >
                  All retailers
                </Button>
                {retailerOptions.length === 0 ? (
                  <p className="px-2 py-1 text-xs text-muted-foreground">No retailers available yet.</p>
                ) : (
                  retailerOptions.map((option) => (
                    <DropdownMenuCheckboxItem
                      key={option.id}
                      checked={selectedRetailerIds.includes(option.id)}
                      onSelect={(event) => event.preventDefault()}
                      onCheckedChange={() => toggleRetailer(option.id)}
                    >
                      {option.label}
                    </DropdownMenuCheckboxItem>
                  ))
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="space-y-2">
            <Label htmlFor="dashboard-spend-view">Spend view</Label>
            <Select value={spendView} onValueChange={(nextView) => updateSearchParams({ spend: nextView as SpendView })}>
              <SelectTrigger id="dashboard-spend-view">
                <SelectValue placeholder="Select spend view" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="net">Net</SelectItem>
                <SelectItem value="gross">Gross</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="dashboard-discount-view">Discount view</Label>
            <Select value={view} onValueChange={(nextView) => updateSearchParams({ view: nextView as DiscountView })}>
              <SelectTrigger id="dashboard-discount-view">
                <SelectValue placeholder="Select view" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="native">Native</SelectItem>
                <SelectItem value="normalized">Normalized</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {periodMode === "range" ? (
          <div className="flex flex-wrap gap-2">
            {RANGE_PRESETS.map((preset) => (
              <Button
                key={preset.label}
                type="button"
                size="sm"
                variant={startMonth === preset.startMonth && endMonth === preset.endMonth ? "default" : "outline"}
                onClick={() =>
                  updateSearchParams({
                    period: "range",
                    startMonth: preset.startMonth,
                    endMonth: preset.endMonth
                  })
                }
              >
                {preset.label}
              </Button>
            ))}
          </div>
        ) : null}

        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <p className="text-sm text-muted-foreground">
            {periodMode === "month"
              ? `Showing ${monthYearLabel(year, month)}`
              : periodMode === "range"
                ? `Showing ${monthName(startMonth)}-${monthName(endMonth)} ${year}`
                : `Showing full year ${year}`}
            {`, ${selectedRetailerSummary()}`}
          </p>
          <Button asChild>
            <Link to={ledgerLink}>Drill down to transactions</Link>
          </Button>
        </div>
      </div>

      {warnings.length > 0 ? (
        <Alert>
          <AlertTitle>Backend warnings</AlertTitle>
          <AlertDescription>
            <ul className="list-inside list-disc space-y-1">
              {warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load dashboard</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <section className="grid gap-4 md:grid-cols-5">
        {loading ? (
          <>
            <Skeleton className="h-28 rounded-lg" />
            <Skeleton className="h-28 rounded-lg" />
            <Skeleton className="h-28 rounded-lg" />
            <Skeleton className="h-28 rounded-lg" />
            <Skeleton className="h-28 rounded-lg" />
          </>
        ) : (
          <>
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Net spend
                  </CardTitle>
                  <span className="rounded-md bg-primary/10 p-1.5 text-primary">
                    <TrendingDown className="h-3.5 w-3.5" />
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold tabular-nums">
                  {netSpendCents !== null ? formatEurFromCents(netSpendCents) : "—"}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Gross spend
                  </CardTitle>
                  <span className="rounded-md bg-muted p-1.5 text-muted-foreground">
                    <Euro className="h-3.5 w-3.5" />
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold tabular-nums">
                  {grossSpendCents !== null ? formatEurFromCents(grossSpendCents) : "—"}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Savings
                  </CardTitle>
                  <span className="rounded-md bg-success/10 p-1.5 text-success">
                    <PiggyBank className="h-3.5 w-3.5" />
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold tabular-nums">
                  {savingsCents !== null ? formatEurFromCents(savingsCents) : "—"}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Savings rate
                  </CardTitle>
                  <span className="rounded-md bg-chart-2/10 p-1.5 text-chart-2">
                    <Percent className="h-3.5 w-3.5" />
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold tabular-nums">{savingsRatePct}</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Pfand paid (all-time)
                  </CardTitle>
                  <span className="rounded-md bg-amber-500/10 p-1.5 text-amber-600">
                    <Package className="h-3.5 w-3.5" />
                  </span>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold tabular-nums">
                  {depositQuery.data ? formatEurFromCents(depositQuery.data.total_paid_cents) : "—"}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">excluded from spend totals</p>
              </CardContent>
            </Card>
          </>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Upcoming bills this month</CardTitle>
          </CardHeader>
          <CardContent>
            {recurringCalendarQuery.isPending ? (
              <p className="text-sm text-muted-foreground">Loading recurring calendar...</p>
            ) : (recurringCalendarQuery.data?.days ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No recurring bills scheduled this month.</p>
            ) : (
              <ul className="space-y-3">
                {(recurringCalendarQuery.data?.days ?? []).map((day) => (
                  <li
                    key={day.date}
                    className="flex items-start justify-between rounded-md border bg-muted/20 px-3 py-2"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {new Date(`${day.date}T00:00:00`).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric"
                        })}
                      </p>
                      <p className="text-xs text-muted-foreground">{day.count} bill(s)</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold tabular-nums">
                        {formatEurFromCents(day.total_expected_cents)}
                      </p>
                      <p className="text-xs text-muted-foreground">expected</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">3-month recurring forecast</CardTitle>
            <CalendarCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {recurringForecastQuery.isPending ? (
              <p className="text-sm text-muted-foreground">Loading recurring forecast...</p>
            ) : (recurringForecastQuery.data?.points ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No recurring projection data available.</p>
            ) : (
              <ul className="space-y-3">
                {(recurringForecastQuery.data?.points ?? []).map((point) => {
                  const widthPct = Math.max(
                    8,
                    Math.round((point.projected_cents / recurringForecastMax) * 100)
                  );
                  const label = new Date(`${point.period}-01T00:00:00`).toLocaleDateString(
                    undefined,
                    { month: "short", year: "numeric" }
                  );
                  return (
                    <li key={point.period} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{label}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {formatEurFromCents(point.projected_cents)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div className="h-2 rounded-full bg-primary" style={{ width: `${widthPct}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{trendTitle}</CardTitle>
          </CardHeader>
          <CardContent>
            {trendPoints.length === 0 ? (
              <p className="text-sm text-muted-foreground">No trend points in this period.</p>
            ) : (
              <ul className="space-y-3">
                {trendPoints.map((point) => {
                  const grossCents = point.gross_cents ?? point.paid_cents + point.saved_cents;
                  const netCents = point.net_cents ?? point.paid_cents;
                  const pointSavingsCents = point.discount_total_cents ?? point.saved_cents;
                  const spendCents = spendView === "gross" ? grossCents : netCents;
                  const width = Math.max(8, Math.round((spendCents / maxTrendSpend) * 100));
                  return (
                    <li key={point.period_key} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{labelFromTrendPoint(point)}</span>
                        <span className="text-muted-foreground">
                          {spendView} {formatEurFromCents(spendCents)} | net {formatEurFromCents(netCents)} | gross{" "}
                          {formatEurFromCents(grossCents)} | savings {formatEurFromCents(pointSavingsCents)}
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div className="h-2 rounded-full bg-primary" style={{ width: `${width}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="space-y-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Savings by discount type ({view})</CardTitle>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={breakdownDisplay === "chart" ? "default" : "outline"}
                  onClick={() => updateSearchParams({ breakdown: "chart" })}
                >
                  Chart
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={breakdownDisplay === "table" ? "default" : "outline"}
                  onClick={() => updateSearchParams({ breakdown: "table" })}
                >
                  Table
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {breakdownRows.length === 0 ? (
              <p className="text-sm text-muted-foreground">No discount rows in this period.</p>
            ) : breakdownDisplay === "chart" ? (
              <ul className="space-y-3">
                {breakdownRows.map((row) => {
                  const width = Math.max(8, Math.round((row.saved_cents / maxBreakdownSaved) * 100));
                  return (
                    <li key={row.type} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{row.type}</span>
                        <span className="text-muted-foreground">
                          {formatEurFromCents(row.saved_cents)} ({row.discount_events} events)
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div className="h-2 rounded-full bg-primary" style={{ width: `${width}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Type</TableHead>
                    <TableHead>Saved</TableHead>
                    <TableHead>Events</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {breakdownRows.map((row) => (
                    <TableRow key={row.type}>
                      <TableCell>{row.type}</TableCell>
                      <TableCell className="tabular-nums">{formatEurFromCents(row.saved_cents)}</TableCell>
                      <TableCell className="tabular-nums">{row.discount_events}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Savings by retailer</CardTitle>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={exportSnapshotAsJson}>
              Export JSON
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={exportSnapshotAsCsv}>
              Export CSV
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {exportStatus ? <p className="mb-3 text-xs text-muted-foreground">{exportStatus}</p> : null}
          {retailerRows.length === 0 ? (
            <p className="text-sm text-muted-foreground">No retailer composition rows in this period.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Retailer</TableHead>
                  <TableHead>{spendColumnTitle}</TableHead>
                  <TableHead>Saved</TableHead>
                  <TableHead>Saved share</TableHead>
                  <TableHead>{spendColumnTitle} share</TableHead>
                  <TableHead>Savings rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {retailerRows.map((row) => {
                  const grossCents = row.gross_cents ?? row.paid_cents + row.saved_cents;
                  const netCents = row.net_cents ?? row.paid_cents;
                  const spendCents = spendView === "gross" ? grossCents : netCents;
                  const spendShare =
                    spendView === "gross" ? row.gross_share ?? 0 : row.net_share ?? row.paid_share;
                  return (
                    <TableRow key={row.source_id}>
                      <TableCell>{row.retailer}</TableCell>
                      <TableCell className="tabular-nums">{formatEurFromCents(spendCents)}</TableCell>
                      <TableCell className="tabular-nums">{formatEurFromCents(row.saved_cents)}</TableCell>
                      <TableCell className="tabular-nums">{formatPercent(row.saved_share)}</TableCell>
                      <TableCell className="tabular-nums">{formatPercent(spendShare)}</TableCell>
                      <TableCell className="tabular-nums">{formatPercent(row.savings_rate)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
