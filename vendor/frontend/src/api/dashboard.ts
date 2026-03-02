import { z } from "zod";

import { apiClient } from "@/lib/api-client";

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

export type DashboardCardsResponse = z.infer<typeof DashboardCardsResponseSchema>;
export type DashboardTrendsResponse = z.infer<typeof DashboardTrendsResponseSchema>;
export type SavingsBreakdownResponse = z.infer<typeof SavingsBreakdownResponseSchema>;
export type RetailerCompositionResponse = z.infer<typeof RetailerCompositionResponseSchema>;
export type DashboardResponseWithWarnings<T> = {
  result: T;
  warnings: string[];
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
