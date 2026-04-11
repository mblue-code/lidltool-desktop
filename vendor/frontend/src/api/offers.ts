import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const OfferSourceRefreshSchema = z.object({
  source_id: z.string(),
  status: z.string(),
  error: z.string().nullable().optional(),
  offers_seen: z.number(),
  inserted: z.number(),
  updated: z.number(),
  blocked: z.number(),
  matched: z.number(),
  alerts_created: z.number()
});

const OfferSourceSchema = z.object({
  id: z.string().optional(),
  source_id: z.string(),
  plugin_id: z.string(),
  display_name: z.string(),
  merchant_name: z.string(),
  country_code: z.string(),
  runtime_kind: z.string(),
  merchant_url: z.string().nullable().optional(),
  active: z.boolean().optional(),
  notes: z.string().nullable().optional(),
  feed_path: z.string().nullable().optional(),
  active_offer_count: z.number(),
  total_offer_count: z.number(),
  latest_refresh: OfferSourceRefreshSchema.nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional()
});

const OfferRefreshRunSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable(),
  rule_id: z.string().nullable(),
  trigger_kind: z.string(),
  status: z.string(),
  source_count: z.number(),
  source_ids: z.array(z.string()),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  error: z.string().nullable(),
  totals: z.record(z.string(), z.unknown()),
  source_results: z.array(OfferSourceRefreshSchema),
  success_count: z.number(),
  failure_count: z.number()
});

const OfferWatchlistSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  product_id: z.string().nullable(),
  product_name: z.string().nullable(),
  query_text: z.string().nullable(),
  source_id: z.string().nullable(),
  min_discount_percent: z.number().nullable(),
  max_price_cents: z.number().nullable(),
  active: z.boolean(),
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

const OfferMatchSchema = z.object({
  id: z.string(),
  status: z.string(),
  match_kind: z.string(),
  match_method: z.string(),
  matched_product_id: z.string().nullable(),
  matched_product_name: z.string().nullable(),
  watchlist: OfferWatchlistSchema.nullable(),
  offer: z.object({
    offer_id: z.string(),
    source_id: z.string(),
    merchant_name: z.string(),
    title: z.string(),
    summary: z.string().nullable(),
    offer_type: z.string(),
    price_cents: z.number().nullable(),
    original_price_cents: z.number().nullable(),
    discount_percent: z.number().nullable(),
    offer_url: z.string().nullable(),
    image_url: z.string().nullable(),
    validity_start: z.string(),
    validity_end: z.string(),
    item_title: z.string().nullable()
  }),
  reason: z.object({
    title: z.string(),
    summary: z.string(),
    explanations: z.array(z.string()).optional(),
    reasons: z.array(z.record(z.string(), z.unknown()))
  }).and(z.record(z.string(), z.unknown())),
  unread_alert_count: z.number(),
  created_at: z.string(),
  updated_at: z.string()
});

const OfferAlertSchema = z.object({
  id: z.string(),
  status: z.string(),
  event_type: z.string(),
  title: z.string(),
  body: z.string().nullable(),
  read_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  match: OfferMatchSchema
});

const OfferOverviewSchema = z.object({
  counts: z.object({
    watchlists: z.number(),
    active_matches: z.number(),
    unread_alerts: z.number()
  }),
  sources: z.array(OfferSourceSchema),
  recent_refresh_runs: z.array(OfferRefreshRunSchema)
});

const OfferSourcesResponseSchema = z.object({
  items: z.array(OfferSourceSchema)
});

const OfferMerchantItemSchema = z.object({
  product_id: z.string().nullable(),
  product_name: z.string().nullable(),
  item_name: z.string(),
  label: z.string(),
  purchase_count: z.number(),
  last_purchased_at: z.string().nullable()
});

const OfferMerchantItemsResponseSchema = z.object({
  count: z.number(),
  items: z.array(OfferMerchantItemSchema)
});

const OfferWatchlistListSchema = z.object({
  count: z.number(),
  items: z.array(OfferWatchlistSchema)
});

const OfferMatchListSchema = z.object({
  count: z.number(),
  items: z.array(OfferMatchSchema)
});

const OfferAlertListSchema = z.object({
  count: z.number(),
  items: z.array(OfferAlertSchema)
});

const OfferRefreshRunListSchema = z.object({
  count: z.number(),
  items: z.array(OfferRefreshRunSchema)
});

const DeleteWatchlistSchema = z.object({
  deleted: z.boolean(),
  id: z.string()
});

const DeleteOfferSourceSchema = z.object({
  deleted: z.boolean(),
  source_id: z.string()
});

export type OfferSource = z.infer<typeof OfferSourceSchema>;
export type OfferRefreshRun = z.infer<typeof OfferRefreshRunSchema>;
export type OfferWatchlist = z.infer<typeof OfferWatchlistSchema>;
export type OfferMatch = z.infer<typeof OfferMatchSchema>;
export type OfferAlert = z.infer<typeof OfferAlertSchema>;
export type OfferOverview = z.infer<typeof OfferOverviewSchema>;
export type OfferMerchantItem = z.infer<typeof OfferMerchantItemSchema>;

export async function fetchOffersOverview(): Promise<OfferOverview> {
  return apiClient.get("/api/v1/offers", OfferOverviewSchema);
}

export async function fetchOfferSources(): Promise<z.infer<typeof OfferSourcesResponseSchema>> {
  return apiClient.get("/api/v1/offers/sources", OfferSourcesResponseSchema);
}

export async function createOfferSource(payload: {
  merchant_name: string;
  merchant_url: string;
  display_name?: string;
  country_code?: string;
  notes?: string;
}): Promise<OfferSource> {
  return apiClient.post("/api/v1/offers/sources", OfferSourceSchema, payload);
}

export async function updateOfferSource(
  sourceId: string,
  payload: {
    merchant_name?: string;
    merchant_url?: string;
    display_name?: string;
    country_code?: string;
    notes?: string | null;
    active?: boolean;
  }
): Promise<OfferSource> {
  return apiClient.patch(`/api/v1/offers/sources/${sourceId}`, OfferSourceSchema, payload);
}

export async function deleteOfferSource(sourceId: string): Promise<z.infer<typeof DeleteOfferSourceSchema>> {
  return apiClient.delete(`/api/v1/offers/sources/${sourceId}`, DeleteOfferSourceSchema);
}

export async function fetchOfferMerchantItems(params: {
  merchantName: string;
  limit?: number;
}): Promise<z.infer<typeof OfferMerchantItemsResponseSchema>> {
  return apiClient.get("/api/v1/offers/merchant-items", OfferMerchantItemsResponseSchema, {
    merchant_name: params.merchantName,
    limit: String(params.limit ?? 100)
  });
}

export async function fetchOfferRefreshRuns(limit = 20): Promise<z.infer<typeof OfferRefreshRunListSchema>> {
  return apiClient.get("/api/v1/offers/refresh-runs", OfferRefreshRunListSchema, {
    limit: String(limit)
  });
}

export async function postOfferRefresh(payload?: {
  source_ids?: string[];
  discovery_limit?: number;
}): Promise<OfferRefreshRun> {
  return apiClient.post("/api/v1/offers/refresh", OfferRefreshRunSchema, payload ?? {});
}

export async function fetchOfferWatchlists(): Promise<z.infer<typeof OfferWatchlistListSchema>> {
  return apiClient.get("/api/v1/offers/watchlists", OfferWatchlistListSchema);
}

export async function createOfferWatchlist(payload: {
  product_id?: string;
  query_text?: string;
  source_id?: string;
  min_discount_percent?: number;
  max_price_cents?: number;
  notes?: string;
}): Promise<OfferWatchlist> {
  return apiClient.post("/api/v1/offers/watchlists", OfferWatchlistSchema, payload);
}

export async function updateOfferWatchlist(
  watchlistId: string,
  payload: {
    product_id?: string | null;
    query_text?: string | null;
    source_id?: string | null;
    min_discount_percent?: number | null;
    max_price_cents?: number | null;
    active?: boolean;
    notes?: string | null;
  }
): Promise<OfferWatchlist> {
  return apiClient.patch(`/api/v1/offers/watchlists/${watchlistId}`, OfferWatchlistSchema, payload);
}

export async function deleteOfferWatchlist(watchlistId: string): Promise<z.infer<typeof DeleteWatchlistSchema>> {
  return apiClient.delete(`/api/v1/offers/watchlists/${watchlistId}`, DeleteWatchlistSchema);
}

export async function fetchOfferMatches(limit = 100): Promise<z.infer<typeof OfferMatchListSchema>> {
  return apiClient.get("/api/v1/offers/matches", OfferMatchListSchema, {
    limit: String(limit)
  });
}

export async function fetchOfferAlerts(params?: {
  unreadOnly?: boolean;
  limit?: number;
}): Promise<z.infer<typeof OfferAlertListSchema>> {
  return apiClient.get("/api/v1/offers/alerts", OfferAlertListSchema, {
    unread_only: params?.unreadOnly === undefined ? undefined : String(params.unreadOnly),
    limit: String(params?.limit ?? 100)
  });
}

export async function patchOfferAlert(alertId: string, read = true): Promise<OfferAlert> {
  return apiClient.patch(`/api/v1/offers/alerts/${alertId}`, OfferAlertSchema, { read });
}
