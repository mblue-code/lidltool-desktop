import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Database, ReceiptText, Store, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { fetchConnectors, type ConnectorDiscoveryRow } from "@/api/connectors";
import { fetchMerchantSummary } from "@/api/merchants";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { MetricCard } from "@/components/shared/MetricCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatEurFromCents } from "@/utils/format";

type MerchantConnectorCard = {
  label: string;
  sourceIds: string[];
  connected: boolean;
  needsAttention: boolean;
  statusLabel: string;
  lastSyncSummary: string | null;
  lastSyncedAt: string | null;
};

function isAmazonConnector(sourceId: string): boolean {
  return sourceId.startsWith("amazon_");
}

function isLidlPlusConnector(sourceId: string): boolean {
  return sourceId.startsWith("lidl_plus");
}

function canonicalMerchantLabel(connector: ConnectorDiscoveryRow): string {
  if (isAmazonConnector(connector.source_id)) {
    return "Amazon";
  }
  if (isLidlPlusConnector(connector.source_id)) {
    return "Lidl Plus";
  }
  return connector.display_name.trim() || connector.source_id;
}

function isExternalPlugin(connector: ConnectorDiscoveryRow): boolean {
  return connector.origin !== "builtin";
}

function isVisibleMerchantConnector(connector: ConnectorDiscoveryRow): boolean {
  if (!isExternalPlugin(connector)) {
    return true;
  }
  return connector.enable_state === "enabled" || connector.ui.status === "connected" || connector.ui.status === "ready";
}

function isConnectedMerchantConnector(connector: ConnectorDiscoveryRow): boolean {
  return (
    connector.enable_state === "enabled" ||
    connector.ui.status === "connected" ||
    connector.ui.status === "ready" ||
    connector.ui.status === "syncing"
  );
}

function merchantStatusLabel(connector: ConnectorDiscoveryRow, locale: "en" | "de"): string {
  if (isConnectedMerchantConnector(connector)) {
    return locale === "de" ? "Verbunden" : "Connected";
  }
  if (connector.ui.status === "needs_attention" || connector.advanced.stale) {
    return locale === "de" ? "Aktion nötig" : "Needs attention";
  }
  if (connector.ui.status === "setup_required") {
    return locale === "de" ? "Einrichtung nötig" : "Setup required";
  }
  if (connector.ui.status === "syncing") {
    return locale === "de" ? "Synchronisierung läuft" : "Syncing";
  }
  return locale === "de" ? "Vorschau" : "Preview";
}

function statusChipClass(card: MerchantConnectorCard): string {
  if (card.connected) {
    return "border border-emerald-500/20 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300";
  }
  if (card.needsAttention) {
    return "border border-amber-500/20 bg-amber-500/12 text-amber-700 dark:text-amber-300";
  }
  return "border border-border/60 bg-background/70 text-foreground/70";
}

export function MerchantsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const { locale } = useI18n();
  const copy = locale === "de"
    ? {
        pageTitle: "Händler",
        description: "Verbinde den Zustand der Anbindungen, die Belegmenge und die Ausgabenkonzentration in einem händlerorientierten Arbeitsbereich.",
        openConnectors: "Anbindungen öffnen",
        connectedMerchants: "Verbundene Händler",
        attentionNeeded: "Handlungsbedarf",
        merchantsInHistory: "Händler im Verlauf",
        trackedSpend: "Erfasste Ausgaben",
        connectedMerchantGrid: "Verbundenes Händlernetz",
        merchantDirectory: "Händlerverzeichnis",
        searchMerchant: "Händler suchen",
        merchant: "Händler",
        categoryFocus: "Kategorienfokus",
        receipts: "Belege",
        sources: "Quellen",
        spend: "Ausgaben",
        topMerchant: "Top-Händler",
        largestReceiptCount: "Größte Beleganzahl",
        activeConnectors: "Aktive Anbindungen",
        noSyncSummaryYet: "Noch keine Synchronisierungszusammenfassung.",
        noSyncYet: "Noch keine Synchronisierung.",
        noRecentPurchase: "Kein aktueller Einkauf",
        topMerchantNone: "Noch keiner"
      }
    : {
        pageTitle: "Merchants",
        description: "Bridge connector health, receipt volume, and spend concentration in one merchant-oriented workspace.",
        openConnectors: "Open connectors",
        connectedMerchants: "Connected merchants",
        attentionNeeded: "Attention needed",
        merchantsInHistory: "Merchants in history",
        trackedSpend: "Tracked spend",
        connectedMerchantGrid: "Connected merchant grid",
        merchantDirectory: "Merchant directory",
        searchMerchant: "Search merchant",
        merchant: "Merchant",
        categoryFocus: "Category focus",
        receipts: "Receipts",
        sources: "Sources",
        spend: "Spend",
        topMerchant: "Top merchant",
        largestReceiptCount: "Largest receipt count",
        activeConnectors: "Active connectors",
        noSyncSummaryYet: "No sync summary yet.",
        noSyncYet: "No sync yet.",
        noRecentPurchase: "No recent purchase",
        topMerchantNone: "None yet"
      };
  const [search, setSearch] = useState("");
  const connectorsQuery = useQuery({
    queryKey: ["merchants-page", "connectors"],
    queryFn: fetchConnectors,
    staleTime: 0
  });
  const summaryQuery = useQuery({
    queryKey: ["merchants-page", fromDate, toDate, search],
    queryFn: () => fetchMerchantSummary(fromDate, toDate, search || undefined),
    staleTime: 0
  });
  const merchants = summaryQuery.data?.items ?? [];
  const connectors = connectorsQuery.data?.connectors ?? [];
  const merchantCards = useMemo<MerchantConnectorCard[]>(() => {
    const grouped = new Map<string, MerchantConnectorCard>();

    for (const connector of connectors) {
      if (!isVisibleMerchantConnector(connector)) {
        continue;
      }

      const label = canonicalMerchantLabel(connector);
      const existing = grouped.get(label);
      const connected = isConnectedMerchantConnector(connector);
      const needsAttention = connector.ui.status === "needs_attention" || connector.advanced.stale;
      const sourceIds = existing
        ? Array.from(new Set([...existing.sourceIds, connector.source_id])).sort()
        : [connector.source_id];
      const statusLabel = connected
        ? merchantStatusLabel(connector, locale)
        : existing?.needsAttention
          ? existing.statusLabel
          : needsAttention
            ? merchantStatusLabel(connector, locale)
            : existing?.statusLabel || merchantStatusLabel(connector, locale);

      grouped.set(label, {
        label,
        sourceIds,
        connected: (existing?.connected ?? false) || connected,
        needsAttention: (existing?.needsAttention ?? false) || needsAttention,
        statusLabel,
        lastSyncSummary: existing?.lastSyncSummary || connector.last_sync_summary,
        lastSyncedAt: existing?.lastSyncedAt || connector.last_synced_at
      });
    }

    return Array.from(grouped.values()).sort((left, right) => {
      if (left.connected !== right.connected) {
        return left.connected ? -1 : 1;
      }
      return left.label.localeCompare(right.label, locale);
    });
  }, [connectors, locale]);
  const attentionCount = merchantCards.filter((card) => card.needsAttention).length;
  const activeMerchantCount = merchantCards.filter((card) => card.connected).length;
  const spendTotal = merchants.reduce((sum, merchant) => sum + merchant.spend_cents, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title={copy.pageTitle}
        description={copy.description}
      >
        <Button asChild variant="outline">
          <Link to="/connectors">{copy.openConnectors}</Link>
        </Button>
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.connectedMerchants} value={String(activeMerchantCount)} icon={<Database className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.attentionNeeded} value={String(attentionCount)} icon={<AlertTriangle className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.merchantsInHistory} value={String(merchants.length)} icon={<Store className="h-4 w-4" />} />
        </Card>
        <Card className="app-dashboard-surface border-border/60">
          <MetricCard title={copy.trackedSpend} value={formatEurFromCents(spendTotal)} icon={<TrendingUp className="h-4 w-4" />} />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card className="app-dashboard-surface border-border/60">
          <CardHeader>
            <CardTitle>{copy.connectedMerchantGrid}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-2">
            {merchantCards.map((card) => (
              <div key={card.label} className="app-soft-surface rounded-[24px] border border-border/60 p-4 text-foreground">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold text-foreground">{card.label}</p>
                    <p className="text-sm text-foreground/60">
                      {card.sourceIds.length === 1
                        ? card.sourceIds[0]
                        : locale === "de"
                          ? `${card.sourceIds.length} Quellen`
                          : `${card.sourceIds.length} sources`}
                    </p>
                  </div>
                  <span className={cn("rounded-full px-2.5 py-1 text-xs font-semibold", statusChipClass(card))}>
                    {card.statusLabel}
                  </span>
                </div>
                <div className="mt-4 space-y-1 text-sm text-foreground/68">
                  <p>{card.lastSyncSummary || copy.noSyncSummaryYet}</p>
                  <p>
                    {card.lastSyncedAt
                      ? locale === "de"
                        ? `Zuletzt synchronisiert ${formatDate(card.lastSyncedAt)}`
                        : `Last synced ${formatDate(card.lastSyncedAt)}`
                      : copy.noSyncYet}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="app-dashboard-surface border-border/60">
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>{copy.merchantDirectory}</CardTitle>
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={copy.searchMerchant}
              className="max-w-56"
            />
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{copy.merchant}</TableHead>
                  <TableHead>{copy.categoryFocus}</TableHead>
                  <TableHead>{copy.receipts}</TableHead>
                  <TableHead>{copy.sources}</TableHead>
                  <TableHead className="text-right">{copy.spend}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {merchants.map((row) => (
                  <TableRow key={row.merchant}>
                    <TableCell>
                      <div>
                        <p className="font-medium">{row.merchant}</p>
                        <p className="text-xs text-muted-foreground">
                          {row.last_purchased_at
                            ? locale === "de"
                              ? `Letzter Einkauf ${formatDate(row.last_purchased_at)}`
                              : `Last purchase ${formatDate(row.last_purchased_at)}`
                            : copy.noRecentPurchase}
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
          <div className="app-soft-surface rounded-[24px] border border-border/60 p-4">
            <ReceiptText className="mb-3 h-5 w-5 text-foreground/75" />
            <p className="text-sm text-foreground/68">{copy.topMerchant}</p>
            <p className="mt-2 text-xl font-semibold">{merchants[0]?.merchant || copy.topMerchantNone}</p>
          </div>
          <div className="app-soft-surface rounded-[24px] border border-border/60 p-4">
            <Store className="mb-3 h-5 w-5 text-foreground/75" />
            <p className="text-sm text-foreground/68">{copy.largestReceiptCount}</p>
            <p className="mt-2 text-xl font-semibold">{merchants[0]?.receipt_count ?? 0}</p>
          </div>
          <div className="app-soft-surface rounded-[24px] border border-border/60 p-4">
            <Database className="mb-3 h-5 w-5 text-foreground/75" />
            <p className="text-sm text-foreground/68">{copy.activeConnectors}</p>
            <p className="mt-2 text-xl font-semibold">{activeMerchantCount}</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
