import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const CurrentUserSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string().nullable(),
  is_admin: z.boolean()
});

const UserSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string().nullable(),
  is_admin: z.boolean(),
  created_at: z.string(),
  updated_at: z.string()
});

const UsersListSchema = z.object({
  users: z.array(UserSchema),
  count: z.number()
});

const AgentKeySchema = z.object({
  key_id: z.string(),
  user_id: z.string(),
  label: z.string(),
  key_prefix: z.string(),
  is_active: z.boolean(),
  last_used_at: z.string().nullable(),
  expires_at: z.string().nullable(),
  created_at: z.string()
});

const AgentKeysListSchema = z.object({
  keys: z.array(AgentKeySchema),
  count: z.number()
});

const AgentKeyCreateSchema = z.object({
  api_key: z.string(),
  key: AgentKeySchema
});

const AgentKeyRevokeSchema = z.object({
  key_id: z.string(),
  revoked: z.boolean()
});

export type CurrentUser = z.infer<typeof CurrentUserSchema>;
export type User = z.infer<typeof UserSchema>;
export type UsersList = z.infer<typeof UsersListSchema>;
export type AgentKey = z.infer<typeof AgentKeySchema>;
export type AgentKeysList = z.infer<typeof AgentKeysListSchema>;
export type AgentKeyCreateResponse = z.infer<typeof AgentKeyCreateSchema>;

export async function fetchCurrentUser(): Promise<CurrentUser> {
  return apiClient.get("/api/v1/auth/me", CurrentUserSchema);
}

export async function fetchUsers(): Promise<UsersList> {
  return apiClient.get("/api/v1/users", UsersListSchema);
}

export async function createUser(payload: {
  username: string;
  display_name?: string | null;
  password: string;
  is_admin: boolean;
}): Promise<User> {
  return apiClient.post("/api/v1/users", UserSchema, payload);
}

export async function updateUser(
  userId: string,
  payload: {
    display_name?: string | null;
    password?: string;
    is_admin?: boolean;
  }
): Promise<User> {
  return apiClient.patch(`/api/v1/users/${userId}`, UserSchema, payload);
}

export async function deleteUser(userId: string): Promise<{ user_id: string; deleted: boolean }> {
  const schema = z.object({ user_id: z.string(), deleted: z.boolean() });
  return apiClient.delete(`/api/v1/users/${userId}`, schema);
}

export async function fetchAgentKeys(): Promise<AgentKeysList> {
  return apiClient.get("/api/v1/auth/keys", AgentKeysListSchema);
}

export async function createAgentKey(payload: {
  label: string;
  expires_at?: string;
}): Promise<AgentKeyCreateResponse> {
  return apiClient.post("/api/v1/auth/keys", AgentKeyCreateSchema, payload);
}

export async function revokeAgentKey(keyId: string): Promise<{ key_id: string; revoked: boolean }> {
  return apiClient.delete(`/api/v1/auth/keys/${keyId}`, AgentKeyRevokeSchema);
}
