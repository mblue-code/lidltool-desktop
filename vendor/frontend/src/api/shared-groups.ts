import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const UserDirectoryEntrySchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string().nullable(),
  is_admin: z.boolean(),
  preferred_locale: z.enum(["en", "de"]).nullable().optional().default(null)
});

const SharedGroupMemberSchema = z.object({
  group_id: z.string(),
  user_id: z.string(),
  role: z.enum(["owner", "manager", "member"]),
  membership_status: z.enum(["active", "removed"]),
  joined_at: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  user: UserDirectoryEntrySchema
});

const SharedGroupSchema = z.object({
  group_id: z.string(),
  name: z.string(),
  group_type: z.enum(["household", "community"]),
  status: z.enum(["active", "archived"]),
  created_at: z.string(),
  updated_at: z.string(),
  created_by_user: UserDirectoryEntrySchema.nullable(),
  viewer_role: z.enum(["owner", "manager", "member"]).nullable(),
  viewer_membership_status: z.enum(["active", "removed"]).nullable(),
  can_manage: z.boolean(),
  owner_count: z.number(),
  member_count: z.number(),
  members: z.array(SharedGroupMemberSchema).default([])
});

const SharedGroupsListSchema = z.object({
  groups: z.array(SharedGroupSchema),
  count: z.number()
});

const SharedGroupUserDirectorySchema = z.object({
  users: z.array(UserDirectoryEntrySchema),
  count: z.number()
});

export type SharedGroup = z.infer<typeof SharedGroupSchema>;
export type SharedGroupMember = z.infer<typeof SharedGroupMemberSchema>;
export type SharedGroupUserDirectoryEntry = z.infer<typeof UserDirectoryEntrySchema>;

export async function fetchSharedGroups(): Promise<{ groups: SharedGroup[]; count: number }> {
  return apiClient.get("/api/v1/shared-groups", SharedGroupsListSchema);
}

export async function createSharedGroup(payload: {
  name: string;
  group_type: "household" | "community";
}): Promise<SharedGroup> {
  return apiClient.post("/api/v1/shared-groups", SharedGroupSchema, payload);
}

export async function updateSharedGroup(
  groupId: string,
  payload: {
    name?: string;
    group_type?: "household" | "community";
    status?: "active" | "archived";
  }
): Promise<SharedGroup> {
  return apiClient.patch(`/api/v1/shared-groups/${groupId}`, SharedGroupSchema, payload);
}

export async function fetchSharedGroupUserDirectory(): Promise<{
  users: SharedGroupUserDirectoryEntry[];
  count: number;
}> {
  return apiClient.get("/api/v1/shared-groups/user-directory", SharedGroupUserDirectorySchema);
}

export async function addSharedGroupMember(
  groupId: string,
  payload: {
    user_id: string;
    role: "owner" | "manager" | "member";
  }
): Promise<SharedGroup> {
  return apiClient.post(`/api/v1/shared-groups/${groupId}/members`, SharedGroupSchema, payload);
}

export async function updateSharedGroupMember(
  groupId: string,
  userId: string,
  payload: {
    role?: "owner" | "manager" | "member";
    membership_status?: "active" | "removed";
  }
): Promise<SharedGroup> {
  return apiClient.patch(`/api/v1/shared-groups/${groupId}/members/${userId}`, SharedGroupSchema, payload);
}

export async function removeSharedGroupMember(groupId: string, userId: string): Promise<SharedGroup> {
  return apiClient.delete(`/api/v1/shared-groups/${groupId}/members/${userId}`, SharedGroupSchema);
}
