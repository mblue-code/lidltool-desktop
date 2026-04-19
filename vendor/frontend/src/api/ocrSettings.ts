import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const OCRProviderSchema = z.enum(["desktop_local", "glm_ocr_local", "openai_compatible", "external_api"]);

const OCRSettingsSchema = z.object({
  default_provider: OCRProviderSchema,
  fallback_enabled: z.boolean(),
  fallback_provider: OCRProviderSchema.nullable(),
  glm_local_base_url: z.string().nullable(),
  glm_local_api_mode: z.enum(["ollama_generate", "openai_chat_completion"]),
  glm_local_model: z.string(),
  openai_base_url: z.string().nullable(),
  openai_model: z.string().nullable(),
  openai_credentials_ready: z.boolean()
});

const SaveOCRSettingsSchema = z.object({
  ok: z.boolean(),
  error: z.string().nullable()
});

export type OCRSettings = z.infer<typeof OCRSettingsSchema>;
export type OCRProvider = z.infer<typeof OCRProviderSchema>;
export type SaveOCRSettingsResult = z.infer<typeof SaveOCRSettingsSchema>;

export async function fetchOCRSettings(): Promise<OCRSettings> {
  return apiClient.get("/api/v1/settings/ocr", OCRSettingsSchema);
}

export async function saveOCRSettings(payload: {
  default_provider: OCRProvider;
  fallback_enabled: boolean;
  fallback_provider?: OCRProvider;
  glm_local_base_url: string;
  glm_local_api_mode: "ollama_generate" | "openai_chat_completion";
  glm_local_model: string;
  openai_base_url?: string;
  openai_model?: string;
}): Promise<SaveOCRSettingsResult> {
  return apiClient.post("/api/v1/settings/ocr", SaveOCRSettingsSchema, payload);
}
