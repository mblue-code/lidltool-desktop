import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, ChevronDown } from "lucide-react";

import { fetchDashboardYears } from "@/api/dashboard";
import { fetchMerchantSummary } from "@/api/merchants";
import { fetchReportPatterns, fetchReportTemplates } from "@/api/reports";
import { fetchSources } from "@/api/sources";
import { useDateRangeContext, type DateRangePreset } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/i18n";
import { directionLabel, financeCategoryLabel } from "@/lib/category-presentation";
import { formatEurFromCents } from "@/utils/format";

type MultiSelectOption = {
  value: string;
  label: string;
  description?: string;
};

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function downloadFile(filename: string, content: string) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function heatmapColor(rgb: string, intensity: number): string {
  const alpha = intensity > 0 ? Math.max(0.14, Math.min(1, intensity)) : 0.08;
  return `rgba(${rgb}, ${alpha})`;
}

function formatSelectionSummary(
  locale: string,
  options: MultiSelectOption[],
  selectedValues: string[],
  placeholder: string,
): string {
  if (selectedValues.length === 0) {
    return placeholder;
  }

  const labels = selectedValues.map((value) => {
    const option = options.find((entry) => entry.value === value);
    return option?.label ?? value;
  });

  if (labels.length <= 2) {
    return labels.join(", ");
  }

  return locale === "de" ? `${labels.length} ausgewählt` : `${labels.length} selected`;
}

function formatHeatmapMetric(locale: string, valueMode: string, amountCents: number, count: number): string {
  if (valueMode === "count") {
    return locale === "de" ? `${count} Belege` : `${count} receipts`;
  }
  return formatEurFromCents(amountCents);
}

function formatDateOnly(value: Date): string {
  const copy = new Date(value);
  copy.setHours(0, 0, 0, 0);
  const year = copy.getFullYear();
  const month = String(copy.getMonth() + 1).padStart(2, "0");
  const day = String(copy.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDays(value: Date, days: number): Date {
  const copy = new Date(value);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function startOfWeek(value: Date): Date {
  const copy = new Date(value);
  const weekday = (copy.getDay() + 6) % 7;
  copy.setDate(copy.getDate() - weekday);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function endOfWeek(value: Date): Date {
  return shiftDays(startOfWeek(value), 6);
}

function monthBounds(monthValue: string): { fromDate: string; toDate: string } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(monthValue);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const from = new Date(year, month - 1, 1);
  const to = new Date(year, month, 0);
  return { fromDate: formatDateOnly(from), toDate: formatDateOnly(to) };
}

function yearBounds(year: number): { fromDate: string; toDate: string } {
  return {
    fromDate: formatDateOnly(new Date(year, 0, 1)),
    toDate: formatDateOnly(new Date(year, 11, 31))
  };
}

function deriveWeekdayHeatmap(
  fallback: Array<{ weekday: number; amount_cents: number; count: number }>,
  matrixPoints: Array<{ weekday: number; hour: number; amount_cents: number; count: number }>
): Array<{ weekday: number; amount_cents: number; count: number }> {
  if (matrixPoints.length === 0) {
    return Array.from({ length: 7 }, (_, weekday) => (
      fallback.find((point) => point.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 }
    ));
  }

  const buckets = new Map<number, { weekday: number; amount_cents: number; count: number }>();
  for (const point of matrixPoints) {
    const current = buckets.get(point.weekday) ?? { weekday: point.weekday, amount_cents: 0, count: 0 };
    current.amount_cents += point.amount_cents;
    current.count += point.count;
    buckets.set(point.weekday, current);
  }

  return Array.from({ length: 7 }, (_, weekday) => (
    buckets.get(weekday) ?? fallback.find((point) => point.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 }
  ));
}

export function ReportsPage() {
  const { fromDate, toDate, setPreset, setCustomRange } = useDateRangeContext();
  const { locale, t } = useI18n();
  const copy = locale === "de"
    ? {
        sourceLabel: "Quelle",
        sourcePlaceholder: "Alle Quellen",
        sourceEmpty: "Keine Quellen vorhanden.",
        merchantLabel: "Händler",
        merchantPlaceholder: "Alle Händler",
        merchantEmpty: "Keine Händler für diese Auswahl.",
        clearSelection: "Auswahl zurücksetzen",
        weeklyHeatmapTitle: "Wochen-Heatmap",
        weeklyHeatmapDescription: "Ein Feld pro Wochentag. Dunklere Felder bedeuten mehr Ausgaben oder mehr Belege.",
        weekdayHourlyTitle: "Wochen- und Stunden-Heatmap",
        weekdayHourlyDescription: "Zeigt, an welchen Wochentagen und Stunden Ihre Aktivität konzentriert ist.",
        heatmapLegend: "Stärker = mehr Aktivität",
        receiptsShort: "Belege",
        hourAxis: "Stunde",
        dateRangeTitle: "Zeitraum",
        dateRangeDescription: "Wählen Sie hier direkt Wochen, Monate, Jahre oder einen eigenen Bereich für diese Auswertung.",
        currentRange: "Aktiver Zeitraum",
        lastWeek: "Letzte Woche",
        lastYear: "Letztes Jahr",
        allTime: "Gesamte Zeit",
        monthLabel: "Monat",
        yearLabel: "Jahr",
        customFrom: "Von",
        customTo: "Bis",
        pickYear: "Jahr wählen",
      }
    : {
        sourceLabel: "Source",
        sourcePlaceholder: "All sources",
        sourceEmpty: "No sources available.",
        merchantLabel: "Merchant",
        merchantPlaceholder: "All merchants",
        merchantEmpty: "No merchants for this selection.",
        clearSelection: "Clear selection",
        weeklyHeatmapTitle: "Weekly heatmap",
        weeklyHeatmapDescription: "One tile per weekday. Darker tiles mean more spend or more receipts.",
        weekdayHourlyTitle: "Weekly hourly heatmap",
        weekdayHourlyDescription: "Shows which weekday and hour combinations carry the most activity.",
        heatmapLegend: "Stronger = more activity",
        receiptsShort: "receipts",
        hourAxis: "Hour",
        dateRangeTitle: "Date range",
        dateRangeDescription: "Pick weeks, months, years, or a custom window directly on this report page.",
        currentRange: "Active range",
        lastWeek: "Last week",
        lastYear: "Last year",
        allTime: "All time",
        monthLabel: "Month",
        yearLabel: "Year",
        customFrom: "From",
        customTo: "To",
        pickYear: "Pick year",
      };
  const weekdayLabels = locale === "de"
    ? ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    : ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [selectedMerchants, setSelectedMerchants] = useState<string[]>([]);
  const [category, setCategory] = useState("all");
  const [direction, setDirection] = useState("all");
  const [valueMode, setValueMode] = useState("amount");
  const templates = useQuery({ queryKey: ["reports-page", fromDate, toDate], queryFn: () => fetchReportTemplates(fromDate, toDate) });
  const sourcesQuery = useQuery({ queryKey: ["reports-sources"], queryFn: fetchSources, staleTime: 0 });
  const yearsQuery = useQuery({
    queryKey: ["reports-years", selectedSourceIds],
    queryFn: () => fetchDashboardYears(selectedSourceIds),
    staleTime: 60_000
  });
  const merchantSummaryQuery = useQuery({
    queryKey: ["reports-merchants", fromDate, toDate],
    queryFn: () => fetchMerchantSummary(fromDate, toDate),
    staleTime: 0
  });
  const sourceOptions = (sourcesQuery.data?.sources ?? [])
    .slice()
    .sort((left, right) => left.display_name.localeCompare(right.display_name, locale))
    .map((source) => ({
      value: source.id,
      label: source.display_name,
      description: `${source.kind} · ${source.id}`,
    }));
  const merchantOptions = (merchantSummaryQuery.data?.items ?? [])
    .filter((merchant) => (
      selectedSourceIds.length === 0
      || merchant.source_ids.some((sourceId) => selectedSourceIds.includes(sourceId))
    ))
    .slice()
    .sort((left, right) => left.merchant.localeCompare(right.merchant, locale))
    .map((merchant) => ({
      value: merchant.merchant,
      label: merchant.merchant,
      description: merchant.source_ids.join(", "),
    }));

  useEffect(() => {
    if (!merchantSummaryQuery.data) {
      return;
    }
    const availableMerchants = new Set(
      merchantSummaryQuery.data.items
        .filter((merchant) => (
          selectedSourceIds.length === 0
          || merchant.source_ids.some((sourceId) => selectedSourceIds.includes(sourceId))
        ))
        .map((merchant) => merchant.merchant)
    );
    setSelectedMerchants((current) => {
      const next = current.filter((merchant) => availableMerchants.has(merchant));
      return next.length === current.length ? current : next;
    });
  }, [merchantSummaryQuery.data, selectedSourceIds]);

  const patterns = useQuery({
    queryKey: ["reports-patterns", fromDate, toDate, selectedSourceIds, selectedMerchants, category, direction, valueMode],
    queryFn: () => fetchReportPatterns({
      fromDate,
      toDate,
      merchants: selectedMerchants,
      financeCategoryId: category === "all" ? undefined : category,
      direction: direction === "all" ? undefined : direction,
      sourceIds: selectedSourceIds,
      valueMode
    })
  });
  const data = patterns.data;
  const matrixPoints = data?.weekday_hour_matrix ?? [];
  const weekdayHeatmap = deriveWeekdayHeatmap(data?.weekday_heatmap ?? [], matrixPoints);
  const maxWeekday = Math.max(1, ...weekdayHeatmap.map((point) => valueMode === "count" ? point.count : point.amount_cents));
  const maxMatrix = Math.max(1, ...matrixPoints.map((point) => valueMode === "count" ? point.count : point.amount_cents));
  const weeklyCards = weekdayLabels.map((label, weekday) => {
    const point = weekdayHeatmap.find((entry) => entry.weekday === weekday) ?? { weekday, amount_cents: 0, count: 0 };
    const rawValue = valueMode === "count" ? point.count : point.amount_cents;
    const metric = formatHeatmapMetric(locale, valueMode, point.amount_cents, point.count);
    return {
      label,
      weekday,
      count: point.count,
      metric,
      title: `${label}: ${metric}`,
      backgroundColor: heatmapColor("16, 185, 129", rawValue / maxWeekday)
    };
  });
  const matrixRows = weekdayLabels.map((label, weekday) => ({
    label,
    cells: HOURS.map((hour) => {
      const point = matrixPoints.find((entry) => entry.weekday === weekday && entry.hour === hour) ?? { amount_cents: 0, count: 0 };
      const rawValue = valueMode === "count" ? point.count : point.amount_cents;
      const metric = formatHeatmapMetric(locale, valueMode, point.amount_cents, point.count);
      return {
        hour,
        title: `${label}, ${hour}:00 - ${metric}`,
        ariaLabel: `${label}, ${hour}:00, ${metric}`,
        backgroundColor: heatmapColor("14, 165, 233", rawValue / maxMatrix)
      };
    })
  }));

  return (
    <div className="space-y-6">
      <PageHeader title={t("pages.reports.title")} description={t("pages.reports.description")} />
      <Card className="app-dashboard-surface border-border/60">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            {t("pages.reports.patterns.title")}
          </CardTitle>
          <CardDescription>{t("pages.reports.patterns.description")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <ReportDateRangePanel
            locale={locale}
            copy={copy}
            fromDate={fromDate}
            toDate={toDate}
            years={yearsQuery.data?.years ?? []}
            onSelectPreset={setPreset}
            onSelectRange={setCustomRange}
          />
          <div className="grid gap-3 md:grid-cols-4">
            <MultiSelectDropdown
              label={copy.sourceLabel}
              placeholder={copy.sourcePlaceholder}
              emptyText={copy.sourceEmpty}
              options={sourceOptions}
              selectedValues={selectedSourceIds}
              onChange={setSelectedSourceIds}
              locale={locale}
              clearLabel={copy.clearSelection}
            />
            <MultiSelectDropdown
              label={copy.merchantLabel}
              placeholder={copy.merchantPlaceholder}
              emptyText={copy.merchantEmpty}
              options={merchantOptions}
              selectedValues={selectedMerchants}
              onChange={setSelectedMerchants}
              locale={locale}
              clearLabel={copy.clearSelection}
            />
            <SelectBox label={t("pages.transactions.filter.category")} value={category} onChange={setCategory}>
              <SelectItem value="all">{t("pages.transactions.allCategories")}</SelectItem>
              {["groceries", "housing", "insurance", "credit", "mobility", "car", "investment", "subscriptions", "income", "fees", "tax", "other"].map((value) => (
                <SelectItem key={value} value={value}>{financeCategoryLabel(value, t)}</SelectItem>
              ))}
            </SelectBox>
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectBox label={t("pages.transactions.filter.direction")} value={direction} onChange={setDirection}>
                <SelectItem value="all">{t("pages.transactions.allDirections")}</SelectItem>
                {["outflow", "inflow", "transfer", "neutral"].map((value) => (
                  <SelectItem key={value} value={value}>{directionLabel(value, t)}</SelectItem>
                ))}
              </SelectBox>
              <SelectBox label={t("pages.reports.patterns.valueMode")} value={valueMode} onChange={setValueMode}>
                <SelectItem value="amount">{t("pages.reports.patterns.valueMode.amount")}</SelectItem>
                <SelectItem value="count">{t("pages.reports.patterns.valueMode.count")}</SelectItem>
              </SelectBox>
            </div>
          </div>

          <Card className="border-border/60 bg-background/30">
            <CardHeader>
              <CardTitle>{copy.weeklyHeatmapTitle}</CardTitle>
              <CardDescription>{copy.weeklyHeatmapDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>{copy.heatmapLegend}</span>
                <span>{valueMode === "count" ? copy.receiptsShort : t("pages.reports.patterns.valueMode.amount")}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-7">
                {weeklyCards.map((card) => (
                    <div
                      key={`${card.label}-${card.metric}-${card.count}`}
                      className="relative overflow-hidden rounded-2xl border border-border/60 p-4"
                      title={card.title}
                    >
                      <div
                        className="absolute inset-0"
                        style={{ backgroundColor: card.backgroundColor }}
                      />
                      <div className="relative space-y-10">
                        <div>
                          <p className="text-sm font-semibold">{card.label}</p>
                          <p className="text-xs text-muted-foreground">{card.metric}</p>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {card.count} {copy.receiptsShort}
                        </p>
                      </div>
                    </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-background/30">
            <CardHeader>
              <CardTitle>{copy.weekdayHourlyTitle}</CardTitle>
              <CardDescription>{copy.weekdayHourlyDescription}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-1 overflow-x-auto" style={{ gridTemplateColumns: "72px repeat(24, minmax(28px, 1fr))" }}>
                <div className="flex items-end text-[11px] font-medium text-muted-foreground">{copy.hourAxis}</div>
                {HOURS.map((hour) => (
                  <div key={hour} className="text-center text-[11px] text-muted-foreground">
                    {hour}
                  </div>
                ))}
                {matrixRows.map((row) => (
                  <FragmentRow
                    key={row.label}
                    label={row.label}
                    cells={row.cells.map((cell) => (
                        <div
                          key={`${row.label}-${cell.hour}-${cell.title}`}
                          aria-label={cell.ariaLabel}
                          className="h-8 rounded-md border border-border/40"
                          style={{ backgroundColor: cell.backgroundColor }}
                          title={cell.title}
                        />
                    ))}
                  />
                ))}
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.reports.patterns.merchantComparison")}</CardTitle>
              </CardHeader>
              <CardContent>
                {(data?.merchant_comparison ?? []).map((merchant) => (
                  <div key={merchant.merchant} className="flex justify-between gap-3 border-b border-border/60 py-2">
                    <span>{merchant.merchant}</span>
                    <span className="text-muted-foreground">{merchant.count} {copy.receiptsShort}</span>
                    <strong>{formatEurFromCents(merchant.amount_cents)}</strong>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>{t("pages.reports.patterns.insights")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {(data?.insights ?? []).map((insight, index) => <Insight key={index} insight={insight} />)}
              </CardContent>
            </Card>
          </div>
        </CardContent>
      </Card>
      <div className="grid gap-4 xl:grid-cols-3">
        {(templates.data?.templates ?? []).map((template) => (
          <Card key={template.slug} className="app-dashboard-surface border-border/60">
            <CardHeader>
              <CardTitle>{t((`pages.reports.template.${template.slug}.title`) as never)}</CardTitle>
              <CardDescription>{t((`pages.reports.template.${template.slug}.description`) as never)}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button type="button" onClick={() => downloadFile(`${template.slug}.json`, JSON.stringify(template.payload, null, 2))}>
                {t("pages.reports.exportJson")}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );

  function Insight({ insight }: { insight: Record<string, unknown> }) {
    const kind = String(insight.kind || "");
    if (kind === "top_day") {
      return <InsightRow title={t("pages.reports.patterns.insight.topDay")} body={t("pages.reports.patterns.insight.topDayBody", { date: String(insight.date), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    }
    if (kind === "top_merchant") {
      return <InsightRow title={t("pages.reports.patterns.insight.topMerchant")} body={t("pages.reports.patterns.insight.topMerchantBody", { merchant: String(insight.merchant), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
    }
    return <InsightRow title={t("pages.reports.patterns.insight.merchantGap")} body={t("pages.reports.patterns.insight.merchantGapBody", { merchant: String(insight.merchant || ""), amount: formatEurFromCents(Number(insight.amount_cents || 0)) })} />;
  }
}

function FragmentRow({ label, cells }: { label: string; cells: ReactNode[] }) {
  return (
    <>
      <div className="flex items-center text-sm font-medium">{label}</div>
      {cells}
    </>
  );
}

function MultiSelectDropdown({
  label,
  placeholder,
  emptyText,
  options,
  selectedValues,
  onChange,
  locale,
  clearLabel,
}: {
  label: string;
  placeholder: string;
  emptyText: string;
  options: MultiSelectOption[];
  selectedValues: string[];
  onChange: (values: string[]) => void;
  locale: string;
  clearLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    function handlePointerDown(event: MouseEvent) {
      if (containerRef.current?.contains(event.target as Node)) {
        return;
      }
      setOpen(false);
    }
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, [open]);

  return (
    <div ref={containerRef} className="relative space-y-2">
      <Label>{label}</Label>
      <Button type="button" variant="outline" className="w-full justify-between" onClick={() => setOpen((current) => !current)}>
        <span className="truncate text-left">
          {formatSelectionSummary(locale, options, selectedValues, placeholder)}
        </span>
        <ChevronDown className="h-4 w-4 opacity-70" />
      </Button>
      {open ? (
        <div className="absolute z-20 mt-2 max-h-72 w-full overflow-y-auto rounded-xl border border-border/70 bg-popover/95 p-1.5 shadow-2xl ring-1 ring-white/5 supports-[backdrop-filter]:bg-popover/85 supports-[backdrop-filter]:backdrop-blur-xl">
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</span>
            <button
              type="button"
              className="text-xs font-medium text-muted-foreground transition hover:text-foreground disabled:opacity-50"
              disabled={selectedValues.length === 0}
              onClick={() => onChange([])}
            >
              {clearLabel}
            </button>
          </div>
          {options.length === 0 ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">{emptyText}</div>
          ) : (
            options.map((option) => {
              const checked = selectedValues.includes(option.value);
              return (
                <label key={option.value} className="flex cursor-pointer items-start gap-3 rounded-md px-2.5 py-2 text-sm transition hover:bg-accent/80">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(event) => {
                      if (event.target.checked) {
                        onChange(checked ? selectedValues : [...selectedValues, option.value]);
                        return;
                      }
                      onChange(selectedValues.filter((value) => value !== option.value));
                    }}
                  />
                  <span className="flex min-w-0 flex-col">
                    <span>{option.label}</span>
                    {option.description ? <span className="text-xs text-muted-foreground">{option.description}</span> : null}
                  </span>
                </label>
              );
            })
          )}
        </div>
      ) : null}
    </div>
  );
}

function SelectBox({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger><SelectValue /></SelectTrigger>
        <SelectContent>{children}</SelectContent>
      </Select>
    </div>
  );
}

function InsightRow({ title, body }: { title: string; body: string }) {
  return <div className="rounded-lg border border-border/60 p-3"><p className="font-medium">{title}</p><p className="text-sm text-muted-foreground">{body}</p></div>;
}

function ReportDateRangePanel({
  locale,
  copy,
  fromDate,
  toDate,
  years,
  onSelectPreset,
  onSelectRange,
}: {
  locale: string;
  copy: {
    dateRangeTitle: string;
    dateRangeDescription: string;
    currentRange: string;
    lastWeek: string;
    lastYear: string;
    allTime: string;
    monthLabel: string;
    yearLabel: string;
    customFrom: string;
    customTo: string;
    pickYear: string;
  };
  fromDate: string;
  toDate: string;
  years: number[];
  onSelectPreset: (preset: DateRangePreset) => void;
  onSelectRange: (fromDate: string, toDate: string) => void;
}) {
  const today = new Date();
  const currentMonthValue = fromDate.slice(0, 7);
  const currentYearValue = fromDate.slice(0, 4);
  const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
  const currentRangeLabel = `${formatter.format(new Date(fromDate))} - ${formatter.format(new Date(toDate))}`;

  return (
    <div className="rounded-2xl border border-border/60 bg-background/40 p-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold">{copy.dateRangeTitle}</p>
          <p className="text-sm text-muted-foreground">{copy.dateRangeDescription}</p>
        </div>
        <div className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{copy.currentRange}:</span> {currentRangeLabel}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => onSelectPreset("this_week")}>
          {locale === "de" ? "Diese Woche" : "This week"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const end = shiftDays(startOfWeek(today), -1);
            const start = shiftDays(startOfWeek(today), -7);
            onSelectRange(formatDateOnly(start), formatDateOnly(end));
          }}
        >
          {copy.lastWeek}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => onSelectPreset("last_month")}>
          {locale === "de" ? "Letzter Monat" : "Last month"}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const previousYear = today.getFullYear() - 1;
            const bounds = yearBounds(previousYear);
            onSelectRange(bounds.fromDate, bounds.toDate);
          }}
        >
          {copy.lastYear}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={years.length === 0}
          onClick={() => {
            if (years.length === 0) {
              return;
            }
            const firstYear = Math.min(...years);
            onSelectRange(`${firstYear}-01-01`, formatDateOnly(today));
          }}
        >
          {copy.allTime}
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-4">
        <div className="space-y-2">
          <Label>{copy.monthLabel}</Label>
          <input
            type="month"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={currentMonthValue}
            onChange={(event) => {
              const next = monthBounds(event.target.value);
              if (next) {
                onSelectRange(next.fromDate, next.toDate);
              }
            }}
          />
        </div>
        <div className="space-y-2">
          <Label>{copy.yearLabel}</Label>
          <select
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={years.includes(Number(currentYearValue)) ? currentYearValue : ""}
            onChange={(event) => {
              if (!event.target.value) {
                return;
              }
              const bounds = yearBounds(Number(event.target.value));
              onSelectRange(bounds.fromDate, bounds.toDate);
            }}
          >
            <option value="">{copy.pickYear}</option>
            {years.map((year) => (
              <option key={year} value={String(year)}>
                {year}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label>{copy.customFrom}</Label>
          <input
            type="date"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={fromDate}
            onChange={(event) => onSelectRange(event.target.value, toDate)}
          />
        </div>
        <div className="space-y-2">
          <Label>{copy.customTo}</Label>
          <input
            type="date"
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={toDate}
            onChange={(event) => onSelectRange(fromDate, event.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
