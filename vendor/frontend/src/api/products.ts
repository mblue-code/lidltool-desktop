import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const ProductSearchResponseSchema = z.object({
  items: z.array(
    z.object({
      product_id: z.string(),
      canonical_name: z.string(),
      brand: z.string().nullable(),
      default_unit: z.string().nullable(),
      category_id: z.string().nullable(),
      gtin_ean: z.string().nullable(),
      alias_count: z.number()
    })
  ),
  count: z.number()
});

const ProductCategoryListResponseSchema = z.object({
  items: z.array(
    z.object({
      category_id: z.string(),
      name: z.string(),
      parent_category_id: z.string().nullable(),
      depth: z.number(),
      child_count: z.number()
    })
  ),
  count: z.number()
});

const ProductDetailResponseSchema = z.object({
  product: z.object({
    product_id: z.string(),
    canonical_name: z.string(),
    brand: z.string().nullable(),
    default_unit: z.string().nullable(),
    category_id: z.string().nullable(),
    gtin_ean: z.string().nullable(),
    created_at: z.string()
  }),
  aliases: z.array(
    z.object({
      alias_id: z.string(),
      source_kind: z.string().nullable(),
      raw_name: z.string(),
      raw_sku: z.string().nullable(),
      match_confidence: z.number().nullable(),
      match_method: z.string(),
      created_at: z.string()
    })
  )
});

const ProductPriceSeriesResponseSchema = z.object({
  product_id: z.string(),
  net: z.boolean(),
  grain: z.string(),
  points: z.array(
    z.object({
      period: z.string(),
      source_kind: z.string(),
      unit_price_cents: z.number(),
      purchase_count: z.number(),
      min_unit_price_cents: z.number(),
      max_unit_price_cents: z.number()
    })
  )
});

const ProductPurchasesResponseSchema = z.object({
  product_id: z.string(),
  count: z.number(),
  items: z.array(
    z.object({
      transaction_id: z.string(),
      date: z.string(),
      source_id: z.string(),
      source_kind: z.string(),
      merchant_name: z.string().nullable(),
      raw_item_name: z.string(),
      quantity_value: z.number().nullable(),
      quantity_unit: z.string().nullable(),
      unit_price_gross_cents: z.number(),
      unit_price_net_cents: z.number(),
      line_total_gross_cents: z.number(),
      line_total_net_cents: z.number()
    })
  )
});

const ProductMatchResponseSchema = z.object({
  product_id: z.string(),
  raw_name: z.string(),
  source_kind: z.string().nullable(),
  alias_id: z.string(),
  matched_item_count: z.number(),
  matched_transaction_count: z.number()
});

const ProductCreateResponseSchema = z.object({
  product_id: z.string(),
  canonical_name: z.string(),
  brand: z.string().nullable(),
  default_unit: z.string().nullable(),
  category_id: z.string().nullable(),
  gtin_ean: z.string().nullable(),
  is_ai_generated: z.boolean(),
  cluster_confidence: z.number().nullable(),
  created_at: z.string()
});

const ProductSeedResponseSchema = z.object({
  created: z.number(),
  skipped: z.number(),
  total_products: z.number()
});

const ProductMergeResponseSchema = z.object({
  target_product_id: z.string(),
  merged_products: z.number(),
  moved_aliases: z.number(),
  moved_items: z.number()
});

const ProductClusterStartResponseSchema = z.object({
  job_id: z.string(),
  status: z.string()
});

const ProductClusterStatusResponseSchema = z.object({
  status: z.string(),
  total_batches: z.number(),
  completed_batches: z.number(),
  products_created: z.number(),
  aliases_created: z.number(),
  items_matched: z.number(),
  errors: z.array(z.string())
});

export type ProductSearchResponse = z.infer<typeof ProductSearchResponseSchema>;
export type ProductCategoryListResponse = z.infer<typeof ProductCategoryListResponseSchema>;
export type ProductDetailResponse = z.infer<typeof ProductDetailResponseSchema>;
export type ProductPriceSeriesResponse = z.infer<typeof ProductPriceSeriesResponseSchema>;
export type ProductPurchasesResponse = z.infer<typeof ProductPurchasesResponseSchema>;
export type ProductMatchResponse = z.infer<typeof ProductMatchResponseSchema>;
export type ProductCreateResponse = z.infer<typeof ProductCreateResponseSchema>;
export type ProductSeedResponse = z.infer<typeof ProductSeedResponseSchema>;
export type ProductMergeResponse = z.infer<typeof ProductMergeResponseSchema>;
export type ProductClusterStartResponse = z.infer<typeof ProductClusterStartResponseSchema>;
export type ProductClusterStatusResponse = z.infer<typeof ProductClusterStatusResponseSchema>;

export async function fetchProducts(params?: {
  search?: string;
  sourceKind?: string;
  categoryId?: string;
  limit?: number;
}): Promise<ProductSearchResponse> {
  return apiClient.get("/api/v1/products", ProductSearchResponseSchema, {
    search: params?.search,
    source_kind: params?.sourceKind,
    category_id: params?.categoryId,
    limit: params?.limit === undefined ? undefined : String(params.limit)
  });
}

export async function fetchProductCategories(): Promise<ProductCategoryListResponse> {
  return apiClient.get("/api/v1/products/categories", ProductCategoryListResponseSchema);
}

export async function fetchProductDetail(productId: string): Promise<ProductDetailResponse> {
  return apiClient.get(`/api/v1/products/${productId}`, ProductDetailResponseSchema);
}

export async function fetchProductPriceSeries(params: {
  productId: string;
  fromDate?: string;
  toDate?: string;
  grain?: "day" | "month" | "year";
  net?: boolean;
}): Promise<ProductPriceSeriesResponse> {
  return apiClient.get(`/api/v1/products/${params.productId}/price-series`, ProductPriceSeriesResponseSchema, {
    from_date: params.fromDate,
    to_date: params.toDate,
    grain: params.grain,
    net: params.net === undefined ? undefined : String(params.net)
  });
}

export async function fetchProductPurchases(params: {
  productId: string;
  fromDate?: string;
  toDate?: string;
}): Promise<ProductPurchasesResponse> {
  return apiClient.get(`/api/v1/products/${params.productId}/purchases`, ProductPurchasesResponseSchema, {
    from_date: params.fromDate,
    to_date: params.toDate
  });
}

export async function postProductMatch(payload: {
  product_id: string;
  raw_name: string;
  source_kind?: string;
  raw_sku?: string;
}): Promise<ProductMatchResponse> {
  return apiClient.post("/api/v1/products/match", ProductMatchResponseSchema, payload);
}

export async function postCreateProduct(payload: {
  canonical_name: string;
  brand?: string;
  default_unit?: string;
  gtin_ean?: string;
}): Promise<ProductCreateResponse> {
  return apiClient.post("/api/v1/products", ProductCreateResponseSchema, payload);
}

export async function postSeedProducts(): Promise<ProductSeedResponse> {
  return apiClient.post("/api/v1/products/seed", ProductSeedResponseSchema);
}

export async function postMergeProducts(
  productId: string,
  payload: { source_product_ids: string[] }
): Promise<ProductMergeResponse> {
  return apiClient.post(`/api/v1/products/${productId}/merge`, ProductMergeResponseSchema, payload);
}

export async function postClusterProducts(payload?: {
  force?: boolean;
}): Promise<ProductClusterStartResponse> {
  return apiClient.post("/api/v1/products/cluster", ProductClusterStartResponseSchema, payload);
}

export async function fetchProductClusterStatus(jobId: string): Promise<ProductClusterStatusResponse> {
  return apiClient.get(`/api/v1/products/cluster/${jobId}`, ProductClusterStatusResponseSchema);
}
