import { z } from "zod";

import { apiClient } from "@/lib/api-client";
import type { ApiWarning } from "@/lib/api-messages";

const DashboardCardsResponseSchema = z.object({
  totals: z.object({
    receipt_count: z.number(),
    gross_cents: z.number(),
    gross_currency: z.string(),
    net_cents: z.number().optional(),
    net_currency: z.string().optional(),
    discount_total_cents: z.number().optional(),
    discount_total_currency: z.string().optional(),
    paid_cents: z.number(),
    paid_currency: z.string(),
    saved_cents: z.number(),
    saved_currency: z.string(),
    savings_rate: z.number()
  })
});

const DashboardTrendsResponseSchema = z.object({
  points: z.array(
    z.object({
      year: z.number(),
      month: z.number(),
      period_key: z.string(),
      gross_cents: z.number().optional(),
      net_cents: z.number().optional(),
      discount_total_cents: z.number().optional(),
      paid_cents: z.number(),
      saved_cents: z.number(),
      savings_rate: z.number()
    })
  )
});

const SavingsBreakdownResponseSchema = z.object({
  view: z.enum(["native", "normalized"]),
  by_type: z.array(
    z.object({
      type: z.string(),
      saved_cents: z.number(),
      saved_currency: z.string(),
      discount_events: z.number()
    })
  )
});

const RetailerCompositionResponseSchema = z.object({
  retailers: z.array(
    z.object({
      source_id: z.string(),
      retailer: z.string(),
      receipt_count: z.number().optional(),
      gross_cents: z.number().optional(),
      net_cents: z.number().optional(),
      discount_total_cents: z.number().optional(),
      paid_cents: z.number(),
      saved_cents: z.number(),
      gross_share: z.number().optional(),
      net_share: z.number().optional(),
      paid_share: z.number(),
      saved_share: z.number(),
      savings_rate: z.number()
    })
  )
});

const DashboardOverviewResponseSchema = z.object({
  period: z.object({
    from_date: z.string(),
    to_date: z.string(),
    comparison_from_date: z.string(),
    comparison_to_date: z.string(),
    days: z.number()
  }),
  source_filters: z.array(
    z.object({
      source_id: z.string(),
      label: z.string(),
      transaction_count: z.number()
    })
  ),
  selected_source_ids: z.array(z.string()),
  kpis: z.object({
    total_spending: z.object({
      current_cents: z.number(),
      previous_cents: z.number(),
      delta_cents: z.number(),
      delta_pct: z.number().nullable()
    }),
    groceries: z.object({
      current_cents: z.number(),
      previous_cents: z.number(),
      delta_cents: z.number(),
      delta_pct: z.number().nullable()
    }),
    cash_inflow: z.object({
      current_cents: z.number(),
      previous_cents: z.number(),
      delta_cents: z.number(),
      delta_pct: z.number().nullable()
    }),
    cash_outflow: z.object({
      current_cents: z.number(),
      previous_cents: z.number(),
      delta_cents: z.number(),
      delta_pct: z.number().nullable()
    })
  }),
  spending_overview: z.object({
    total_cents: z.number(),
    categories: z.array(
      z.object({
        category: z.string(),
        amount_cents: z.number(),
        share: z.number()
      })
    )
  }),
  cash_flow_summary: z.object({
    totals: z.object({
      inflow_cents: z.number(),
      outflow_cents: z.number(),
      net_cents: z.number()
    }),
    points: z.array(
      z.object({
        date: z.string(),
        inflow_cents: z.number(),
        outflow_cents: z.number(),
        net_cents: z.number()
      })
    )
  }),
  upcoming_bills: z.object({
    count: z.number(),
    total_expected_cents: z.number(),
    items: z.array(
      z.object({
        occurrence_id: z.string(),
        bill_id: z.string(),
        bill_name: z.string(),
        status: z.string(),
        due_date: z.string(),
        expected_amount_cents: z.number().nullable()
      })
    )
  }),
  recent_grocery_transactions: z.object({
    count: z.number(),
    total_cents: z.number(),
    average_basket_cents: z.number(),
    items: z.array(
      z.object({
        id: z.string(),
        purchased_at: z.string(),
        source_id: z.string(),
        store_name: z.string().nullable(),
        total_gross_cents: z.number()
      }).passthrough()
    )
  }),
  budget_progress: z.object({
    count: z.number(),
    items: z.array(
      z.object({
        rule_id: z.string(),
        scope_type: z.string(),
        scope_value: z.string(),
        budget_cents: z.number(),
        spent_cents: z.number(),
        remaining_cents: z.number(),
        utilization: z.number(),
        projected_utilization: z.number(),
        over_budget: z.boolean(),
        projected_over_budget: z.boolean()
      })
    )
  }),
  recent_activity: z.object({
    count: z.number(),
    items: z.array(
      z.object({
        id: z.string(),
        kind: z.string(),
        title: z.string(),
        subtitle: z.string(),
        amount_cents: z.number(),
        occurred_at: z.string(),
        href: z.string()
      })
    )
  }),
  insight: z.object({
    kind: z.string(),
    title: z.string(),
    body: z.string(),
    delta_cents: z.number(),
    delta_pct: z.number(),
    href: z.string()
  }),
  merchants: z.object({
    count: z.number(),
    items: z.array(
      z.object({
        source_id: z.string().optional(),
        merchant: z.string(),
        receipt_count: z.number(),
        spend_cents: z.number(),
        last_purchased_at: z.string().nullable()
      })
    )
  }),
  top_goals: z
    .object({
      count: z.number(),
      items: z.array(
        z.object({
          id: z.string(),
          name: z.string(),
          goal_type: z.string(),
          target_amount_cents: z.number(),
          target_date: z.string().nullable(),
          progress: z.object({
            current_amount_cents: z.number(),
            target_amount_cents: z.number(),
            remaining_amount_cents: z.number(),
            progress_ratio: z.number(),
            status: z.string()
          })
        }).passthrough()
      )
    })
    .optional()
});

export type DashboardCardsResponse = z.infer<typeof DashboardCardsResponseSchema>;
export type DashboardTrendsResponse = z.infer<typeof DashboardTrendsResponseSchema>;
export type SavingsBreakdownResponse = z.infer<typeof SavingsBreakdownResponseSchema>;
export type RetailerCompositionResponse = z.infer<typeof RetailerCompositionResponseSchema>;
export type DashboardOverviewResponse = z.infer<typeof DashboardOverviewResponseSchema>;
export type DashboardResponseWithWarnings<T> = {
  result: T;
  warnings: ApiWarning[];
};

function sourceIdsParam(sourceIds?: string[]): string | undefined {
  if (!sourceIds || sourceIds.length === 0) {
    return undefined;
  }
  const normalized = Array.from(new Set(sourceIds.map((value) => value.trim()).filter(Boolean)));
  return normalized.length > 0 ? normalized.join(",") : undefined;
}

export async function fetchDashboardCardsWithWarnings(
  year: number,
  month?: number,
  sourceIds?: string[]
): Promise<DashboardResponseWithWarnings<DashboardCardsResponse>> {
  return apiClient.getWithWarnings("/api/v1/dashboard/cards", DashboardCardsResponseSchema, {
    year: String(year),
    month: month === undefined ? undefined : String(month),
    source_ids: sourceIdsParam(sourceIds)
  });
}

export async function fetchDashboardCards(
  year: number,
  month?: number,
  sourceIds?: string[]
): Promise<DashboardCardsResponse> {
  const { result } = await fetchDashboardCardsWithWarnings(year, month, sourceIds);
  return result;
}

export async function fetchDashboardTrendsWithWarnings(
  year: number,
  monthsBack: number,
  endMonth: number,
  sourceIds?: string[]
): Promise<DashboardResponseWithWarnings<DashboardTrendsResponse>> {
  return apiClient.getWithWarnings("/api/v1/dashboard/trends", DashboardTrendsResponseSchema, {
    year: String(year),
    months_back: String(monthsBack),
    end_month: String(endMonth),
    source_ids: sourceIdsParam(sourceIds)
  });
}

export async function fetchDashboardTrends(
  year: number,
  monthsBack: number,
  endMonth: number,
  sourceIds?: string[]
): Promise<DashboardTrendsResponse> {
  const { result } = await fetchDashboardTrendsWithWarnings(year, monthsBack, endMonth, sourceIds);
  return result;
}

export async function fetchSavingsBreakdownWithWarnings(
  year: number,
  month: number | undefined,
  view: "native" | "normalized",
  sourceIds?: string[]
): Promise<DashboardResponseWithWarnings<SavingsBreakdownResponse>> {
  return apiClient.getWithWarnings("/api/v1/dashboard/savings-breakdown", SavingsBreakdownResponseSchema, {
    year: String(year),
    month: month === undefined ? undefined : String(month),
    view,
    source_ids: sourceIdsParam(sourceIds)
  });
}

export async function fetchSavingsBreakdown(
  year: number,
  month: number | undefined,
  view: "native" | "normalized",
  sourceIds?: string[]
): Promise<SavingsBreakdownResponse> {
  const { result } = await fetchSavingsBreakdownWithWarnings(year, month, view, sourceIds);
  return result;
}

export async function fetchRetailerCompositionWithWarnings(
  year: number,
  month?: number,
  sourceIds?: string[]
): Promise<DashboardResponseWithWarnings<RetailerCompositionResponse>> {
  return apiClient.getWithWarnings("/api/v1/dashboard/retailer-composition", RetailerCompositionResponseSchema, {
    year: String(year),
    month: month === undefined ? undefined : String(month),
    source_ids: sourceIdsParam(sourceIds)
  });
}

export async function fetchRetailerComposition(
  year: number,
  month?: number,
  sourceIds?: string[]
): Promise<RetailerCompositionResponse> {
  const { result } = await fetchRetailerCompositionWithWarnings(year, month, sourceIds);
  return result;
}

export async function fetchDashboardOverview(
  fromDate: string,
  toDate: string,
  sourceIds?: string[]
): Promise<DashboardOverviewResponse> {
  return apiClient.get("/api/v1/dashboard/overview", DashboardOverviewResponseSchema, {
    from_date: fromDate,
    to_date: toDate,
    source_ids: sourceIdsParam(sourceIds)
  });
}
