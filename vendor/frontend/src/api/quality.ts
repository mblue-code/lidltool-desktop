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

const RecategorizeJobSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  requested_by_user_id: z.string(),
  requested_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  source_id: z.string().nullable(),
  only_fallback_other: z.boolean(),
  include_suspect_model_items: z.boolean(),
  max_transactions: z.number().nullable(),
  transaction_count: z.number(),
  candidate_item_count: z.number(),
  updated_transaction_count: z.number(),
  updated_item_count: z.number(),
  skipped_transaction_count: z.number(),
  method_counts: z.record(z.string(), z.number()),
  error: z.string().nullable()
});

const RecategorizeStartResponseSchema = z.object({
  job: RecategorizeJobSchema
});

export type UnmatchedItemsResponse = z.infer<typeof UnmatchedItemsResponseSchema>;
export type LowConfidenceOcrResponse = z.infer<typeof LowConfidenceOcrResponseSchema>;
export type RecategorizeJob = z.infer<typeof RecategorizeJobSchema>;

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

export async function startQualityRecategorize(payload?: {
  source_id?: string;
  only_fallback_other?: boolean;
  include_suspect_model_items?: boolean;
  max_transactions?: number;
}): Promise<RecategorizeJob> {
  const response = await apiClient.post(
    "/api/v1/quality/recategorize",
    RecategorizeStartResponseSchema,
    payload ?? {}
  );
  return response.job;
}

export async function fetchQualityRecategorizeStatus(jobId: string): Promise<RecategorizeJob> {
  return apiClient.get("/api/v1/quality/recategorize/status", RecategorizeJobSchema, {
    job_id: jobId
  });
}
