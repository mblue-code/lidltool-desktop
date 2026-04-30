import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { IngestionPage } from "../IngestionPage";

vi.mock("@/api/aiSettings", () => ({
  fetchAIAgentConfig: vi.fn(async () => ({
    proxy_url: "/api/v1/ai/proxy",
    auth_token: "test-token",
    model: "gpt-test",
    default_model: "gpt-test",
    local_model: "gpt-test",
    preferred_model: "gpt-test",
    oauth_provider: null,
    oauth_connected: false,
    available_models: []
  }))
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <MemoryRouter initialEntries={["/ingestion"]}>
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <IngestionPage />
        </I18nProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("IngestionPage", () => {
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
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the review-first intake workspace", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Ingestion Agent" })).toBeInTheDocument();
    expect(screen.getByLabelText("Agent intake")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Run agent/ })).toBeInTheDocument();
    expect(screen.getByText("Agent Review")).toBeInTheDocument();
    expect(screen.getByText("Attach evidence")).toBeInTheDocument();
    expect(screen.getByText("Advanced: paste raw table")).toBeInTheDocument();
    expect(screen.getByText(/No proposals yet/)).toBeInTheDocument();
  });
});
