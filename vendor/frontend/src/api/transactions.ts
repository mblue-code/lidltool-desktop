import { z } from "zod";

import { apiClient } from "@/lib/api-client";
import { isDemoSnapshotMode } from "@/demo/mode";

const TransactionListItemSchema = z.object({
  id: z.string(),
  purchased_at: z.string(),
  source_id: z.string(),
  user_id: z.string().nullable().optional(),
  shared_group_id: z.string().nullable().optional(),
  workspace_kind: z.string().nullable().optional(),
  source_transaction_id: z.string(),
  store_name: z.string().nullable(),
  total_gross_cents: z.number(),
  discount_total_cents: z.number().nullable(),
  currency: z.string(),
  allocation_mode: z.enum(["personal", "shared_receipt", "split_items"]).optional(),
  owner_username: z.string().nullable().optional(),
  owner_display_name: z.string().nullable().optional(),
  is_owner: z.boolean().nullable().optional()
});

const TransactionListResponseSchema = z.object({
  count: z.number(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  items: z.array(TransactionListItemSchema)
});

const TransactionDetailResponseSchema = z.object({
  transaction: z.object({
    id: z.string(),
    source_id: z.string(),
    user_id: z.string().nullable().optional(),
    shared_group_id: z.string().nullable().optional(),
    workspace_kind: z.string().nullable().optional(),
    source_transaction_id: z.string(),
    source_account_id: z.string().nullable().optional(),
    purchased_at: z.string(),
    merchant_name: z.string().nullable(),
    total_gross_cents: z.number(),
    currency: z.string().optional(),
    discount_total_cents: z.number().nullable(),
    allocation_mode: z.enum(["personal", "shared_receipt", "split_items"]).optional(),
    owner_username: z.string().nullable().optional(),
    owner_display_name: z.string().nullable().optional(),
    is_owner: z.boolean().nullable().optional(),
    raw_payload: z.unknown()
  }),
  items: z.array(
    z.object({
      id: z.string(),
      source_item_id: z.string().nullable().optional(),
      shared_group_id: z.string().nullable().optional(),
      line_no: z.number(),
      name: z.string(),
      qty: z.number(),
      unit: z.string().nullable(),
      unit_price_cents: z.number().nullable().optional(),
      line_total_cents: z.number(),
      category: z.string().nullable(),
      is_shared_allocation: z.boolean().optional()
    })
  ),
  discounts: z.array(
    z.object({
      id: z.string(),
      transaction_item_id: z.string().nullable(),
      source_label: z.string(),
      scope: z.string(),
      kind: z.string(),
      amount_cents: z.number()
    })
  ),
  documents: z.array(
    z.object({
      id: z.string(),
      shared_group_id: z.string().nullable().optional(),
      mime_type: z.string(),
      file_name: z.string().nullable(),
      created_at: z.string()
    })
  )
});

const TransactionHistoryResponseSchema = z.object({
  transaction_id: z.string(),
  count: z.number(),
  events: z.array(
    z.object({
      id: z.string(),
      created_at: z.string(),
      action: z.string(),
      actor_id: z.string().nullable(),
      entity_type: z.string().nullable(),
      details: z.record(z.string(), z.unknown()).nullable()
    })
  )
});

const OverrideLocalTransactionResultSchema = z
  .object({
    transaction_id: z.string(),
    updated_fields: z.array(z.string())
  })
  .nullable();

const OverrideLocalItemResultSchema = z.object({
  transaction_item_id: z.string(),
  updated_fields: z.array(z.string())
});

const OverrideGlobalCreatedSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("merchant_alias"),
    id: z.string(),
    alias: z.string(),
    canonical_name: z.string()
  }),
  z.object({
    type: z.literal("normalization_rule"),
    id: z.string(),
    rule_type: z.string(),
    pattern: z.string(),
    replacement: z.string()
  })
]);

const TransactionOverrideResponseSchema = z.object({
  transaction_id: z.string(),
  mode: z.enum(["local", "global", "both"]),
  local: z.object({
    transaction: OverrideLocalTransactionResultSchema,
    items: z.array(OverrideLocalItemResultSchema)
  }),
  global: z.object({
    created: z.array(OverrideGlobalCreatedSchema)
  })
});

const TransactionWorkspaceResponseSchema = z.object({
  transaction_id: z.string(),
  user_id: z.string().nullable(),
  shared_group_id: z.string().nullable().optional(),
  source_id: z.string(),
  allocation_mode: z.enum(["personal", "shared_receipt", "split_items"]),
  updated_at: z.string()
});

const TransactionItemAllocationResponseSchema = z.object({
  transaction_id: z.string(),
  item_id: z.string(),
  shared: z.boolean(),
  shared_group_id: z.string().nullable().optional()
});

const ManualTransactionResponseSchema = z.object({
  transaction_id: z.string(),
  source_id: z.string(),
  source_transaction_id: z.string(),
  reused: z.boolean(),
  transaction: z
    .object({
      id: z.string(),
      source_id: z.string(),
      shared_group_id: z.string().nullable().optional(),
      workspace_kind: z.string().nullable().optional(),
      source_transaction_id: z.string(),
      purchased_at: z.string(),
      merchant_name: z.string().nullable(),
      total_gross_cents: z.number(),
      currency: z.string(),
      discount_total_cents: z.number().nullable()
    })
    .nullable()
    .optional()
});

export type TransactionListResponse = z.infer<typeof TransactionListResponseSchema>;
export type TransactionListItem = z.infer<typeof TransactionListItemSchema>;
export type TransactionDetailResponse = z.infer<typeof TransactionDetailResponseSchema>;
export type TransactionHistoryResponse = z.infer<typeof TransactionHistoryResponseSchema>;
export type TransactionOverrideResponse = z.infer<typeof TransactionOverrideResponseSchema>;
export type TransactionWorkspaceResponse = z.infer<typeof TransactionWorkspaceResponseSchema>;
export type TransactionItemAllocationResponse = z.infer<typeof TransactionItemAllocationResponseSchema>;
export type ManualTransactionResponse = z.infer<typeof ManualTransactionResponseSchema>;

export type TransactionOverrideRequest = {
  actor_id?: string;
  reason?: string;
  mode: "local" | "global" | "both";
  transaction_corrections?: Record<string, unknown>;
  item_corrections?: Array<{ item_id: string; corrections: Record<string, unknown> }>;
};

export type ManualTransactionRequest = {
  purchased_at: string;
  merchant_name: string;
  total_gross_cents: number;
  idempotency_key?: string;
  source_id?: string;
  source_display_name?: string;
  source_transaction_id?: string;
  source_account_ref?: string;
  currency?: string;
  discount_total_cents?: number;
  allocation_mode?: "personal" | "shared_receipt" | "split_items";
  confidence?: number;
  reason?: string;
  actor_id?: string;
  raw_payload?: Record<string, unknown>;
  items?: Array<{
    name: string;
    line_total_cents: number;
    qty?: number;
    unit?: string;
    unit_price_cents?: number;
    category?: string;
    line_no?: number;
    source_item_id?: string;
    shared?: boolean;
    raw_payload?: Record<string, unknown>;
  }>;
  discounts?: Array<{
    source_label: string;
    amount_cents: number;
    scope?: "transaction" | "item";
    transaction_item_line_no?: number;
    source_discount_code?: string;
    kind?: string;
    subkind?: string;
    funded_by?: string;
    is_loyalty_program?: boolean;
    raw_payload?: Record<string, unknown>;
  }>;
};

export async function fetchTransactions(filters: {
  query?: string;
  sourceId?: string;
  sourceKind?: string;
  weekday?: number;
  hour?: number;
  tzOffsetMinutes?: number;
  merchantName?: string;
  year?: number;
  month?: number;
  purchasedFrom?: string;
  purchasedTo?: string;
  sortBy?: "purchased_at" | "store_name" | "source_id" | "total_gross_cents" | "discount_total_cents";
  sortDir?: "asc" | "desc";
  minTotalCents?: number;
  maxTotalCents?: number;
  limit?: number;
  offset?: number;
}): Promise<TransactionListResponse> {
  return apiClient.get("/api/v1/transactions", TransactionListResponseSchema, {
    query: filters.query,
    source_id: filters.sourceId,
    source_kind: filters.sourceKind,
    weekday: filters.weekday !== undefined ? String(filters.weekday) : undefined,
    hour: filters.hour !== undefined ? String(filters.hour) : undefined,
    tz_offset_minutes:
      filters.tzOffsetMinutes !== undefined ? String(filters.tzOffsetMinutes) : undefined,
    merchant_name: filters.merchantName,
    year: filters.year ? String(filters.year) : undefined,
    month: filters.month ? String(filters.month) : undefined,
    purchased_from: filters.purchasedFrom,
    purchased_to: filters.purchasedTo,
    sort_by: filters.sortBy === "store_name" ? "merchant_name" : filters.sortBy,
    sort_dir: filters.sortDir,
    min_total_cents: filters.minTotalCents !== undefined ? String(filters.minTotalCents) : undefined,
    max_total_cents: filters.maxTotalCents !== undefined ? String(filters.maxTotalCents) : undefined,
    limit: String(filters.limit ?? 50),
    offset: String(filters.offset ?? 0)
  });
}

export async function fetchTransactionDetail(transactionId: string): Promise<TransactionDetailResponse> {
  return apiClient.get(`/api/v1/transactions/${transactionId}`, TransactionDetailResponseSchema);
}

export async function fetchTransactionHistory(transactionId: string): Promise<TransactionHistoryResponse> {
  return apiClient.get(`/api/v1/transactions/${transactionId}/history`, TransactionHistoryResponseSchema);
}

export async function patchTransactionOverrides(
  transactionId: string,
  payload: TransactionOverrideRequest
): Promise<TransactionOverrideResponse> {
  return apiClient.patch(
    `/api/v1/transactions/${transactionId}/overrides`,
    TransactionOverrideResponseSchema,
    payload
  );
}

export async function patchTransactionWorkspace(
  transactionId: string,
  payload: {
    allocation_mode: "personal" | "shared_receipt" | "split_items";
    shared_group_id?: string;
  }
): Promise<TransactionWorkspaceResponse> {
  return apiClient.patch(
    `/api/v1/transactions/${transactionId}/workspace`,
    TransactionWorkspaceResponseSchema,
    {
      allocation_mode: payload.allocation_mode,
      shared_group_id: payload.shared_group_id
    }
  );
}

export async function patchTransactionItemAllocation(
  transactionId: string,
  itemId: string,
  shared: boolean
): Promise<TransactionItemAllocationResponse> {
  return apiClient.patch(
    `/api/v1/transactions/${transactionId}/items/${itemId}/allocation`,
    TransactionItemAllocationResponseSchema,
    {
      shared
    }
  );
}

export async function createManualTransaction(
  payload: ManualTransactionRequest
): Promise<ManualTransactionResponse> {
  return apiClient.post("/api/v1/transactions/manual", ManualTransactionResponseSchema, payload);
}

export function buildDocumentPreviewUrl(documentId: string): string {
  if (isDemoSnapshotMode()) {
    const safeText = encodeURIComponent(`Outlays Demo Snapshot\n${documentId}\nSynthetic receipt preview`);
    return `data:image/svg+xml;charset=UTF-8,<svg xmlns='http://www.w3.org/2000/svg' width='800' height='1200' viewBox='0 0 800 1200'><rect width='800' height='1200' fill='%23f8fafc'/><rect x='64' y='64' width='672' height='1072' rx='24' fill='white' stroke='%23cbd5e1' stroke-width='4'/><text x='400' y='180' text-anchor='middle' font-family='Arial, sans-serif' font-size='34' fill='%230f172a'>Outlays Demo Snapshot</text><text x='400' y='250' text-anchor='middle' font-family='Arial, sans-serif' font-size='24' fill='%23475569'>Synthetic receipt preview</text><text x='400' y='330' text-anchor='middle' font-family='Arial, sans-serif' font-size='20' fill='%2364748b'>${safeText}</text><line x1='120' y1='420' x2='680' y2='420' stroke='%23e2e8f0' stroke-width='2'/><text x='120' y='500' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>Bio Bananen</text><text x='640' y='500' text-anchor='end' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>2.29 EUR</text><text x='120' y='560' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>Milbona Vollmilch 3.5%</text><text x='640' y='560' text-anchor='end' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>1.39 EUR</text><text x='120' y='620' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>Junger Gouda 400g</text><text x='640' y='620' text-anchor='end' font-family='Arial, sans-serif' font-size='22' fill='%230f172a'>2.79 EUR</text><line x1='120' y1='720' x2='680' y2='720' stroke='%23e2e8f0' stroke-width='2'/><text x='120' y='790' font-family='Arial, sans-serif' font-size='24' fill='%230f172a'>Total</text><text x='640' y='790' text-anchor='end' font-family='Arial, sans-serif' font-size='24' fill='%230f172a'>48.92 EUR</text></svg>`;
  }
  return apiClient.buildUrl(`/api/v1/documents/${documentId}/preview`).toString();
}
