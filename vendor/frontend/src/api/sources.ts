import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const SourceSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable().optional(),
  owner_username: z.string().nullable().optional(),
  owner_display_name: z.string().nullable().optional(),
  kind: z.string(),
  display_name: z.string(),
  status: z.string(),
  enabled: z.boolean(),
  family_share_mode: z.enum(["all", "manual", "none"]).optional()
});

const SourcesResponseSchema = z.object({
  sources: z.array(SourceSchema)
});

const SourceSharingResponseSchema = z.object({
  source_id: z.string(),
  user_id: z.string().nullable(),
  family_share_mode: z.enum(["all", "manual", "none"]),
  updated_at: z.string()
});

export type SourcesResponse = z.infer<typeof SourcesResponseSchema>;
export type SourceSharingResponse = z.infer<typeof SourceSharingResponseSchema>;

export async function fetchSources(): Promise<SourcesResponse> {
  return apiClient.get("/api/v1/sources", SourcesResponseSchema);
}

export async function patchSourceSharing(
  sourceId: string,
  familyShareMode: "all" | "manual" | "none"
): Promise<SourceSharingResponse> {
  return apiClient.patch(`/api/v1/sources/${sourceId}/sharing`, SourceSharingResponseSchema, {
    family_share_mode: familyShareMode
  });
}
