import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Loader2, RefreshCw, Tag } from "lucide-react";
import { toast } from "sonner";

import { fetchProducts, type ProductSearchResponse } from "@/api/products";
import {
  createOfferWatchlist,
  fetchOfferAlerts,
  fetchOfferWatchlists,
  patchOfferAlert,
  refreshOffers,
  type OfferAlert,
  type OfferWatchlist
} from "@/api/offers";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/i18n";
import { formatDateTime, formatEurFromCents } from "@/utils/format";
import { parseEuroInputToCents } from "@/utils/money-input";

const UNCATEGORIZED_CATEGORY_KEY = "__uncategorized__";
const PRODUCT_LIMIT = 2000;
const WATCHLIST_LIMIT = 25;
const ALERT_LIMIT = 25;

function normalizeCategoryKey(categoryId: string | null | undefined): string {
  return categoryId && categoryId.trim().length > 0 ? categoryId : UNCATEGORIZED_CATEGORY_KEY;
}

function watchlistId(entry: OfferWatchlist): string {
  return entry.id ?? entry.watchlist_id ?? "";
}

function alertId(entry: OfferAlert): string {
  return entry.id ?? entry.alert_id ?? "";
}

function productLabel(product: { canonical_name?: string; brand?: string | null }): string {
  return [product.brand, product.canonical_name].filter(Boolean).join(" · ");
}

function offerWatchlistTitle(entry: OfferWatchlist): string {
  if (entry.product?.canonical_name) {
    return entry.product.brand ? `${entry.product.brand} · ${entry.product.canonical_name}` : entry.product.canonical_name;
  }
  if (entry.product_id) {
    return entry.product_id;
  }
  return entry.query_text?.trim() || "Untitled watchlist";
}

function formatSourceLabel(sourceId: string | null | undefined, anyLabel: string): string {
  return sourceId && sourceId.trim().length > 0 ? sourceId : anyLabel;
}

function formatDiscountLabel(value: number | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return `${value}%`;
}

function friendlyWatchlistError(error: unknown, fallback: string): string {
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = Number((error as { status?: number }).status);
    if (status === 400) {
      return fallback;
    }
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

export function OffersPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [selectedCategoryId, setSelectedCategoryId] = useState("");
  const [selectedProductId, setSelectedProductId] = useState("");
  const [queryText, setQueryText] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [minDiscountPercent, setMinDiscountPercent] = useState("");
  const [maxPriceInput, setMaxPriceInput] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const productsQuery = useQuery({
    queryKey: ["offers", "products"],
    queryFn: () => fetchProducts({ limit: PRODUCT_LIMIT })
  });
  const watchlistsQuery = useQuery({
    queryKey: ["offers", "watchlists"],
    queryFn: () => fetchOfferWatchlists({ limit: WATCHLIST_LIMIT, offset: 0 })
  });
  const alertsQuery = useQuery({
    queryKey: ["offers", "alerts"],
    queryFn: () => fetchOfferAlerts({ limit: ALERT_LIMIT, offset: 0, unreadOnly: false })
  });

  const groupedProducts = useMemo(() => {
    type ProductRow = ProductSearchResponse["items"][number];
    const groups = new Map<string, ProductRow[]>();
    for (const product of productsQuery.data?.items ?? []) {
      const key = normalizeCategoryKey(product.category_id);
      const existing = groups.get(key) ?? [];
      existing.push(product);
      groups.set(key, existing);
    }

    return [...groups.entries()]
      .map(([categoryKey, items]) => ({
        categoryKey,
        items: [...items].sort((left, right) => left.canonical_name.localeCompare(right.canonical_name))
      }))
      .sort((left, right) => {
        if (left.categoryKey === UNCATEGORIZED_CATEGORY_KEY) {
          return -1;
        }
        if (right.categoryKey === UNCATEGORIZED_CATEGORY_KEY) {
          return 1;
        }
        return left.categoryKey.localeCompare(right.categoryKey);
      });
  }, [productsQuery.data?.items]);

  const productsById = useMemo(() => {
    return new Map((productsQuery.data?.items ?? []).map((product) => [product.product_id, product]));
  }, [productsQuery.data?.items]);

  const selectedCategoryProducts = useMemo(() => {
    if (!selectedCategoryId) {
      return [];
    }
    return groupedProducts.find((group) => group.categoryKey === selectedCategoryId)?.items ?? [];
  }, [groupedProducts, selectedCategoryId]);

  const watchlists = watchlistsQuery.data?.items ?? [];
  const alerts = alertsQuery.data?.items ?? [];

  useEffect(() => {
    if (!selectedProductId) {
      return;
    }
    const selectedProduct = productsById.get(selectedProductId);
    if (!selectedProduct) {
      setSelectedProductId("");
      return;
    }
    if (selectedCategoryId && normalizeCategoryKey(selectedProduct.category_id) !== selectedCategoryId) {
      setSelectedProductId("");
    }
  }, [productsById, selectedCategoryId, selectedProductId]);

  const refreshMutation = useMutation({
    mutationFn: refreshOffers,
    onSuccess: () => {
      toast.success(t("pages.offers.refresh.success"));
      void queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] });
      void queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : t("pages.offers.refresh.error"));
    }
  });

  const createWatchlistMutation = useMutation({
    mutationFn: createOfferWatchlist,
    onSuccess: () => {
      setFormError(null);
      setSelectedCategoryId("");
      setSelectedProductId("");
      setQueryText("");
      setSourceId("");
      setMinDiscountPercent("");
      setMaxPriceInput("");
      setNotes("");
      toast.success(t("pages.offers.form.success"));
      void queryClient.invalidateQueries({ queryKey: ["offers", "watchlists"] });
      void queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] });
    },
    onError: (error) => {
      setFormError(
        friendlyWatchlistError(error, t("pages.offers.form.validation.backendRejected"))
      );
    }
  });

  const patchAlertMutation = useMutation({
    mutationFn: ({ id, read }: { id: string; read: boolean }) => patchOfferAlert(id, { read }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["offers", "alerts"] });
    }
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();

    const normalizedQuery = queryText.trim();
    const normalizedSource = sourceId.trim();
    const normalizedNotes = notes.trim();

    if (!selectedProductId && !normalizedQuery) {
      setFormError(t("pages.offers.form.validation.missingTarget"));
      return;
    }

    const discount = minDiscountPercent.trim().length > 0 ? Number(minDiscountPercent) : undefined;
    if (discount !== undefined && (!Number.isFinite(discount) || discount < 0)) {
      setFormError(t("pages.offers.form.validation.invalidDiscount"));
      return;
    }

    const maxPriceCents =
      maxPriceInput.trim().length > 0 ? parseEuroInputToCents(maxPriceInput) : undefined;
    if (maxPriceInput.trim().length > 0 && maxPriceCents === null) {
      setFormError(t("pages.offers.form.validation.invalidPrice"));
      return;
    }

    setFormError(null);
    createWatchlistMutation.mutate({
      product_id: selectedProductId || undefined,
      query_text: normalizedQuery || undefined,
      source_id: normalizedSource || undefined,
      min_discount_percent: discount,
      max_price_cents: maxPriceCents ?? undefined,
      notes: normalizedNotes || undefined,
      active: true
    });
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.offers")} description={t("pages.offers.description")}>
        <Button
          variant="outline"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
        >
          {refreshMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {t("pages.offers.refresh.button")}
        </Button>
      </PageHeader>

      <Alert>
        <Tag className="h-4 w-4" />
        <AlertTitle>{t("pages.offers.banner.title")}</AlertTitle>
        <AlertDescription>{t("pages.offers.banner.description")}</AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.offers.form.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 lg:grid-cols-2" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label htmlFor="offers-category">{t("pages.offers.form.categoryLabel")}</Label>
              <Select
                value={selectedCategoryId}
                onValueChange={(value) => {
                  setSelectedCategoryId(value);
                  setSelectedProductId("");
                }}
              >
                <SelectTrigger id="offers-category">
                  <SelectValue placeholder={t("pages.offers.form.categoryPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {groupedProducts.map((group) => (
                    <SelectItem key={group.categoryKey} value={group.categoryKey}>
                      {group.categoryKey === UNCATEGORIZED_CATEGORY_KEY
                        ? t("pages.offers.category.uncategorized")
                        : group.categoryKey}
                      {" "}
                      ({group.items.length})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {t("pages.offers.form.categoryHelp")}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="offers-product">{t("pages.offers.form.productLabel")}</Label>
              <Select
                value={selectedProductId}
                onValueChange={(value) => setSelectedProductId(value)}
                disabled={!selectedCategoryId || selectedCategoryProducts.length === 0}
              >
                <SelectTrigger id="offers-product">
                  <SelectValue placeholder={t("pages.offers.form.productPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {selectedCategoryProducts.map((product) => (
                    <SelectItem key={product.product_id} value={product.product_id}>
                      {productLabel(product)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {selectedCategoryId
                  ? selectedCategoryProducts.length > 0
                    ? t("pages.offers.form.productHelp")
                    : t("pages.offers.form.noProductsInCategory")
                  : t("pages.offers.form.productCategoryHint")}
              </p>
            </div>

            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="offers-query">{t("pages.offers.form.queryLabel")}</Label>
              <Input
                id="offers-query"
                value={queryText}
                onChange={(event) => setQueryText(event.target.value)}
                placeholder={t("pages.offers.form.queryPlaceholder")}
              />
              <p className="text-xs text-muted-foreground">{t("pages.offers.form.queryHelp")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="offers-source">{t("pages.offers.form.sourceLabel")}</Label>
              <Input
                id="offers-source"
                value={sourceId}
                onChange={(event) => setSourceId(event.target.value)}
                placeholder={t("pages.offers.form.sourcePlaceholder")}
              />
              <p className="text-xs text-muted-foreground">{t("pages.offers.form.sourceHelp")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="offers-discount">{t("pages.offers.form.discountLabel")}</Label>
              <Input
                id="offers-discount"
                type="number"
                inputMode="decimal"
                min="0"
                step="0.1"
                value={minDiscountPercent}
                onChange={(event) => setMinDiscountPercent(event.target.value)}
                placeholder="20"
              />
              <p className="text-xs text-muted-foreground">{t("pages.offers.form.discountHelp")}</p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="offers-price">{t("pages.offers.form.priceLabel")}</Label>
              <Input
                id="offers-price"
                value={maxPriceInput}
                onChange={(event) => setMaxPriceInput(event.target.value)}
                placeholder={t("pages.offers.form.pricePlaceholder")}
                inputMode="decimal"
              />
              <p className="text-xs text-muted-foreground">{t("pages.offers.form.priceHelp")}</p>
            </div>

            <div className="space-y-2 lg:col-span-2">
              <Label htmlFor="offers-notes">{t("pages.offers.form.notesLabel")}</Label>
              <Textarea
                id="offers-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={3}
                placeholder={t("pages.offers.form.notesPlaceholder")}
              />
            </div>

            <div className="space-y-3 lg:col-span-2">
              {formError ? (
                <p className="text-sm text-destructive" role="alert">
                  {formError}
                </p>
              ) : null}
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={createWatchlistMutation.isPending}>
                  {createWatchlistMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : null}
                  {t("pages.offers.form.saveButton")}
                </Button>
              </div>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.offers.watchlists.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {watchlists.length === 0 ? (
            <EmptyState
              icon={<Tag className="h-6 w-6" />}
              title={t("pages.offers.watchlists.emptyTitle")}
              description={t("pages.offers.watchlists.emptyDescription")}
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("pages.offers.watchlists.columns.target")}</TableHead>
                    <TableHead>{t("pages.offers.watchlists.columns.source")}</TableHead>
                    <TableHead>{t("pages.offers.watchlists.columns.filters")}</TableHead>
                    <TableHead>{t("pages.offers.watchlists.columns.state")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {watchlists.map((entry) => {
                    const id = watchlistId(entry);
                    return (
                      <TableRow key={id || offerWatchlistTitle(entry)}>
                        <TableCell className="max-w-[18rem]">
                          <div className="space-y-1">
                            <div className="font-medium">{offerWatchlistTitle(entry)}</div>
                            {entry.notes ? (
                              <div className="text-xs text-muted-foreground">{entry.notes}</div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>{formatSourceLabel(entry.source_id, t("pages.offers.source.any"))}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          <div className="space-y-1">
                            {entry.min_discount_percent !== null && entry.min_discount_percent !== undefined ? (
                              <div>
                                {t("pages.offers.watchlists.minDiscount", {
                                  value: formatDiscountLabel(entry.min_discount_percent)
                                })}
                              </div>
                            ) : null}
                            {entry.max_price_cents !== null && entry.max_price_cents !== undefined ? (
                              <div>
                                {t("pages.offers.watchlists.maxPrice", {
                                  value: formatEurFromCents(entry.max_price_cents)
                                })}
                              </div>
                            ) : null}
                            {entry.query_text ? (
                              <div>{t("pages.offers.watchlists.queryText", { value: entry.query_text })}</div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge variant={entry.active === false ? "secondary" : "default"}>
                            {entry.active === false
                              ? t("pages.offers.watchlists.paused")
                              : t("pages.offers.watchlists.active")}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.offers.alerts.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          {alerts.length === 0 ? (
            <EmptyState
              icon={<Bell className="h-6 w-6" />}
              title={t("pages.offers.alerts.emptyTitle")}
              description={t("pages.offers.alerts.emptyDescription")}
            />
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("pages.offers.alerts.columns.alert")}</TableHead>
                    <TableHead>{t("pages.offers.alerts.columns.source")}</TableHead>
                    <TableHead>{t("pages.offers.alerts.columns.state")}</TableHead>
                    <TableHead>{t("pages.offers.alerts.columns.created")}</TableHead>
                    <TableHead>{t("pages.offers.alerts.columns.action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alerts.map((entry) => {
                    const id = alertId(entry);
                    const read = entry.read_at !== null && entry.read_at !== undefined ? true : entry.read === true;
                    return (
                      <TableRow key={id || entry.title || entry.created_at || "offer-alert"}>
                        <TableCell>
                          <div className="space-y-1">
                            <div className="font-medium">{entry.title ?? t("pages.offers.alerts.untitled")}</div>
                            {entry.body ? (
                              <div className="text-xs text-muted-foreground">{entry.body}</div>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>{formatSourceLabel(entry.source_id, entry.merchant_name ?? t("pages.offers.source.any"))}</TableCell>
                        <TableCell>
                          <Badge variant={read ? "secondary" : "default"}>
                            {read ? t("pages.offers.alerts.read") : t("pages.offers.alerts.unread")}
                          </Badge>
                        </TableCell>
                        <TableCell>{entry.created_at ? formatDateTime(entry.created_at) : "—"}</TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={patchAlertMutation.isPending || !id}
                            onClick={() => patchAlertMutation.mutate({ id, read: !read })}
                          >
                            {read ? t("pages.offers.alerts.markUnread") : t("pages.offers.alerts.markRead")}
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
