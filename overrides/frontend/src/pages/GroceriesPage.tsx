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

export function GroceriesPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale } = useI18n();
  const copy = locale === "de"
    ? {
        title: "Einkäufe",
        description: "Verfolge Warenkorngröße, Kategorienkonzentration und den neuesten Belegfluss im aktiven Dashboard-Zeitraum.",
        openTransactions: "Transaktionen öffnen",
        trackedSpend: "Erfasste Ausgaben",
        averageBasket: "Durchschnittlicher Warenkorb",
        recentReceipts: "Aktuelle Belege",
        activeMerchants: "Aktive Händler",
        categoryMix: "Kategorienverteilung",
        merchant: "Händler",
        date: "Datum",
        source: "Quelle",
        amount: "Betrag",
        viewAll: "Alle anzeigen"
      }
    : {
        title: "Purchases",
        description: "Track basket size, category concentration, and the latest receipt flow for the active dashboard window.",
        openTransactions: "Open transactions",
        trackedSpend: "Tracked spend",
        averageBasket: "Average basket",
        recentReceipts: "Recent receipts",
        activeMerchants: "Active merchants",
        categoryMix: "Category mix",
        merchant: "Merchant",
        date: "Date",
        source: "Source",
        amount: "Amount",
        viewAll: "View all"
      };
  const summaryQuery = useQuery({
    queryKey: ["groceries-page", fromDate, toDate],
    queryFn: () => fetchGroceriesSummary(fromDate, toDate),
    staleTime: 0
  });
  const summary = summaryQuery.data?.period.from_date === fromDate && summaryQuery.data.period.to_date === toDate
    ? summaryQuery.data
    : undefined;
  const categorySpendCents = (summary?.category_breakdown ?? []).reduce((sum, item) => sum + item.amount_cents, 0);
  const recentSpendCents = (summary?.recent_transactions ?? []).reduce((sum, item) => sum + item.total_gross_cents, 0);
  const recentReceiptCount = summary?.recent_transactions.length ?? 0;
  const recentMerchantCount = new Set((summary?.recent_transactions ?? []).map((item) => item.store_name || item.source_id)).size;
  const spendCents = recentSpendCents || summary?.totals.spend_cents || categorySpendCents || 0;
  const averageBasketCents =
    recentReceiptCount > 0 ? Math.round(recentSpendCents / recentReceiptCount) : summary?.totals.average_basket_cents || 0;
  const receiptCount = recentReceiptCount || summary?.totals.receipt_count || 0;
  const merchantCount = recentMerchantCount || summary?.totals.merchant_count || 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title={copy.title}
        description={copy.description}
      >
        <Button asChild variant="outline">
          <Link to="/transactions">{copy.openTransactions}</Link>
        </Button>
      </PageHeader>

      <div
        key={`${fromDate}:${toDate}:${spendCents}:${recentReceiptCount}:${recentMerchantCount}`}
        className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"
      >
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={copy.trackedSpend}
            value={formatEurFromCents(spendCents)}
            icon={<ShoppingCart className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={copy.averageBasket}
            value={formatEurFromCents(averageBasketCents)}
            icon={<TrendingUp className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={copy.recentReceipts}
            value={String(receiptCount)}
            icon={<ReceiptText className="h-4 w-4" />}
          />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard
            title={copy.activeMerchants}
            value={String(merchantCount)}
            icon={<Database className="h-4 w-4" />}
          />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{copy.categoryMix}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {(summary?.category_breakdown ?? []).map((item) => {
              const total = spendCents;
              const width = total > 0 ? Math.max(6, Math.round((item.amount_cents / total) * 100)) : 0;
              return (
                <div key={item.category} className="space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{categoryLabel(item.category, locale)}</span>
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
            <CardTitle>{locale === "de" ? "Aktuelle Einkäufe" : "Recent purchases"}</CardTitle>
            <Button asChild variant="ghost" size="sm">
              <Link to="/transactions">{copy.viewAll}</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{copy.merchant}</TableHead>
                  <TableHead>{copy.date}</TableHead>
                  <TableHead>{copy.source}</TableHead>
                  <TableHead className="text-right">{copy.amount}</TableHead>
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
