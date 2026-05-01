import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowDown, ArrowUp, ArrowUpDown, Bot, CalendarDays, Filter, Search, SlidersHorizontal, X } from "lucide-react";
import { toast } from "sonner";

import { TransactionsFilters, transactionsQueryOptions } from "@/app/queries";
import { fetchAISettings } from "@/api/aiSettings";
import {
  fetchTransactionCategorizationAgentStatus,
  fetchTransactionFacets,
  startTransactionCategorizationAgent,
  type TransactionListItem
} from "@/api/transactions";
import { isDemoSnapshotMode } from "@/demo/mode";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
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
import { cn } from "@/lib/utils";
import { formatDateTime, formatEurFromCents } from "@/utils/format";

const PAGE_SIZE = 25;
const SORT_FIELDS = ["purchased_at", "store_name", "direction", "finance_category_id", "source_id", "total_gross_cents"] as const;
const DIRECTIONS = ["outflow", "inflow", "transfer", "neutral"] as const;

type SortField = (typeof SORT_FIELDS)[number];
type SortDirection = "asc" | "desc";

type UrlFilterKey =
  | "query"
  | "direction_filter"
  | "finance_category_id"
  | "parent_category"
  | "tag"
  | "merchant_name"
  | "source_id"
  | "source_account_id"
  | "purchased_from"
  | "purchased_to"
  | "min_total"
  | "max_total"
  | "uncategorized"
  | "min_category_confidence"
  | "max_category_confidence"
  | "date_range";

type FilterChip = {
  key: UrlFilterKey;
  label: string;
  value: string;
};

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

function readSortField(value: string | null): SortField {
  return SORT_FIELDS.includes(value as SortField) ? (value as SortField) : "purchased_at";
}

function readSortDirection(value: string | null): SortDirection {
  return value === "asc" ? "asc" : "desc";
}

function formatLocalDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localDate(daysBack: number): string {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(date.getDate() - daysBack);
  return formatLocalDate(date);
}

function monthStart(): string {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  date.setDate(1);
  return formatLocalDate(date);
}

export function TransactionsPage() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const demoMode = isDemoSnapshotMode();
  const [searchParams, setSearchParams] = useSearchParams();
  const [advancedOpen, setAdvancedOpen] = useState(() => hasAdvancedFilters(searchParams));
  const [categorizationJobId, setCategorizationJobId] = useState<string | null>(null);

  const offset = Number(searchParams.get("offset") || 0);
  const sortBy = readSortField(searchParams.get("sort"));
  const sortDir = readSortDirection(searchParams.get("direction"));
  const defaultPurchasedFrom = monthStart();
  const explicitAllTime = searchParams.get("date_range") === "all";
  const effectivePurchasedFrom = explicitAllTime ? undefined : searchParams.get("purchased_from") || defaultPurchasedFrom;
  const effectivePurchasedTo = explicitAllTime ? undefined : searchParams.get("purchased_to") || undefined;

  const filters = useMemo<TransactionsFilters>(() => ({
    query: searchParams.get("query") || undefined,
    direction: (searchParams.get("direction_filter") || undefined) as TransactionsFilters["direction"],
    financeCategoryId: searchParams.get("finance_category_id") || undefined,
    parentCategory: searchParams.get("parent_category") || undefined,
    tag: searchParams.get("tag") || undefined,
    merchantName: searchParams.get("merchant_name") || undefined,
    sourceId: searchParams.get("source_id") || undefined,
    sourceAccountId: searchParams.get("source_account_id") || undefined,
    purchasedFrom: effectivePurchasedFrom,
    purchasedTo: effectivePurchasedTo,
    minTotalCents: cents(searchParams.get("min_total")),
    maxTotalCents: cents(searchParams.get("max_total")),
    uncategorized: searchParams.get("uncategorized") === "true",
    minCategoryConfidence: searchParams.get("min_category_confidence") ? Number(searchParams.get("min_category_confidence")) : undefined,
    maxCategoryConfidence: searchParams.get("max_category_confidence") ? Number(searchParams.get("max_category_confidence")) : undefined,
    sortBy,
    sortDir,
    limit: PAGE_SIZE,
    offset
  }), [effectivePurchasedFrom, effectivePurchasedTo, offset, searchParams, sortBy, sortDir]);

  const transactionsQuery = useQuery(transactionsQueryOptions(filters));
  const facetsQuery = useQuery({ queryKey: ["transaction-facets", filters], queryFn: () => fetchTransactionFacets(filters) });
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

  const items = transactionsQuery.data?.items ?? [];
  const facets = facetsQuery.data;
  const total = items.reduce((sum, item) => sum + item.total_gross_cents, 0);
  const inflow = items.filter((item) => item.direction === "inflow").reduce((sum, item) => sum + item.total_gross_cents, 0);
  const outflow = items.filter((item) => (item.direction || "outflow") === "outflow").reduce((sum, item) => sum + item.total_gross_cents, 0);
  const summary = transactionsQuery.data?.summary ?? {
    count: items.length,
    total_cents: total,
    inflow_cents: inflow,
    outflow_cents: outflow
  };
  const categorizationReady = aiSettings.data?.categorization_enabled === true && aiSettings.data?.categorization_runtime_ready === true;
  const categorizationJob = categorizationStatus.data;
  const categorizationRunning = categorizationJob?.status === "queued" || categorizationJob?.status === "running";
  const activeChips = useMemo(() => buildActiveChips(searchParams, t), [searchParams, t]);

  function updateParams(updates: Record<string, string | undefined>, options: { resetOffset?: boolean } = { resetOffset: true }) {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value && value !== "all") next.set(key, value);
      else next.delete(key);
    }
    if (options.resetOffset !== false) next.set("offset", "0");
    setSearchParams(next);
  }

  function clearFilters() {
    const next = new URLSearchParams();
    next.set("sort", sortBy);
    next.set("direction", sortDir);
    next.set("purchased_from", defaultPurchasedFrom);
    setSearchParams(next);
  }

  function setSort(field: SortField) {
    updateParams({ sort: field, direction: sortBy === field && sortDir === "desc" ? "asc" : "desc" }, { resetOffset: false });
  }

  function applyQuickFilter(kind: "thisMonth" | "last7Days" | "highValue" | "allTime") {
    if (kind === "thisMonth") updateParams({ purchased_from: monthStart(), purchased_to: undefined, date_range: undefined });
    if (kind === "last7Days") updateParams({ purchased_from: localDate(6), purchased_to: undefined, date_range: undefined });
    if (kind === "highValue") updateParams({ min_total: "50" });
    if (kind === "allTime") updateParams({ purchased_from: undefined, purchased_to: undefined, date_range: "all" });
    setAdvancedOpen(true);
  }

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

  useEffect(() => {
    setAdvancedOpen((current) => current || hasAdvancedFilters(searchParams));
  }, [searchParams]);

  useEffect(() => {
    if (searchParams.has("purchased_from") || searchParams.has("purchased_to") || searchParams.get("date_range") === "all") return;
    const next = new URLSearchParams(searchParams);
    next.set("purchased_from", defaultPurchasedFrom);
    next.set("offset", "0");
    setSearchParams(next, { replace: true });
  }, [defaultPurchasedFrom, searchParams, setSearchParams]);

  useEffect(() => {
    if (!categorizationJob) return;
    if (categorizationJob.status === "completed") {
      setCategorizationJobId(null);
      void queryClient.invalidateQueries({ queryKey: ["transactions"] });
      void queryClient.invalidateQueries({ queryKey: ["transaction-facets"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-overview"] });
      toast.success(t("pages.transactions.categorization.completed", { transactions: categorizationJob.updated_transaction_count, items: categorizationJob.updated_item_count }));
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
          title={categorizationReady ? t("pages.transactions.categorization.tooltip") : t("pages.transactions.categorization.notReady")}
        >
          <Bot className="mr-2 h-4 w-4" />
          {categorizationRunning || categorizationMutation.isPending ? t("pages.transactions.categorization.running") : t("pages.transactions.categorization.button")}
        </Button>
        <Button asChild><Link to="/add">{t("nav.item.addReceipt")}</Link></Button>
      </PageHeader>

      <CategorizationStrip ready={categorizationReady} model={aiSettings.data?.categorization_model} job={categorizationJob} running={categorizationRunning} />

      <Card className="app-dashboard-surface border-border/60">
        <CardContent className="space-y-4 p-4">
          <div className="grid gap-3 xl:grid-cols-[minmax(260px,1.4fr)_auto] xl:items-end">
            <div className="space-y-2">
              <Label>{t("pages.transactions.filter.query")}</Label>
              <SearchInput value={searchParams.get("query") || ""} onChange={(value) => updateParams({ query: value || undefined })} debounceMs={200} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" onClick={() => applyQuickFilter("thisMonth")}><CalendarDays className="mr-2 h-4 w-4" />{t("pages.transactions.quickFilter.thisMonth")}</Button>
              <Button type="button" variant="outline" onClick={() => applyQuickFilter("last7Days")}>{t("pages.transactions.quickFilter.last7Days")}</Button>
              <Button type="button" variant="outline" onClick={() => applyQuickFilter("highValue")}>{t("pages.transactions.quickFilter.highValue")}</Button>
              <Button type="button" variant={explicitAllTime ? "secondary" : "outline"} onClick={() => applyQuickFilter("allTime")}>{t("pages.transactions.quickFilter.allTime")}</Button>
              <Button type="button" variant={advancedOpen ? "secondary" : "outline"} onClick={() => setAdvancedOpen((value) => !value)}><SlidersHorizontal className="mr-2 h-4 w-4" />{advancedOpen ? t("pages.transactions.fewerFilters") : t("pages.transactions.moreFilters")}</Button>
            </div>
          </div>

          <DirectionControl value={searchParams.get("direction_filter") || "all"} onChange={(value) => updateParams({ direction_filter: value })} />

          {advancedOpen ? (
            <div className="grid gap-3 lg:grid-cols-4">
              <SelectField label={t("pages.transactions.filter.category")} value={searchParams.get("finance_category_id") || "all"} onChange={(value) => updateParams({ finance_category_id: value })} allLabel={t("pages.transactions.allCategories")}>
                {(facets?.categories ?? []).map((row) => <SelectItem key={row.category_id} value={row.category_id}>{financeCategoryLabel(row.category_id, t)} ({row.count})</SelectItem>)}
              </SelectField>
              <SelectField label={t("pages.transactions.filter.parentCategory")} value={searchParams.get("parent_category") || "all"} onChange={(value) => updateParams({ parent_category: value })} allLabel={t("pages.transactions.allCategories")}>
                {uniqueParentCategories(facets?.categories ?? []).map((row) => <SelectItem key={row.value} value={row.value}>{financeCategoryLabel(row.value, t)} ({row.count})</SelectItem>)}
              </SelectField>
              <SelectField label={t("pages.transactions.filter.merchant")} value={searchParams.get("merchant_name") || "all"} onChange={(value) => updateParams({ merchant_name: value })} allLabel={t("pages.transactions.allMerchants")}>
                {(facets?.merchants ?? []).map((row) => <SelectItem key={row.value} value={row.value}>{row.value} ({row.count})</SelectItem>)}
              </SelectField>
              <SelectField label={t("pages.transactions.filter.source")} value={searchParams.get("source_id") || "all"} onChange={(value) => updateParams({ source_id: value })} allLabel={t("pages.transactions.allSources")}>
                {(facets?.sources ?? []).map((row) => <SelectItem key={row.source_id} value={row.source_id}>{row.source_id} ({row.count})</SelectItem>)}
              </SelectField>
              <SelectField label={t("pages.transactions.filter.tag")} value={searchParams.get("tag") || "all"} onChange={(value) => updateParams({ tag: value })} allLabel={t("pages.transactions.filter.tag")}>
                {(facets?.tags ?? []).map((row) => <SelectItem key={row.value} value={row.value}>{row.value} ({row.count})</SelectItem>)}
              </SelectField>
              <InputField label={t("pages.transactions.filter.purchasedFrom")} type="date" value={effectivePurchasedFrom || ""} onChange={(value) => updateParams({ purchased_from: value || undefined, date_range: undefined })} />
              <InputField label={t("pages.transactions.filter.purchasedTo")} type="date" value={effectivePurchasedTo || ""} onChange={(value) => updateParams({ purchased_to: value || undefined, date_range: undefined })} />
              <div className="grid grid-cols-2 gap-3">
                <InputField label={t("pages.transactions.amountFrom")} value={euro(searchParams.get("min_total"))} onChange={(value) => updateParams({ min_total: value || undefined })} />
                <InputField label={t("pages.transactions.amountTo")} value={euro(searchParams.get("max_total"))} onChange={(value) => updateParams({ max_total: value || undefined })} />
              </div>
              <InputField label={t("pages.transactions.filter.minConfidence")} type="number" value={searchParams.get("min_category_confidence") || ""} onChange={(value) => updateParams({ min_category_confidence: value || undefined })} />
              <InputField label={t("pages.transactions.filter.maxConfidence")} type="number" value={searchParams.get("max_category_confidence") || ""} onChange={(value) => updateParams({ max_category_confidence: value || undefined })} />
              <div className="flex items-end">
                <Button type="button" variant={searchParams.get("uncategorized") === "true" ? "secondary" : "outline"} className="w-full justify-start" onClick={() => updateParams({ uncategorized: searchParams.get("uncategorized") === "true" ? undefined : "true" })}>
                  <Filter className="mr-2 h-4 w-4" />{t("pages.transactions.filter.uncategorized")}
                </Button>
              </div>
            </div>
          ) : null}

          <ActiveChips chips={activeChips} onRemove={(key) => updateParams({ [key]: undefined })} onClear={clearFilters} />
        </CardContent>
      </Card>

      <SummaryStrip
        key={`${summary.count}:${summary.total_cents}:${summary.inflow_cents}:${summary.outflow_cents}`}
        totalCount={summary.count}
        visibleCents={summary.total_cents}
        inflowCents={summary.inflow_cents}
        outflowCents={summary.outflow_cents}
      />

      <Card className="app-dashboard-surface hidden border-border/60 md:block">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <SortableHead label={t("pages.transactions.col.purchasedAt")} field="purchased_at" current={sortBy} direction={sortDir} onSort={setSort} />
                <SortableHead label={t("pages.transactions.col.store")} field="store_name" current={sortBy} direction={sortDir} onSort={setSort} />
                <SortableHead label={t("pages.transactions.col.direction")} field="direction" current={sortBy} direction={sortDir} onSort={setSort} />
                <SortableHead label={t("pages.transactions.col.category")} field="finance_category_id" current={sortBy} direction={sortDir} onSort={setSort} />
                <SortableHead label={t("pages.transactions.col.source")} field="source_id" current={sortBy} direction={sortDir} onSort={setSort} />
                <SortableHead label={t("pages.transactions.col.total")} field="total_gross_cents" current={sortBy} direction={sortDir} onSort={setSort} align="right" />
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow><TableCell colSpan={7}><EmptyState icon={<Search className="h-8 w-8" />} title={t("pages.transactions.empty")} /></TableCell></TableRow>
              ) : items.map((item) => <TransactionRow key={item.id} item={item} />)}
            </TableBody>
          </Table>
        </div>
      </Card>

      <div className="space-y-3 md:hidden">
        {items.length === 0 ? (
          <Card className="app-dashboard-surface border-border/60"><CardContent className="p-6"><EmptyState icon={<Search className="h-8 w-8" />} title={t("pages.transactions.empty")} /></CardContent></Card>
        ) : items.map((item) => <TransactionMobileCard key={item.id} item={item} />)}
      </div>

      <PaginationFooter offset={offset} count={transactionsQuery.data?.count ?? 0} total={transactionsQuery.data?.total ?? 0} onPage={(nextOffset) => updateParams({ offset: String(nextOffset) }, { resetOffset: false })} />
    </section>
  );

  function DirectionControl({ value, onChange }: { value: string; onChange: (value: string) => void }) {
    return (
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" variant={value === "all" ? "secondary" : "outline"} onClick={() => onChange("all")}>{t("pages.transactions.allDirections")}</Button>
        {DIRECTIONS.map((direction) => (
          <Button key={direction} type="button" size="sm" variant={value === direction ? "secondary" : "outline"} onClick={() => onChange(direction)}>{directionLabel(direction, t)}</Button>
        ))}
      </div>
    );
  }
}

function hasAdvancedFilters(searchParams: URLSearchParams): boolean {
  return ["finance_category_id", "parent_category", "tag", "merchant_name", "source_id", "source_account_id", "purchased_from", "purchased_to", "min_total", "max_total", "uncategorized", "min_category_confidence", "max_category_confidence"].some((key) => Boolean(searchParams.get(key)));
}

function uniqueParentCategories(categories: Array<{ parent_category_id: string | null; count: number }>): Array<{ value: string; count: number }> {
  const counts = new Map<string, number>();
  for (const category of categories) {
    if (!category.parent_category_id) continue;
    counts.set(category.parent_category_id, (counts.get(category.parent_category_id) ?? 0) + category.count);
  }
  return Array.from(counts, ([value, count]) => ({ value, count }));
}

function buildActiveChips(searchParams: URLSearchParams, t: ReturnType<typeof useI18n>["t"]): FilterChip[] {
  const labels: Record<UrlFilterKey, string> = {
    query: t("pages.transactions.filter.query"),
    direction_filter: t("pages.transactions.filter.direction"),
    finance_category_id: t("pages.transactions.filter.category"),
    parent_category: t("pages.transactions.filter.parentCategory"),
    tag: t("pages.transactions.filter.tag"),
    merchant_name: t("pages.transactions.filter.merchant"),
    source_id: t("pages.transactions.filter.source"),
    source_account_id: t("pages.transactions.filter.sourceAccount"),
    purchased_from: t("pages.transactions.filter.purchasedFrom"),
    purchased_to: t("pages.transactions.filter.purchasedTo"),
    min_total: t("pages.transactions.chip.minTotal"),
    max_total: t("pages.transactions.chip.maxTotal"),
    uncategorized: t("pages.transactions.filter.uncategorized"),
    min_category_confidence: t("pages.transactions.filter.minConfidence"),
    max_category_confidence: t("pages.transactions.filter.maxConfidence"),
    date_range: t("pages.transactions.filter.dateRange")
  };
  return (Object.keys(labels) as UrlFilterKey[]).flatMap((key) => {
    const value = searchParams.get(key);
    if (!value) return [];
    const display = key === "finance_category_id" || key === "parent_category" ? financeCategoryLabel(value, t) : key === "date_range" && value === "all" ? t("pages.transactions.quickFilter.allTime") : value;
    return [{ key, label: labels[key], value: key === "uncategorized" ? labels[key] : display }];
  });
}

function ActiveChips({ chips, onRemove, onClear }: { chips: FilterChip[]; onRemove: (key: UrlFilterKey) => void; onClear: () => void }) {
  const { t } = useI18n();
  if (chips.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((chip) => (
        <Badge key={chip.key} variant="secondary" className="gap-1 rounded-full px-3 py-1">
          <span>{chip.label}: {chip.value}</span>
          <button type="button" aria-label={t("pages.transactions.removeFilter", { label: chip.label })} onClick={() => onRemove(chip.key)}><X className="h-3 w-3" /></button>
        </Badge>
      ))}
      <Button type="button" variant="ghost" size="sm" onClick={onClear}>{t("pages.transactions.clearFilters")}</Button>
    </div>
  );
}

function CategorizationStrip({ ready, model, job, running }: { ready: boolean; model?: string | null; job?: { status: string; updated_transaction_count: number; updated_item_count: number } | null; running: boolean }) {
  const { t } = useI18n();
  function statusLabel(status: string): string {
    if (status === "queued") return t("pages.transactions.categorization.status.queued");
    if (status === "running") return t("pages.transactions.categorization.status.running");
    if (status === "completed") return t("pages.transactions.categorization.status.completed");
    if (status === "error") return t("pages.transactions.categorization.status.error");
    return status;
  }
  return (
    <Card className="app-dashboard-surface border-border/60">
      <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{t("pages.transactions.categorization.title")}</p>
            <Badge variant={ready ? "secondary" : "outline"}>{ready ? t("pages.transactions.categorization.ready") : t("pages.transactions.categorization.notConfigured")}</Badge>
            {model ? <Badge variant="outline">{model}</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">{t("pages.transactions.categorization.description")}</p>
          {!ready ? <p className="text-xs text-muted-foreground">{t("pages.transactions.categorization.settingsHint")} <Link className="font-medium text-primary underline-offset-4 hover:underline" to="/settings/ai">{t("pages.transactions.categorization.settingsLink")}</Link></p> : null}
        </div>
        {job ? (
          <div className="grid shrink-0 gap-1 text-sm text-muted-foreground sm:grid-cols-3 md:text-right">
            <span>{t("pages.transactions.categorization.status")}: {statusLabel(job.status)}</span>
            <span>{t("pages.transactions.categorization.transactions")}: {job.updated_transaction_count}</span>
            <span>{t("pages.transactions.categorization.items")}: {job.updated_item_count}</span>
          </div>
        ) : running ? <Badge variant="secondary">{t("pages.transactions.categorization.running")}</Badge> : null}
      </CardContent>
    </Card>
  );
}

function SummaryStrip({ totalCount, visibleCents, inflowCents, outflowCents }: { totalCount: number; visibleCents: number; inflowCents: number; outflowCents: number }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-3 md:grid-cols-4">
      <Summary label={t("pages.transactions.summary.visible")} value={String(totalCount)} />
      <Summary label={t("pages.transactions.summary.total")} value={formatEurFromCents(visibleCents)} />
      <Summary label={t("pages.transactions.summary.inflow")} value={formatEurFromCents(inflowCents)} />
      <Summary label={t("pages.transactions.summary.outflow")} value={formatEurFromCents(outflowCents)} />
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return <Card className="app-dashboard-surface border-border/60"><CardContent className="p-4"><p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">{label}</p><p className="mt-2 min-w-0 truncate text-2xl font-semibold tabular-nums">{value}</p></CardContent></Card>;
}

function SortableHead({ label, field, current, direction, onSort, align }: { label: string; field: SortField; current: SortField; direction: SortDirection; onSort: (field: SortField) => void; align?: "right" }) {
  const active = current === field;
  const Icon = !active ? ArrowUpDown : direction === "asc" ? ArrowUp : ArrowDown;
  return <TableHead className={cn(align === "right" && "text-right")}><Button type="button" variant="ghost" size="sm" className={cn("h-8 px-1", align === "right" && "ml-auto")} onClick={() => onSort(field)}>{label}<Icon className="ml-1 h-3.5 w-3.5" /></Button></TableHead>;
}

function TransactionRow({ item }: { item: TransactionListItem }) {
  const { t } = useI18n();
  const category = financeCategoryLabel(item.finance_category_id, t);
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap">{formatDateTime(item.purchased_at)}</TableCell>
      <TableCell className="min-w-[180px] max-w-[280px] truncate font-medium">{item.store_name || item.source_id}</TableCell>
      <TableCell><DirectionBadge direction={item.direction || "outflow"} /></TableCell>
      <TableCell className="max-w-[220px] truncate">{category}</TableCell>
      <TableCell className="max-w-[180px] truncate text-muted-foreground">{item.source_account_id || item.source_id}</TableCell>
      <TableCell className="whitespace-nowrap text-right font-semibold tabular-nums">{formatEurFromCents(item.total_gross_cents)}</TableCell>
      <TableCell className="text-right"><Button asChild variant="ghost" size="sm"><Link to={`/transactions/${item.id}`}>{t("pages.transactions.details")}</Link></Button></TableCell>
    </TableRow>
  );
}

function TransactionMobileCard({ item }: { item: TransactionListItem }) {
  const { t } = useI18n();
  const direction = directionLabel(item.direction || "outflow", t);
  const category = financeCategoryLabel(item.finance_category_id, t);
  return (
    <Card className="app-dashboard-surface border-border/60">
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><p className="truncate font-medium">{item.store_name || item.source_id}</p><p className="mt-1 text-sm text-muted-foreground">{formatDateTime(item.purchased_at)}</p></div>
          <p className="whitespace-nowrap font-semibold tabular-nums">{formatEurFromCents(item.total_gross_cents)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2"><DirectionBadge direction={item.direction || "outflow"} /><Badge variant="outline">{t("pages.transactions.mobileMeta", { direction, category })}</Badge>{item.finance_tags?.map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}</div>
        <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground"><span className="truncate">{item.source_account_id || item.source_id}</span><Button asChild variant="ghost" size="sm"><Link to={`/transactions/${item.id}`}>{t("pages.transactions.details")}</Link></Button></div>
      </CardContent>
    </Card>
  );
}

function DirectionBadge({ direction }: { direction: string }) {
  const { t } = useI18n();
  const tone = direction === "inflow" ? "bg-emerald-500/10 text-emerald-600" : direction === "outflow" ? "bg-rose-500/10 text-rose-600" : "bg-slate-500/10 text-slate-600";
  return <Badge variant="outline" className={cn("border-transparent", tone)}>{directionLabel(direction, t)}</Badge>;
}

function SelectField({ label, value, onChange, allLabel, children }: { label: string; value: string; onChange: (value: string) => void; allLabel: string; children: ReactNode }) {
  return <div className="space-y-2"><Label>{label}</Label><Select value={value} onValueChange={onChange}><SelectTrigger><SelectValue placeholder={allLabel} /></SelectTrigger><SelectContent><SelectItem value="all">{allLabel}</SelectItem>{children}</SelectContent></Select></div>;
}

function InputField({ label, value, onChange, type = "text" }: { label: string; value: string; onChange: (value: string) => void; type?: string }) {
  return <div className="space-y-2"><Label>{label}</Label><Input type={type} value={value} onChange={(event) => onChange(event.target.value)} /></div>;
}

function PaginationFooter({ offset, count, total, onPage }: { offset: number; count: number; total: number; onPage: (offset: number) => void }) {
  const { t } = useI18n();
  const start = total > 0 ? offset + 1 : 0;
  const end = Math.min(offset + count, total);
  return <div className="flex flex-col gap-3 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between"><span>{t("pages.transactions.pagination", { start, end, total })}</span><div className="flex gap-2"><Button variant="outline" disabled={offset <= 0} onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))}>{t("pagination.previous")}</Button><Button variant="outline" disabled={offset + PAGE_SIZE >= total} onClick={() => onPage(offset + PAGE_SIZE)}>{t("pagination.next")}</Button></div></div>;
}
