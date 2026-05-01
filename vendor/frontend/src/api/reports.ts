import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const ReportTemplateSchema = z.object({
  slug: z.string(),
  title: z.string(),
  description: z.string(),
  format: z.string(),
  payload: z.unknown()
});

const ReportTemplatesSchema = z.object({
  period: z.object({
    from_date: z.string(),
    to_date: z.string()
  }),
  count: z.number(),
  templates: z.array(ReportTemplateSchema)
});

const ReportPatternsSchema = z.object({
  period: z.object({ from_date: z.string(), to_date: z.string() }),
  value_mode: z.string(),
  daily_heatmap: z.array(z.object({ date: z.string(), amount_cents: z.number(), count: z.number() })),
  weekday_hour_matrix: z.array(z.object({ weekday: z.number(), hour: z.number(), amount_cents: z.number(), count: z.number() })),
  merchant_profiles: z.array(z.object({ merchant: z.string(), amount_cents: z.number(), count: z.number(), average_cents: z.number() })),
  merchant_comparison: z.array(z.object({ merchant: z.string(), amount_cents: z.number(), count: z.number(), average_cents: z.number() })),
  insights: z.array(z.record(z.string(), z.unknown()))
});

export type ReportTemplate = z.infer<typeof ReportTemplateSchema>;
export type ReportTemplatesResponse = z.infer<typeof ReportTemplatesSchema>;
export type ReportPatternsResponse = z.infer<typeof ReportPatternsSchema>;

export async function fetchReportTemplates(
  fromDate: string,
  toDate: string
): Promise<ReportTemplatesResponse> {
  return apiClient.get("/api/v1/reports/templates", ReportTemplatesSchema, {
    from_date: fromDate,
    to_date: toDate
  });
}

export async function fetchReportPatterns(filters: {
  fromDate: string;
  toDate: string;
  merchants?: string[];
  financeCategoryId?: string;
  direction?: string;
  sourceId?: string;
  valueMode?: string;
}): Promise<ReportPatternsResponse> {
  return apiClient.get("/api/v1/reports/patterns", ReportPatternsSchema, {
    from_date: filters.fromDate,
    to_date: filters.toDate,
    merchants: filters.merchants && filters.merchants.length > 0 ? filters.merchants.slice(0, 2).join(",") : undefined,
    finance_category_id: filters.financeCategoryId,
    direction: filters.direction,
    source_id: filters.sourceId,
    value_mode: filters.valueMode
  });
}
