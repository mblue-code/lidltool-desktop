import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const UnmatchedItemsResponseSchema = z.object({
  items: z.array(
    z.object({
      raw_name: z.string(),
      source_kind: z.string(),
      purchase_count: z.number(),
      total_spend_cents: z.number(),
      last_seen_at: z.string().nullable()
    })
  ),
  count: z.number()
});

const LowConfidenceOcrResponseSchema = z.object({
  items: z.array(
    z.object({
      document_id: z.string(),
      transaction_id: z.string().nullable(),
      source_id: z.string().nullable(),
      file_name: z.string().nullable(),
      review_status: z.string().nullable(),
      ocr_status: z.string().nullable(),
      ocr_confidence: z.number().nullable(),
      created_at: z.string()
    })
  ),
  count: z.number(),
  threshold: z.number()
});

export type UnmatchedItemsResponse = z.infer<typeof UnmatchedItemsResponseSchema>;
export type LowConfidenceOcrResponse = z.infer<typeof LowConfidenceOcrResponseSchema>;

export async function fetchUnmatchedItems(limit = 200): Promise<UnmatchedItemsResponse> {
  return apiClient.get("/api/v1/quality/unmatched-items", UnmatchedItemsResponseSchema, {
    limit: String(limit)
  });
}

export async function fetchLowConfidenceOcr(params?: {
  threshold?: number;
  limit?: number;
}): Promise<LowConfidenceOcrResponse> {
  return apiClient.get("/api/v1/quality/low-confidence-ocr", LowConfidenceOcrResponseSchema, {
    threshold: params?.threshold === undefined ? undefined : String(params.threshold),
    limit: params?.limit === undefined ? undefined : String(params.limit)
  });
}
