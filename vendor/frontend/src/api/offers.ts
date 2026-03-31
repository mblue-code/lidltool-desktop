import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const OfferProductSchema = z
  .object({
    product_id: z.string(),
    canonical_name: z.string().optional(),
    brand: z.string().nullable().optional(),
    category_id: z.string().nullable().optional()
  })
  .passthrough();

const OfferWatchlistSchema = z
  .object({
    id: z.string().optional(),
    watchlist_id: z.string().optional(),
    product_id: z.string().nullable().optional(),
    query_text: z.string().nullable().optional(),
    source_id: z.string().nullable().optional(),
    min_discount_percent: z.number().nullable().optional(),
    max_price_cents: z.number().nullable().optional(),
    active: z.boolean().optional(),
    notes: z.string().nullable().optional(),
    created_at: z.string().nullable().optional(),
    updated_at: z.string().nullable().optional(),
    product: OfferProductSchema.optional()
  })
  .passthrough();

const OfferAlertSchema = z
  .object({
    id: z.string().optional(),
    alert_id: z.string().optional(),
    title: z.string().optional(),
    body: z.string().nullable().optional(),
    read: z.boolean().optional(),
    read_at: z.string().nullable().optional(),
    source_id: z.string().nullable().optional(),
    merchant_name: z.string().nullable().optional(),
    created_at: z.string().nullable().optional(),
    payload_json: z.unknown().optional(),
    payload: z.unknown().optional()
  })
  .passthrough();

const CollectionSchema = <T extends z.ZodTypeAny>(itemSchema: T) =>
  z
    .object({
      items: z.array(itemSchema),
      count: z.number().optional(),
      total: z.number().optional(),
      limit: z.number().optional(),
      offset: z.number().optional()
    })
    .passthrough();

const OfferWatchlistListResponseSchema = CollectionSchema(OfferWatchlistSchema);
const OfferAlertListResponseSchema = CollectionSchema(OfferAlertSchema).extend({
  unread_count: z.number().optional()
});
const RefreshOffersResponseSchema = z.object({}).passthrough();

export type OfferProduct = z.infer<typeof OfferProductSchema>;
export type OfferWatchlist = z.infer<typeof OfferWatchlistSchema>;
export type OfferWatchlistListResponse = z.infer<typeof OfferWatchlistListResponseSchema>;
export type OfferAlert = z.infer<typeof OfferAlertSchema>;
export type OfferAlertListResponse = z.infer<typeof OfferAlertListResponseSchema>;
export type RefreshOffersResult = z.infer<typeof RefreshOffersResponseSchema>;

export async function fetchOfferWatchlists(params?: {
  limit?: number;
  offset?: number;
}): Promise<OfferWatchlistListResponse> {
  return apiClient.get("/api/v1/offers/watchlists", OfferWatchlistListResponseSchema, {
    limit: params?.limit,
    offset: params?.offset
  });
}

export async function createOfferWatchlist(payload: {
  product_id?: string;
  query_text?: string;
  source_id?: string;
  min_discount_percent?: number;
  max_price_cents?: number;
  notes?: string;
  active?: boolean;
}): Promise<OfferWatchlist> {
  return apiClient.post("/api/v1/offers/watchlists", OfferWatchlistSchema, payload);
}

export async function updateOfferWatchlist(
  watchlistId: string,
  payload: {
    product_id?: string;
    query_text?: string;
    source_id?: string;
    min_discount_percent?: number;
    max_price_cents?: number;
    notes?: string;
    active?: boolean;
  }
): Promise<OfferWatchlist> {
  return apiClient.patch(`/api/v1/offers/watchlists/${watchlistId}`, OfferWatchlistSchema, payload);
}

export async function deleteOfferWatchlist(watchlistId: string): Promise<Record<string, unknown>> {
  return apiClient.delete(`/api/v1/offers/watchlists/${watchlistId}`, z.object({}).passthrough());
}

export async function fetchOfferAlerts(params?: {
  limit?: number;
  offset?: number;
  unreadOnly?: boolean;
}): Promise<OfferAlertListResponse> {
  return apiClient.get("/api/v1/offers/alerts", OfferAlertListResponseSchema, {
    limit: params?.limit,
    offset: params?.offset,
    unread_only: params?.unreadOnly
  });
}

export async function patchOfferAlert(
  alertId: string,
  payload: {
    read: boolean;
  }
): Promise<OfferAlert> {
  return apiClient.patch(`/api/v1/offers/alerts/${alertId}`, OfferAlertSchema, payload);
}

export async function refreshOffers(payload?: { source_ids?: string[] }): Promise<RefreshOffersResult> {
  return apiClient.post("/api/v1/offers/refresh", RefreshOffersResponseSchema, payload);
}
