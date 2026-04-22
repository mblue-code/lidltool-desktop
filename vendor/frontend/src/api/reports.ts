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

export type ReportTemplate = z.infer<typeof ReportTemplateSchema>;
export type ReportTemplatesResponse = z.infer<typeof ReportTemplatesSchema>;

export async function fetchReportTemplates(
  fromDate: string,
  toDate: string
): Promise<ReportTemplatesResponse> {
  return apiClient.get("/api/v1/reports/templates", ReportTemplatesSchema, {
    from_date: fromDate,
    to_date: toDate
  });
}
