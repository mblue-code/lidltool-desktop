import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { AISettingsPage } from "../AISettingsPage";

const mocks = vi.hoisted(() => ({
  fetchAISettingsMock: vi.fn(),
  fetchAIOAuthStatusMock: vi.fn(),
  saveAISettingsMock: vi.fn(),
  startAIOAuthMock: vi.fn(),
  disconnectAISettingsMock: vi.fn()
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAISettings: mocks.fetchAISettingsMock,
  fetchAIOAuthStatus: mocks.fetchAIOAuthStatusMock,
  saveAISettings: mocks.saveAISettingsMock,
  startAIOAuth: mocks.startAIOAuthMock,
  disconnectAISettings: mocks.disconnectAISettingsMock
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <AISettingsPage />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AISettingsPage", () => {
  beforeEach(() => {
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
        }
      }
    });
    window.localStorage.setItem("app.locale", "en");
    vi.restoreAllMocks();
    mocks.fetchAISettingsMock.mockResolvedValue({
      enabled: true,
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      api_key_set: true,
      oauth_provider: "openai-codex",
      oauth_connected: true
    });
    mocks.fetchAIOAuthStatusMock.mockResolvedValue({ status: "connected", error: null });
    mocks.saveAISettingsMock.mockResolvedValue({ ok: true, error: null });
    mocks.startAIOAuthMock.mockResolvedValue({ auth_url: "https://example.com/oauth", expires_in: 300 });
    mocks.disconnectAISettingsMock.mockResolvedValue({ ok: true });
    Object.defineProperty(window, "open", {
      configurable: true,
      value: vi.fn()
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders desktop-safe provider controls without OCR settings", async () => {
    renderPage();

    expect(await screen.findByText("AI Assistant")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "OpenAI" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ollama (local)" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sign in with..." })).toBeInTheDocument();
    expect(screen.queryByText("Receipt OCR")).not.toBeInTheDocument();
    expect(screen.queryByText("Save OCR settings")).not.toBeInTheDocument();
  });

  it("saves a custom OpenAI-compatible endpoint", async () => {
    renderPage();

    await screen.findByDisplayValue("gpt-4o-mini");
    fireEvent.change(screen.getByLabelText("Base URL"), {
      target: { value: "https://llm.example.com/v1" }
    });
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: "gpt-4.1-mini" }
    });
    fireEvent.change(screen.getByPlaceholderText("sk-..."), {
      target: { value: "secret-key" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Test & Save" }));

    await waitFor(() => {
      expect(mocks.saveAISettingsMock).toHaveBeenCalledWith({
        base_url: "https://llm.example.com/v1",
        api_key: "secret-key",
        model: "gpt-4.1-mini"
      });
    });
  });
});
