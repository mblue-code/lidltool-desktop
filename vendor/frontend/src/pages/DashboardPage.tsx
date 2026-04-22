import { useMemo } from "react";
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
import { useI18n } from "@/i18n";
import { formatDate, formatEurFromCents } from "@/utils/format";

function sectionTitle(title: string, actionHref?: string, actionLabel?: string) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <h2 className="text-xl font-semibold tracking-[-0.02em]">{title}</h2>
      </div>
      {actionHref && actionLabel ? (
        <Button asChild variant="ghost" size="sm">
          <Link to={actionHref}>{actionLabel}</Link>
        </Button>
      ) : null}
    </div>
  );
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
  locale
}: {
  categories: Array<{ category: string; amount_cents: number; share: number }>;
  totalCents: number;
  locale: "en" | "de";
}) {
  const colors = ["#14b8a6", "#2563eb", "#7c3aed", "#fb923c", "#ec4899", "#cbd5e1"];
  const gradient = useMemo(() => {
    let offset = 0;
    return categories
      .map((item, index) => {
        const next = offset + item.share * 100;
        const slice = `${colors[index % colors.length]} ${offset}% ${next}%`;
        offset = next;
        return slice;
      })
      .join(", ");
  }, [categories]);

  return (
    <div className="grid gap-6 xl:grid-cols-[280px_1fr]">
      <div className="flex items-center justify-center">
        <div
          className="relative h-[240px] w-[240px] rounded-full"
          style={{ background: `conic-gradient(${gradient || "#e2e8f0 0 100%"})` }}
        >
          <div className="absolute inset-[26px] flex flex-col items-center justify-center rounded-full bg-white">
            <span className="text-4xl font-semibold tracking-[-0.03em]">{formatEurFromCents(totalCents)}</span>
            <span className="mt-2 text-sm text-muted-foreground">{locale === "de" ? "Nettoausgaben" : "Net spend"}</span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {categories.map((item, index) => (
          <div key={item.category} className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-3 border-b border-border/60 py-3 last:border-b-0">
            <span className="h-3 w-3 rounded-full" style={{ backgroundColor: colors[index % colors.length] }} />
            <span className="font-medium capitalize">{item.category.replace(/:/g, " ")}</span>
            <span className="text-sm text-muted-foreground">{(item.share * 100).toFixed(1)}%</span>
            <span className="font-semibold">{formatEurFromCents(item.amount_cents)}</span>
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
  points: Array<{ date: string; inflow_cents: number; outflow_cents: number; net_cents: number }>;
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
          const outflowHeight = Math.max(8, (Math.abs(point.outflow_cents) / maxAbs) * 70);
          const netBottom = 30 + (Math.max(point.net_cents, 0) / maxAbs) * 140;
          return (
            <div key={point.date} className="relative flex h-full flex-col items-center justify-end gap-3">
              <div className="relative flex h-[220px] w-full items-end justify-center gap-1">
                <div className="w-3 rounded-full bg-emerald-400" style={{ height: inflowHeight }} />
                <div className="w-3 rounded-full bg-rose-400" style={{ height: outflowHeight }} />
                <div className="absolute left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full border-2 border-slate-900 bg-white" style={{ bottom: `${netBottom}px` }} />
              </div>
              <span className="text-xs text-muted-foreground">{formatDate(point.date)}</span>
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-emerald-400" /> {locale === "de" ? "Einnahmen" : "Inflow"}</span>
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-rose-400" /> {locale === "de" ? "Ausgaben" : "Outflow"}</span>
        <span className="inline-flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-slate-900" /> Net</span>
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
  const { locale, tText } = useI18n();
  const overviewQuery = useQuery({
    queryKey: ["dashboard-overview", fromDate, toDate],
    queryFn: () => fetchDashboardOverview(fromDate, toDate)
  });
  const overview = overviewQuery.data;
  const periodLabel = useMemo(() => {
    const start = new Date(overview?.period.from_date ?? fromDate);
    const end = new Date(overview?.period.to_date ?? toDate);
    const formatter = new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
      month: "short",
      day: "numeric"
    });
    return `${formatter.format(start)} - ${formatter.format(end)}`;
  }, [fromDate, locale, overview?.period.from_date, overview?.period.to_date, toDate]);

  return (
    <div className="space-y-6">
      <section className="app-dashboard-surface-strong rounded-[32px] border border-border/60 px-6 py-7 lg:px-8">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-400">Dashboard</p>
            <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-white">{tText("Your finance overview")}</h1>
            <p className="mt-3 max-w-2xl text-base text-slate-300">
              {tText("Track spend, groceries, cash movement, bills, and merchants from the same local-first desktop profile.")}
            </p>
          </div>
          <div className="rounded-[24px] border border-white/10 bg-white/6 px-5 py-4 text-sm text-slate-200">
            {periodLabel}
          </div>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
        {overview ? (
          <>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{tText("Total spending")}</span>
                  <Wallet className="h-5 w-5 text-rose-500" />
                </div>
                <div className="text-4xl font-semibold tracking-[-0.03em]">{formatEurFromCents(overview.kpis.total_spending.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.total_spending.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{tText("Purchases")}</span>
                  <ReceiptText className="h-5 w-5 text-emerald-500" />
                </div>
                <div className="text-4xl font-semibold tracking-[-0.03em]">{formatEurFromCents(overview.kpis.groceries.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.groceries.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{tText("Cash inflow")}</span>
                  <ArrowDownRight className="h-5 w-5 text-emerald-500" />
                </div>
                <div className="text-4xl font-semibold tracking-[-0.03em]">{formatEurFromCents(overview.kpis.cash_inflow.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.cash_inflow.delta_pct} locale={locale} />
              </CardContent>
            </Card>
            <Card className="app-dashboard-surface border-border/60">
              <CardContent className="space-y-3 p-5">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{tText("Cash outflow")}</span>
                  <ArrowUpRight className="h-5 w-5 text-rose-500" />
                </div>
                <div className="text-4xl font-semibold tracking-[-0.03em]">{formatEurFromCents(overview.kpis.cash_outflow.current_cents)}</div>
                <DeltaPill deltaPct={overview.kpis.cash_outflow.delta_pct} locale={locale} />
              </CardContent>
            </Card>
          </>
        ) : null}
      </div>

      {overview ? (
        <>
          <div className="grid gap-4 xl:grid-cols-[1.15fr_1fr_0.82fr]">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Spending overview", "/reports", "View reports")}</CardHeader>
              <CardContent>
                <RingChart
                  categories={overview.spending_overview.categories}
                  totalCents={overview.spending_overview.total_cents}
                  locale={locale}
                />
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Cash flow summary", "/cash-flow", "View cash flow")}</CardHeader>
              <CardContent>
                <CashFlowBars points={overview.cash_flow_summary.points} locale={locale} />
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Upcoming bills", "/bills", "View all")}</CardHeader>
              <CardContent className="space-y-3">
                {overview.upcoming_bills.items.map((bill) => (
                  <div key={bill.occurrence_id} className="flex items-center justify-between gap-3 rounded-[22px] bg-slate-50 px-4 py-3">
                    <div>
                      <p className="font-medium">{bill.bill_name}</p>
                      <p className="text-sm text-muted-foreground">{formatDate(bill.due_date)}</p>
                    </div>
                    <div className="text-right font-semibold">{formatEurFromCents(bill.expected_amount_cents ?? 0)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-[1.15fr_0.9fr_0.85fr]">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Recent grocery transactions", "/transactions", "View all")}</CardHeader>
              <CardContent className="space-y-3">
                {overview.recent_grocery_transactions.items.map((item) => (
                  <div key={item.id} className="flex items-center justify-between gap-3 border-b border-border/60 py-3 last:border-b-0">
                    <div>
                      <p className="font-medium">{item.store_name || item.source_id}</p>
                      <p className="text-sm text-muted-foreground">{formatDate(item.purchased_at)}</p>
                    </div>
                    <div className="font-semibold">{formatEurFromCents(item.total_gross_cents)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Budget progress", "/budget", "View all")}</CardHeader>
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
              <CardHeader>{sectionTitle("Recent activity", "/transactions", "View all")}</CardHeader>
              <CardContent className="space-y-3">
                {overview.recent_activity.items.map((item) => (
                  <Link key={item.id} to={item.href} className="flex items-center justify-between gap-3 border-b border-border/60 py-3 last:border-b-0">
                    <div className="min-w-0">
                      <p className="font-medium">{item.title}</p>
                      <p className="truncate text-sm text-muted-foreground">{item.subtitle}</p>
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
                  <p className="text-lg font-semibold tracking-[-0.02em]">{overview.insight.title}</p>
                  <p className="mt-1 text-muted-foreground">{overview.insight.body}</p>
                </div>
              </div>
              <Button asChild variant="outline">
                <Link to={overview.insight.href}>Open details</Link>
              </Button>
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Merchants", "/merchants", "Manage merchants")}</CardHeader>
              <CardContent className="space-y-3">
                {overview.merchants.items.map((merchant) => (
                  <div key={merchant.merchant} className="flex items-center justify-between gap-3 rounded-[22px] bg-slate-50 px-4 py-3">
                    <div>
                      <p className="font-medium">{merchant.merchant}</p>
                      <p className="text-sm text-muted-foreground">
                        {locale === "de" ? `${merchant.receipt_count} Belege` : `${merchant.receipt_count} receipts`}
                      </p>
                    </div>
                    <div className="font-semibold">{formatEurFromCents(merchant.spend_cents)}</div>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Goals", "/goals", "Manage goals")}</CardHeader>
              <CardContent className="space-y-3">
                {(overview.top_goals?.items ?? []).map((goal) => {
                  const percent = Math.min(100, Math.round(goal.progress.progress_ratio * 100));
                  return (
                    <div key={goal.id} className="space-y-2 rounded-[22px] bg-slate-50 px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-medium">{goal.name}</p>
                          <p className="text-sm text-muted-foreground">{tText(goal.progress.status.replace(/_/g, " "))}</p>
                        </div>
                        <div className="font-semibold">{formatEurFromCents(goal.target_amount_cents)}</div>
                      </div>
                      <div className="h-2 rounded-full bg-white">
                        <div className="h-2 rounded-full bg-sky-500" style={{ width: `${percent}%` }} />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            <Card className="app-dashboard-surface border-border/60">
              <CardHeader>{sectionTitle("Workspace status")}</CardHeader>
              <CardContent className="grid gap-4 md:grid-cols-3">
                <div className="rounded-[24px] bg-slate-50 p-4">
                  <Activity className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">Activity items</p>
                  <p className="mt-2 text-2xl font-semibold">{overview.recent_activity.count}</p>
                </div>
                <div className="rounded-[24px] bg-slate-50 p-4">
                  <CalendarCheck className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">Upcoming bills</p>
                  <p className="mt-2 text-2xl font-semibold">{overview.upcoming_bills.count}</p>
                </div>
                <div className="rounded-[24px] bg-slate-50 p-4">
                  <Database className="mb-3 h-5 w-5 text-slate-700" />
                  <p className="text-sm text-muted-foreground">Active merchants</p>
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
