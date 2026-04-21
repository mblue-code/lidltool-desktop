import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarCheck, Euro, Package, Percent, PiggyBank, RefreshCw, TrendingDown } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { fetchRecurringCalendar, fetchRecurringForecast } from "@/api/recurringBills";
import { DashboardPeriodMode, dashboardPanelsQueryOptions } from "@/app/queries";
import { fetchDepositAnalytics } from "@/api/analytics";
import { fetchSources } from "@/api/sources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { MetricCard } from "@/components/shared/MetricCard";
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
import { PageHeader } from "@/components/shared/PageHeader";
import { type TranslationKey, useI18n } from "@/i18n";
import { resolveApiErrorMessage, resolveApiWarningMessage } from "@/lib/backend-messages";
import { formatEurFromCents, formatMonthDay, formatMonthName, formatMonthYear, formatPercent } from "../utils/format";

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
const RANGE_PRESETS: Array<{ label?: string; labelKey?: TranslationKey; startMonth: number; endMonth: number }> = [
  { label: "Q1", startMonth: 1, endMonth: 3 },
  { label: "Q2", startMonth: 4, endMonth: 6 },
  { label: "Q3", startMonth: 7, endMonth: 9 },
  { label: "Q4", startMonth: 10, endMonth: 12 },
  { label: "H1", startMonth: 1, endMonth: 6 },
  { label: "H2", startMonth: 7, endMonth: 12 },
  { labelKey: "pages.dashboard.period.year", startMonth: 1, endMonth: 12 }
];
const DASHBOARD_SURFACE_CLASS = "app-dashboard-surface border-border/60";
const DASHBOARD_SURFACE_STRONG_CLASS = "app-dashboard-surface-strong border-border/60";
const DASHBOARD_CONTROL_CLASS = "app-dashboard-control border-border/70 text-foreground shadow-none";

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
  return formatMonthName(clampNumber(month, MONTH_MIN, MONTH_MAX));
}

function monthYearLabel(year: number, month: number): string {
  return formatMonthYear(new Date(Date.UTC(year, month - 1, 1, 12, 0, 0)));
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

function discountTypeLabel(
  t: (key: TranslationKey, params?: Record<string, string | number>) => string,
  type: string,
  view: DiscountView
): string {
  if (view !== "normalized") {
    return type;
  }
  const keyByType: Record<string, TranslationKey> = {
    promotion: "pages.dashboard.discountType.promotion",
    coupon: "pages.dashboard.discountType.coupon",
    loyalty: "pages.dashboard.discountType.loyalty",
    markdown: "pages.dashboard.discountType.markdown",
    cashback: "pages.dashboard.discountType.cashback",
    other: "pages.dashboard.discountType.other"
  };
  const key = keyByType[type];
  return key ? t(key) : type;
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
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [showFilters, setShowFilters] = useState(() => searchParams.toString() !== "");
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
  const spendViewLabel = t(`pages.dashboard.spendView.${spendView}` as TranslationKey);
  const savingsViewLabel = t(`pages.dashboard.discountView.${view}` as TranslationKey);
  const depositFilters = useMemo(() => {
    if (periodMode === "month") {
      return {
        fromDate: monthIsoStart(year, month),
        toDate: monthIsoEnd(year, month),
      };
    }
    if (periodMode === "range") {
      return {
        fromDate: monthIsoStart(year, startMonth),
        toDate: monthIsoEnd(year, endMonth),
      };
    }
    return {
      fromDate: monthIsoStart(year, 1),
      toDate: monthIsoEnd(year, 12),
    };
  }, [endMonth, month, periodMode, startMonth, year]);

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
  const depositQuery = useQuery({
    queryKey: ["deposit-analytics", depositFilters.fromDate, depositFilters.toDate, selectedRetailerIds],
    queryFn: () =>
      fetchDepositAnalytics({
        fromDate: depositFilters.fromDate,
        toDate: depositFilters.toDate,
        sourceIds: selectedRetailerIds
      })
  });
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
  const refreshing =
    isFetching ||
    depositQuery.isFetching ||
    recurringCalendarQuery.isFetching ||
    recurringForecastQuery.isFetching;
  const errorMessage = error ? resolveApiErrorMessage(error, t, t("pages.dashboard.loadError")) : null;

  const trendPoints = trends?.points ?? [];
  const breakdownRows = breakdown?.by_type ?? [];
  const retailerRows = composition?.retailers ?? [];
  const displayBreakdownRows = useMemo(
    () =>
      breakdownRows.map((row) => ({
        ...row,
        label: discountTypeLabel(t, row.type, view)
      })),
    [breakdownRows, t, view]
  );

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
      return t("pages.dashboard.allRetailers");
    }
    if (selectedRetailerIds.length === 1) {
      return retailerNameById.get(selectedRetailerIds[0]) ?? selectedRetailerIds[0];
    }
    return t("pages.dashboard.retailersSelected", { count: selectedRetailerIds.length });
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
  const spendColumnTitle =
    spendView === "gross" ? t("pages.dashboard.card.grossSpend") : t("pages.dashboard.card.netSpend");
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
  const savingsLedgerLink = `/transactions?${ledgerParams.toString()}&has_discounts=true`;

  const trendTitle =
    periodMode === "month"
      ? t("pages.dashboard.trendTitle.month", { spendView: spendViewLabel })
      : periodMode === "range"
        ? t("pages.dashboard.trendTitle.range", {
            rangeLabel: `${monthName(startMonth)}-${monthName(endMonth)} ${year}`,
            spendView: spendViewLabel
          })
        : t("pages.dashboard.trendTitle.year", { year, spendView: spendViewLabel });

  const exportRows = useMemo<ExportRow[]>(() => {
    const rows: ExportRow[] = [];
    if (breakdownDisplay === "table") {
      for (const row of breakdownRows) {
        rows.push({
          table: "savings_breakdown",
          label: discountTypeLabel(t, row.type, view),
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
  }, [breakdownDisplay, breakdownRows, retailerRows, t, view]);

  function refreshDashboard(): void {
    void Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["deposit-analytics"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-recurring-calendar"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-recurring-forecast"] }),
      queryClient.invalidateQueries({ queryKey: ["sources"] })
    ]);
  }

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
    setExportStatus(downloaded ? t("pages.dashboard.exportedJson") : t("pages.dashboard.downloadUnavailable"));
  }

  function exportSnapshotAsCsv(): void {
    const downloaded = downloadBlob(
      `dashboard_snapshot_${periodExportLabel}.csv`,
      "text/csv;charset=utf-8",
      `${buildCsv(exportRows)}\n`
    );
    setExportStatus(downloaded ? t("pages.dashboard.exportedCsv") : t("pages.dashboard.downloadUnavailable"));
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.overview")} description={t("pages.dashboard.description")}>
        <Button asChild variant="outline">
          <Link to="/receipts">{t("nav.item.receipts")}</Link>
        </Button>
        <Button asChild>
          <Link to="/add">{t("nav.item.addReceipt")}</Link>
        </Button>
      </PageHeader>
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {periodMode === "month"
              ? t("pages.dashboard.showingMonth", { period: monthYearLabel(year, month) })
              : periodMode === "range"
                ? t("pages.dashboard.showingRange", { period: `${monthName(startMonth)}-${monthName(endMonth)} ${year}` })
                : t("pages.dashboard.showingYear", { year })}
          </p>
          <p className="text-sm text-muted-foreground">{selectedRetailerSummary()}</p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={refreshDashboard}>
            <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            {t(refreshing ? "pages.dashboard.refreshing" : "pages.dashboard.refresh")}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setShowFilters((current) => !current)}>
            {t(showFilters ? "pages.dashboard.hideFilters" : "pages.dashboard.showFilters")}
          </Button>
          <Button asChild size="sm">
            <Link to={ledgerLink}>{t("pages.dashboard.drillDown")}</Link>
          </Button>
        </div>
      </div>

      {showFilters ? (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-6">
            <div className="space-y-2">
              <Label htmlFor="dashboard-period-mode">{t("pages.dashboard.period")}</Label>
              <Select
                value={periodMode}
                onValueChange={(nextMode) => updateSearchParams({ period: nextMode as DashboardPeriodMode })}
              >
                <SelectTrigger id="dashboard-period-mode" className={DASHBOARD_CONTROL_CLASS}>
                  <SelectValue placeholder={t("pages.dashboard.selectPeriod")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="month">{t("pages.dashboard.period.month")}</SelectItem>
                  <SelectItem value="range">{t("pages.dashboard.period.range")}</SelectItem>
                  <SelectItem value="year">{t("pages.dashboard.period.year")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dashboard-year">{t("common.year")}</Label>
              <Input
                id="dashboard-year"
                type="number"
                value={year}
                min={YEAR_MIN}
                max={YEAR_MAX}
                className={DASHBOARD_CONTROL_CLASS}
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
                <Label htmlFor="dashboard-month">{t("common.month")}</Label>
                <Select
                  value={String(month)}
                  onValueChange={(value) => updateSearchParams({ month: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })}
                >
                  <SelectTrigger id="dashboard-month" className={DASHBOARD_CONTROL_CLASS}>
                    <SelectValue placeholder={t("pages.dashboard.selectMonth")} />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 12 }, (_, index) => (
                      <SelectItem key={index + 1} value={String(index + 1)}>
                        {formatMonthName(index + 1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            {periodMode === "range" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="dashboard-start-month">{t("common.from")}</Label>
                  <Select
                    value={String(startMonth)}
                    onValueChange={(value) =>
                      updateSearchParams({ startMonth: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })
                    }
                  >
                    <SelectTrigger id="dashboard-start-month" className={DASHBOARD_CONTROL_CLASS}>
                      <SelectValue placeholder={t("pages.dashboard.startMonth")} />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 12 }, (_, index) => (
                        <SelectItem key={`start-${index + 1}`} value={String(index + 1)}>
                          {formatMonthName(index + 1)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dashboard-end-month">{t("common.to")}</Label>
                  <Select
                    value={String(endMonth)}
                    onValueChange={(value) =>
                      updateSearchParams({ endMonth: clampNumber(Number(value), MONTH_MIN, MONTH_MAX) })
                    }
                  >
                    <SelectTrigger id="dashboard-end-month" className={DASHBOARD_CONTROL_CLASS}>
                      <SelectValue placeholder={t("pages.dashboard.endMonth")} />
                    </SelectTrigger>
                    <SelectContent>
                      {Array.from({ length: 12 }, (_, index) => (
                        <SelectItem key={`end-${index + 1}`} value={String(index + 1)}>
                          {formatMonthName(index + 1)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            ) : null}

            {periodMode === "year" ? (
              <div className="space-y-2">
                <Label>{t("common.window")}</Label>
                <div className="flex h-9 items-center rounded-md border border-border/70 bg-[var(--app-dashboard-control)] px-3 text-sm text-foreground/85">
                  {t("pages.dashboard.janToDec")}
                </div>
              </div>
            ) : null}

            <div className="space-y-2">
              <Label>{t("pages.dashboard.retailers")}</Label>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    className={`w-full justify-start text-left ${DASHBOARD_CONTROL_CLASS}`}
                  >
                    {selectedRetailerSummary()}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className={`w-72 ${DASHBOARD_SURFACE_STRONG_CLASS}`}>
                  <DropdownMenuLabel>{t("pages.dashboard.filterRetailers")}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="mx-1 mb-1 w-[calc(100%-0.5rem)] justify-start"
                    onClick={() => updateSearchParams({ retailers: [] })}
                  >
                    {t("pages.dashboard.allRetailers")}
                  </Button>
                  {retailerOptions.length === 0 ? (
                    <p className="px-2 py-1 text-xs text-muted-foreground">{t("pages.dashboard.noRetailers")}</p>
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
              <Label htmlFor="dashboard-spend-view">{t("pages.dashboard.spendView")}</Label>
              <Select value={spendView} onValueChange={(nextView) => updateSearchParams({ spend: nextView as SpendView })}>
                <SelectTrigger id="dashboard-spend-view" className={DASHBOARD_CONTROL_CLASS}>
                  <SelectValue placeholder={t("pages.dashboard.selectSpendView")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="net">{t("pages.dashboard.spendView.net")}</SelectItem>
                  <SelectItem value="gross">{t("pages.dashboard.spendView.gross")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="dashboard-discount-view">{t("pages.dashboard.discountView")}</Label>
              <Select value={view} onValueChange={(nextView) => updateSearchParams({ view: nextView as DiscountView })}>
                <SelectTrigger id="dashboard-discount-view" className={DASHBOARD_CONTROL_CLASS}>
                  <SelectValue placeholder={t("pages.dashboard.selectDiscountView")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="native">{t("pages.dashboard.discountView.native")}</SelectItem>
                  <SelectItem value="normalized">{t("pages.dashboard.discountView.normalized")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {periodMode === "range" ? (
            <div className="flex flex-wrap gap-2">
              {RANGE_PRESETS.map((preset) => (
                <Button
                  key={preset.labelKey ?? preset.label}
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
                  {preset.labelKey ? t(preset.labelKey) : preset.label}
                </Button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {warnings.length > 0 ? (
        <Alert>
          <AlertTitle>{t("pages.dashboard.backendWarnings")}</AlertTitle>
          <AlertDescription>
            <ul className="list-inside list-disc space-y-1">
              {warnings.map((warning) => (
                <li key={`${warning.code ?? ""}:${warning.message}`}>
                  {resolveApiWarningMessage(warning, t)}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>{t("pages.dashboard.loadError")}</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <section
        className="rounded-xl border border-border/60 app-dashboard-surface"
        aria-labelledby="dashboard-summary-heading"
      >
        <h2 id="dashboard-summary-heading" className="sr-only">
          Dashboard summary
        </h2>
        {loading ? (
          <div className="grid gap-4 p-4 lg:grid-cols-3 2xl:grid-cols-5">
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
            <Skeleton className="h-20 rounded-lg" />
          </div>
        ) : (
          <div className="grid divide-y lg:divide-y-0 lg:divide-x divide-border/40 lg:grid-cols-3 2xl:grid-cols-5">
            <Link to={ledgerLink}>
              <MetricCard
                title={t("pages.dashboard.card.netSpend")}
                value={netSpendCents !== null ? formatEurFromCents(netSpendCents) : "—"}
                icon={<TrendingDown className="h-3.5 w-3.5" />}
                iconClassName="bg-primary/10 text-primary"
              />
            </Link>
            <Link to={ledgerLink}>
              <MetricCard
                title={t("pages.dashboard.card.grossSpend")}
                value={grossSpendCents !== null ? formatEurFromCents(grossSpendCents) : "—"}
                icon={<Euro className="h-3.5 w-3.5" />}
                iconClassName="bg-muted text-muted-foreground"
              />
            </Link>
            <Link to={savingsLedgerLink}>
              <MetricCard
                title={t("pages.dashboard.card.savings")}
                value={savingsCents !== null ? formatEurFromCents(savingsCents) : "—"}
                icon={<PiggyBank className="h-3.5 w-3.5" />}
                iconClassName="bg-success/10 text-success"
              />
            </Link>
            <Link to={savingsLedgerLink}>
              <MetricCard
                title={t("pages.dashboard.card.savingsRate")}
                value={savingsRatePct}
                icon={<Percent className="h-3.5 w-3.5" />}
                iconClassName="bg-chart-2/10 text-chart-2"
              />
            </Link>
            <MetricCard
              title={t("pages.dashboard.card.depositPaid")}
              value={depositQuery.data ? formatEurFromCents(depositQuery.data.total_paid_cents) : "—"}
              icon={<Package className="h-3.5 w-3.5" />}
              iconClassName="bg-amber-500/10 text-amber-600"
              subtitle={t("pages.dashboard.card.depositExcluded")}
            />
          </div>
        )}
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card className={DASHBOARD_SURFACE_CLASS}>
          <CardHeader>
            <CardTitle className="text-base">{t("pages.dashboard.upcomingBills")}</CardTitle>
          </CardHeader>
          <CardContent>
            {recurringCalendarQuery.isPending ? (
              <p className="text-sm text-muted-foreground">{t("pages.dashboard.loadingRecurringCalendar")}</p>
            ) : (recurringCalendarQuery.data?.days ?? []).length === 0 ? (
              <EmptyState title={t("pages.dashboard.emptyUpcomingBills")} />
            ) : (
              <ul className="divide-y divide-border/30">
                {(recurringCalendarQuery.data?.days ?? []).map((day) => (
                  <li
                    key={day.date}
                    className="flex items-start justify-between py-2.5"
                  >
                    <div>
                      <p className="text-sm font-medium">
                        {formatMonthDay(`${day.date}T00:00:00`)}
                      </p>
                      <p className="text-xs text-muted-foreground">{t("pages.dashboard.billCount", { count: day.count })}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold tabular-nums">
                        {formatEurFromCents(day.total_expected_cents)}
                      </p>
                      <p className="text-xs text-muted-foreground">{t("pages.dashboard.expected")}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card className={DASHBOARD_SURFACE_CLASS}>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">{t("pages.dashboard.forecastTitle")}</CardTitle>
            <CalendarCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {recurringForecastQuery.isPending ? (
              <p className="text-sm text-muted-foreground">{t("pages.dashboard.loadingForecast")}</p>
            ) : (recurringForecastQuery.data?.points ?? []).length === 0 ? (
              <EmptyState title={t("pages.dashboard.emptyForecast")} />
            ) : (
              <ul className="space-y-3">
                {(recurringForecastQuery.data?.points ?? []).map((point) => {
                  const widthPct = Math.max(
                    8,
                    Math.round((point.projected_cents / recurringForecastMax) * 100)
                  );
                  const label = formatMonthYear(`${point.period}-01T00:00:00`);
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
        <Card className={DASHBOARD_SURFACE_CLASS}>
          <CardHeader>
            <CardTitle className="text-base">{trendTitle}</CardTitle>
          </CardHeader>
          <CardContent>
            {trendPoints.length === 0 ? (
              <EmptyState title={t("pages.dashboard.emptyTrend")} />
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
                          {spendView === "gross" ? t("pages.dashboard.trendGross") : t("pages.dashboard.trendNet")}{" "}
                          {formatEurFromCents(spendCents)} | {t("pages.dashboard.trendNet")} {formatEurFromCents(netCents)} | {t("pages.dashboard.trendGross")}{" "}
                          {formatEurFromCents(grossCents)} | {t("pages.dashboard.trendSavings")} {formatEurFromCents(pointSavingsCents)}
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
              <CardTitle className="text-base">{t("pages.dashboard.savingsByType", { view: savingsViewLabel })}</CardTitle>
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant={breakdownDisplay === "chart" ? "default" : "outline"}
                  onClick={() => updateSearchParams({ breakdown: "chart" })}
                >
                  {t("pages.dashboard.chart")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={breakdownDisplay === "table" ? "default" : "outline"}
                  onClick={() => updateSearchParams({ breakdown: "table" })}
                >
                  {t("pages.dashboard.table")}
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {displayBreakdownRows.length === 0 ? (
              <EmptyState title={t("pages.dashboard.emptyBreakdown")} />
            ) : breakdownDisplay === "chart" ? (
              <ul className="space-y-3">
                {displayBreakdownRows.map((row) => {
                  const width = Math.max(8, Math.round((row.saved_cents / maxBreakdownSaved) * 100));
                  return (
                    <li key={row.type} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{row.label}</span>
                        <span className="text-muted-foreground">
                          {formatEurFromCents(row.saved_cents)} ({row.discount_events} {t("pages.dashboard.events").toLowerCase()})
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
                    <TableHead>{t("common.type")}</TableHead>
                    <TableHead>{t("pages.dashboard.saved")}</TableHead>
                    <TableHead>{t("pages.dashboard.events")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayBreakdownRows.map((row) => (
                    <TableRow key={row.type}>
                      <TableCell>{row.label}</TableCell>
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

      <Card className={DASHBOARD_SURFACE_CLASS}>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">{t("pages.dashboard.byRetailer")}</CardTitle>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={exportSnapshotAsJson}>
              {t("pages.dashboard.exportJson")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={exportSnapshotAsCsv}>
              {t("pages.dashboard.exportCsv")}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {exportStatus ? <p className="mb-3 text-xs text-muted-foreground">{exportStatus}</p> : null}
          {retailerRows.length === 0 ? (
            <EmptyState title={t("pages.dashboard.emptyRetailers")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("pages.dashboard.retailer")}</TableHead>
                  <TableHead>{spendColumnTitle}</TableHead>
                  <TableHead>{t("pages.dashboard.saved")}</TableHead>
                  <TableHead>{t("pages.dashboard.savedShare")}</TableHead>
                  <TableHead>{t("pages.dashboard.spendShare", { label: spendColumnTitle })}</TableHead>
                  <TableHead>{t("pages.dashboard.card.savingsRate")}</TableHead>
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
