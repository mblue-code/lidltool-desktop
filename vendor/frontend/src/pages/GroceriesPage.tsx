import { useQuery } from "@tanstack/react-query";
import { Database, ReceiptText, ShoppingCart, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchGroceriesSummary } from "@/api/groceries";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useI18n } from "@/i18n";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

export function GroceriesPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { tText } = useI18n();
  const summaryQuery = useQuery({
    queryKey: ["groceries-page", fromDate, toDate],
    queryFn: () => fetchGroceriesSummary(fromDate, toDate)
  });
  const summary = summaryQuery.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={tText("Purchases")}
        description={tText("Track basket size, category concentration, and the latest receipt flow for the active dashboard window.")}
      >
        <Button asChild variant="outline">
          <Link to="/transactions">{tText("Open transactions")}</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={tText("Tracked spend")}
            value={formatEurFromCents(summary?.totals.spend_cents ?? 0)}
            icon={<ShoppingCart className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={tText("Average basket")}
            value={formatEurFromCents(summary?.totals.average_basket_cents ?? 0)}
            icon={<TrendingUp className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={tText("Recent receipts")}
            value={String(summary?.totals.receipt_count ?? 0)}
            icon={<ReceiptText className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={tText("Active merchants")}
            value={String(summary?.totals.merchant_count ?? 0)}
            icon={<Database className="h-4 w-4" />}
          />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{tText("Category mix")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(summary?.category_breakdown ?? []).map((item) => {
              const total = summary?.totals.spend_cents ?? 0;
              const width = total > 0 ? Math.max(6, Math.round((item.amount_cents / total) * 100)) : 0;
              return (
                <div key={item.category} className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium capitalize">{item.category.replace(/_/g, " ")}</span>
                    <span className="text-sm text-muted-foreground">{formatEurFromCents(item.amount_cents)}</span>
                  </div>
                  <div className="h-2.5 rounded-full bg-slate-100">
                    <div className="h-2.5 rounded-full bg-emerald-400" style={{ width: `${width}%` }} />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card className="app-dashboard-surface border-border/60">
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>{tText("Recent purchases")}</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link to="/transactions">{tText("View all")}</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{tText("Merchant")}</TableHead>
                  <TableHead>{tText("Date")}</TableHead>
                  <TableHead>{tText("Source")}</TableHead>
                  <TableHead className="text-right">{tText("Amount")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(summary?.recent_transactions ?? []).map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.store_name || item.source_id}</TableCell>
                    <TableCell>{formatDate(item.purchased_at)}</TableCell>
                    <TableCell>{item.source_id}</TableCell>
                    <TableCell className="text-right">{formatEurFromCents(item.total_gross_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
