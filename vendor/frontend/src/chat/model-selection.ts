import type { AIAgentConfig } from "@/api/aiSettings";

export const CHAT_PANEL_MODEL_STORAGE_KEY = "agent.chat.model.v1";
export const CHAT_WORKSPACE_MODEL_STORAGE_KEY = "chat.workspace.model-selection.v1";

export function enabledAgentModels(config: AIAgentConfig) {
  return config.available_models.filter((model) => model.enabled);
}

export function resolveAgentModelSelection(
  config: AIAgentConfig,
  requestedModelId?: string | null
): string {
  const enabledModels = enabledAgentModels(config);
  if (requestedModelId && enabledModels.some((model) => model.id === requestedModelId)) {
    return requestedModelId;
  }
  if (enabledModels.some((model) => model.id === config.preferred_model)) {
    return config.preferred_model;
  }
  return enabledModels[0]?.id ?? config.local_model;
}

export function readStoredString(key: string): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStoredString(key: string, value: string): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore localStorage write failures.
  }
}

export function readStoredModelMap(key: string): Record<string, string> {
  const raw = readStoredString(key);
  if (!raw) {
    return {};
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, string] =>
          typeof entry[0] === "string" && typeof entry[1] === "string"
      )
    );
  } catch {
    return {};
  }
}

export function writeStoredModelMap(key: string, value: Record<string, string>): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore localStorage write failures.
  }
}
