import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const GroceryTransactionSchema = z.object({
  id: z.string(),
  purchased_at: z.string(),
  source_id: z.string(),
  store_name: z.string().nullable(),
  total_gross_cents: z.number()
}).passthrough();

const GroceriesSummarySchema = z.object({
  period: z.object({
    from_date: z.string(),
    to_date: z.string()
  }),
  totals: z.object({
    spend_cents: z.number(),
    receipt_count: z.number(),
    average_basket_cents: z.number(),
    merchant_count: z.number()
  }),
  category_breakdown: z.array(
    z.object({
      category: z.string(),
      amount_cents: z.number()
    })
  ),
  recent_transactions: z.array(GroceryTransactionSchema)
});

export type GroceriesSummary = z.infer<typeof GroceriesSummarySchema>;

export async function fetchGroceriesSummary(fromDate: string, toDate: string): Promise<GroceriesSummary> {
  return apiClient.get("/api/v1/groceries/summary", GroceriesSummarySchema, {
    from_date: fromDate,
    to_date: toDate
  });
}
