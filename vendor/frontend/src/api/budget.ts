import { z } from "zod";

import { ApiTransportError, ApiValidationError } from "@/lib/api-errors";
import { apiClient } from "@/lib/api-client";
import { emitApiWarnings } from "@/lib/api-warnings";
import { parseEnvelopeResult } from "@/lib/envelope";

const OPTIONAL_API_KEY = import.meta.env.VITE_OPENCLAW_API_KEY || "";

function mergeHeaders(headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  if (OPTIONAL_API_KEY && !merged.has("X-API-Key")) {
    merged.set("X-API-Key", OPTIONAL_API_KEY);
  }
  return merged;
}

async function requestJson<T, B = unknown>(args: {
  path: string;
  schema: z.ZodType<T>;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  query?: Record<string, string | number | boolean | undefined | null>;
  body?: B;
}): Promise<T> {
  const url = apiClient.buildUrl(args.path, args.query);
  const response = await fetch(url.toString(), {
    credentials: "include",
    method: args.method,
    headers: mergeHeaders(
      args.body === undefined ? undefined : { "Content-Type": "application/json" }
    ),
    body: args.body === undefined ? undefined : JSON.stringify(args.body)
  });

  if (!response.ok) {
    throw new ApiTransportError(response.status, `Request failed with status ${response.status}`);
  }

  const payload = await response.json();
  try {
    const parsed = parseEnvelopeResult(payload, args.schema);
    emitApiWarnings(parsed.warnings);
    return parsed.result;
  } catch (error) {
    if (error instanceof ApiValidationError) {
      throw error;
    }
    throw error;
  }
}

const BudgetMonthSchema = z.object({
  year: z.number(),
  month: z.number(),
  planned_income_cents: z.number().nullable(),
  target_savings_cents: z.number().nullable(),
  opening_balance_cents: z.number().nullable(),
  currency: z.string(),
  notes: z.string().nullable()
});

const BudgetRuleSchema = z.object({
  rule_id: z.string(),
  scope_type: z.string(),
  scope_value: z.string(),
  period: z.string(),
  budget_cents: z.number(),
  spent_cents: z.number(),
  remaining_cents: z.number(),
  utilization: z.number(),
  projected_spent_cents: z.number(),
  projected_utilization: z.number(),
  over_budget: z.boolean(),
  projected_over_budget: z.boolean()
});

const RecurringSummaryItemSchema = z.object({
  occurrence_id: z.string(),
  bill_id: z.string(),
  bill_name: z.string(),
  due_date: z.string(),
  status: z.string(),
  expected_amount_cents: z.number().nullable(),
  actual_amount_cents: z.number().nullable()
});

const LinkedTransactionSchema = z.object({
  id: z.string(),
  purchased_at: z.string(),
  merchant_name: z.string().nullable(),
  total_gross_cents: z.number(),
  currency: z.string()
});

const BudgetSummarySchema = z.object({
  period: z.object({
    year: z.number(),
    month: z.number()
  }),
  month: BudgetMonthSchema,
  totals: z.object({
    planned_income_cents: z.number().nullable(),
    actual_income_cents: z.number(),
    income_basis_cents: z.number(),
    income_basis: z.string(),
    target_savings_cents: z.number().nullable(),
    opening_balance_cents: z.number().nullable(),
    receipt_spend_cents: z.number(),
    manual_outflow_cents: z.number(),
    total_outflow_cents: z.number(),
    recurring_expected_cents: z.number(),
    recurring_paid_cents: z.number(),
    available_cents: z.number(),
    remaining_cents: z.number(),
    saved_cents: z.number(),
    savings_delta_cents: z.number()
  }),
  budget_rules: z.array(BudgetRuleSchema),
  recurring: z.object({
    count: z.number(),
    paid_count: z.number(),
    unpaid_count: z.number(),
    items: z.array(RecurringSummaryItemSchema)
  }),
  cashflow: z.object({
    count: z.number(),
    inflow_count: z.number(),
    outflow_count: z.number(),
    reconciled_count: z.number()
  })
});

const CashflowEntrySchema = z.object({
  id: z.string(),
  user_id: z.string(),
  effective_date: z.string(),
  direction: z.enum(["inflow", "outflow"]),
  category: z.string(),
  amount_cents: z.number(),
  currency: z.string(),
  description: z.string().nullable(),
  source_type: z.string(),
  linked_transaction_id: z.string().nullable(),
  is_reconciled: z.boolean(),
  linked_transaction: LinkedTransactionSchema.nullable(),
  linked_recurring_occurrence_id: z.string().nullable(),
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

const CashflowEntryListSchema = z.object({
  count: z.number(),
  total: z.number(),
  items: z.array(CashflowEntrySchema)
});

const DeletedCashflowEntrySchema = z.object({
  deleted: z.boolean(),
  id: z.string()
});

export type BudgetMonth = z.infer<typeof BudgetMonthSchema>;
export type BudgetRule = z.infer<typeof BudgetRuleSchema>;
export type BudgetSummary = z.infer<typeof BudgetSummarySchema>;
export type CashflowEntry = z.infer<typeof CashflowEntrySchema>;
export type CashflowEntryList = z.infer<typeof CashflowEntryListSchema>;

export async function fetchBudgetMonth(year: number, month: number): Promise<BudgetMonth> {
  return requestJson({
    path: `/api/v1/budget/months/${year}/${month}`,
    method: "GET",
    schema: BudgetMonthSchema
  });
}

export async function updateBudgetMonth(
  year: number,
  month: number,
  payload: {
    planned_income_cents: number | null;
    target_savings_cents: number | null;
    opening_balance_cents: number | null;
    currency?: string;
    notes?: string | null;
  }
): Promise<BudgetMonth> {
  return requestJson({
    path: `/api/v1/budget/months/${year}/${month}`,
    method: "PUT",
    schema: BudgetMonthSchema,
    body: payload
  });
}

export async function fetchBudgetSummary(year: number, month: number): Promise<BudgetSummary> {
  return requestJson({
    path: `/api/v1/budget/months/${year}/${month}/summary`,
    method: "GET",
    schema: BudgetSummarySchema
  });
}

export async function fetchCashflowEntries(
  year: number,
  month: number,
  filters?: {
    direction?: "inflow" | "outflow";
    category?: string;
    reconciled?: boolean;
  }
): Promise<CashflowEntryList> {
  return requestJson({
    path: "/api/v1/cashflow-entries",
    method: "GET",
    schema: CashflowEntryListSchema,
    query: {
      year,
      month,
      direction: filters?.direction,
      category: filters?.category?.trim() || undefined,
      reconciled: filters?.reconciled
    }
  });
}

export async function createCashflowEntry(payload: {
  effective_date: string;
  direction: "inflow" | "outflow";
  category: string;
  amount_cents: number;
  currency?: string;
  description: string;
  source_type?: string;
  linked_transaction_id?: string | null;
  linked_recurring_occurrence_id?: string | null;
  notes?: string | null;
}): Promise<CashflowEntry> {
  return requestJson({
    path: "/api/v1/cashflow-entries",
    method: "POST",
    schema: CashflowEntrySchema,
    body: payload
  });
}

export async function updateCashflowEntry(
  entryId: string,
  payload: Partial<{
    effective_date: string;
    direction: "inflow" | "outflow";
    category: string;
    amount_cents: number;
    currency: string;
    description: string;
    source_type: string;
    linked_transaction_id: string | null;
    linked_recurring_occurrence_id: string | null;
    notes: string | null;
  }>
): Promise<CashflowEntry> {
  return requestJson({
    path: `/api/v1/cashflow-entries/${entryId}`,
    method: "PATCH",
    schema: CashflowEntrySchema,
    body: payload
  });
}

export async function deleteCashflowEntry(entryId: string): Promise<{ deleted: boolean; id: string }> {
  return requestJson({
    path: `/api/v1/cashflow-entries/${entryId}`,
    method: "DELETE",
    schema: DeletedCashflowEntrySchema
  });
}
