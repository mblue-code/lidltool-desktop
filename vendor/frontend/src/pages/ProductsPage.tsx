import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { fetchAISettings } from "@/api/aiSettings";
import { isDemoSnapshotMode } from "@/demo/mode";
import {
  fetchProductDetail,
  fetchProductPriceSeries,
  fetchProductPurchases,
  fetchProducts,
  postSeedProducts
} from "@/api/products";
import { fetchQualityRecategorizeStatus, startQualityRecategorize } from "@/api/quality";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { SearchInput } from "@/components/shared/SearchInput";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";
import { formatEurFromCents } from "@/utils/format";

export function ProductsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const demoMode = isDemoSnapshotMode();
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [recategorizeJobId, setRecategorizeJobId] = useState<string | null>(null);

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
  const recategorizeStatusQuery = useQuery({
    queryKey: ["quality-recategorize-status", recategorizeJobId],
    queryFn: () => fetchQualityRecategorizeStatus(recategorizeJobId ?? ""),
    enabled: Boolean(recategorizeJobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    }
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
  const recategorizeMutation = useMutation({
    mutationFn: () =>
      startQualityRecategorize({
        only_fallback_other: true,
        include_suspect_model_items: false
      }),
    onSuccess: (job) => {
      setRecategorizeJobId(job.job_id);
      toast.success("AI recategorization started");
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to start recategorization");
    }
  });

  const selectedProduct = detailQuery.data?.product ?? null;
  const selectedPricePoints = seriesQuery.data?.points ?? [];
  const selectedPurchases = purchasesQuery.data?.items ?? [];
  const selectedAliases = detailQuery.data?.aliases ?? [];

  const productRows = useMemo(() => productsQuery.data?.items ?? [], [productsQuery.data]);
  const aiEnabled = aiSettingsQuery.data?.enabled === true;
  const categorizationEnabled = aiSettingsQuery.data?.categorization_enabled === true;
  const categorizationReady = aiSettingsQuery.data?.categorization_runtime_ready === true;
  const recategorizeJob = recategorizeStatusQuery.data;
  const recategorizeRunning =
    recategorizeMutation.isPending ||
    recategorizeJob?.status === "queued" ||
    recategorizeJob?.status === "running";

  useEffect(() => {
    if (!recategorizeJob) {
      return;
    }
    if (recategorizeJob.status === "completed") {
      setRecategorizeJobId(null);
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      toast.success(`Recategorized ${recategorizeJob.updated_item_count} items`);
    } else if (recategorizeJob.status === "error") {
      setRecategorizeJobId(null);
      toast.error(recategorizeJob.error || "AI recategorization failed");
    }
  }, [queryClient, recategorizeJob]);

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.products")}>
        <Button
          variant="outline"
          onClick={() => void seedMutation.mutateAsync()}
          disabled={demoMode || seedMutation.isPending}
          title={t("pages.products.seed.tooltip")}
        >
          {t("pages.products.seedButton")}
        </Button>
        {aiEnabled ? (
          <Button
            variant="outline"
            onClick={() => void recategorizeMutation.mutateAsync()}
            disabled={demoMode || !categorizationEnabled || !categorizationReady || recategorizeRunning}
            title="Re-run AI categorization for items still in other"
          >
            {recategorizeRunning ? "Repairing categories..." : "Repair uncategorized items"}
          </Button>
        ) : null}
      </PageHeader>
      {demoMode ? (
        <Alert>
          <AlertTitle>Demo Snapshot</AlertTitle>
          <AlertDescription>
            Product search, clustering results, and price history use synthetic demo data. Seed and repair actions are disabled on the public demo.
          </AlertDescription>
        </Alert>
      ) : null}
      <Card>
        <CardContent>
          <div className="space-y-3">
            {aiEnabled ? (
              <div className="rounded-md border p-3 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="space-y-1">
                    <p className="font-medium">AI item categorization</p>
                    <p className="text-muted-foreground">
                      Use the configured categorization model to repair items that are still in{" "}
                      <code>other</code>. This uses the normal categorization job, not a full Pi-agent
                      run per item.
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={categorizationEnabled ? "secondary" : "outline"}>
                      {categorizationEnabled ? "enabled" : "disabled"}
                    </Badge>
                    {aiSettingsQuery.data?.categorization_provider ? (
                      <Badge variant="outline">{aiSettingsQuery.data.categorization_provider}</Badge>
                    ) : null}
                    {aiSettingsQuery.data?.categorization_model ? (
                      <Badge variant="outline">{aiSettingsQuery.data.categorization_model}</Badge>
                    ) : null}
                    <Button variant="outline" size="sm" asChild>
                      <Link to="/settings/ai">AI settings</Link>
                    </Button>
                  </div>
                </div>
                {!categorizationEnabled ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Enable item categorization in AI Settings and choose either ChatGPT Codex
                    subscription mode or an API-compatible provider.
                  </p>
                ) : null}
                {categorizationEnabled && !categorizationReady ? (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Runtime is not ready yet: {aiSettingsQuery.data?.categorization_runtime_status || "not configured"}.
                  </p>
                ) : null}
                {recategorizeJob ? (
                  <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-4">
                    <p>Status: {recategorizeJob.status}</p>
                    <p>Candidates: {recategorizeJob.candidate_item_count}</p>
                    <p>Updated items: {recategorizeJob.updated_item_count}</p>
                    <p>Updated transactions: {recategorizeJob.updated_transaction_count}</p>
                  </div>
                ) : null}
                {recategorizeJob?.error ? (
                  <p className="mt-2 text-sm text-destructive">{recategorizeJob.error}</p>
                ) : null}
              </div>
            ) : null}
            <Label htmlFor="products-search">Search products</Label>
            <SearchInput
              id="products-search"
              value={debouncedSearch}
              onChange={(value) => setDebouncedSearch(value.trim())}
              placeholder="Milk, butter, yogurt..."
              isLoading={productsQuery.isFetching}
            />
          </div>
          <div className="app-section-divider mt-4 pt-4">
            {productRows.length === 0 ? (
              <EmptyState
                title="No products found"
                description={debouncedSearch ? "Try a different search term." : undefined}
              />
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
          </div>
        </CardContent>
      </Card>

      {selectedProduct ? (
        <Card>
          <CardHeader>
            <CardTitle>{selectedProduct.canonical_name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-0">
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-4">
              <div>
                <span className="text-muted-foreground">Brand:</span> {selectedProduct.brand ?? "-"}
              </div>
              <div>
                <span className="text-muted-foreground">Unit:</span> {selectedProduct.default_unit ?? "-"}
              </div>
              <div>
                <span className="text-muted-foreground">GTIN/EAN:</span> {selectedProduct.gtin_ean ?? "-"}
              </div>
              <div>
                <span className="text-muted-foreground">Aliases:</span> {selectedAliases.length}
              </div>
            </div>

            <div className="app-section-divider mt-4 pt-4">
              <p className="mb-2 text-sm font-medium">Price Series (Monthly)</p>
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
                          <TableCell className="tabular-nums">
                            {formatEurFromCents(point.unit_price_cents)}
                          </TableCell>
                          <TableCell className="tabular-nums">{point.purchase_count}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>

            <div className="app-section-divider mt-4 pt-4">
              <p className="mb-2 text-sm font-medium">Purchases</p>
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
                          <TableCell className="tabular-nums">
                            {formatEurFromCents(row.line_total_gross_cents)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      ) : null}
    </section>
  );
}
