import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  CalendarCheck,
  Database,
  ReceiptText,
  TrendingUp,
  Wallet
} from "lucide-react";
import { Link } from "react-router-dom";

import { useDateRangeContext } from "@/app/date-range-context";
import { fetchDashboardOverview } from "@/api/dashboard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useI18n } from "@/i18n";
import { financeCategoryLabel, groceryCategoryLabel } from "@/lib/category-presentation";
import { formatDate, formatEurFromCents } from "@/utils/format";

function sectionTitle(title: string, actionHref?: string, actionLabel?: string) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      {actionHref && actionLabel ? (
        <Button asChild variant="ghost" size="sm">
          <Link to={actionHref}>{actionLabel}</Link>
        </Button>
      ) : null}
    </div>
  );
}

function goalProgressStatusLabel(status: string, locale: "en" | "de"): string {
  if (status === "completed") return locale === "de" ? "Abgeschlossen" : "Completed";
  if (status === "at_risk") return locale === "de" ? "Gefährdet" : "At risk";
  if (status === "on_track") return locale === "de" ? "Im Plan" : "On track";
  if (status === "paused") return locale === "de" ? "Pausiert" : "Paused";
  return status.replace(/_/g, " ");
}

function titleCase(value: string): string {
  return value
    .split(/[\s_:]+/)
    .filter(Boolean)
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1).toLowerCase()}`)
    .join(" ");
}

function categoryLabel(category: string, locale: "en" | "de"): string {
  const normalized = category.trim().toLowerCase();
  if (locale === "de") {
    const labels: Record<string, string> = {
      "groceries": "Lebensmittel",
      "groceries:bakery": "Backwaren",
      "groceries:beverages": "Getränke",
      "groceries:dairy": "Molkereiprodukte",
      "groceries:fish": "Fisch",
      "groceries:frozen": "Tiefkühlkost",
      "groceries:household": "Haushalt",
      "groceries:meat": "Fleisch",
      "groceries:pantry": "Vorrat",
      "groceries:produce": "Obst & Gemüse",
      "groceries:snacks": "Snacks",
      "deposit": "Pfand",
      "household": "Haushalt",
      "other": "Sonstiges",
      "uncategorized": "Unkategorisiert"
    };
    return labels[normalized] ?? titleCase(category);
  }
  return titleCase(category);
}

function activitySubtitleLabel(subtitle: string, locale: "en" | "de"): string {
  if (locale !== "de") return subtitle;
  const labels: Record<string, string> = {
    "Transaction imported": "Transaktion importiert",
    "Inflow": "Zufluss",
    "Outflow": "Abfluss",
    "Upcoming": "Anstehend",
    "Due": "Fällig",
    "Overdue": "Überfällig"
  };
  return labels[subtitle] ?? subtitle;
}

function insightTitleLabel(insight: { kind: string; title: string }, locale: "en" | "de"): string {
  if (locale === "de" && insight.kind === "spend_change") {
    return "Ausgabenentwicklung";
  }
  return insight.title;
}

function insightBodyLabel(
  insight: { kind: string; body: string; delta_cents: number },
  locale: "en" | "de"
): string {
  if (locale !== "de" || insight.kind !== "spend_change") {
    return insight.body;
  }
  if (insight.delta_cents < 0) {
    return "Die Nettoausgaben liegen unter dem vorherigen Vergleichszeitraum.";
  }
  if (insight.delta_cents > 0) {
    return "Die Nettoausgaben liegen über dem vorherigen Vergleichszeitraum.";
  }
  return "Die Nettoausgaben entsprechen dem vorherigen Vergleichszeitraum.";
}

function deltaLabel(deltaPct: number | null, locale: "en" | "de"): string {
  if (deltaPct === null) {
    return locale === "de" ? "Kein Vergleichszeitraum" : "No previous comparison";
  }
  return locale === "de"
    ? `${Math.abs(deltaPct * 100).toFixed(1)}% zum vorherigen Zeitraum`
    : `${Math.abs(deltaPct * 100).toFixed(1)}% vs previous period`;
}

function DeltaPill({ deltaPct, locale }: { deltaPct: number | null; locale: "en" | "de" }) {
  const positive = (deltaPct ?? 0) > 0;
  const negative = (deltaPct ?? 0) < 0;
  const Icon = positive ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={[
        "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold",
        positive ? "bg-rose-50 text-rose-600" : "",
        negative ? "bg-emerald-50 text-emerald-600" : "",
        !positive && !negative ? "bg-slate-100 text-slate-500" : ""
      ].join(" ")}
    >
      {(positive || negative) && <Icon className="h-3.5 w-3.5" />}
      {deltaLabel(deltaPct, locale)}
    </span>
  );
}

function RingChart({
  categories,
  totalCents,
  locale,
  labelForCategory
}: {
  categories: Array<{ category: string; amount_cents: number; share: number }>;
  totalCents: number;
  locale: "en" | "de";
  labelForCategory?: (category: string) => string;
}) {
  const colors = ["#14b8a6", "#2563eb", "#7c3aed", "#fb923c", "#ec4899", "#cbd5e1"];
  const visibleCategories = categories.filter((item) => item.amount_cents > 0 && item.share > 0);
  const hasData = totalCents > 0 && visibleCategories.length > 0;
  const gradient = useMemo(() => {
    let offset = 0;
    return visibleCategories
      .map((item, index) => {
        const next = offset + item.share * 100;
        const slice = `${colors[index % colors.length]} ${offset}% ${next}%`;
        offset = next;
        return slice;
      })
      .join(", ");
  }, [visibleCategories]);

  if (!hasData) {
    return (
      <div className="app-soft-surface flex min-h-[270px] flex-col items-center justify-center rounded-lg border border-dashed border-border/70 px-6 py-10 text-center">
        <ReceiptText className="h-10 w-10 text-muted-foreground/70" />
        <p className="mt-4 text-base font-semibold">
          {locale === "de" ? "Noch keine Ausgaben im gewählten Zeitraum" : "No spending in the selected period yet"}
        </p>
        <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">
          {locale === "de"
            ? "Importiere Belege oder erfasse eine Ausgabe, damit die Kategorienübersicht hier erscheint."
            : "Import receipts or add spending, then the category breakdown will appear here."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-6 2xl:grid-cols-[240px_minmax(0,1fr)]">
      <div className="flex items-center justify-center">
        <div
          className="relative h-[220px] w-[220px] rounded-full"
          style={{ background: `conic-gradient(${gradient || "#e2e8f0 0 100%"})` }}
        >
          <div className="absolute inset-[26px] flex flex-col items-center justify-center rounded-full border border-white/10 bg-slate-950 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
            <span className="app-value max-w-[150px] truncate text-center text-3xl font-semibold text-slate-100">{formatEurFromCents(totalCents)}</span>
            <span className="mt-2 text-sm text-slate-300">{locale === "de" ? "Nettoausgaben" : "Net spend"}</span>
          </div>
        </div>
      </div>

      <div className="min-w-0 space-y-3">
        {visibleCategories.map((item, index) => (
          <div key={item.category} className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border-b border-border/60 py-3 last:border-b-0 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto]">
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: colors[index % colors.length] }} />
            <span className="min-w-0 truncate font-medium" title={labelForCategory ? labelForCategory(item.category) : categoryLabel(item.category, locale)}>
              {labelForCategory ? labelForCategory(item.category) : categoryLabel(item.category, locale)}
            </span>
            <span className="text-sm tabular-nums text-muted-foreground">{(item.share * 100).toFixed(1)}%</span>
            <span className="hidden whitespace-nowrap text-right font-semibold tabular-nums sm:block">{formatEurFromCents(item.amount_cents)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CashFlowBars({
  points,
  locale
}: {
  points: Array<{ date: string; label?: string; inflow_cents: number; outflow_cents: number; net_cents: number }>;
  locale: "en" | "de";
}) {
  const maxAbs = Math.max(
    1,
    ...points.flatMap((point) => [Math.abs(point.inflow_cents), Math.abs(point.outflow_cents), Math.abs(point.net_cents)])
  );
  return (
    <div className="grid gap-3">
      <div className="grid h-64 grid-cols-[repeat(auto-fit,minmax(36px,1fr))] items-end gap-4">
        {points.map((point) => {
          const inflowHeight = Math.max(8, (Math.abs(point.inflow_cents) / maxAbs) * 170);
          const outflowHeight = Math.max(8, (Math.abs(point.outflow_cents) / maxAbs) * 170);
          const netBottom = 30 + (Math.max(point.net_cents, 0) / maxAbs) * 140;
          return (
            <div key={point.date} className="relative flex h-full flex-col items-center justify-end gap-3">
              <div className="relative flex h-[220px] w-full items-end justify-center gap-1">
                <div className="w-3 rounded-full bg-emerald-400" style={{ height: inflowHeight }} />
                <div className="w-3 rounded-full bg-rose-400" style={{ height: outflowHeight }} />
                <div className="absolute left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full border-2 border-slate-900 bg-white" style={{ bottom: `${netBottom}px` }} />
              </div>
              <span className="text-xs text-muted-foreground">{point.label ?? formatDate(point.date)}</span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-emerald-400" /> {locale === "de" ? "Einnahmen" : "Inflow"}</span>
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-rose-400" /> {locale === "de" ? "Ausgaben" : "Outflow"}</span>
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-slate-900" /> {locale === "de" ? "Netto" : "Net"}</span>
      </div>
    </div>
  );
}

function ProgressRow({
  label,
  spentCents,
  budgetCents,
  utilization
}: {
  label: string;
  spentCents: number;
  budgetCents: number;
  utilization: number;
}) {
  const percent = Math.min(100, Math.round(utilization * 100));
  return (
    <div className="space-y-2 border-b border-border/60 py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium capitalize">{label.replace(/_/g, " ")}</span>
        <span className="text-sm text-muted-foreground">
          {formatEurFromCents(spentCents)} / {formatEurFromCents(budgetCents)}
        </span>
      </div>
      <div className="h-2 rounded-full bg-slate-100">
        <div className="h-2 rounded-full bg-emerald-400" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale, t } = useI18n();
  const [selectedSourceId, setSelectedSourceId] = useState("all");
  const selectedSourceIds = selectedSourceId === "all" ? undefined : [selectedSourceId];
  const dataKey = `${fromDate}:${toDate}:${selectedSourceId}`;
  const copy = locale === "de"
    ? {
        pageTitle: "Ihre Finanzübersicht",
        pageDescription: "Verfolge Ausgaben, Einkäufe, Cashflow, Rechnungen und Händler aus demselben lokalen Desktop-Profil.",
        totalSpending: "Gesamtausgaben",
        purchases: "Einkäufe",
        cashInflow: "Cashflow-Zufluss",
        cashOutflow: "Cashflow-Abfluss",
        spendingOverview: "Ausgabenübersicht",
        cashFlowSummary: "Cashflow-Zusammenfassung",
        upcomingBills: "Anstehende Rechnungen",
        recentGroceryTransactions: "Aktuelle Einkaufstransaktionen",
        budgetProgress: "Budgetfortschritt",
        recentActivity: "Letzte Aktivitäten",
        viewAll: "Alle anzeigen",
        openDetails: "Details öffnen",
        manageMerchants: "Händler verwalten",
        manageGoals: "Ziele verwalten",
        workspaceStatus: "Arbeitsstatus",
        activityItems: "Aktivitäts-Einträge",
        activeMerchants: "Aktive Händler",
        merchants: "Händler",
        goals: "Ziele",
        merchantFilter: "Händlerfilter",
        allMerchants: "Alle Händler"
      }
    : {
        pageTitle: "Your finance overview",
        pageDescription: "Track spend, groceries, cash movement, bills, and merchants from the same local-first desktop profile.",
        totalSpending: "Total spending",
        purchases: "Purchases",
        cashInflow: "Cash inflow",
        cashOutflow: "Cash outflow",
        spendingOverview: "Spending overview",
        cashFlowSummary: "Cash flow summary",
        upcomingBills: "Upcoming bills",
        recentGroceryTransactions: "Recent grocery transactions",
        budgetProgress: "Budget progress",
        recentActivity: "Recent activity",
        viewAll: "View all",
        openDetails: "Open details",
        manageMerchants: "Manage merchants",
        manageGoals: "Manage goals",
        workspaceStatus: "Workspace status",
        activityItems: "Activity items",
        activeMerchants: "Active merchants",
        merchants: "Merchants",
        goals: "Goals",
        merchantFilter: "Merchant filter",
        allMerchants: "All merchants"
      };
  const overviewQuery = useQuery({
    queryKey: ["dashboard-overview", fromDate, toDate, selectedSourceId],
    queryFn: () => fetchDashboardOverview(fromDate, toDate, selectedSourceIds),
    staleTime: 0
  });
  const overview = overviewQuery.data?.period.from_date === fromDate && overviewQuery.data.period.to_date === toDate
    && (selectedSourceId === "all" || overviewQuery.data.selected_source_ids.includes(selectedSourceId))
    ? overviewQuery.data
    : undefined;
  const sourceFilters = overview?.source_filters ?? overviewQuery.data?.source_filters ?? [];
  const periodLabel = useMemo(() => {
    const start = new Date(fromDate);
    const end = new Date(toDate);
    const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
      month: "short",
      day: "numeric"
    });
    return `${formatter.format(start)} - ${formatter.format(end)}`;
  }, [fromDate, locale, toDate]);
  const cashFlowSummaryPoints = useMemo(() => {
    if (!overview) return [];
    const totals = overview.cash_flow_summary.totals;
    return [
      {
        date: toDate,
        label: periodLabel,
        inflow_cents: totals.inflow_cents,
        outflow_cents: totals.outflow_cents,
        net_cents: totals.net_cents
      }
    ];
  }, [overview, periodLabel, toDate]);

  return (
    <div className="space-y-6">
      <section className="app-dashboard-surface-strong rounded-xl border border-border/60 px-5 py-6 lg:px-7">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-400">Dashboard</p>
            <h1 className="mt-2 text-3xl font-semibold text-white md:text-4xl">{copy.pageTitle}</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
              {copy.pageDescription}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end xl:flex-col xl:items-end">
            <div className="min-w-[210px]">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                {copy.merchantFilter}
              </span>
              <Select value={selectedSourceId} onValueChange={setSelectedSourceId}>
                <SelectTrigger className="h-10 border-white/10 bg-white/6 text-slate-100">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{copy.allMerchants}</SelectItem>
                  {sourceFilters.map((source) => (
                    <SelectItem key={source.source_id} value={source.source_id}>
                      {source.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div
              key={`${fromDate}:${toDate}`}
              className="rounded-lg border border-white/10 bg-white/6 px-4 py-3 text-sm font-medium text-slate-200"
            >
              {periodLabel}
            </div>
          </div>
        </div>
      </section>

      <div key={`kpis:${dataKey}`} className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
        {overview ? (
          <>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{copy.totalSpending}</span>
                  <Wallet className="h-5 w-5 text-rose-500" />
                </div>
                <div className="app-value text-3xl font-semibold">{formatEurFromCents(overview.kpis.total_spending.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.total_spending.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{copy.purchases}</span>
                  <ReceiptText className="h-5 w-5 text-emerald-500" />
                </div>
                <div className="app-value text-3xl font-semibold">{formatEurFromCents(overview.kpis.groceries.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.groceries.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{copy.cashInflow}</span>
                  <ArrowDownRight className="h-5 w-5 text-emerald-500" />
                </div>
                <div className="app-value text-3xl font-semibold">{formatEurFromCents(overview.kpis.cash_inflow.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.cash_inflow.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{copy.cashOutflow}</span>
                  <ArrowUpRight className="h-5 w-5 text-rose-500" />
                </div>
                <div className="app-value text-3xl font-semibold">{formatEurFromCents(overview.kpis.cash_outflow.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.cash_outflow.delta_pct} locale={locale} />
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>

      {overview ? (
        <>
          <div key={`main:${dataKey}`} className="grid gap-4 xl:grid-cols-2">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(t("pages.dashboard.overallSpending"), "/transactions?direction_filter=outflow", t("pages.dashboard.viewTransactions"))}</CardHeader>
              <CardContent>
                <RingChart
                  categories={overview.overall_spending.categories}
                  totalCents={overview.overall_spending.total_cents}
                  locale={locale}
                  labelForCategory={(category) => financeCategoryLabel(category, t)}
                />
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(t("pages.dashboard.grocerySpending"), "/groceries", t("pages.dashboard.viewGroceries"))}</CardHeader>
              <CardContent>
                <RingChart
                  categories={overview.grocery_spending.categories}
                  totalCents={overview.grocery_spending.total_cents}
                  locale={locale}
                  labelForCategory={(category) => groceryCategoryLabel(category, t)}
                />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1fr_0.82fr]">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.cashFlowSummary, "/cash-flow", locale === "de" ? "Cashflow anzeigen" : "View cash flow")}</CardHeader>
              <CardContent>
                <CashFlowBars points={cashFlowSummaryPoints} locale={locale} />
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.upcomingBills, "/bills", copy.viewAll)}</CardHeader>
              <CardContent className="space-y-3">
                {overview.upcoming_bills.items.map((bill) => (
                  <div key={bill.occurrence_id} className="app-row-surface flex items-center justify-between gap-3 rounded-lg px-4 py-3">
                    <div>
                      <p className="font-medium">{bill.bill_name}</p>
                      <p className="text-sm text-muted-foreground">{formatDate(bill.due_date)}</p>
                    </div>
                    <div className="app-value text-right font-semibold">{formatEurFromCents(bill.expected_amount_cents ?? 0)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <div key={`activity:${dataKey}`} className="grid gap-4 xl:grid-cols-[1.15fr_0.9fr_0.85fr]">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.recentGroceryTransactions, "/transactions", copy.viewAll)}</CardHeader>
              <CardContent className="space-y-3">
                {overview.recent_grocery_transactions.items.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 border-b border-border/60 py-3 last:border-b-0">
                    <div>
                      <p className="font-medium">{item.store_name || item.source_id}</p>
                      <p className="text-sm text-muted-foreground">{formatDate(item.purchased_at)}</p>
                    </div>
                    <div className="app-value font-semibold">{formatEurFromCents(item.total_gross_cents)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.budgetProgress, "/budget", copy.viewAll)}</CardHeader>
              <CardContent>
                {overview.budget_progress.items.map((item) => (
                  <ProgressRow
                    key={item.rule_id}
                    label={item.scope_value}
                    spentCents={item.spent_cents}
                    budgetCents={item.budget_cents}
                    utilization={item.utilization}
                  />
                ))}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.recentActivity, "/transactions", copy.viewAll)}</CardHeader>
              <CardContent className="space-y-3">
                {overview.recent_activity.items.map((item) => (
                  <Link key={item.id} to={item.href} className="flex items-center justify-between gap-3 border-b border-border/60 py-3 last:border-b-0">
                    <div className="min-w-0">
                      <p className="font-medium">{item.title}</p>
                      <p className="truncate text-sm text-muted-foreground">{activitySubtitleLabel(item.subtitle, locale)}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{formatEurFromCents(item.amount_cents)}</p>
                      <p className="text-xs text-muted-foreground">{formatDate(item.occurred_at)}</p>
                    </div>
                  </Link>
                ))}
              </CardContent>
            </Card>
          </div>

          <Card className="app-dashboard-surface border-border/60">
            <CardContent className="flex flex-col gap-4 p-6 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex items-start gap-4">
                <div className="rounded-2xl bg-sky-50 p-3 text-sky-600">
                  <TrendingUp className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-lg font-semibold">{insightTitleLabel(overview.insight, locale)}</p>
                  <p className="mt-1 text-muted-foreground">{insightBodyLabel(overview.insight, locale)}</p>
                </div>
              </div>
              <Button asChild variant="outline">
                <Link to={overview.insight.href}>{copy.openDetails}</Link>
              </Button>
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(locale === "de" ? "Händler" : "Merchants", "/merchants", copy.manageMerchants)}</CardHeader>
              <CardContent className="space-y-3">
                {overview.merchants.items.map((merchant) => (
                  <div key={merchant.merchant} className="app-row-surface flex items-center justify-between gap-3 rounded-lg px-4 py-3">
                    <div>
                      <p className="font-medium">{merchant.merchant}</p>
                      <p className="text-sm text-muted-foreground">
                        {locale === "de" ? `${merchant.receipt_count} Belege` : `${merchant.receipt_count} receipts`}
                      </p>
                    </div>
                    <div className="app-value font-semibold">{formatEurFromCents(merchant.spend_cents)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(locale === "de" ? "Ziele" : "Goals", "/goals", copy.manageGoals)}</CardHeader>
              <CardContent className="space-y-3">
                {(overview.top_goals?.items ?? []).map((goal) => {
                  const percent = Math.min(100, Math.round(goal.progress.progress_ratio * 100));
                  return (
                    <div key={goal.id} className="app-row-surface space-y-2 rounded-lg px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-medium">{goal.name}</p>
                          <p className="text-sm text-muted-foreground">{goalProgressStatusLabel(goal.progress.status, locale)}</p>
                        </div>
                        <div className="app-value font-semibold">{formatEurFromCents(goal.target_amount_cents)}</div>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div className="h-2 rounded-full bg-sky-500" style={{ width: `${percent}%` }} />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle(copy.workspaceStatus)}</CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-3">
                <div className="app-row-surface rounded-lg p-4">
                  <Activity className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">{copy.activityItems}</p>
                  <p className="mt-2 text-2xl font-semibold">{overview.recent_activity.count}</p>
                </div>
                <div className="app-row-surface rounded-lg p-4">
                  <CalendarCheck className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">{copy.upcomingBills}</p>
                  <p className="mt-2 text-2xl font-semibold">{overview.upcoming_bills.count}</p>
                </div>
                <div className="app-row-surface rounded-lg p-4">
                  <Database className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">{copy.activeMerchants}</p>
                  <p className="mt-2 text-2xl font-semibold">{overview.merchants.count}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
