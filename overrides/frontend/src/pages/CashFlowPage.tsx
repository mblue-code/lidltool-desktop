import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownCircle, ArrowUpCircle, CalendarCheck, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchBudgetSummary, fetchCashflowEntries } from "@/api/budget";
import { useDateRangeContext } from "@/app/date-range-context";
import { fetchRecurringCalendar } from "@/api/recurringBills";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/i18n";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

function monthFromDateString(value: string): { year: number; month: number } {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) {
    const now = new Date();
    return { year: now.getFullYear(), month: now.getMonth() + 1 };
  }
  return { year: Number(match[1]), month: Number(match[2]) };
}

export function CashFlowPage() {
  const { toDate } = useDateRangeContext();
  const { locale } = useI18n();
  const copy = locale === "de"
    ? {
        description: "Verfolge Geld hinein und hinaus aus dem Monat und springe dann direkt zum Cashflow-Ledger oder zu wiederkehrenden Rechnungen.",
        openBudget: "Budget öffnen",
        inflow: "Einnahmen",
        outflow: "Ausgaben",
        remaining: "Verbleibend",
        upcomingBills: "Anstehende Rechnungen",
        cashLedger: "Cashflow-Ledger",
        manageEntries: "Einträge verwalten",
        date: "Datum",
        direction: "Richtung",
        category: "Kategorie",
        descriptionLabel: "Beschreibung",
        amount: "Betrag",
        manualEntry: "Manueller Eintrag"
      }
    : {
        description: "Follow money in and out of the month, then jump straight into the cash ledger or recurring commitments.",
        openBudget: "Open budget",
        inflow: "Inflow",
        outflow: "Outflow",
        remaining: "Remaining",
        upcomingBills: "Upcoming bills",
        cashLedger: "Cash ledger",
        manageEntries: "Manage entries",
        date: "Date",
        direction: "Direction",
        category: "Category",
        descriptionLabel: "Description",
        amount: "Amount",
        manualEntry: "Manual entry"
      };
  const { year, month } = monthFromDateString(toDate);
  const budgetSummaryQuery = useQuery({
    queryKey: ["cash-flow-page", "summary", year, month],
    queryFn: () => fetchBudgetSummary(year, month),
    staleTime: 0
  });
  const cashflowEntriesQuery = useQuery({
    queryKey: ["cash-flow-page", "entries", year, month],
    queryFn: () => fetchCashflowEntries(year, month),
    staleTime: 0
  });
  const recurringCalendarQuery = useQuery({
    queryKey: ["cash-flow-page", "calendar", year, month],
    queryFn: () => fetchRecurringCalendar({ year, month }),
    staleTime: 0
  });

  const totals = useMemo(() => {
    const summary = budgetSummaryQuery.data?.totals;
    const entries = cashflowEntriesQuery.data?.items ?? [];
    const ledgerInflow = entries
      .filter((entry) => entry.direction === "inflow")
      .reduce((sum, entry) => sum + entry.amount_cents, 0);
    const ledgerOutflow = entries
      .filter((entry) => entry.direction === "outflow")
      .reduce((sum, entry) => sum + entry.amount_cents, 0);
    return {
      inflow: ledgerInflow || summary?.actual_income_cents || 0,
      outflow: ledgerOutflow || summary?.total_outflow_cents || 0,
      remaining: summary?.remaining_cents ?? 0,
      upcomingBills: recurringCalendarQuery.data?.days.reduce((sum, day) => sum + day.total_expected_cents, 0) ?? 0
    };
  }, [budgetSummaryQuery.data, cashflowEntriesQuery.data?.items, recurringCalendarQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title={locale === "de" ? "Cashflow" : "Cash Flow"}
        description={copy.description}
      >
        <Button asChild variant="outline">
          <Link to="/budget">{copy.openBudget}</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.inflow} value={formatEurFromCents(totals.inflow)} icon={<ArrowUpCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.outflow} value={formatEurFromCents(totals.outflow)} icon={<ArrowDownCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.remaining} value={formatEurFromCents(totals.remaining)} icon={<Wallet className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.upcomingBills} value={formatEurFromCents(totals.upcomingBills)} icon={<CalendarCheck className="h-4 w-4" />} />
        </Card>
      </div>

      <Card className="app-dashboard-surface border-border/60">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>{copy.cashLedger}</CardTitle>
          <Button asChild variant="ghost" size="sm">
            <Link to="/budget">{copy.manageEntries}</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{copy.date}</TableHead>
                <TableHead>{copy.direction}</TableHead>
                <TableHead>{copy.category}</TableHead>
                <TableHead>{copy.descriptionLabel}</TableHead>
                <TableHead className="text-right">{copy.amount}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(cashflowEntriesQuery.data?.items ?? []).slice(0, 10).map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>{formatDate(entry.effective_date)}</TableCell>
                  <TableCell className="capitalize">{entry.direction === "inflow" ? copy.inflow : copy.outflow}</TableCell>
                  <TableCell>{entry.category}</TableCell>
                  <TableCell>{entry.description || copy.manualEntry}</TableCell>
                  <TableCell className="text-right">{formatEurFromCents(entry.amount_cents)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
