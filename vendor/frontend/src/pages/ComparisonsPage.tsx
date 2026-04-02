import { FormEvent, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addCompareGroupMember,
  createCompareGroup,
  fetchCompareGroups,
  fetchCompareGroupSeries
} from "@/api/compare";
import { fetchPriceIndex, postBasketCompare } from "@/api/analytics";
import { fetchProducts } from "@/api/products";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/shared/PageHeader";
import { SearchInput } from "@/components/shared/SearchInput";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { formatEurFromCents } from "@/utils/format";

type BasketItem = {
  product_id: string;
  name: string;
  quantity: number;
};

const BASKET_STORAGE_KEY = "analytics.compare.basket.v1";

function readStoredBasket(): BasketItem[] {
  if (typeof window === "undefined" || typeof window.localStorage?.getItem !== "function") {
    return [];
  }
  const raw = window.localStorage.getItem(BASKET_STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as BasketItem[];
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter(
      (item) => item && typeof item.product_id === "string" && typeof item.quantity === "number"
    );
  } catch {
    return [];
  }
}

function writeStoredBasket(items: BasketItem[]): void {
  if (typeof window === "undefined" || typeof window.localStorage?.setItem !== "function") {
    return;
  }
  window.localStorage.setItem(BASKET_STORAGE_KEY, JSON.stringify(items));
}

export function ComparisonsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [groupName, setGroupName] = useState("");
  const [groupId, setGroupId] = useState<string | null>(null);
  const [productSearch, setProductSearch] = useState("");
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [basket, setBasket] = useState<BasketItem[]>([]);

  const groupsQuery = useQuery({
    queryKey: ["compare-groups"],
    queryFn: fetchCompareGroups
  });
  const productsQuery = useQuery({
    queryKey: ["compare-products", productSearch],
    queryFn: () => fetchProducts({ search: productSearch }),
    enabled: productSearch.trim().length > 0
  });
  const seriesQuery = useQuery({
    queryKey: ["compare-series", groupId],
    queryFn: () => fetchCompareGroupSeries({ groupId: groupId!, grain: "month", net: true }),
    enabled: groupId !== null
  });
  const priceIndexQuery = useQuery({
    queryKey: ["price-index"],
    queryFn: () => fetchPriceIndex()
  });

  const createGroupMutation = useMutation({
    mutationFn: createCompareGroup,
    onSuccess: (group) => {
      setGroupName("");
      setGroupId(group.group_id);
      void queryClient.invalidateQueries({ queryKey: ["compare-groups"] });
    }
  });

  const addMemberMutation = useMutation({
    mutationFn: async () => {
      if (!groupId || !selectedProductId) {
        throw new Error("Select a group and product first.");
      }
      return addCompareGroupMember(groupId, { product_id: selectedProductId, weight: 1.0 });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["compare-series", groupId] });
      void queryClient.invalidateQueries({ queryKey: ["compare-groups"] });
    }
  });
  const basketMutation = useMutation({
    mutationFn: () =>
      postBasketCompare({
        items: basket.map((item) => ({ product_id: item.product_id, quantity: item.quantity })),
        net: true
      })
  });

  useEffect(() => {
    setBasket(readStoredBasket());
  }, []);

  useEffect(() => {
    writeStoredBasket(basket);
  }, [basket]);

  function submitGroup(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (!groupName.trim()) {
      return;
    }
    void createGroupMutation.mutateAsync({ name: groupName.trim(), unit_standard: "€/pcs" });
  }

  const groups = groupsQuery.data?.items ?? [];
  const seriesPoints = seriesQuery.data?.points ?? [];
  const basketResult = basketMutation.data?.retailers ?? [];
  const indexPoints = priceIndexQuery.data?.points ?? [];
  const products = useMemo(() => productsQuery.data?.items ?? [], [productsQuery.data]);

  function addSelectedToBasket(): void {
    if (!selectedProductId) {
      return;
    }
    const product = products.find((item) => item.product_id === selectedProductId);
    if (!product) {
      return;
    }
    setBasket((previous) => {
      const existing = previous.find((item) => item.product_id === selectedProductId);
      if (existing) {
        return previous.map((item) =>
          item.product_id === selectedProductId
            ? { ...item, quantity: Number((item.quantity + 1).toFixed(2)) }
            : item
        );
      }
      return [
        ...previous,
        {
          product_id: selectedProductId,
          name: product.canonical_name,
          quantity: 1
        }
      ];
    });
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.comparisons")} />
      <div className="space-y-3">
        <form className="flex gap-2" onSubmit={submitGroup}>
          <div className="flex-1 space-y-1">
            <Label htmlFor="compare-group-name">Create group</Label>
            <Input
              id="compare-group-name"
              value={groupName}
              onChange={(event) => setGroupName(event.target.value)}
              placeholder="Weekly basket"
            />
          </div>
          <Button type="submit" className="self-end" disabled={createGroupMutation.isPending}>
            Create
          </Button>
        </form>

        <div className="grid gap-2 md:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="compare-group-select">Group</Label>
            <select
              id="compare-group-select"
              className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
              value={groupId ?? ""}
              onChange={(event) => setGroupId(event.target.value || null)}
            >
              <option value="">Select group</option>
              {groups.map((group) => (
                <option key={group.group_id} value={group.group_id}>
                  {group.name} ({group.member_count})
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="compare-product-search">Find product</Label>
            <SearchInput
              id="compare-product-search"
              value={productSearch}
              onChange={setProductSearch}
              placeholder="Milk"
              isLoading={productsQuery.isFetching}
            />
          </div>
        </div>

        {productSearch.trim().length > 0 && !productsQuery.isFetching && products.length === 0 ? (
          <EmptyState title={t("pages.comparisons.noProductsFound")} description={t("pages.comparisons.noProductsFoundDescription")} />
        ) : null}
        {products.length > 0 ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">Search results</p>
            <div className="flex flex-wrap gap-2">
              {products.slice(0, 8).map((product) => (
                <Button
                  key={product.product_id}
                  size="sm"
                  variant={selectedProductId === product.product_id ? "default" : "outline"}
                  onClick={() => setSelectedProductId(product.product_id)}
                >
                  {product.canonical_name}
                </Button>
              ))}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => void addMemberMutation.mutateAsync()}
                disabled={groupId === null || selectedProductId === null || addMemberMutation.isPending}
              >
                Add selected product to group
              </Button>
              <Button variant="outline" onClick={addSelectedToBasket} disabled={selectedProductId === null}>
                Add selected product to basket
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Basket Builder</CardTitle>
            <p className="text-xs text-muted-foreground">{t("pages.comparisons.basketSavedLocally")}</p>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {basket.length === 0 ? (
            <p className="text-sm text-muted-foreground">Add products to build a comparison basket.</p>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Product</TableHead>
                  <TableHead>Qty</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {basket.map((item) => (
                  <TableRow key={item.product_id}>
                    <TableCell>{item.name}</TableCell>
                    <TableCell>{item.quantity}</TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-10 w-10 min-w-10 min-h-10"
                          onClick={() =>
                            setBasket((previous) =>
                              previous.map((row) =>
                                row.product_id === item.product_id
                                  ? { ...row, quantity: Number(Math.max(0.1, row.quantity - 0.1).toFixed(2)) }
                                  : row
                              )
                            )
                          }
                        >
                          -
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-10 w-10 min-w-10 min-h-10"
                          onClick={() =>
                            setBasket((previous) =>
                              previous.map((row) =>
                                row.product_id === item.product_id
                                  ? { ...row, quantity: Number((row.quantity + 0.1).toFixed(2)) }
                                  : row
                              )
                            )
                          }
                        >
                          +
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setBasket((previous) => previous.filter((row) => row.product_id !== item.product_id))
                          }
                        >
                          Remove
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => void basketMutation.mutateAsync()}
              disabled={basket.length === 0 || basketMutation.isPending}
            >
              Compare basket
            </Button>
            <Button variant="outline" onClick={() => setBasket([])} disabled={basket.length === 0}>
              Clear basket
            </Button>
          </div>
          {basketResult.length > 0 ? (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Total</TableHead>
                  <TableHead>Coverage</TableHead>
                  <TableHead>Missing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {basketResult.map((row) => (
                  <TableRow key={row.source_kind}>
                    <TableCell>{row.source_kind}</TableCell>
                    <TableCell>{formatEurFromCents(row.total_cents)}</TableCell>
                    <TableCell>{Math.round(row.coverage_rate * 100)}%</TableCell>
                    <TableCell>{row.missing_items}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Group Price Series</CardTitle>
        </CardHeader>
        <CardContent>
          {groupId === null ? (
            <p className="text-sm text-muted-foreground">Select a group to view series.</p>
          ) : seriesPoints.length === 0 ? (
            <p className="text-sm text-muted-foreground">No series points yet.</p>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Unit Price</TableHead>
                  <TableHead>Purchases</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {seriesPoints.map((point) => (
                  <TableRow key={`${point.period}-${point.source_kind}-${point.product_id}`}>
                    <TableCell>{point.period}</TableCell>
                    <TableCell>{point.source_kind}</TableCell>
                    <TableCell>{point.product_name ?? point.product_id ?? "-"}</TableCell>
                    <TableCell>{formatEurFromCents(point.unit_price_cents)}</TableCell>
                    <TableCell>{point.purchase_count}</TableCell>
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
          <CardTitle>Retailer Price Index</CardTitle>
        </CardHeader>
        <CardContent>
          {indexPoints.length === 0 ? (
            <p className="text-sm text-muted-foreground">No index points available.</p>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Index</TableHead>
                  <TableHead>Products</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {indexPoints.map((point) => (
                  <TableRow key={`${point.period}-${point.source_kind}`}>
                    <TableCell>{point.period}</TableCell>
                    <TableCell>{point.source_kind}</TableCell>
                    <TableCell>{point.index}</TableCell>
                    <TableCell>{point.product_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
