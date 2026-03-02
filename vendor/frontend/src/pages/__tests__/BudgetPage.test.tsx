import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BudgetPage } from "../BudgetPage";

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <BudgetPage />
    </QueryClientProvider>
  );
}

describe("BudgetPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/analytics/budget-rules" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { items: [], count: 0 },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/budget" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { period: { year: 2026, month: 2 }, rows: [], count: 0 },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/budget-rules" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                rule_id: "r1",
                scope_type: "category",
                scope_value: "Dairy",
                period: "monthly",
                amount_cents: 2000,
                currency: "EUR",
                active: true,
                created_at: "2026-02-20T00:00:00Z",
                updated_at: "2026-02-20T00:00:00Z"
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("creates a budget rule", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Scope value"), { target: { value: "Dairy" } });
    fireEvent.change(screen.getByLabelText("Amount (cents)"), { target: { value: "2000" } });
    fireEvent.click(screen.getByRole("button", { name: "Add budget rule" }));

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => {
        const url = new URL(String(call[0]));
        return `${call[1]?.method ?? "GET"} ${url.pathname}`;
      });
      expect(calls.some((entry) => entry === "POST /api/v1/analytics/budget-rules")).toBe(true);
    });
  });
});
