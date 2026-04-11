import { z } from "zod";

import { apiClient } from "@/lib/api-client";
import { notifySessionChanged } from "@/i18n";

const SetupRequiredSchema = z.object({
  required: z.boolean(),
  bootstrap_token_required: z.boolean().optional().default(false)
});

const AuthResultSchema = z.object({
  user_id: z.string(),
  username: z.string(),
  display_name: z.string().nullable(),
  is_admin: z.boolean(),
  preferred_locale: z.enum(["en", "de"]).nullable().optional().default(null)
});

const LogoutSchema = z.object({ logged_out: z.boolean() });

export type AuthResult = z.infer<typeof AuthResultSchema>;
export type SetupStatus = z.infer<typeof SetupRequiredSchema>;

export async function checkSetupRequired(): Promise<boolean> {
  const result = await getSetupStatus();
  return result.required;
}

export async function getSetupStatus(): Promise<SetupStatus> {
  const result = await apiClient.get("/api/v1/auth/setup-required", SetupRequiredSchema);
  return result;
}

export async function login(username: string, password: string): Promise<AuthResult> {
  const result = await apiClient.post("/api/v1/auth/login", AuthResultSchema, { username, password });
  notifySessionChanged();
  return result;
}

export async function setup(
  username: string,
  password: string,
  displayName?: string,
  bootstrapToken?: string
): Promise<AuthResult> {
  const result = await apiClient.post("/api/v1/auth/setup", AuthResultSchema, {
    username,
    password,
    display_name: displayName || null,
    bootstrap_token: bootstrapToken || null
  });
  notifySessionChanged();
  return result;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout", LogoutSchema);
  notifySessionChanged();
}
