import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownCircle, ArrowUpCircle, CalendarCheck, CalendarDays, ChevronLeft, ChevronRight, Wallet } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { fetchBudgetSummary, fetchCashflowEntries } from "@/api/budget";
import { fetchTransactions, type TransactionListItem } from "@/api/transactions";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/i18n";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

type MonthValue = { year: number; month: number };
type CashFlowTab = "outflow" | "inflow";
type CashFlowRow = {
  id: string;
  date: string;
  source: string;
  category: string;
  description: string;
  amount_cents: number;
  href?: string;
};

function currentMonthValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function monthDisplayValue(monthValue: string): MonthValue {
  const [yearRaw, monthRaw] = monthValue.split("-");
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    const fallback = currentMonthValue();
    const [fallbackYear, fallbackMonth] = fallback.split("-");
    return { year: Number(fallbackYear), month: Number(fallbackMonth) };
  }
  return { year, month };
}

function monthValueFromParts(value: MonthValue): string {
  return `${value.year}-${String(value.month).padStart(2, "0")}`;
}

function shiftMonthValue(monthValue: string, delta: number): string {
  const { year, month } = monthDisplayValue(monthValue);
  const next = new Date(Date.UTC(year, month - 1 + delta, 1));
  return monthValueFromParts({
    year: next.getUTCFullYear(),
    month: next.getUTCMonth() + 1
  });
}

function monthLabel(monthValue: string, locale: "en" | "de"): string {
  const { year, month } = monthDisplayValue(monthValue);
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-US", {
    month: "long",
    year: "numeric"
  }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function parseMonthSearch(params: URLSearchParams): string {
  const year = Number(params.get("year"));
  const month = Number(params.get("month"));
  if (Number.isInteger(year) && year >= 2000 && year <= 2100 && Number.isInteger(month) && month >= 1 && month <= 12) {
    return monthValueFromParts({ year, month });
  }
  return currentMonthValue();
}

function parseTabSearch(params: URLSearchParams): CashFlowTab {
  return params.get("view") === "inflow" ? "inflow" : "outflow";
}

function transactionCategory(transaction: TransactionListItem): string {
  return transaction.finance_category_id || "uncategorized";
}

function transactionQuery(direction: CashFlowTab, year: number, month: number) {
  return {
    direction,
    year,
    month,
    sortBy: "purchased_at" as const,
    sortDir: "desc" as const,
    limit: 1000,
    offset: 0
  };
}

export function CashFlowPage() {
  const { locale, t } = useI18n();
  const location = useLocation();
  const navigate = useNavigate();
  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const monthValue = parseMonthSearch(searchParams);
  const selectedTab = parseTabSearch(searchParams);
  const { year, month } = monthDisplayValue(monthValue);

  function updateRoute(nextMonthValue: string, nextTab: CashFlowTab): void {
    const params = new URLSearchParams(location.search);
    const nextMonth = monthDisplayValue(nextMonthValue);
    params.set("year", String(nextMonth.year));
    params.set("month", String(nextMonth.month));
    if (nextTab === "inflow") {
      params.set("view", "inflow");
    } else {
      params.delete("view");
    }
    navigate(
      {
        pathname: location.pathname,
        search: `?${params.toString()}`
      },
      { replace: true }
    );
  }

  function updateMonth(nextMonthValue: string): void {
    updateRoute(nextMonthValue, selectedTab);
  }

  function updateTab(nextTab: CashFlowTab): void {
    updateRoute(monthValue, nextTab);
  }

  const copy = {
    description: t("pages.cashflow.description"),
    openBudget: t("pages.cashflow.openBudget"),
    currentMonth: t("pages.cashflow.currentMonth"),
    previousMonth: t("pages.cashflow.previousMonth"),
    nextMonth: t("pages.cashflow.nextMonth"),
    inflow: t("pages.cashflow.inflow"),
    outflow: t("pages.cashflow.outflow"),
    remaining: t("pages.cashflow.remaining"),
    upcomingBills: t("pages.cashflow.upcomingBills"),
    manageEntries: t("pages.cashflow.manageEntries"),
    monthlyOutflows: t("pages.cashflow.monthlyOutflows"),
    monthlyInflows: t("pages.cashflow.monthlyInflows"),
    outflowDescription: t("pages.cashflow.outflowDescription"),
    inflowDescription: t("pages.cashflow.inflowDescription"),
    date: t("common.date"),
    source: t("common.source"),
    category: t("common.category"),
    descriptionLabel: t("pages.cashflow.descriptionLabel"),
    amount: t("common.amount"),
    manualEntry: t("pages.cashflow.manualEntry"),
    manual: t("pages.cashflow.manual"),
    transaction: t("pages.cashflow.transaction"),
    noOutflows: t("pages.cashflow.noOutflows"),
    noInflows: t("pages.cashflow.noInflows"),
    loading: t("common.loading")
  };

  const selectedMonthLabel = useMemo(() => monthLabel(monthValue, locale), [locale, monthValue]);
  const budgetSummaryQuery = useQuery({
    queryKey: ["cashflow-page", "summary", year, month],
    queryFn: () => fetchBudgetSummary(year, month)
  });
  const cashflowEntriesQuery = useQuery({
    queryKey: ["cashflow-page", "entries", year, month],
    queryFn: () => fetchCashflowEntries(year, month)
  });
  const outflowTransactionsQuery = useQuery({
    queryKey: ["cashflow-page", "transactions", "outflow", year, month],
    queryFn: () => fetchTransactions(transactionQuery("outflow", year, month))
  });
  const inflowTransactionsQuery = useQuery({
    queryKey: ["cashflow-page", "transactions", "inflow", year, month],
    queryFn: () => fetchTransactions(transactionQuery("inflow", year, month))
  });

  const cashflowEntries = cashflowEntriesQuery.data?.items ?? [];
  const selectedTransactionQuery = selectedTab === "outflow" ? outflowTransactionsQuery : inflowTransactionsQuery;
  const selectedTransactions = selectedTransactionQuery.data?.items ?? [];

  const totals = useMemo(() => {
    const summary = budgetSummaryQuery.data?.totals;
    const ledgerInflow = cashflowEntries
      .filter((entry) => entry.direction === "inflow")
      .reduce((sum, entry) => sum + entry.amount_cents, 0);
    const ledgerOutflow = cashflowEntries
      .filter((entry) => entry.direction === "outflow")
      .reduce((sum, entry) => sum + entry.amount_cents, 0);

    return {
      inflow: Math.max(summary?.actual_income_cents ?? 0, ledgerInflow),
      outflow: Math.max(summary?.total_outflow_cents ?? 0, ledgerOutflow),
      remaining: summary?.remaining_cents ?? 0,
      upcomingBills: summary?.recurring_expected_cents ?? 0
    };
  }, [budgetSummaryQuery.data?.totals, cashflowEntries]);

  const rows = useMemo<CashFlowRow[]>(() => {
    const manualRows = cashflowEntries
      .filter((entry) => entry.direction === selectedTab && entry.linked_transaction_id === null)
      .map((entry) => ({
        id: `cashflow-${entry.id}`,
        date: entry.effective_date,
        source: copy.manual,
        category: entry.category,
        description: entry.description || copy.manualEntry,
        amount_cents: entry.amount_cents
      }));

    return [
      ...selectedTransactions.map((transaction) => ({
        id: `transaction-${transaction.id}`,
        date: transaction.purchased_at,
        source: copy.transaction,
        category: transactionCategory(transaction),
        description: transaction.store_name || transaction.source_id,
        amount_cents: transaction.total_gross_cents,
        href: `/transactions/${transaction.id}`
      })),
      ...manualRows
    ].sort((left, right) => right.date.localeCompare(left.date));
  }, [cashflowEntries, copy.manual, copy.manualEntry, copy.transaction, selectedTab, selectedTransactions]);

  const isLoadingTotals = budgetSummaryQuery.isPending && !budgetSummaryQuery.data;
  const isLoadingRows = (cashflowEntriesQuery.isPending && !cashflowEntriesQuery.data) || (selectedTransactionQuery.isPending && !selectedTransactionQuery.data);
  const emptyText = selectedTab === "outflow" ? copy.noOutflows : copy.noInflows;
  const tableTitle = selectedTab === "outflow" ? copy.monthlyOutflows : copy.monthlyInflows;
  const tableDescription = selectedTab === "outflow" ? copy.outflowDescription : copy.inflowDescription;

  return (
    <div className="space-y-6">
      <PageHeader
        title={locale === "de" ? "Cashflow" : "Cash Flow"}
        description={copy.description}
      >
        <div className="flex flex-wrap items-center gap-2">
          <div
            key={`month-${monthValue}`}
            className="flex items-center rounded-lg border border-border/70 bg-background/60"
          >
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={copy.previousMonth}
              onClick={() => updateMonth(shiftMonthValue(monthValue, -1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <div className="flex min-w-[170px] items-center justify-center gap-2 px-3 text-sm font-medium">
              <CalendarDays className="h-4 w-4 text-muted-foreground" />
              <span>{selectedMonthLabel}</span>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={copy.nextMonth}
              onClick={() => updateMonth(shiftMonthValue(monthValue, 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
          <Button type="button" variant="outline" onClick={() => updateMonth(currentMonthValue())}>
            {copy.currentMonth}
          </Button>
          <Button asChild variant="outline">
            <Link to="/budget">{copy.openBudget}</Link>
          </Button>
        </div>
      </PageHeader>

      <div
        key={`totals-${monthValue}-${budgetSummaryQuery.status}-${budgetSummaryQuery.data?.period.year ?? "none"}-${budgetSummaryQuery.data?.period.month ?? "none"}-${budgetSummaryQuery.isPending ? "pending" : "ready"}`}
        className="grid gap-4 xl:grid-cols-4 md:grid-cols-2"
      >
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.inflow} value={isLoadingTotals ? copy.loading : formatEurFromCents(totals.inflow)} icon={<ArrowUpCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.outflow} value={isLoadingTotals ? copy.loading : formatEurFromCents(totals.outflow)} icon={<ArrowDownCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.remaining} value={isLoadingTotals ? copy.loading : formatEurFromCents(totals.remaining)} icon={<Wallet className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.upcomingBills} value={isLoadingTotals ? copy.loading : formatEurFromCents(totals.upcomingBills)} icon={<CalendarCheck className="h-4 w-4" />} />
        </Card>
      </div>

      <Card className="app-dashboard-surface border-border/60">
        <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <CardTitle>{tableTitle}</CardTitle>
            <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{tableDescription}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-border/70 bg-background/60 p-1">
              <Button type="button" size="sm" variant={selectedTab === "outflow" ? "secondary" : "ghost"} onClick={() => updateTab("outflow")}>
                {copy.outflow}
              </Button>
              <Button type="button" size="sm" variant={selectedTab === "inflow" ? "secondary" : "ghost"} onClick={() => updateTab("inflow")}>
                {copy.inflow}
              </Button>
            </div>
            <Button asChild variant="ghost" size="sm">
              <Link to="/budget">{copy.manageEntries}</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{copy.date}</TableHead>
                <TableHead>{copy.source}</TableHead>
                <TableHead>{copy.category}</TableHead>
                <TableHead>{copy.descriptionLabel}</TableHead>
                <TableHead className="text-right">{copy.amount}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoadingRows ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">{copy.loading}</TableCell>
                </TableRow>
              ) : rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="py-10 text-center text-muted-foreground">{emptyText}</TableCell>
                </TableRow>
              ) : rows.slice(0, 25).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{formatDate(row.date)}</TableCell>
                  <TableCell>{row.source}</TableCell>
                  <TableCell>{row.category}</TableCell>
                  <TableCell>
                    {row.href ? <Link to={row.href} className="text-primary hover:underline">{row.description}</Link> : row.description}
                  </TableCell>
                  <TableCell className="text-right">{formatEurFromCents(row.amount_cents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
