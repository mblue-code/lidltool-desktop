import type * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";

import { I18nProvider } from "@/i18n";
import { AISettingsPage } from "../AISettingsPage";

const mocks = vi.hoisted(() => ({
  fetchAISettingsMock: vi.fn(),
  fetchOCRSettingsMock: vi.fn(),
  fetchAIOAuthStatusMock: vi.fn(),
  saveAISettingsMock: vi.fn(),
  saveAIChatSettingsMock: vi.fn(),
  saveAICategorizationSettingsMock: vi.fn(),
  saveOCRSettingsMock: vi.fn(),
  startAIOAuthMock: vi.fn(),
  disconnectAISettingsMock: vi.fn(),
  fetchAIAgentConfigMock: vi.fn()
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAISettings: mocks.fetchAISettingsMock,
  fetchAIOAuthStatus: mocks.fetchAIOAuthStatusMock,
  saveAISettings: mocks.saveAISettingsMock,
  saveAIChatSettings: mocks.saveAIChatSettingsMock,
  saveAICategorizationSettings: mocks.saveAICategorizationSettingsMock,
  startAIOAuth: mocks.startAIOAuthMock,
  disconnectAISettings: mocks.disconnectAISettingsMock,
  fetchAIAgentConfig: mocks.fetchAIAgentConfigMock
}));

vi.mock("@/api/ocrSettings", () => ({
  fetchOCRSettings: mocks.fetchOCRSettingsMock,
  saveOCRSettings: mocks.saveOCRSettingsMock
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

vi.mock("@/api/users", () => ({
  fetchCurrentUser: vi.fn(async () => ({
    user_id: "u1",
    username: "alice",
    display_name: null,
    is_admin: false,
    preferred_locale: null
  })),
  updateCurrentUserLocale: vi.fn()
}));

function renderPage(ui: React.JSX.Element): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>{ui}</I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AISettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const storage = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
        removeItem: (key: string) => {
          storage.delete(key);
        },
        clear: () => {
          storage.clear();
        }
      }
    });

    mocks.fetchAISettingsMock.mockResolvedValue({
      enabled: true,
      base_url: "https://api.x.ai/v1",
      model: "grok-3-mini",
      api_key_set: true,
      oauth_provider: "openai-codex",
      oauth_model: "gpt-5.4-mini",
      remote_enabled: true,
      local_runtime_enabled: true,
      local_runtime_ready: true,
      local_runtime_status: "ready",
      categorization_enabled: true,
      categorization_provider: "api_compatible",
      categorization_base_url: "https://categorization.example/v1",
      categorization_api_key_set: true,
      categorization_model: "mistral-small",
      categorization_runtime_ready: true,
      categorization_runtime_status: "ready"
    });

    mocks.fetchOCRSettingsMock.mockResolvedValue({
      default_provider: "glm_ocr_local",
      fallback_enabled: false,
      fallback_provider: "openai_compatible",
      glm_local_base_url: "",
      glm_local_api_mode: "openai_chat_completion",
      glm_local_model: "glm-ocr",
      openai_base_url: "",
      openai_model: "",
      openai_credentials_ready: false
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders saved categorization runtime state and keeps chat and categorization model selectors separate", async () => {
    renderPage(<AISettingsPage />);

    expect(await screen.findByText("Item categorization")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connect ChatGPT / Codex" })).toBeInTheDocument();

    const oauthTab = screen.getByRole("tab", { name: "ChatGPT / Codex" });
    fireEvent.mouseDown(oauthTab);
    fireEvent.click(oauthTab);

    await waitFor(() => {
      expect(document.getElementById("oauth-chat-model")).not.toBeNull();
    });

    expect((document.getElementById("oauth-chat-model") as HTMLSelectElement).value).toBe("gpt-5.4-mini");
    expect((document.getElementById("categorization-provider") as HTMLSelectElement).value).toBe("api_compatible");
    expect((document.getElementById("categorization-api-base-url") as HTMLInputElement).value).toBe(
      "https://categorization.example/v1"
    );
    expect((document.getElementById("categorization-api-model") as HTMLInputElement).value).toBe("mistral-small");
  });

  it("localizes AI save feedback and categorization runtime status in German", async () => {
    window.localStorage.setItem("app.locale", "de");
    mocks.saveAISettingsMock.mockResolvedValue({ ok: true });
    mocks.saveAIChatSettingsMock.mockResolvedValue({ ok: true });
    mocks.saveAICategorizationSettingsMock.mockResolvedValue({ ok: false, error: null });

    renderPage(<AISettingsPage />);

    expect(await screen.findByText("Artikelkategorisierung")).toBeInTheDocument();
    expect(screen.getByText("Kategorisierungsstatus")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Chatmodell speichern" }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith("Chatmodell gespeichert");
    });

    fireEvent.click(screen.getByRole("button", { name: /Kategorisierung .* speichern/i }));

    expect(await screen.findByText("Kategorisierungseinstellungen konnten nicht gespeichert werden")).toBeInTheDocument();
  });
});
