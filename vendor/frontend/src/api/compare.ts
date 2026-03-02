import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const CompareGroupsResponseSchema = z.object({
  items: z.array(
    z.object({
      group_id: z.string(),
      name: z.string(),
      unit_standard: z.string().nullable(),
      notes: z.string().nullable(),
      member_count: z.number(),
      created_at: z.string()
    })
  ),
  count: z.number()
});

const CompareGroupResponseSchema = z.object({
  group_id: z.string(),
  name: z.string(),
  unit_standard: z.string().nullable(),
  notes: z.string().nullable(),
  created_at: z.string()
});

const CompareGroupMemberResponseSchema = z.object({
  group_id: z.string(),
  product_id: z.string(),
  weight: z.number().nullable()
});

const CompareGroupSeriesResponseSchema = z.object({
  group: z.object({
    group_id: z.string(),
    name: z.string(),
    unit_standard: z.string().nullable()
  }),
  net: z.boolean(),
  grain: z.string(),
  points: z.array(
    z.object({
      period: z.string(),
      source_kind: z.string(),
      product_id: z.string().nullable(),
      product_name: z.string().nullable(),
      unit_price_cents: z.number(),
      purchase_count: z.number()
    })
  )
});

export type CompareGroupsResponse = z.infer<typeof CompareGroupsResponseSchema>;
export type CompareGroupResponse = z.infer<typeof CompareGroupResponseSchema>;
export type CompareGroupMemberResponse = z.infer<typeof CompareGroupMemberResponseSchema>;
export type CompareGroupSeriesResponse = z.infer<typeof CompareGroupSeriesResponseSchema>;

export async function fetchCompareGroups(): Promise<CompareGroupsResponse> {
  return apiClient.get("/api/v1/compare/groups", CompareGroupsResponseSchema);
}

export async function createCompareGroup(payload: {
  name: string;
  unit_standard?: string;
  notes?: string;
}): Promise<CompareGroupResponse> {
  return apiClient.post("/api/v1/compare/groups", CompareGroupResponseSchema, payload);
}

export async function addCompareGroupMember(
  groupId: string,
  payload: { product_id: string; weight?: number }
): Promise<CompareGroupMemberResponse> {
  return apiClient.post(`/api/v1/compare/groups/${groupId}/members`, CompareGroupMemberResponseSchema, payload);
}

export async function fetchCompareGroupSeries(params: {
  groupId: string;
  fromDate?: string;
  toDate?: string;
  grain?: "day" | "month" | "year";
  net?: boolean;
}): Promise<CompareGroupSeriesResponse> {
  return apiClient.get(
    `/api/v1/compare/groups/${params.groupId}/series`,
    CompareGroupSeriesResponseSchema,
    {
      from_date: params.fromDate,
      to_date: params.toDate,
      grain: params.grain,
      net: params.net === undefined ? undefined : String(params.net)
    }
  );
}
