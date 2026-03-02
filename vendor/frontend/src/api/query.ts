import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const QueryResultSchema = z.object({
  columns: z.array(z.string()),
  rows: z.array(z.array(z.unknown())),
  totals: z.record(z.string(), z.unknown()),
  drilldown_token: z.string(),
  explain: z.string()
});
const QueryDslResponseSchema = z.object({
  query: z.record(z.string(), z.unknown()),
  result: QueryResultSchema
});

const SavedQuerySchema = z.object({
  query_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  query_json: z.record(z.string(), z.unknown()),
  is_preset: z.boolean(),
  created_at: z.string()
});

const SavedQueryListSchema = z.object({
  items: z.array(SavedQuerySchema),
  count: z.number()
});

export type QueryRunRequest = {
  metrics: string[];
  dimensions?: string[];
  filters?: Record<string, unknown>;
  time_grain?: string;
  sort_by?: string;
  sort_dir?: "asc" | "desc";
  limit?: number;
  chart_pref?: string;
};

export type QueryResult = z.infer<typeof QueryResultSchema>;
export type QueryDslResponse = z.infer<typeof QueryDslResponseSchema>;
export type SavedQuery = z.infer<typeof SavedQuerySchema>;
export type SavedQueryList = z.infer<typeof SavedQueryListSchema>;

export async function runQuery(payload: QueryRunRequest): Promise<QueryResult> {
  return apiClient.post("/api/v1/query/run", QueryResultSchema, payload);
}

export async function runQueryDsl(dsl: string): Promise<QueryDslResponse> {
  return apiClient.post("/api/v1/query/dsl", QueryDslResponseSchema, { dsl });
}

export async function fetchSavedQueries(): Promise<SavedQueryList> {
  return apiClient.get("/api/v1/query/saved", SavedQueryListSchema);
}

export async function createSavedQuery(payload: {
  name: string;
  description?: string;
  query_json: Record<string, unknown>;
}): Promise<SavedQuery> {
  return apiClient.post("/api/v1/query/saved", SavedQuerySchema, payload);
}

export async function deleteSavedQuery(queryId: string): Promise<{ query_id: string; deleted: boolean }> {
  const schema = z.object({ query_id: z.string(), deleted: z.boolean() });
  return apiClient.delete(`/api/v1/query/saved/${queryId}`, schema);
}
