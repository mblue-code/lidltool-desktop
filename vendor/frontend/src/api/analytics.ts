import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const TimingValueModeSchema = z.enum(["net", "gross", "count"]);

const DepositAnalyticsSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  total_paid_cents: z.number(),
  total_returned_cents: z.number(),
  net_outstanding_cents: z.number(),
  monthly: z.array(
    z.object({
      month: z.string(),
      paid_cents: z.number(),
      returned_cents: z.number(),
      net_cents: z.number()
    })
  )
});

export type DepositAnalytics = z.infer<typeof DepositAnalyticsSchema>;

export async function fetchDepositAnalytics(): Promise<DepositAnalytics> {
  return apiClient.get("/api/v1/analytics/deposits", DepositAnalyticsSchema);
}

const HeatmapResponseSchema = z.object({
  value: TimingValueModeSchema,
  date_from: z.string(),
  date_to: z.string(),
  source_kinds: z.array(z.string()).nullable(),
  tz_offset_minutes: z.number(),
  points: z.array(
    z.object({
      date: z.string(),
      weekday: z.number(),
      week: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  ),
  weekday_totals: z.array(
    z.object({
      weekday: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  )
});

const HourHeatmapResponseSchema = z.object({
  value: TimingValueModeSchema,
  date_from: z.string(),
  date_to: z.string(),
  source_kind: z.string().nullable(),
  tz_offset_minutes: z.number(),
  points: z.array(
    z.object({
      hour: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  ),
  totals: z.object({
    value_cents: z.number(),
    count: z.number()
  })
});

const TimingMatrixResponseSchema = z.object({
  value: TimingValueModeSchema,
  date_from: z.string(),
  date_to: z.string(),
  source_kind: z.string().nullable(),
  tz_offset_minutes: z.number(),
  grid: z.array(
    z.object({
      weekday: z.number(),
      hour: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  ),
  weekday_totals: z.array(
    z.object({
      weekday: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  ),
  hour_totals: z.array(
    z.object({
      hour: z.number(),
      value_cents: z.number(),
      count: z.number(),
      value: z.number()
    })
  ),
  grand_total: z.object({
    value_cents: z.number(),
    count: z.number()
  })
});

const PriceIndexResponseSchema = z.object({
  grain: z.string(),
  date_from: z.string(),
  date_to: z.string(),
  points: z.array(
    z.object({
      period: z.string(),
      source_kind: z.string(),
      index: z.number(),
      product_count: z.number()
    })
  )
});

const BasketCompareResponseSchema = z.object({
  net: z.boolean(),
  basket_items: z.array(
    z.object({
      product_id: z.string(),
      quantity: z.number()
    })
  ),
  retailers: z.array(
    z.object({
      source_kind: z.string(),
      total_cents: z.number(),
      covered_items: z.number(),
      missing_items: z.number(),
      coverage_rate: z.number(),
      line_items: z.array(
        z.object({
          product_id: z.string(),
          quantity: z.number(),
          unit_price_cents: z.number().nullable(),
          line_total_cents: z.number().nullable(),
          missing: z.boolean()
        })
      )
    })
  )
});

const PatternsResponseSchema = z.object({
  date_from: z.string(),
  date_to: z.string(),
  shopping_frequency: z.array(
    z.object({
      source_id: z.string(),
      purchase_count: z.number(),
      avg_days_between_shops: z.number().nullable()
    })
  ),
  basket_size_distribution: z.array(
    z.object({
      min_cents: z.number(),
      max_cents: z.number().nullable(),
      count: z.number()
    })
  ),
  impulse_indicator: z.object({
    one_time_items: z.number(),
    unique_items: z.number(),
    one_time_share: z.number()
  }),
  spend_velocity: z.array(
    z.object({
      date: z.string(),
      rolling_7d_cents: z.number(),
      rolling_30d_cents: z.number()
    })
  ),
  seasonal_patterns: z.array(
    z.object({
      month: z.number(),
      avg_spend_cents: z.number(),
      total_spend_cents: z.number()
    })
  )
});

const BudgetRulesResponseSchema = z.object({
  items: z.array(
    z.object({
      rule_id: z.string(),
      scope_type: z.string(),
      scope_value: z.string(),
      period: z.string(),
      amount_cents: z.number(),
      currency: z.string(),
      active: z.boolean(),
      created_at: z.string(),
      updated_at: z.string()
    })
  ),
  count: z.number()
});

const BudgetUtilizationResponseSchema = z.object({
  period: z.object({
    year: z.number(),
    month: z.number()
  }),
  rows: z.array(
    z.object({
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
    })
  ),
  count: z.number()
});

export type HeatmapResponse = z.infer<typeof HeatmapResponseSchema>;
export type TimingValueMode = z.infer<typeof TimingValueModeSchema>;
export type HourHeatmapResponse = z.infer<typeof HourHeatmapResponseSchema>;
export type TimingMatrixResponse = z.infer<typeof TimingMatrixResponseSchema>;
export type PriceIndexResponse = z.infer<typeof PriceIndexResponseSchema>;
export type BasketCompareResponse = z.infer<typeof BasketCompareResponseSchema>;
export type PatternsResponse = z.infer<typeof PatternsResponseSchema>;
export type BudgetRulesResponse = z.infer<typeof BudgetRulesResponseSchema>;
export type BudgetUtilizationResponse = z.infer<typeof BudgetUtilizationResponseSchema>;

export async function fetchWeekdayHeatmap(params?: {
  fromDate?: string;
  toDate?: string;
  value?: TimingValueMode;
  sourceKind?: string;
  tzOffsetMinutes?: number;
}): Promise<HeatmapResponse> {
  return apiClient.get("/api/v1/analytics/heatmap/weekday", HeatmapResponseSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate,
    value: params?.value,
    source_kind: params?.sourceKind,
    tz_offset_minutes: params?.tzOffsetMinutes
  });
}

export async function fetchHourHeatmap(params?: {
  fromDate?: string;
  toDate?: string;
  value?: TimingValueMode;
  sourceKind?: string;
  tzOffsetMinutes?: number;
}): Promise<HourHeatmapResponse> {
  return apiClient.get("/api/v1/analytics/heatmap/hour", HourHeatmapResponseSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate,
    value: params?.value,
    source_kind: params?.sourceKind,
    tz_offset_minutes: params?.tzOffsetMinutes
  });
}

export async function fetchTimingMatrix(params?: {
  fromDate?: string;
  toDate?: string;
  value?: TimingValueMode;
  sourceKind?: string;
  tzOffsetMinutes?: number;
}): Promise<TimingMatrixResponse> {
  return apiClient.get("/api/v1/analytics/heatmap/matrix", TimingMatrixResponseSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate,
    value: params?.value,
    source_kind: params?.sourceKind,
    tz_offset_minutes: params?.tzOffsetMinutes
  });
}

export async function fetchPriceIndex(params?: {
  fromDate?: string;
  toDate?: string;
}): Promise<PriceIndexResponse> {
  return apiClient.get("/api/v1/analytics/price-index", PriceIndexResponseSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate
  });
}

export async function postBasketCompare(payload: {
  items: Array<{ product_id: string; quantity: number }>;
  net?: boolean;
}): Promise<BasketCompareResponse> {
  return apiClient.post("/api/v1/analytics/basket-compare", BasketCompareResponseSchema, payload);
}

export async function fetchPatterns(params?: {
  fromDate?: string;
  toDate?: string;
}): Promise<PatternsResponse> {
  return apiClient.get("/api/v1/analytics/patterns", PatternsResponseSchema, {
    from_date: params?.fromDate,
    to_date: params?.toDate
  });
}

export async function fetchBudgetRules(): Promise<BudgetRulesResponse> {
  return apiClient.get("/api/v1/analytics/budget-rules", BudgetRulesResponseSchema);
}

export async function createBudgetRule(payload: {
  scope_type: "category" | "source_kind";
  scope_value: string;
  period: "monthly" | "annual";
  amount_cents: number;
  currency?: string;
  active?: boolean;
}) {
  const schema = z.object({
    rule_id: z.string(),
    scope_type: z.string(),
    scope_value: z.string(),
    period: z.string(),
    amount_cents: z.number(),
    currency: z.string(),
    active: z.boolean(),
    created_at: z.string(),
    updated_at: z.string()
  });
  return apiClient.post("/api/v1/analytics/budget-rules", schema, payload);
}

export async function fetchBudgetUtilization(params?: {
  year?: number;
  month?: number;
}): Promise<BudgetUtilizationResponse> {
  return apiClient.get("/api/v1/analytics/budget", BudgetUtilizationResponseSchema, {
    year: params?.year === undefined ? undefined : String(params.year),
    month: params?.month === undefined ? undefined : String(params.month)
  });
}
