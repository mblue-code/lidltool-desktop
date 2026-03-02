import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const DEFAULT_DB = import.meta.env.VITE_DASHBOARD_DB || "";

const DocumentUploadResponseSchema = z.object({
  document_id: z.string(),
  storage_uri: z.string(),
  sha256: z.string(),
  mime_type: z.string(),
  status: z.string()
});

const DocumentProcessResponseSchema = z.object({
  document_id: z.string(),
  job_id: z.string(),
  status: z.string(),
  reused: z.boolean()
});

const DocumentStatusResponseSchema = z.object({
  document_id: z.string(),
  transaction_id: z.string().nullable(),
  source_id: z.string().nullable(),
  status: z.string(),
  review_status: z.string().nullable(),
  ocr_provider: z.string().nullable(),
  ocr_confidence: z.number().nullable(),
  ocr_fallback_used: z.boolean().nullable(),
  ocr_latency_ms: z.number().nullable(),
  processed_at: z.string().nullable(),
  job: z.record(z.string(), z.unknown()).optional()
});

export type DocumentUploadResponse = z.infer<typeof DocumentUploadResponseSchema>;
export type DocumentProcessResponse = z.infer<typeof DocumentProcessResponseSchema>;
export type DocumentStatusResponse = z.infer<typeof DocumentStatusResponseSchema>;

function appendCommonFormFields(formData: FormData): void {
  if (DEFAULT_DB) {
    formData.set("db", DEFAULT_DB);
  }
}

export async function uploadDocument(params: {
  file: File;
  source?: string;
  metadata?: Record<string, unknown>;
}): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.set("file", params.file);
  if (params.source?.trim()) {
    formData.set("source", params.source.trim());
  }
  if (params.metadata && Object.keys(params.metadata).length > 0) {
    formData.set("metadata_json", JSON.stringify(params.metadata));
  }
  appendCommonFormFields(formData);
  return apiClient.postForm("/api/v1/documents/upload", DocumentUploadResponseSchema, formData);
}

export async function processDocument(
  documentId: string,
  params?: { callerToken?: string }
): Promise<DocumentProcessResponse> {
  const formData = new FormData();
  if (params?.callerToken?.trim()) {
    formData.set("caller_token", params.callerToken.trim());
  }
  appendCommonFormFields(formData);
  return apiClient.postForm(`/api/v1/documents/${documentId}/process`, DocumentProcessResponseSchema, formData);
}

export async function fetchDocumentStatus(
  documentId: string,
  params?: { jobId?: string }
): Promise<DocumentStatusResponse> {
  return apiClient.get(`/api/v1/documents/${documentId}/status`, DocumentStatusResponseSchema, {
    job_id: params?.jobId
  });
}
