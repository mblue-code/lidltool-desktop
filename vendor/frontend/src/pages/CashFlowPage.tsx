import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownCircle, ArrowUpCircle, CalendarCheck, Wallet } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchBudgetSummary, fetchCashflowEntries } from "@/api/budget";
import { fetchRecurringCalendar } from "@/api/recurringBills";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

function currentMonth() {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

export function CashFlowPage() {
  const { year, month } = currentMonth();
  const budgetSummaryQuery = useQuery({
    queryKey: ["cash-flow-page", "summary", year, month],
    queryFn: () => fetchBudgetSummary(year, month)
  });
  const cashflowEntriesQuery = useQuery({
    queryKey: ["cash-flow-page", "entries", year, month],
    queryFn: () => fetchCashflowEntries(year, month)
  });
  const recurringCalendarQuery = useQuery({
    queryKey: ["cash-flow-page", "calendar", year, month],
    queryFn: () => fetchRecurringCalendar({ year, month })
  });

  const totals = useMemo(() => {
    const summary = budgetSummaryQuery.data?.totals;
    return {
      inflow: summary?.actual_income_cents ?? 0,
      outflow: summary?.total_outflow_cents ?? 0,
      remaining: summary?.remaining_cents ?? 0,
      upcomingBills: recurringCalendarQuery.data?.days.reduce((sum, day) => sum + day.total_expected_cents, 0) ?? 0
    };
  }, [budgetSummaryQuery.data, recurringCalendarQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Cash Flow"
        description="Follow money in and out of the month, then jump straight into the cash ledger or recurring commitments."
      >
        <Button asChild variant="outline">
          <Link to="/budget">Open budget</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Inflow" value={formatEurFromCents(totals.inflow)} icon={<ArrowUpCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Outflow" value={formatEurFromCents(totals.outflow)} icon={<ArrowDownCircle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Remaining" value={formatEurFromCents(totals.remaining)} icon={<Wallet className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Upcoming bills" value={formatEurFromCents(totals.upcomingBills)} icon={<CalendarCheck className="h-4 w-4" />} />
        </Card>
      </div>

      <Card className="app-dashboard-surface border-border/60">
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Cash ledger</CardTitle>
          <Button asChild variant="ghost" size="sm">
            <Link to="/budget">Manage entries</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(cashflowEntriesQuery.data?.items ?? []).slice(0, 10).map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell>{formatDate(entry.effective_date)}</TableCell>
                  <TableCell className="capitalize">{entry.direction}</TableCell>
                  <TableCell>{entry.category}</TableCell>
                  <TableCell>{entry.description || "Manual entry"}</TableCell>
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
