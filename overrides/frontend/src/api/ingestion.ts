import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const IngestionSessionSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable(),
  shared_group_id: z.string().nullable(),
  title: z.string(),
  input_kind: z.string(),
  approval_mode: z.enum(["review_first", "yolo_auto"]),
  status: z.string(),
  summary_json: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string()
});

const IngestionProposalSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  statement_row_id: z.string().nullable(),
  type: z.string(),
  status: z.string(),
  confidence: z.number().nullable(),
  payload_json: z.record(z.string(), z.unknown()),
  explanation: z.string().nullable(),
  model_metadata_json: z.record(z.string(), z.unknown()),
  commit_result_json: z.record(z.string(), z.unknown()).nullable(),
  error: z.string().nullable(),
  matches: z.array(
    z.object({
      id: z.string(),
      transaction_id: z.string(),
      score: z.number(),
      reason_json: z.record(z.string(), z.unknown()),
      selected: z.boolean(),
      created_at: z.string()
    })
  ),
  created_at: z.string(),
  updated_at: z.string()
});

const IngestionMatchCandidateSchema = z.object({
  transaction_id: z.string(),
  score: z.number(),
  reason: z.record(z.string(), z.unknown()),
  transaction: z.object({
    id: z.string(),
    merchant_name: z.string().nullable(),
    purchased_at: z.string(),
    total_gross_cents: z.number(),
    currency: z.string(),
    source_id: z.string()
  })
});

const IngestionMatchCandidateListSchema = z.object({
  count: z.number(),
  items: z.array(IngestionMatchCandidateSchema)
});

const IngestionProposalListSchema = z.object({
  count: z.number(),
  items: z.array(IngestionProposalSchema)
});

const IngestionMessageResultSchema = z.object({
  message_received: z.boolean(),
  proposals: z.array(IngestionProposalSchema)
});

const IngestionFileSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  storage_uri: z.string(),
  file_name: z.string().nullable(),
  mime_type: z.string().nullable(),
  sha256: z.string(),
  metadata_json: z.record(z.string(), z.unknown()),
  created_at: z.string()
});

const StatementRowSchema = z.object({
  id: z.string(),
  session_id: z.string(),
  file_id: z.string().nullable(),
  row_index: z.number(),
  row_hash: z.string(),
  occurred_at: z.string().nullable(),
  booked_at: z.string().nullable(),
  payee: z.string().nullable(),
  description: z.string().nullable(),
  amount_cents: z.number().nullable(),
  currency: z.string(),
  raw_json: z.record(z.string(), z.unknown()).nullable().optional(),
  status: z.string(),
  created_at: z.string(),
  updated_at: z.string()
});

const StatementRowListSchema = z.object({
  count: z.number(),
  skipped_duplicates: z.number().optional(),
  items: z.array(StatementRowSchema),
  proposals: z.array(IngestionProposalSchema).optional()
});

const IngestionAgentSettingsSchema = z.object({
  approval_mode: z.enum(["review_first", "yolo_auto"]),
  auto_commit_confidence_threshold: z.number(),
  auto_link_confidence_threshold: z.number(),
  auto_ignore_confidence_threshold: z.number(),
  auto_create_recurring_enabled: z.boolean(),
  personal_system_prompt: z.string(),
  updated_at: z.string()
});

export type IngestionSession = z.infer<typeof IngestionSessionSchema>;
export type IngestionProposal = z.infer<typeof IngestionProposalSchema>;
export type IngestionMatchCandidate = z.infer<typeof IngestionMatchCandidateSchema>;
export type StatementRow = z.infer<typeof StatementRowSchema>;
export type IngestionAgentSettings = z.infer<typeof IngestionAgentSettingsSchema>;

export type CreateTransactionProposalPayload = {
  type: "create_transaction";
  purchased_at: string;
  merchant_name: string;
  total_gross_cents: number;
  direction?: "outflow" | "inflow";
  ledger_scope?: "household" | "investment" | "internal" | "unknown";
  dashboard_include?: boolean;
  currency: string;
  source_id: string;
  source_display_name: string;
  source_account_ref?: string | null;
  source_transaction_id?: string | null;
  idempotency_key: string;
  confidence: number;
  items: Array<Record<string, unknown>>;
  discounts: Array<Record<string, unknown>>;
  raw_payload: Record<string, unknown>;
};

export function isCreateTransactionPayload(
  payload: Record<string, unknown>
): payload is CreateTransactionProposalPayload {
  return payload.type === "create_transaction";
}

export async function createIngestionSession(body: {
  title?: string;
  input_kind?: string;
  approval_mode?: "review_first" | "yolo_auto";
}): Promise<IngestionSession> {
  return apiClient.post("/api/v1/ingestion/sessions", IngestionSessionSchema, body);
}

export async function fetchIngestionSession(sessionId: string): Promise<IngestionSession> {
  return apiClient.get(`/api/v1/ingestion/sessions/${sessionId}`, IngestionSessionSchema);
}

export async function updateIngestionSession(
  sessionId: string,
  body: Partial<Pick<IngestionSession, "title" | "status" | "approval_mode">>
): Promise<IngestionSession> {
  return apiClient.patch(`/api/v1/ingestion/sessions/${sessionId}`, IngestionSessionSchema, body);
}

export async function archiveIngestionSession(sessionId: string): Promise<IngestionSession> {
  return apiClient.delete(`/api/v1/ingestion/sessions/${sessionId}`, IngestionSessionSchema);
}

export async function fetchIngestionAgentSettings(): Promise<IngestionAgentSettings> {
  return apiClient.get("/api/v1/settings/ingestion-agent", IngestionAgentSettingsSchema);
}

export async function updateIngestionAgentSettings(
  body: Partial<Omit<IngestionAgentSettings, "updated_at">>
): Promise<IngestionAgentSettings> {
  return apiClient.post("/api/v1/settings/ingestion-agent", IngestionAgentSettingsSchema, body);
}

export async function sendIngestionMessage(
  sessionId: string,
  message: string
): Promise<z.infer<typeof IngestionMessageResultSchema>> {
  return apiClient.post(`/api/v1/ingestion/sessions/${sessionId}/message`, IngestionMessageResultSchema, { message });
}

export async function fetchIngestionProposals(sessionId: string): Promise<z.infer<typeof IngestionProposalListSchema>> {
  return apiClient.get(`/api/v1/ingestion/sessions/${sessionId}/proposals`, IngestionProposalListSchema);
}

export async function uploadIngestionFile(
  sessionId: string,
  file: File,
  contextText?: string
): Promise<z.infer<typeof IngestionFileSchema>> {
  const formData = new FormData();
  formData.set("file", file);
  if (contextText?.trim()) {
    formData.set("context_text", contextText.trim());
  }
  return apiClient.postForm(`/api/v1/ingestion/sessions/${sessionId}/files`, IngestionFileSchema, formData);
}

export async function parseIngestionFile(fileId: string): Promise<z.infer<typeof StatementRowListSchema>> {
  return apiClient.post(`/api/v1/ingestion/files/${fileId}/parse`, StatementRowListSchema);
}

export async function parseIngestionPastedTable(sessionId: string, text: string): Promise<z.infer<typeof StatementRowListSchema>> {
  return apiClient.post(`/api/v1/ingestion/sessions/${sessionId}/pasted-table`, StatementRowListSchema, { text });
}

export async function fetchIngestionRows(sessionId: string): Promise<z.infer<typeof StatementRowListSchema>> {
  return apiClient.get(`/api/v1/ingestion/sessions/${sessionId}/rows`, StatementRowListSchema);
}

export async function classifyIngestionRows(sessionId: string): Promise<z.infer<typeof IngestionProposalListSchema>> {
  return apiClient.post(`/api/v1/ingestion/sessions/${sessionId}/classify-rows`, IngestionProposalListSchema);
}

export async function updateIngestionProposal(
  proposalId: string,
  body: { payload?: Record<string, unknown>; explanation?: string | null }
): Promise<IngestionProposal> {
  return apiClient.patch(`/api/v1/ingestion/proposals/${proposalId}`, IngestionProposalSchema, body);
}

export async function approveIngestionProposal(proposalId: string): Promise<IngestionProposal> {
  return apiClient.post(`/api/v1/ingestion/proposals/${proposalId}/approve`, IngestionProposalSchema);
}

export async function rejectIngestionProposal(proposalId: string): Promise<IngestionProposal> {
  return apiClient.post(`/api/v1/ingestion/proposals/${proposalId}/reject`, IngestionProposalSchema);
}

export async function refreshIngestionProposalMatches(proposalId: string): Promise<z.infer<typeof IngestionMatchCandidateListSchema>> {
  return apiClient.post(`/api/v1/ingestion/proposals/${proposalId}/refresh-matches`, IngestionMatchCandidateListSchema);
}

export async function commitIngestionProposal(proposalId: string): Promise<IngestionProposal> {
  return apiClient.post(`/api/v1/ingestion/proposals/${proposalId}/commit`, IngestionProposalSchema);
}

export async function undoIngestionProposal(proposalId: string): Promise<IngestionProposal> {
  return apiClient.post(`/api/v1/ingestion/proposals/${proposalId}/undo`, IngestionProposalSchema);
}

export async function batchApproveIngestionProposals(proposalIds: string[]): Promise<z.infer<typeof IngestionProposalListSchema>> {
  return apiClient.post("/api/v1/ingestion/proposals/batch-approve", IngestionProposalListSchema, { proposal_ids: proposalIds });
}

export async function batchCommitIngestionProposals(proposalIds: string[]): Promise<z.infer<typeof IngestionProposalListSchema>> {
  return apiClient.post("/api/v1/ingestion/proposals/batch-commit", IngestionProposalListSchema, { proposal_ids: proposalIds });
}

export async function batchRejectIngestionProposals(proposalIds: string[]): Promise<z.infer<typeof IngestionProposalListSchema>> {
  return apiClient.post("/api/v1/ingestion/proposals/batch-reject", IngestionProposalListSchema, { proposal_ids: proposalIds });
}
