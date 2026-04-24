import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const SourceSchema = z.object({
  id: z.string(),
  user_id: z.string().nullable().optional(),
  shared_group_id: z.string().nullable().optional(),
  workspace_kind: z.string().optional(),
  owner_username: z.string().nullable().optional(),
  owner_display_name: z.string().nullable().optional(),
  kind: z.string(),
  display_name: z.string(),
  status: z.string(),
  enabled: z.boolean()
});

const SourcesResponseSchema = z.object({
  sources: z.array(SourceSchema)
});

const SourceWorkspaceResponseSchema = z.object({
  source_id: z.string(),
  user_id: z.string().nullable(),
  shared_group_id: z.string().nullable().optional(),
  workspace_kind: z.enum(["personal", "shared_group"]),
  updated_at: z.string()
});

export type SourcesResponse = z.infer<typeof SourcesResponseSchema>;
export type SourceWorkspaceResponse = z.infer<typeof SourceWorkspaceResponseSchema>;

export async function fetchSources(): Promise<SourcesResponse> {
  return apiClient.get("/api/v1/sources", SourcesResponseSchema);
}

export async function patchSourceWorkspace(
  sourceId: string,
  payload: { workspace_kind: "personal" | "shared_group"; shared_group_id?: string }
): Promise<SourceWorkspaceResponse> {
  return apiClient.patch(`/api/v1/sources/${sourceId}/workspace`, SourceWorkspaceResponseSchema, {
    workspace_kind: payload.workspace_kind,
    shared_group_id: payload.shared_group_id
  });
}
