import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const SetupRequiredSchema = z.object({ required: z.boolean() });

const AuthResultSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string().nullable(),
  is_admin: z.boolean()
});

const LogoutSchema = z.object({ logged_out: z.boolean() });

export type AuthResult = z.infer<typeof AuthResultSchema>;

export async function checkSetupRequired(): Promise<boolean> {
  const result = await apiClient.get("/api/v1/auth/setup-required", SetupRequiredSchema);
  return result.required;
}

export async function login(username: string, password: string): Promise<AuthResult> {
  return apiClient.post("/api/v1/auth/login", AuthResultSchema, { username, password });
}

export async function setup(
  username: string,
  password: string,
  displayName?: string
): Promise<AuthResult> {
  return apiClient.post("/api/v1/auth/setup", AuthResultSchema, {
    username,
    password,
    display_name: displayName || null
  });
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout", LogoutSchema);
}
