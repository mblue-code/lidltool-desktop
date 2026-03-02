import { z } from "zod";

import { apiClient } from "@/lib/api-client";

export const RecurringBillSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  name: z.string(),
  merchant_canonical: z.string().nullable(),
  merchant_alias_pattern: z.string().nullable(),
  category: z.string(),
  frequency: z.enum(["weekly", "biweekly", "monthly", "quarterly", "yearly"]),
  interval_value: z.number(),
  amount_cents: z.number().nullable(),
  amount_tolerance_pct: z.number(),
  currency: z.string(),
  anchor_date: z.string(),
  active: z.boolean(),
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

const RecurringBillMatchSchema = z.object({
  id: z.string(),
  occurrence_id: z.string(),
  transaction_id: z.string(),
  match_confidence: z.number(),
  match_method: z.string(),
  matched_at: z.string(),
  created_at: z.string()
});

export const RecurringBillOccurrenceSchema = z.object({
  id: z.string(),
  bill_id: z.string(),
  due_date: z.string(),
  status: z.enum(["upcoming", "due", "paid", "overdue", "skipped", "unmatched"]),
  expected_amount_cents: z.number().nullable(),
  actual_amount_cents: z.number().nullable(),
  notes: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  matches: z.array(RecurringBillMatchSchema)
});

export const RecurringOverviewSchema = z.object({
  active_bills: z.number(),
  due_this_week: z.number(),
  overdue: z.number(),
  monthly_committed_cents: z.number(),
  status_counts: z.record(z.string(), z.number()),
  currency: z.string()
});

export const RecurringCalendarSchema = z.object({
  year: z.number(),
  month: z.number(),
  days: z.array(
    z.object({
      date: z.string(),
      items: z.array(
        z.object({
          occurrence_id: z.string(),
          bill_id: z.string(),
          bill_name: z.string(),
          status: z.string(),
          expected_amount_cents: z.number().nullable(),
          actual_amount_cents: z.number().nullable()
        })
      ),
      count: z.number(),
      total_expected_cents: z.number()
    })
  ),
  count: z.number()
});

export const RecurringForecastSchema = z.object({
  months: z.number(),
  points: z.array(
    z.object({
      period: z.string(),
      projected_cents: z.number(),
      currency: z.string()
    })
  ),
  total_projected_cents: z.number(),
  currency: z.string()
});

const RecurringGapsSchema = z.object({
  count: z.number(),
  items: z.array(RecurringBillOccurrenceSchema)
});

const RecurringBillListSchema = z.object({
  count: z.number(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  items: z.array(RecurringBillSchema)
});

const RecurringOccurrenceListSchema = z.object({
  count: z.number(),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
  items: z.array(RecurringBillOccurrenceSchema)
});

const RecurringGenerateResponseSchema = z.object({
  bill_id: z.string(),
  created: z.number(),
  updated: z.number(),
  count: z.number(),
  items: z.array(RecurringBillOccurrenceSchema)
});

const RecurringMatchCandidateSchema = z.object({
  transaction_id: z.string(),
  score: z.number(),
  match_method: z.string(),
  merchant_score: z.number(),
  amount_score: z.number(),
  date_score: z.number(),
  purchased_at: z.string(),
  merchant_name: z.string().nullable(),
  total_gross_cents: z.number()
});

const RecurringRunMatchingSchema = z.object({
  processed: z.number(),
  auto_matched: z.number(),
  review_candidates: z.number(),
  unmatched: z.number(),
  items: z.array(
    z.object({
      occurrence: RecurringBillOccurrenceSchema,
      best_score: z.number(),
      candidates: z.array(RecurringMatchCandidateSchema)
    })
  )
});

const RecurringDeleteSchema = z.object({
  deleted: z.boolean(),
  id: z.string(),
  active: z.boolean()
});

export type RecurringBill = z.infer<typeof RecurringBillSchema>;
export type RecurringBillOccurrence = z.infer<typeof RecurringBillOccurrenceSchema>;
export type RecurringOverview = z.infer<typeof RecurringOverviewSchema>;
export type RecurringCalendar = z.infer<typeof RecurringCalendarSchema>;
export type RecurringForecast = z.infer<typeof RecurringForecastSchema>;

export async function fetchRecurringBills(params?: {
  includeInactive?: boolean;
  limit?: number;
  offset?: number;
}) {
  return apiClient.get("/api/v1/recurring-bills", RecurringBillListSchema, {
    include_inactive: params?.includeInactive,
    limit: params?.limit,
    offset: params?.offset
  });
}

export async function createRecurringBill(payload: {
  name: string;
  merchant_canonical?: string | null;
  merchant_alias_pattern?: string | null;
  category?: string;
  frequency: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
  interval_value?: number;
  amount_cents?: number | null;
  amount_tolerance_pct?: number;
  currency?: string;
  anchor_date: string;
  active?: boolean;
  notes?: string | null;
}) {
  return apiClient.post("/api/v1/recurring-bills", RecurringBillSchema, payload);
}

export async function fetchRecurringBill(billId: string) {
  return apiClient.get(`/api/v1/recurring-bills/${billId}`, RecurringBillSchema);
}

export async function updateRecurringBill(
  billId: string,
  payload: Partial<{
    name: string;
    merchant_canonical: string | null;
    merchant_alias_pattern: string | null;
    category: string;
    frequency: "weekly" | "biweekly" | "monthly" | "quarterly" | "yearly";
    interval_value: number;
    amount_cents: number | null;
    amount_tolerance_pct: number;
    currency: string;
    anchor_date: string;
    active: boolean;
    notes: string | null;
  }>
) {
  return apiClient.patch(`/api/v1/recurring-bills/${billId}`, RecurringBillSchema, payload);
}

export async function deleteRecurringBill(billId: string) {
  return apiClient.delete(`/api/v1/recurring-bills/${billId}`, RecurringDeleteSchema);
}

export async function fetchRecurringOverview() {
  return apiClient.get("/api/v1/recurring-bills/analytics/overview", RecurringOverviewSchema);
}

export async function fetchRecurringCalendar(params?: { year?: number; month?: number }) {
  return apiClient.get("/api/v1/recurring-bills/analytics/calendar", RecurringCalendarSchema, {
    year: params?.year,
    month: params?.month
  });
}

export async function fetchRecurringForecast(params?: { months?: number }) {
  return apiClient.get("/api/v1/recurring-bills/analytics/forecast", RecurringForecastSchema, {
    months: params?.months
  });
}

export async function fetchRecurringGaps() {
  return apiClient.get("/api/v1/recurring-bills/analytics/gaps", RecurringGapsSchema);
}

export async function fetchBillOccurrences(
  billId: string,
  params?: {
    fromDate?: string;
    toDate?: string;
    status?: string;
    limit?: number;
    offset?: number;
  }
) {
  return apiClient.get(`/api/v1/recurring-bills/${billId}/occurrences`, RecurringOccurrenceListSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate,
    status: params?.status,
    limit: params?.limit,
    offset: params?.offset
  });
}

export async function generateBillOccurrences(
  billId: string,
  payload?: {
    from_date?: string;
    to_date?: string;
    horizon_months?: number;
  }
) {
  return apiClient.post(
    `/api/v1/recurring-bills/${billId}/occurrences/generate`,
    RecurringGenerateResponseSchema,
    payload
  );
}

export async function runBillMatching(
  billId: string,
  payload?: {
    auto_match_threshold?: number;
    review_threshold?: number;
  }
) {
  return apiClient.post(`/api/v1/recurring-bills/${billId}/match`, RecurringRunMatchingSchema, payload);
}

export async function updateOccurrenceStatus(
  occurrenceId: string,
  payload: {
    status: "upcoming" | "due" | "paid" | "overdue" | "skipped" | "unmatched";
    notes?: string | null;
  }
) {
  return apiClient.patch(
    `/api/v1/recurring-bills/occurrences/${occurrenceId}/status`,
    RecurringBillOccurrenceSchema,
    payload
  );
}

export async function skipOccurrence(occurrenceId: string, notes?: string | null) {
  return apiClient.post(`/api/v1/recurring-bills/occurrences/${occurrenceId}/skip`, RecurringBillOccurrenceSchema, {
    notes
  });
}

export async function reconcileOccurrence(
  occurrenceId: string,
  payload: {
    transaction_id: string;
    match_confidence?: number;
    match_method?: string;
    notes?: string | null;
  }
) {
  return apiClient.post(
    `/api/v1/recurring-bills/occurrences/${occurrenceId}/reconcile`,
    RecurringBillOccurrenceSchema,
    payload
  );
}
