import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ItemRecategorizeControl } from "../ItemRecategorizeControl";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

function renderControl() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ItemRecategorizeControl />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ItemRecategorizeControl", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input), "http://localhost");
        const method = (init?.method || "GET").toUpperCase();

        if (method === "GET" && url.pathname === "/api/v1/settings/ai") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                enabled: true,
                base_url: null,
                model: "gpt-5.4-mini",
                api_key_set: false,
                oauth_provider: "openai-codex",
                oauth_connected: true,
                oauth_model: "gpt-5.4",
                remote_enabled: true,
                local_runtime_enabled: false,
                local_runtime_ready: false,
                local_runtime_status: "disabled",
                categorization_enabled: true,
                categorization_provider: "oauth_codex",
                categorization_base_url: null,
                categorization_api_key_set: false,
                categorization_model: "gpt-5.4-mini",
                categorization_runtime_ready: true,
                categorization_runtime_status: "ready"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "POST" && url.pathname === "/api/v1/quality/recategorize") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                job: {
                  job_id: "job-123",
                  status: "queued",
                  requested_by_user_id: "user-1",
                  requested_at: "2026-04-24T10:00:00Z",
                  started_at: null,
                  finished_at: null,
                  source_id: null,
                  only_fallback_other: true,
                  include_suspect_model_items: false,
                  max_transactions: null,
                  transaction_count: 0,
                  candidate_item_count: 12,
                  updated_transaction_count: 0,
                  updated_item_count: 0,
                  skipped_transaction_count: 0,
                  method_counts: {},
                  error: null
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/quality/recategorize/status") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                job_id: "job-123",
                status: "completed",
                requested_by_user_id: "user-1",
                requested_at: "2026-04-24T10:00:00Z",
                started_at: "2026-04-24T10:00:01Z",
                finished_at: "2026-04-24T10:00:03Z",
                source_id: null,
                only_fallback_other: true,
                include_suspect_model_items: false,
                max_transactions: null,
                transaction_count: 4,
                candidate_item_count: 12,
                updated_transaction_count: 3,
                updated_item_count: 9,
                skipped_transaction_count: 1,
                method_counts: {},
                error: null
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unhandled request: ${method} ${url.pathname}`);
      })
    );
  });

  it("starts a bulk recategorization job when categorization is enabled", async () => {
    renderControl();

    const button = await screen.findByRole("button", { name: "Repair uncategorized items" });
    expect(button).toBeEnabled();

    fireEvent.click(button);

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes("/api/v1/quality/recategorize"))).toBe(true);
    });
  });
});
