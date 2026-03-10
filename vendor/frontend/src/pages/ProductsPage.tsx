import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { fetchAISettings } from "@/api/aiSettings";
import {
  fetchProductClusterStatus,
  fetchProductDetail,
  fetchProductPriceSeries,
  fetchProductPurchases,
  fetchProducts,
  postClusterProducts,
  postSeedProducts
} from "@/api/products";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { SearchInput } from "@/components/shared/SearchInput";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { useI18n } from "@/i18n";
import { formatEurFromCents } from "@/utils/format";

export function ProductsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [clusterJobId, setClusterJobId] = useState<string | null>(null);
  const [clusterProgress, setClusterProgress] = useState<{
    status: string;
    total_batches: number;
    completed_batches: number;
    products_created: number;
    errors: string[];
  } | null>(null);

  const productsQuery = useQuery({
    queryKey: ["products", debouncedSearch],
    queryFn: () => fetchProducts({ search: debouncedSearch })
  });
  const aiSettingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });
  const detailQuery = useQuery({
    queryKey: ["product-detail", selectedProductId],
    queryFn: () => fetchProductDetail(selectedProductId!),
    enabled: selectedProductId !== null
  });
  const seriesQuery = useQuery({
    queryKey: ["product-series", selectedProductId],
    queryFn: () => fetchProductPriceSeries({ productId: selectedProductId!, grain: "month", net: true }),
    enabled: selectedProductId !== null
  });
  const purchasesQuery = useQuery({
    queryKey: ["product-purchases", selectedProductId],
    queryFn: () => fetchProductPurchases({ productId: selectedProductId! }),
    enabled: selectedProductId !== null
  });

  const seedMutation = useMutation({
    mutationFn: postSeedProducts,
    onSuccess: (result) => {
      toast.success(`Created ${result.created} products`);
      void queryClient.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to seed products");
    }
  });
  const clusterMutation = useMutation({
    mutationFn: () => postClusterProducts(),
    onSuccess: (result) => {
      setClusterJobId(result.job_id);
      setClusterProgress({
        status: result.status,
        total_batches: 0,
        completed_batches: 0,
        products_created: 0,
        errors: []
      });
      toast.success("Product clustering started");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to start clustering");
    }
  });

  useEffect(() => {
    if (!clusterJobId) {
      return;
    }
    let isCancelled = false;

    const poll = async () => {
      try {
        const progress = await fetchProductClusterStatus(clusterJobId);
        if (isCancelled) {
          return;
        }
        setClusterProgress(progress);
        if (progress.status === "completed") {
          setClusterJobId(null);
          void queryClient.invalidateQueries({ queryKey: ["products"] });
          toast.success(`AI clustering complete (${progress.products_created} products created)`);
        } else if (progress.status === "error") {
          setClusterJobId(null);
          toast.error(progress.errors[0] || "AI clustering failed");
        }
      } catch (error) {
        if (isCancelled) {
          return;
        }
        setClusterJobId(null);
        toast.error(error instanceof Error ? error.message : "Failed to poll clustering progress");
      }
    };

    void poll();
    const intervalId = window.setInterval(() => {
      void poll();
    }, 2000);
    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [clusterJobId, queryClient]);

  const selectedProduct = detailQuery.data?.product ?? null;
  const selectedPricePoints = seriesQuery.data?.points ?? [];
  const selectedPurchases = purchasesQuery.data?.items ?? [];
  const selectedAliases = detailQuery.data?.aliases ?? [];

  const productRows = useMemo(() => productsQuery.data?.items ?? [], [productsQuery.data]);
  const clusterPercent =
    clusterProgress && clusterProgress.total_batches > 0
      ? Math.round((clusterProgress.completed_batches / clusterProgress.total_batches) * 100)
      : 0;
  const aiEnabled = aiSettingsQuery.data?.enabled === true;

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.products")}>
        <Button
          variant="outline"
          onClick={() => void seedMutation.mutateAsync()}
          disabled={seedMutation.isPending}
          title={t("pages.products.seed.tooltip")}
        >
          {t("pages.products.seedButton")}
        </Button>
        {aiEnabled ? (
          <Button
            variant="outline"
            onClick={() => void clusterMutation.mutateAsync()}
            disabled={clusterMutation.isPending || clusterJobId !== null}
            title={t("pages.products.cluster.tooltip")}
          >
            Cluster with AI
          </Button>
        ) : null}
      </PageHeader>
      <Card>
        <CardContent>
          <div className="space-y-3">
            {clusterProgress ? (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>AI clustering progress</span>
                  <span>
                    {clusterProgress.completed_batches}/{clusterProgress.total_batches} batches ({clusterPercent}%)
                  </span>
                </div>
                <div className="h-2 w-full rounded bg-muted">
                  <div
                    className="h-full rounded bg-primary transition-all"
                    style={{ width: `${Math.min(Math.max(clusterPercent, 0), 100)}%` }}
                  />
                </div>
              </div>
            ) : null}
            <Label htmlFor="products-search">Search products</Label>
            <SearchInput
              value={debouncedSearch}
              onChange={(value) => setDebouncedSearch(value.trim())}
              placeholder="Milk, butter, yogurt..."
              isLoading={productsQuery.isFetching}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Matches</CardTitle>
        </CardHeader>
        <CardContent>
          {productRows.length === 0 ? (
            <EmptyState title="No products found" description={debouncedSearch ? "Try a different search term." : undefined} />
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Brand</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Aliases</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {productRows.map((row) => (
                  <TableRow
                    key={row.product_id}
                    className={cn(
                      "cursor-pointer transition-colors",
                      selectedProductId === row.product_id
                        ? "bg-primary/15 ring-1 ring-primary/30 hover:bg-primary/15"
                        : ""
                    )}
                    onClick={() => setSelectedProductId(row.product_id)}
                  >
                    <TableCell className={cn(selectedProductId === row.product_id && "font-medium")}>
                      {row.canonical_name}
                    </TableCell>
                    <TableCell>
                      {row.brand ? <Badge variant="secondary">{row.brand}</Badge> : <span>—</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.category_id ?? "uncategorized"}</Badge>
                    </TableCell>
                    <TableCell className="tabular-nums">{row.alias_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {selectedProduct ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{selectedProduct.canonical_name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>Brand: {selectedProduct.brand ?? "-"}</p>
              <p>Default unit: {selectedProduct.default_unit ?? "-"}</p>
              <p>GTIN/EAN: {selectedProduct.gtin_ean ?? "-"}</p>
              <p>Aliases: {selectedAliases.length}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Price Series (Monthly)</CardTitle>
            </CardHeader>
            <CardContent>
              {selectedPricePoints.length === 0 ? (
                <p className="text-sm text-muted-foreground">No price points available.</p>
              ) : (
                <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Period</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Unit Price</TableHead>
                      <TableHead>Purchases</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedPricePoints.map((point) => (
                      <TableRow key={`${point.period}-${point.source_kind}`}>
                        <TableCell>{point.period}</TableCell>
                        <TableCell>{point.source_kind}</TableCell>
                        <TableCell className="tabular-nums">{formatEurFromCents(point.unit_price_cents)}</TableCell>
                        <TableCell className="tabular-nums">{point.purchase_count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Purchases</CardTitle>
            </CardHeader>
            <CardContent>
              {selectedPurchases.length === 0 ? (
                <p className="text-sm text-muted-foreground">No purchases found.</p>
              ) : (
                <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Source</TableHead>
                      <TableHead>Qty</TableHead>
                      <TableHead>Net</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {selectedPurchases.map((row) => (
                      <TableRow key={`${row.transaction_id}-${row.raw_item_name}`}>
                        <TableCell>{row.date}</TableCell>
                        <TableCell>{row.source_kind}</TableCell>
                        <TableCell className="tabular-nums">
                          {row.quantity_value ?? "—"} {row.quantity_unit}
                        </TableCell>
                        <TableCell className="tabular-nums">{formatEurFromCents(row.line_total_gross_cents)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}
    </section>
  );
}
