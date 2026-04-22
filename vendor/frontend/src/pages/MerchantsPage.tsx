import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, ReceiptText, Store, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchConnectors } from "@/api/connectors";
import { fetchMerchantSummary } from "@/api/merchants";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

export function MerchantsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const [search, setSearch] = useState("");
  const connectorsQuery = useQuery({
    queryKey: ["merchants-page", "connectors"],
    queryFn: fetchConnectors
  });
  const summaryQuery = useQuery({
    queryKey: ["merchants-page", fromDate, toDate, search],
    queryFn: () => fetchMerchantSummary(fromDate, toDate, search || undefined)
  });
  const merchants = summaryQuery.data?.items ?? [];
  const connectors = connectorsQuery.data?.connectors ?? [];
  const attentionCount = connectors.filter((connector) => connector.ui.status === "needs_attention" || connector.advanced.stale).length;
  const spendTotal = merchants.reduce((sum, merchant) => sum + merchant.spend_cents, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Merchants"
        description="Bridge connector health, receipt volume, and spend concentration in one merchant-oriented workspace."
      >
        <Button asChild variant="outline">
          <Link to="/connectors">Open connectors</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Connected merchants" value={String(connectors.length)} icon={<Database className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Attention needed" value={String(attentionCount)} icon={<AlertTriangle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Merchants in history" value={String(merchants.length)} icon={<Store className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title="Tracked spend" value={formatEurFromCents(spendTotal)} icon={<TrendingUp className="h-4 w-4" />} />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>Connected merchant grid</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {connectors.map((connector) => (
              <div key={connector.source_id} className="rounded-[24px] border border-border/60 bg-white/70 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">{connector.display_name}</p>
                    <p className="text-sm text-muted-foreground">{connector.source_id}</p>
                  </div>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold">
                    {connector.ui.status}
                  </span>
                </div>
                <div className="mt-4 space-y-1 text-sm text-muted-foreground">
                  <p>{connector.last_sync_summary || "No sync summary yet."}</p>
                  <p>{connector.last_synced_at ? `Last synced ${formatDate(connector.last_synced_at)}` : "No sync yet."}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="app-dashboard-surface border-border/60">
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>Merchant directory</CardTitle>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search merchant"
              className="max-w-56"
            />
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Merchant</TableHead>
                  <TableHead>Category focus</TableHead>
                  <TableHead>Receipts</TableHead>
                  <TableHead>Sources</TableHead>
                  <TableHead className="text-right">Spend</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {merchants.map((row) => (
                  <TableRow key={row.merchant}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{row.merchant}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.last_purchased_at ? `Last purchase ${formatDate(row.last_purchased_at)}` : "No recent purchase"}
                        </p>
                      </div>
                    </TableCell>
                    <TableCell>{row.dominant_category || "-"}</TableCell>
                    <TableCell>{row.receipt_count}</TableCell>
                    <TableCell>{row.source_ids.join(", ")}</TableCell>
                    <TableCell className="text-right">{formatEurFromCents(row.spend_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Card className="app-dashboard-surface border-border/60">
        <CardContent className="grid gap-4 p-6 md:grid-cols-3">
          <div className="rounded-[24px] bg-slate-50 p-4">
            <ReceiptText className="mb-3 h-5 w-5 text-slate-700" />
            <p className="text-sm text-muted-foreground">Top merchant</p>
            <p className="mt-2 text-xl font-semibold">{merchants[0]?.merchant || "None yet"}</p>
          </div>
          <div className="rounded-[24px] bg-slate-50 p-4">
            <Store className="mb-3 h-5 w-5 text-slate-700" />
            <p className="text-sm text-muted-foreground">Largest receipt count</p>
            <p className="mt-2 text-xl font-semibold">{merchants[0]?.receipt_count ?? 0}</p>
          </div>
          <div className="rounded-[24px] bg-slate-50 p-4">
            <Database className="mb-3 h-5 w-5 text-slate-700" />
            <p className="text-sm text-muted-foreground">Active connectors</p>
            <p className="mt-2 text-xl font-semibold">{connectors.filter((connector) => connector.enable_state === "enabled").length}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
