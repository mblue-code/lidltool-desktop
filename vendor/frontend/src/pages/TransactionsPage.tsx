import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, CheckCircle2, Loader2, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { TransactionsFilters, transactionsQueryOptions } from "@/app/queries";
import { createManualTransaction, ManualTransactionResponse } from "@/api/transactions";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { formatDateTime, formatEurFromCents } from "../utils/format";

const PAGE_SIZE = 25;
const DEFAULT_SORT_FIELD = "purchased_at";
const DEFAULT_SORT_DIRECTION = "desc";
const STICKY_HEADER_CLASS = "sticky top-0 z-10 bg-background";

const FILTER_KEYS = [
  "query",
  "source_id",
  "source_kind",
  "weekday",
  "hour",
  "tz_offset_minutes",
  "merchant_name",
  "year",
  "month",
  "purchased_from",
  "purchased_to",
  "min_total_cents",
  "max_total_cents"
] as const;

const FILTER_LABELS: Record<(typeof FILTER_KEYS)[number], string> = {
  query: "Search",
  source_id: "Source",
  source_kind: "Source kind",
  weekday: "Weekday",
  hour: "Hour",
  tz_offset_minutes: "TZ offset",
  merchant_name: "Merchant",
  year: "Year",
  month: "Month",
  purchased_from: "Purchased from",
  purchased_to: "Purchased to",
  min_total_cents: "Min total",
  max_total_cents: "Max total"
};

type SortField =
  | "purchased_at"
  | "store_name"
  | "source_id"
  | "total_gross_cents"
  | "discount_total_cents";

type SortDirection = "asc" | "desc";

type FilterChip = {
  key: (typeof FILTER_KEYS)[number];
  label: string;
  value: string;
};

type FilterFormValues = {
  query: string;
  sourceId: string;
  sourceKind: string;
  weekday: string;
  hour: string;
  tzOffsetMinutes: string;
  merchantName: string;
  year: string;
  month: string;
  purchasedFrom: string;
  purchasedTo: string;
  minTotal: string;
  maxTotal: string;
};

type ManualFormValues = {
  purchasedAt: string;
  merchantName: string;
  totalGrossCents: string;
  itemName: string;
  itemTotalCents: string;
  idempotencyKey: string;
};

function defaultPurchasedAtValue(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function readNumberParam(value: string | null): number | undefined {
  if (!value) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function readFilterFormValues(searchParams: URLSearchParams): FilterFormValues {
  return {
    query: searchParams.get("query") || "",
    sourceId: searchParams.get("source_id") || "",
    sourceKind: searchParams.get("source_kind") || "",
    weekday: searchParams.get("weekday") || "",
    hour: searchParams.get("hour") || "",
    tzOffsetMinutes: searchParams.get("tz_offset_minutes") || "",
    merchantName: searchParams.get("merchant_name") || "",
    year: searchParams.get("year") || "",
    month: searchParams.get("month") || "",
    purchasedFrom: searchParams.get("purchased_from") || "",
    purchasedTo: searchParams.get("purchased_to") || "",
    minTotal: searchParams.get("min_total_cents") || "",
    maxTotal: searchParams.get("max_total_cents") || ""
  };
}

function readSortField(value: string | null): SortField {
  if (
    value === "purchased_at" ||
    value === "store_name" ||
    value === "source_id" ||
    value === "total_gross_cents" ||
    value === "discount_total_cents"
  ) {
    return value;
  }
  return DEFAULT_SORT_FIELD;
}

function readSortDirection(value: string | null): SortDirection {
  if (value === "asc" || value === "desc") {
    return value;
  }
  return DEFAULT_SORT_DIRECTION;
}

function formatFilterValue(key: (typeof FILTER_KEYS)[number], value: string): string {
  if (key === "purchased_from" || key === "purchased_to") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.valueOf())) {
      return formatDateTime(parsed.toISOString());
    }
  }
  return value;
}

export function TransactionsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [formValues, setFormValues] = useState<FilterFormValues>(() =>
    readFilterFormValues(searchParams)
  );
  const [manualFormValues, setManualFormValues] = useState<ManualFormValues>({
    purchasedAt: defaultPurchasedAtValue(),
    merchantName: "",
    totalGrossCents: "",
    itemName: "",
    itemTotalCents: "",
    idempotencyKey: ""
  });
  const [manualErrorMessage, setManualErrorMessage] = useState<string | null>(null);
  const [manualSuccess, setManualSuccess] = useState<ManualTransactionResponse | null>(null);

  const searchKey = searchParams.toString();
  const sortField = readSortField(searchParams.get("sort"));
  const sortDirection = readSortDirection(searchParams.get("direction"));
  const offset = readNumberParam(searchParams.get("offset")) ?? 0;

  useEffect(() => {
    setFormValues(readFilterFormValues(searchParams));
  }, [searchKey]);

  const queryValues = useMemo<TransactionsFilters>(
    () => ({
      query: searchParams.get("query") || undefined,
      sourceId: searchParams.get("source_id") || undefined,
      sourceKind: searchParams.get("source_kind") || undefined,
      weekday: readNumberParam(searchParams.get("weekday")),
      hour: readNumberParam(searchParams.get("hour")),
      tzOffsetMinutes: readNumberParam(searchParams.get("tz_offset_minutes")),
      merchantName: searchParams.get("merchant_name") || undefined,
      year: readNumberParam(searchParams.get("year")),
      month: readNumberParam(searchParams.get("month")),
      purchasedFrom: searchParams.get("purchased_from") || undefined,
      purchasedTo: searchParams.get("purchased_to") || undefined,
      sortBy: sortField,
      sortDir: sortDirection,
      minTotalCents: readNumberParam(searchParams.get("min_total_cents")),
      maxTotalCents: readNumberParam(searchParams.get("max_total_cents")),
      limit: PAGE_SIZE,
      offset
    }),
    [searchKey, offset, searchParams]
  );

  const appliedFilters = useMemo<FilterChip[]>(() => {
    const chips: FilterChip[] = [];
    for (const key of FILTER_KEYS) {
      const value = searchParams.get(key);
      if (!value) {
        continue;
      }
      chips.push({
        key,
        label: FILTER_LABELS[key],
        value: formatFilterValue(key, value)
      });
    }
    return chips;
  }, [searchKey, searchParams]);

  const { data, error, isPending, isFetching } = useQuery(transactionsQueryOptions(queryValues));
  const manualMutation = useMutation({
    mutationFn: createManualTransaction,
    onSuccess: async (result) => {
      setManualSuccess(result);
      setManualErrorMessage(null);
      setManualFormValues({
        purchasedAt: defaultPurchasedAtValue(),
        merchantName: "",
        totalGrossCents: "",
        itemName: "",
        itemTotalCents: "",
        idempotencyKey: ""
      });
      await queryClient.invalidateQueries({ queryKey: ["transactions"] });
    }
  });

  const loading = isPending || isFetching;
  const errorMessage = error instanceof Error ? error.message : null;

  function applySortIfNeeded(next: URLSearchParams): void {
    if (sortField !== DEFAULT_SORT_FIELD || sortDirection !== DEFAULT_SORT_DIRECTION) {
      next.set("sort", sortField);
      next.set("direction", sortDirection);
    }
  }

  function submitFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const next = new URLSearchParams();
    if (formValues.query.trim()) {
      next.set("query", formValues.query.trim());
    }
    if (formValues.sourceId.trim()) {
      next.set("source_id", formValues.sourceId.trim());
    }
    if (formValues.sourceKind.trim()) {
      next.set("source_kind", formValues.sourceKind.trim());
    }
    if (formValues.weekday.trim()) {
      next.set("weekday", formValues.weekday.trim());
    }
    if (formValues.hour.trim()) {
      next.set("hour", formValues.hour.trim());
    }
    if (formValues.tzOffsetMinutes.trim()) {
      next.set("tz_offset_minutes", formValues.tzOffsetMinutes.trim());
    }
    if (formValues.merchantName.trim()) {
      next.set("merchant_name", formValues.merchantName.trim());
    }
    if (formValues.year.trim()) {
      next.set("year", formValues.year.trim());
    }
    if (formValues.month.trim()) {
      next.set("month", formValues.month.trim());
    }
    if (formValues.purchasedFrom.trim()) {
      next.set("purchased_from", formValues.purchasedFrom.trim());
    }
    if (formValues.purchasedTo.trim()) {
      next.set("purchased_to", formValues.purchasedTo.trim());
    }
    if (formValues.minTotal.trim()) {
      next.set("min_total_cents", formValues.minTotal.trim());
    }
    if (formValues.maxTotal.trim()) {
      next.set("max_total_cents", formValues.maxTotal.trim());
    }
    next.set("offset", "0");
    applySortIfNeeded(next);
    setSearchParams(next);
  }

  function movePage(delta: number): void {
    const nextOffset = Math.max(0, offset + delta);
    const next = new URLSearchParams(searchParams);
    next.set("offset", String(nextOffset));
    setSearchParams(next);
  }

  function updateSort(nextField: SortField): void {
    const currentField = readSortField(searchParams.get("sort"));
    const currentDirection = readSortDirection(searchParams.get("direction"));
    const nextDirection: SortDirection =
      currentField === nextField
        ? currentDirection === "asc"
          ? "desc"
          : "asc"
        : nextField === "purchased_at"
          ? "desc"
          : "asc";

    const next = new URLSearchParams(searchParams);
    next.set("sort", nextField);
    next.set("direction", nextDirection);
    setSearchParams(next);
  }

  function removeFilter(key: (typeof FILTER_KEYS)[number]): void {
    const next = new URLSearchParams(searchParams);
    next.delete(key);
    next.set("offset", "0");
    setSearchParams(next);
  }

  function clearFilters(): void {
    const next = new URLSearchParams();
    next.set("offset", "0");
    applySortIfNeeded(next);
    setSearchParams(next);
  }

  async function submitManualTransaction(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setManualErrorMessage(null);
    setManualSuccess(null);

    const purchasedDate = new Date(manualFormValues.purchasedAt);
    if (Number.isNaN(purchasedDate.valueOf())) {
      setManualErrorMessage("Purchased at must be a valid date and time.");
      return;
    }
    const merchantName = manualFormValues.merchantName.trim();
    if (!merchantName) {
      setManualErrorMessage("Merchant is required.");
      return;
    }
    const totalGrossCents = Number(manualFormValues.totalGrossCents);
    if (!Number.isInteger(totalGrossCents) || totalGrossCents < 0) {
      setManualErrorMessage("Total cents must be a non-negative integer.");
      return;
    }

    const itemName = manualFormValues.itemName.trim();
    const itemTotalRaw = manualFormValues.itemTotalCents.trim();
    if ((itemName && !itemTotalRaw) || (!itemName && itemTotalRaw)) {
      setManualErrorMessage("Item name and item total cents must be filled together.");
      return;
    }

    let itemTotalCents: number | null = null;
    if (itemTotalRaw) {
      const parsed = Number(itemTotalRaw);
      if (!Number.isInteger(parsed) || parsed < 0) {
        setManualErrorMessage("Item total cents must be a non-negative integer.");
        return;
      }
      itemTotalCents = parsed;
    }

    try {
      await manualMutation.mutateAsync({
        purchased_at: purchasedDate.toISOString(),
        merchant_name: merchantName,
        total_gross_cents: totalGrossCents,
        idempotency_key: manualFormValues.idempotencyKey.trim() || undefined,
        items:
          itemName && itemTotalCents !== null
            ? [
                {
                  name: itemName,
                  line_total_cents: itemTotalCents,
                  qty: 1,
                  line_no: 1
                }
              ]
            : undefined
      });
    } catch (mutationError) {
      setManualErrorMessage(
        mutationError instanceof Error ? mutationError.message : "Failed to create transaction."
      );
    }
  }

  function renderSortButton(field: SortField, label: string) {
    const active = sortField === field;
    const activeSortState = active ? (sortDirection === "asc" ? "ascending" : "descending") : "not sorted";
    const icon = !active ? (
      <ArrowUpDown className="h-3.5 w-3.5" />
    ) : sortDirection === "asc" ? (
      <ArrowUp className="h-3.5 w-3.5" />
    ) : (
      <ArrowDown className="h-3.5 w-3.5" />
    );

    return (
      <button
        type="button"
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1 py-0.5 text-left text-xs font-medium transition-colors",
          active ? "text-foreground" : "text-muted-foreground hover:text-foreground"
        )}
        onClick={() => updateSort(field)}
        aria-label={`Sort by ${label}`}
        aria-pressed={active}
      >
        <span>{label}</span>
        {icon}
        <span className="sr-only">{activeSortState}</span>
      </button>
    );
  }

  function ariaSortForField(field: SortField): "ascending" | "descending" | "none" {
    if (sortField !== field) {
      return "none";
    }
    return sortDirection === "asc" ? "ascending" : "descending";
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Add One-off Purchase</CardTitle>
          <p className="text-sm text-muted-foreground">
            Add a manual transaction for merchants that do not need a dedicated connector.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 md:grid-cols-6" onSubmit={submitManualTransaction}>
            <div className="space-y-2">
              <Label htmlFor="manual-purchased-at">Purchased at (one-off)</Label>
              <Input
                id="manual-purchased-at"
                type="datetime-local"
                value={manualFormValues.purchasedAt}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    purchasedAt: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-merchant">Merchant (one-off)</Label>
              <Input
                id="manual-merchant"
                value={manualFormValues.merchantName}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    merchantName: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-total-cents">Total cents (one-off)</Label>
              <Input
                id="manual-total-cents"
                type="number"
                min={0}
                value={manualFormValues.totalGrossCents}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    totalGrossCents: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-item-name">Item (optional)</Label>
              <Input
                id="manual-item-name"
                value={manualFormValues.itemName}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    itemName: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-item-total-cents">Item total cents (optional)</Label>
              <Input
                id="manual-item-total-cents"
                type="number"
                min={0}
                value={manualFormValues.itemTotalCents}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    itemTotalCents: event.target.value
                  }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="manual-idempotency-key">Idempotency key (optional)</Label>
              <Input
                id="manual-idempotency-key"
                value={manualFormValues.idempotencyKey}
                onChange={(event) =>
                  setManualFormValues((previous) => ({
                    ...previous,
                    idempotencyKey: event.target.value
                  }))
                }
              />
            </div>
            <Button type="submit" className="md:col-span-6 md:w-fit" disabled={manualMutation.isPending}>
              {manualMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                "Add one-off purchase"
              )}
            </Button>
          </form>

          {manualErrorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>Manual ingestion failed</AlertTitle>
              <AlertDescription>{manualErrorMessage}</AlertDescription>
            </Alert>
          ) : null}

          {manualSuccess ? (
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>Transaction saved</AlertTitle>
              <AlertDescription className="space-y-1">
                <p>
                  {manualSuccess.reused ? "Existing transaction reused." : "New transaction created."} Source:
                  {" "}
                  <span className="font-medium">{manualSuccess.source_id}</span>
                </p>
                <Button asChild variant="link" className="h-auto p-0">
                  <Link to={`/transactions/${manualSuccess.transaction_id}`}>Open transaction details</Link>
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Transactions</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-5" onSubmit={submitFilters}>
            <div className="space-y-2">
              <Label htmlFor="query">Search</Label>
              <Input
                id="query"
                value={formValues.query}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, query: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source">Source</Label>
              <Input
                id="source"
                value={formValues.sourceId}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, sourceId: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-kind">Source kind</Label>
              <Input
                id="source-kind"
                value={formValues.sourceKind}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, sourceKind: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="merchant">Merchant</Label>
              <Input
                id="merchant"
                value={formValues.merchantName}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, merchantName: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="year">Year</Label>
              <Input
                id="year"
                type="number"
                value={formValues.year}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, year: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="month">Month</Label>
              <Input
                id="month"
                type="number"
                value={formValues.month}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, month: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="weekday">Weekday (0-6)</Label>
              <Input
                id="weekday"
                type="number"
                min={0}
                max={6}
                value={formValues.weekday}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, weekday: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="hour">Hour (0-23)</Label>
              <Input
                id="hour"
                type="number"
                min={0}
                max={23}
                value={formValues.hour}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, hour: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="tz-offset-minutes">TZ offset minutes</Label>
              <Input
                id="tz-offset-minutes"
                type="number"
                value={formValues.tzOffsetMinutes}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, tzOffsetMinutes: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="purchased-from">Purchased from</Label>
              <Input
                id="purchased-from"
                type="datetime-local"
                value={formValues.purchasedFrom}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, purchasedFrom: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="purchased-to">Purchased to</Label>
              <Input
                id="purchased-to"
                type="datetime-local"
                value={formValues.purchasedTo}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, purchasedTo: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="min-total">Min total cents</Label>
              <Input
                id="min-total"
                type="number"
                value={formValues.minTotal}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, minTotal: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max-total">Max total cents</Label>
              <Input
                id="max-total"
                type="number"
                value={formValues.maxTotal}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, maxTotal: event.target.value }))
                }
              />
            </div>
            <Button type="submit" className="self-end">
              Apply filters
            </Button>
          </form>

          {appliedFilters.length > 0 ? (
            <div className="mt-4 flex flex-wrap items-center gap-2">
              {appliedFilters.map((filter) => (
                <Badge key={filter.key} variant="secondary" className="gap-1 pr-1">
                  <span>
                    {filter.label}: {filter.value}
                  </span>
                  <button
                    type="button"
                    className="rounded-sm p-0.5 text-muted-foreground transition-colors hover:text-foreground"
                    onClick={() => removeFilter(filter.key)}
                    aria-label={`Remove ${filter.label} filter`}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
              <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
                Clear all
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load transactions</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardContent className="pt-6">
          {loading ? <Skeleton className="h-52 w-full" /> : null}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("purchased_at")}>
                  {renderSortButton("purchased_at", "Date")}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("store_name")}>
                  {renderSortButton("store_name", "Merchant")}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("source_id")}>
                  {renderSortButton("source_id", "Source")}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("total_gross_cents")}>
                  {renderSortButton("total_gross_cents", "Total")}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("discount_total_cents")}>
                  {renderSortButton("discount_total_cents", "Discount")}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS}>Open</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.items || []).map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{formatDateTime(item.purchased_at)}</TableCell>
                  <TableCell>{item.store_name || "—"}</TableCell>
                  <TableCell>{item.source_id}</TableCell>
                  <TableCell className="tabular-nums">{formatEurFromCents(item.total_gross_cents)}</TableCell>
                  <TableCell className="tabular-nums">{formatEurFromCents(item.discount_total_cents ?? 0)}</TableCell>
                  <TableCell>
                    <Button asChild variant="link" className="px-0">
                      <Link to={`/transactions/${item.id}`}>Details</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {data && data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>No transactions match current filters.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          <div className="mt-4 flex items-center justify-between">
            <Button type="button" variant="outline" onClick={() => movePage(-PAGE_SIZE)} disabled={offset === 0}>
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Showing {data?.count ?? 0} of {data?.total ?? 0}
            </span>
            <Button
              type="button"
              variant="outline"
              onClick={() => movePage(PAGE_SIZE)}
              disabled={!data || offset + PAGE_SIZE >= data.total}
            >
              Next
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
