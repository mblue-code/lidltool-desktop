import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const MerchantSummarySchema = z.object({
  merchant: z.string(),
  receipt_count: z.number(),
  spend_cents: z.number(),
  last_purchased_at: z.string().nullable(),
  source_ids: z.array(z.string()),
  dominant_category: z.string().nullable().optional()
});

const MerchantSummaryResponseSchema = z.object({
  period: z.object({
    from_date: z.string(),
    to_date: z.string()
  }),
  count: z.number(),
  items: z.array(MerchantSummarySchema)
});

export type MerchantSummary = z.infer<typeof MerchantSummarySchema>;
export type MerchantSummaryResponse = z.infer<typeof MerchantSummaryResponseSchema>;

export async function fetchMerchantSummary(
  fromDate: string,
  toDate: string,
  search?: string
): Promise<MerchantSummaryResponse> {
  return apiClient.get("/api/v1/merchants/summary", MerchantSummaryResponseSchema, {
    from_date: fromDate,
    to_date: toDate,
    search
  });
}
