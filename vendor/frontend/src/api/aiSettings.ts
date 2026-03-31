import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const AISettingsSchema = z.object({
  enabled: z.boolean(),
  base_url: z.string().nullable(),
  model: z.string(),
  api_key_set: z.boolean(),
  oauth_provider: z.string().nullable(),
  oauth_connected: z.boolean()
});

const SaveAISettingsSchema = z.object({
  ok: z.boolean(),
  error: z.string().nullable()
});

const StartAIOAuthSchema = z.object({
  auth_url: z.string(),
  expires_in: z.number()
});

const AIOAuthStatusSchema = z.object({
  status: z.enum(["pending", "connected", "error"]),
  error: z.string().nullable()
});

const AIAgentConfigSchema = z.object({
  proxy_url: z.string(),
  auth_token: z.string(),
  model: z.string(),
  default_model: z.string(),
  local_model: z.string(),
  preferred_model: z.string(),
  oauth_provider: z.string().nullable(),
  oauth_connected: z.boolean(),
  available_models: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      source: z.enum(["local", "oauth"]),
      enabled: z.boolean()
    })
  )
});

const DisconnectAISettingsSchema = z.object({
  ok: z.boolean()
});

export type AISettings = z.infer<typeof AISettingsSchema>;
export type SaveAISettingsResult = z.infer<typeof SaveAISettingsSchema>;
export type StartAIOAuthResult = z.infer<typeof StartAIOAuthSchema>;
export type AIOAuthStatus = z.infer<typeof AIOAuthStatusSchema>;
export type AIAgentConfig = z.infer<typeof AIAgentConfigSchema>;
export type DisconnectAISettingsResult = z.infer<typeof DisconnectAISettingsSchema>;

export async function fetchAISettings(): Promise<AISettings> {
  return apiClient.get("/api/v1/settings/ai", AISettingsSchema);
}

export async function saveAISettings(payload: {
  base_url: string;
  api_key?: string;
  model: string;
}): Promise<SaveAISettingsResult> {
  return apiClient.post("/api/v1/settings/ai", SaveAISettingsSchema, payload);
}

export async function startAIOAuth(payload: {
  provider: "openai-codex" | "github-copilot" | "google-gemini-cli";
}): Promise<StartAIOAuthResult> {
  return apiClient.post("/api/v1/settings/ai/oauth/start", StartAIOAuthSchema, payload);
}

export async function fetchAIOAuthStatus(): Promise<AIOAuthStatus> {
  return apiClient.get("/api/v1/settings/ai/oauth/status", AIOAuthStatusSchema);
}

export async function fetchAIAgentConfig(): Promise<AIAgentConfig> {
  return apiClient.get("/api/v1/settings/ai/agent-config", AIAgentConfigSchema);
}

export async function disconnectAISettings(): Promise<DisconnectAISettingsResult> {
  return apiClient.post("/api/v1/settings/ai/disconnect", DisconnectAISettingsSchema);
}
