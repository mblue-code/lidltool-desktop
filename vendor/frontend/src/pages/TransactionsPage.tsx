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
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
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

export function TransactionsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { t } = useI18n();
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
    const filterLabels: Record<(typeof FILTER_KEYS)[number], string> = {
      query: t("pages.transactions.filter.query"),
      source_id: t("pages.transactions.filter.source"),
      source_kind: t("pages.transactions.filter.sourceKind"),
      weekday: t("pages.transactions.chip.weekday"),
      hour: t("pages.transactions.chip.hour"),
      tz_offset_minutes: t("pages.transactions.chip.tzOffset"),
      merchant_name: t("pages.transactions.filter.merchant"),
      year: t("pages.transactions.filter.year"),
      month: t("pages.transactions.filter.month"),
      purchased_from: t("pages.transactions.filter.purchasedFrom"),
      purchased_to: t("pages.transactions.filter.purchasedTo"),
      min_total_cents: t("pages.transactions.chip.minTotal"),
      max_total_cents: t("pages.transactions.chip.maxTotal")
    };
    const chips: FilterChip[] = [];
    for (const key of FILTER_KEYS) {
      const value = searchParams.get(key);
      if (!value) {
        continue;
      }
      chips.push({
        key,
        label: filterLabels[key],
        value: formatFilterValue(key, value)
      });
    }
    return chips;
  }, [searchKey, searchParams, t]);

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
  const errorMessage = error ? resolveApiErrorMessage(error, t, t("pages.transactions.loadError")) : null;

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
      setManualErrorMessage(t("pages.transactions.manual.invalidDate"));
      return;
    }
    const merchantName = manualFormValues.merchantName.trim();
    if (!merchantName) {
      setManualErrorMessage(t("pages.transactions.manual.merchantRequired"));
      return;
    }
    const totalGrossCents = Number(manualFormValues.totalGrossCents);
    if (!Number.isInteger(totalGrossCents) || totalGrossCents < 0) {
      setManualErrorMessage(t("pages.transactions.manual.totalInvalid"));
      return;
    }

    const itemName = manualFormValues.itemName.trim();
    const itemTotalRaw = manualFormValues.itemTotalCents.trim();
    if ((itemName && !itemTotalRaw) || (!itemName && itemTotalRaw)) {
      setManualErrorMessage(t("pages.transactions.manual.itemPairRequired"));
      return;
    }

    let itemTotalCents: number | null = null;
    if (itemTotalRaw) {
      const parsed = Number(itemTotalRaw);
      if (!Number.isInteger(parsed) || parsed < 0) {
        setManualErrorMessage(t("pages.transactions.manual.itemTotalInvalid"));
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
      setManualErrorMessage(resolveApiErrorMessage(mutationError, t, t("pages.transactions.manual.createFailed")));
    }
  }

  function renderSortButton(field: SortField, label: string): JSX.Element {
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
        aria-label={t("pages.transactions.sortBy", { label })}
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
          <CardTitle>{t("pages.transactions.manual.title")}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {t("pages.transactions.manual.description")}
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 md:grid-cols-6" onSubmit={submitManualTransaction}>
            <div className="space-y-2">
              <Label htmlFor="manual-purchased-at">{t("pages.transactions.manual.purchasedAt")}</Label>
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
              <Label htmlFor="manual-merchant">{t("pages.transactions.manual.merchant")}</Label>
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
              <Label htmlFor="manual-total-cents">{t("pages.transactions.manual.totalCents")}</Label>
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
              <Label htmlFor="manual-item-name">{t("pages.transactions.manual.itemName")}</Label>
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
              <Label htmlFor="manual-item-total-cents">{t("pages.transactions.manual.itemTotalCents")}</Label>
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
              <Label htmlFor="manual-idempotency-key">{t("pages.transactions.manual.idempotencyKey")}</Label>
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
                  {t("pages.transactions.manual.saving")}
                </>
              ) : (
                t("pages.transactions.manual.submit")
              )}
            </Button>
          </form>

          {manualErrorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>{t("pages.transactions.manual.errorTitle")}</AlertTitle>
              <AlertDescription>{manualErrorMessage}</AlertDescription>
            </Alert>
          ) : null}

          {manualSuccess ? (
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>{t("pages.transactions.manual.savedTitle")}</AlertTitle>
              <AlertDescription className="space-y-1">
                <p>
                  {manualSuccess.reused ? t("pages.transactions.manual.reused") : t("pages.transactions.manual.created")}{" "}
                  {t("common.source")}:
                  {" "}
                  <span className="font-medium">{manualSuccess.source_id}</span>
                </p>
                <Button asChild variant="link" className="h-auto p-0">
                  <Link to={`/transactions/${manualSuccess.transaction_id}`}>{t("pages.transactions.manual.openDetails")}</Link>
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.transactions.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-5" onSubmit={submitFilters}>
            <div className="space-y-2">
              <Label htmlFor="query">{t("pages.transactions.filter.query")}</Label>
              <Input
                id="query"
                value={formValues.query}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, query: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source">{t("pages.transactions.filter.source")}</Label>
              <Input
                id="source"
                value={formValues.sourceId}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, sourceId: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-kind">{t("pages.transactions.filter.sourceKind")}</Label>
              <Input
                id="source-kind"
                value={formValues.sourceKind}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, sourceKind: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="merchant">{t("pages.transactions.filter.merchant")}</Label>
              <Input
                id="merchant"
                value={formValues.merchantName}
                onChange={(event) =>
                  setFormValues((previous) => ({ ...previous, merchantName: event.target.value }))
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="year">{t("pages.transactions.filter.year")}</Label>
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
              <Label htmlFor="month">{t("pages.transactions.filter.month")}</Label>
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
              <Label htmlFor="weekday">{t("pages.transactions.filter.weekday")}</Label>
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
              <Label htmlFor="hour">{t("pages.transactions.filter.hour")}</Label>
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
              <Label htmlFor="tz-offset-minutes">{t("pages.transactions.filter.tzOffset")}</Label>
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
              <Label htmlFor="purchased-from">{t("pages.transactions.filter.purchasedFrom")}</Label>
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
              <Label htmlFor="purchased-to">{t("pages.transactions.filter.purchasedTo")}</Label>
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
              <Label htmlFor="min-total">{t("pages.transactions.filter.minTotal")}</Label>
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
              <Label htmlFor="max-total">{t("pages.transactions.filter.maxTotal")}</Label>
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
              {t("pages.transactions.applyFilters")}
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
                    aria-label={t("pages.transactions.removeFilter", { label: filter.label })}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
              <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>
                {t("pages.transactions.clearFilters")}
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>{t("pages.transactions.loadError")}</AlertTitle>
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
                  {renderSortButton("purchased_at", t("pages.transactions.col.purchasedAt"))}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("store_name")}>
                  {renderSortButton("store_name", t("pages.transactions.col.store"))}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("source_id")}>
                  {renderSortButton("source_id", t("pages.transactions.col.source"))}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("total_gross_cents")}>
                  {renderSortButton("total_gross_cents", t("pages.transactions.col.total"))}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS} aria-sort={ariaSortForField("discount_total_cents")}>
                  {renderSortButton("discount_total_cents", t("pages.transactions.col.discounts"))}
                </TableHead>
                <TableHead className={STICKY_HEADER_CLASS}>{t("common.open")}</TableHead>
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
                      <Link to={`/transactions/${item.id}`}>{t("pages.transactions.details")}</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {data && data.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>{t("pages.transactions.empty")}</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          <div className="mt-4 flex items-center justify-between">
            <Button type="button" variant="outline" onClick={() => movePage(-PAGE_SIZE)} disabled={offset === 0}>
              {t("common.previous")}
            </Button>
            <span className="text-sm text-muted-foreground">
              {t("pages.transactions.pagination", {
                start: data && data.count > 0 ? offset + 1 : 0,
                end: data ? offset + data.count : 0,
                total: data?.total ?? 0
              })}
            </span>
            <Button
              type="button"
              variant="outline"
              onClick={() => movePage(PAGE_SIZE)}
              disabled={!data || offset + PAGE_SIZE >= data.total}
            >
              {t("common.next")}
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
