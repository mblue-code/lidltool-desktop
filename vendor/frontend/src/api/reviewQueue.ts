import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const ReviewQueueListResponseSchema = z.object({
  limit: z.number(),
  offset: z.number(),
  count: z.number(),
  total: z.number(),
  items: z.array(
    z.object({
      document_id: z.string(),
      transaction_id: z.string(),
      source_id: z.string().nullable(),
      review_status: z.string(),
      ocr_status: z.string(),
      merchant_name: z.string().nullable(),
      purchased_at: z.string(),
      total_gross_cents: z.number(),
      currency: z.string(),
      transaction_confidence: z.number().nullable(),
      ocr_confidence: z.number().nullable(),
      created_at: z.string()
    })
  )
});

const ReviewQueueDetailResponseSchema = z.object({
  document: z.object({
    id: z.string(),
    transaction_id: z.string(),
    source_id: z.string().nullable(),
    review_status: z.string(),
    ocr_status: z.string(),
    file_name: z.string().nullable(),
    mime_type: z.string(),
    storage_uri: z.string(),
    ocr_provider: z.string().nullable(),
    ocr_confidence: z.number().nullable(),
    ocr_fallback_used: z.boolean().nullable(),
    ocr_latency_ms: z.number().nullable(),
    ocr_text: z.string().nullable(),
    created_at: z.string(),
    processed_at: z.string().nullable()
  }),
  transaction: z.object({
    id: z.string(),
    source_id: z.string(),
    source_transaction_id: z.string(),
    purchased_at: z.string(),
    merchant_name: z.string().nullable(),
    total_gross_cents: z.number(),
    currency: z.string(),
    discount_total_cents: z.number().nullable(),
    confidence: z.number().nullable(),
    raw_payload: z.unknown()
  }),
  items: z.array(
    z.object({
      id: z.string(),
      line_no: z.number(),
      name: z.string(),
      qty: z.number(),
      unit: z.string().nullable(),
      unit_price_cents: z.number().nullable(),
      line_total_cents: z.number(),
      category: z.string().nullable(),
      confidence: z.number().nullable(),
      raw_payload: z.unknown()
    })
  ),
  confidence: z.record(z.string(), z.unknown())
});

const ReviewDecisionResponseSchema = z.object({
  document_id: z.string(),
  review_status: z.string()
});

const ReviewTransactionCorrectionResponseSchema = z.object({
  transaction_id: z.string(),
  updated_fields: z.array(z.string())
});

const ReviewItemCorrectionResponseSchema = z.object({
  transaction_item_id: z.string(),
  updated_fields: z.array(z.string())
});

export type ReviewQueueListResponse = z.infer<typeof ReviewQueueListResponseSchema>;
export type ReviewQueueDetailResponse = z.infer<typeof ReviewQueueDetailResponseSchema>;
export type ReviewDecisionResponse = z.infer<typeof ReviewDecisionResponseSchema>;
export type ReviewTransactionCorrectionResponse = z.infer<typeof ReviewTransactionCorrectionResponseSchema>;
export type ReviewItemCorrectionResponse = z.infer<typeof ReviewItemCorrectionResponseSchema>;

export type ReviewCorrectionRequest = {
  actor_id?: string;
  reason?: string;
  corrections: Record<string, unknown>;
};

export type ReviewDecisionRequest = {
  actor_id?: string;
  reason?: string;
};

export async function fetchReviewQueue(filters: {
  status?: string;
  threshold?: number;
  limit?: number;
  offset?: number;
}): Promise<ReviewQueueListResponse> {
  return apiClient.get("/api/v1/review-queue", ReviewQueueListResponseSchema, {
    status: filters.status,
    threshold: filters.threshold,
    limit: filters.limit ?? 50,
    offset: filters.offset ?? 0
  });
}

export async function fetchReviewQueueDetail(documentId: string): Promise<ReviewQueueDetailResponse> {
  return apiClient.get(`/api/v1/review-queue/${documentId}`, ReviewQueueDetailResponseSchema);
}

export async function approveReviewDocument(
  documentId: string,
  payload: ReviewDecisionRequest
): Promise<ReviewDecisionResponse> {
  return apiClient.post(`/api/v1/review-queue/${documentId}/approve`, ReviewDecisionResponseSchema, payload);
}

export async function rejectReviewDocument(
  documentId: string,
  payload: ReviewDecisionRequest
): Promise<ReviewDecisionResponse> {
  return apiClient.post(`/api/v1/review-queue/${documentId}/reject`, ReviewDecisionResponseSchema, payload);
}

export async function patchReviewTransaction(
  documentId: string,
  payload: ReviewCorrectionRequest
): Promise<ReviewTransactionCorrectionResponse> {
  return apiClient.patch(
    `/api/v1/review-queue/${documentId}/transaction`,
    ReviewTransactionCorrectionResponseSchema,
    payload
  );
}

export async function patchReviewItem(
  documentId: string,
  itemId: string,
  payload: ReviewCorrectionRequest
): Promise<ReviewItemCorrectionResponse> {
  return apiClient.patch(
    `/api/v1/review-queue/${documentId}/items/${itemId}`,
    ReviewItemCorrectionResponseSchema,
    payload
  );
}
