import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Bot, Search } from "lucide-react";
import { toast } from "sonner";
import { TransactionsFilters, transactionsQueryOptions } from "@/app/queries";
import { fetchAISettings } from "@/api/aiSettings";
import {
  fetchTransactionCategorizationAgentStatus,
  fetchTransactionFacets,
  startTransactionCategorizationAgent
} from "@/api/transactions";
import { isDemoSnapshotMode } from "@/demo/mode";
import { PageHeader } from "@/components/shared/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { SearchInput } from "@/components/shared/SearchInput";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { directionLabel, financeCategoryLabel } from "@/lib/category-presentation";
import { formatDateTime, formatEurFromCents } from "@/utils/format";

const PAGE_SIZE = 25;

function cents(value: string | null): number | undefined {
  if (!value) return undefined;
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : undefined;
}

function euro(value: string | null): string {
  if (!value) return "";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? String(parsed / 100) : "";
}

export function TransactionsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const demoMode = isDemoSnapshotMode();
  const [searchParams, setSearchParams] = useSearchParams();
  const [categorizationJobId, setCategorizationJobId] = useState<string | null>(null);
  const offset = Number(searchParams.get("offset") || 0);
  const filters = useMemo<TransactionsFilters>(() => ({
    query: searchParams.get("query") || undefined,
    direction: (searchParams.get("direction_filter") || undefined) as TransactionsFilters["direction"],
    financeCategoryId: searchParams.get("finance_category_id") || undefined,
    parentCategory: searchParams.get("parent_category") || undefined,
    merchantName: searchParams.get("merchant_name") || undefined,
    sourceId: searchParams.get("source_id") || undefined,
    purchasedFrom: searchParams.get("purchased_from") || undefined,
    purchasedTo: searchParams.get("purchased_to") || undefined,
    minTotalCents: cents(searchParams.get("min_total")),
    maxTotalCents: cents(searchParams.get("max_total")),
    uncategorized: searchParams.get("uncategorized") === "true",
    sortBy: (searchParams.get("sort") as TransactionsFilters["sortBy"]) || "purchased_at",
    sortDir: (searchParams.get("direction") as TransactionsFilters["sortDir"]) || "desc",
    limit: PAGE_SIZE,
    offset
  }), [searchParams, offset]);

  const tx = useQuery(transactionsQueryOptions(filters));
  const facets = useQuery({ queryKey: ["transaction-facets", filters], queryFn: () => fetchTransactionFacets(filters) });
  const aiSettings = useQuery({ queryKey: ["ai-settings"], queryFn: fetchAISettings });
  const categorizationStatus = useQuery({
    queryKey: ["transaction-categorization-agent-status", categorizationJobId],
    queryFn: () => fetchTransactionCategorizationAgentStatus(categorizationJobId ?? ""),
    enabled: Boolean(categorizationJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    }
  });
  const items = tx.data?.items ?? [];

  function setParam(key: string, value: string | undefined) {
    const next = new URLSearchParams(searchParams);
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.set("offset", "0");
    setSearchParams(next);
  }

  const total = items.reduce((sum, item) => sum + item.total_gross_cents, 0);
  const inflow = items.filter((item) => item.direction === "inflow").reduce((sum, item) => sum + item.total_gross_cents, 0);
  const outflow = items.filter((item) => (item.direction || "outflow") === "outflow").reduce((sum, item) => sum + item.total_gross_cents, 0);
  const categorizationReady = aiSettings.data?.categorization_enabled === true && aiSettings.data?.categorization_runtime_ready === true;
  const categorizationJob = categorizationStatus.data;
  const categorizationRunning =
    categorizationJob?.status === "queued" ||
    categorizationJob?.status === "running";
  const categorizationMutation = useMutation({
    mutationFn: () => startTransactionCategorizationAgent({ max_transactions: 500 }),
    onSuccess: (job) => {
      setCategorizationJobId(job.job_id);
      toast.success(t("pages.transactions.categorization.started"));
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : t("pages.transactions.categorization.startFailed"));
    }
  });

  function categorizationStatusLabel(status: string): string {
    switch (status) {
      case "queued":
        return t("pages.transactions.categorization.status.queued");
      case "running":
        return t("pages.transactions.categorization.status.running");
      case "completed":
        return t("pages.transactions.categorization.status.completed");
      case "error":
        return t("pages.transactions.categorization.status.error");
      default:
        return status;
    }
  }

  useEffect(() => {
    if (!categorizationJob) return;
    if (categorizationJob.status === "completed") {
      setCategorizationJobId(null);
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["transaction-facets"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
      toast.success(
        t("pages.transactions.categorization.completed", {
          transactions: categorizationJob.updated_transaction_count,
          items: categorizationJob.updated_item_count
        })
      );
    } else if (categorizationJob.status === "error") {
      setCategorizationJobId(null);
      toast.error(categorizationJob.error || t("pages.transactions.categorization.failed"));
    }
  }, [categorizationJob, queryClient, t]);

  return (
    <section className="space-y-5">
      <PageHeader title={t("pages.transactions.title")} description={t("pages.transactions.description")}>
        <Button
          type="button"
          variant="outline"
          onClick={() => void categorizationMutation.mutateAsync()}
          disabled={demoMode || !categorizationReady || categorizationRunning || categorizationMutation.isPending}
          title={
            categorizationReady
              ? t("pages.transactions.categorization.tooltip")
              : t("pages.transactions.categorization.notReady")
          }
        >
          <Bot className="mr-2 h-4 w-4" />
          {categorizationRunning || categorizationMutation.isPending
            ? t("pages.transactions.categorization.running")
            : t("pages.transactions.categorization.button")}
        </Button>
        <Button asChild><Link to="/add">{t("nav.item.addReceipt")}</Link></Button>
      </PageHeader>

      <Card className="app-dashboard-surface border-border/60">
        <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-medium">{t("pages.transactions.categorization.title")}</p>
              <Badge variant={categorizationReady ? "secondary" : "outline"}>
                {categorizationReady ? t("pages.transactions.categorization.ready") : t("pages.transactions.categorization.notConfigured")}
              </Badge>
              {aiSettings.data?.categorization_model ? <Badge variant="outline">{aiSettings.data.categorization_model}</Badge> : null}
            </div>
            <p className="text-sm text-muted-foreground">{t("pages.transactions.categorization.description")}</p>
            {!categorizationReady ? (
              <p className="text-xs text-muted-foreground">
                {t("pages.transactions.categorization.settingsHint")}{" "}
                <Link className="font-medium text-primary underline-offset-4 hover:underline" to="/settings/ai">
                  {t("pages.transactions.categorization.settingsLink")}
                </Link>
              </p>
            ) : null}
          </div>
          {categorizationJob ? (
            <div className="grid shrink-0 gap-1 text-sm text-muted-foreground sm:grid-cols-3 md:text-right">
              <span>{t("pages.transactions.categorization.status")}: {categorizationStatusLabel(categorizationJob.status)}</span>
              <span>{t("pages.transactions.categorization.transactions")}: {categorizationJob.updated_transaction_count}</span>
              <span>{t("pages.transactions.categorization.items")}: {categorizationJob.updated_item_count}</span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="app-dashboard-surface border-border/60">
        <CardContent className="grid gap-4 p-4">
          <div className="grid gap-3 lg:grid-cols-5">
            <div className="space-y-2">
              <Label>{t("pages.transactions.filter.query")}</Label>
              <SearchInput value={searchParams.get("query") || ""} onChange={(value) => setParam("query", value)} debounceMs={200} />
            </div>
            <SelectField label={t("pages.transactions.filter.direction")} value={searchParams.get("direction_filter") || "all"} onChange={(value) => setParam("direction_filter", value)} allLabel={t("pages.transactions.allDirections")}>
              {["outflow", "inflow", "transfer", "neutral"].map((value) => <SelectItem key={value} value={value}>{directionLabel(value, t)}</SelectItem>)}
            </SelectField>
            <SelectField label={t("pages.transactions.filter.category")} value={searchParams.get("finance_category_id") || "all"} onChange={(value) => setParam("finance_category_id", value)} allLabel={t("pages.transactions.allCategories")}>
              {(facets.data?.categories ?? []).map((row) => <SelectItem key={row.category_id} value={row.category_id}>{financeCategoryLabel(row.category_id, t)} ({row.count})</SelectItem>)}
            </SelectField>
            <SelectField label={t("pages.transactions.filter.merchant")} value={searchParams.get("merchant_name") || "all"} onChange={(value) => setParam("merchant_name", value)} allLabel={t("pages.transactions.allMerchants")}>
              {(facets.data?.merchants ?? []).map((row) => <SelectItem key={row.value} value={row.value}>{row.value} ({row.count})</SelectItem>)}
            </SelectField>
            <SelectField label={t("pages.transactions.filter.source")} value={searchParams.get("source_id") || "all"} onChange={(value) => setParam("source_id", value)} allLabel={t("pages.transactions.allSources")}>
              {(facets.data?.sources ?? []).map((row) => <SelectItem key={row.source_id} value={row.source_id}>{row.source_id} ({row.count})</SelectItem>)}
            </SelectField>
          </div>
          <div className="grid gap-3 md:grid-cols-5">
            <InputField label={t("pages.transactions.filter.purchasedFrom")} type="date" value={searchParams.get("purchased_from") || ""} onChange={(value) => setParam("purchased_from", value)} />
            <InputField label={t("pages.transactions.filter.purchasedTo")} type="date" value={searchParams.get("purchased_to") || ""} onChange={(value) => setParam("purchased_to", value)} />
            <InputField label={t("pages.transactions.amountFrom")} value={euro(searchParams.get("min_total"))} onChange={(value) => setParam("min_total", cents(value) === undefined ? undefined : String(cents(value)))} />
            <InputField label={t("pages.transactions.amountTo")} value={euro(searchParams.get("max_total"))} onChange={(value) => setParam("max_total", cents(value) === undefined ? undefined : String(cents(value)))} />
            <div className="flex items-end"><Button type="button" variant="outline" className="w-full" onClick={() => setParam("uncategorized", searchParams.get("uncategorized") === "true" ? undefined : "true")}>{t("pages.transactions.filter.uncategorized")}</Button></div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-4">
        <Summary label={t("pages.transactions.summary.visible")} value={String(tx.data?.total ?? 0)} />
        <Summary label={t("pages.transactions.summary.total")} value={formatEurFromCents(total)} />
        <Summary label={t("pages.transactions.summary.inflow")} value={formatEurFromCents(inflow)} />
        <Summary label={t("pages.transactions.summary.outflow")} value={formatEurFromCents(outflow)} />
      </div>

      <Card className="app-dashboard-surface border-border/60">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>{t("pages.transactions.col.purchasedAt")}</TableHead><TableHead>{t("pages.transactions.col.store")}</TableHead><TableHead>{t("pages.transactions.col.direction")}</TableHead><TableHead>{t("pages.transactions.col.category")}</TableHead><TableHead>{t("pages.transactions.col.source")}</TableHead><TableHead className="text-right">{t("pages.transactions.col.total")}</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {items.length === 0 ? <TableRow><TableCell colSpan={7}><EmptyState icon={<Search className="h-8 w-8" />} title={t("pages.transactions.empty")} /></TableCell></TableRow> : items.map((item) => (
                <TableRow key={item.id}><TableCell>{formatDateTime(item.purchased_at)}</TableCell><TableCell>{item.store_name || item.source_id}</TableCell><TableCell>{directionLabel(item.direction, t)}</TableCell><TableCell>{financeCategoryLabel(item.finance_category_id, t)}</TableCell><TableCell>{item.source_id}</TableCell><TableCell className="text-right">{formatEurFromCents(item.total_gross_cents)}</TableCell><TableCell className="text-right"><Button asChild variant="ghost" size="sm"><Link to={"/transactions/" + item.id}>{t("pages.transactions.details")}</Link></Button></TableCell></TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{t("pages.transactions.pagination", { start: tx.data && tx.data.total > 0 ? offset + 1 : 0, end: tx.data ? Math.min(offset + tx.data.count, tx.data.total) : 0, total: tx.data?.total ?? 0 })}</span>
        <div className="flex gap-2"><Button variant="outline" disabled={offset <= 0} onClick={() => setParam("offset", String(Math.max(0, offset - PAGE_SIZE)))}>{t("pagination.previous")}</Button><Button variant="outline" disabled={!tx.data || offset + PAGE_SIZE >= tx.data.total} onClick={() => setParam("offset", String(offset + PAGE_SIZE))}>{t("pagination.next")}</Button></div>
      </div>
    </section>
  );
}

function SelectField({ label, value, onChange, allLabel, children }: { label: string; value: string; onChange: (value: string) => void; allLabel: string; children: ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label><Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{allLabel}</SelectItem>{children}</SelectContent></Select></div>;
}

function InputField({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return <div className="space-y-2"><Label>{label}</Label><Input type={type} value={value} onChange={(event) => onChange(event.target.value)} /></div>;
}

function Summary({ label, value }: { label: string; value: string }) {
  return <Card className="app-dashboard-surface border-border/60"><CardContent className="p-4"><p className="text-sm text-muted-foreground">{label}</p><p className="text-lg font-semibold">{value}</p></CardContent></Card>;
}
