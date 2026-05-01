import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionsPage } from "../TransactionsPage";

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="transactions-location-search">{location.search}</output>;
}

function renderTransactionsRoute(initialEntry = "/transactions"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/transactions"
            element={
              <>
                <TransactionsPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TransactionsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        if (url.pathname === "/api/v1/transactions/facets") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                merchants: [{ value: "Lidl", count: 1 }],
                categories: [{ category_id: "groceries", parent_category_id: null, count: 1 }],
                directions: [{ value: "outflow", count: 1 }],
                sources: [{ source_id: "lidl", count: 1 }],
                tags: [{ value: "grocery", count: 1 }],
                amount_bounds: { min_cents: 2400, max_cents: 2400 },
                date_bounds: { from_date: "2026-01-10T10:00:00Z", to_date: "2026-01-10T10:00:00Z" }
              },
              warnings: [],
              error: null
            })
          };
        }
        if (url.pathname === "/api/v1/settings/ai") {
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
                oauth_model: "gpt-5.4-mini",
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
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              count: 1,
              total: 1,
              limit: 25,
              offset: Number(url.searchParams.get("offset") || 0),
              items: [
                {
                  id: "tx-groceries",
                  purchased_at: "2026-01-10T10:00:00Z",
                  source_id: "lidl",
                  source_transaction_id: "1",
                  store_name: "Lidl",
                  total_gross_cents: 2400,
                  discount_total_cents: 100,
                  currency: "EUR",
                  direction: "outflow",
                  finance_category_id: "groceries",
                  finance_category_parent_id: null,
                  finance_category_method: "rule",
                  finance_category_confidence: 0.92,
                  finance_category_source_value: "groceries",
                  finance_category_version: "transaction-categorizer-v1",
                  finance_tags: ["grocery"]
                }
              ]
            },
            warnings: [],
            error: null
          })
        };
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the renamed transaction surface with finance direction and category", async () => {
    renderTransactionsRoute("/transactions?query=milk&finance_category_id=groceries&direction_filter=outflow");

    expect(await screen.findByRole("heading", { name: "Transactions" })).toBeInTheDocument();
    expect((await screen.findAllByText("Lidl")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Outflow").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Groceries").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Details" })[0]).toHaveAttribute("href", "/transactions/tx-groceries");
  });

  it("forwards URL-backed finance filters to the transactions and facets APIs", async () => {
    renderTransactionsRoute(
      "/transactions?query=milk&finance_category_id=groceries&direction_filter=outflow&merchant_name=Lidl&source_id=lidl&min_total=1000&max_total=3000"
    );

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(calls.some((url) => url.includes("/api/v1/transactions?") && url.includes("query=milk"))).toBe(true);
    expect(calls.some((url) => url.includes("finance_category_id=groceries"))).toBe(true);
    expect(calls.some((url) => url.includes("direction=outflow"))).toBe(true);
    expect(calls.some((url) => url.includes("merchant_name=Lidl"))).toBe(true);
    expect(calls.some((url) => url.includes("source_id=lidl"))).toBe(true);
    expect(calls.some((url) => url.includes("min_total_cents=1000"))).toBe(true);
    expect(calls.some((url) => url.includes("max_total_cents=3000"))).toBe(true);
    expect(calls.some((url) => url.includes("/api/v1/transactions/facets?"))).toBe(true);
  });

  it("defaults the transaction view to the current month instead of all-time", async () => {
    renderTransactionsRoute("/transactions");

    await waitFor(() => {
      expect(screen.getByTestId("transactions-location-search")).toHaveTextContent("purchased_from=");
    });
    const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(calls.some((url) => url.includes("/api/v1/transactions?") && url.includes("purchased_from="))).toBe(true);
  });

  it("keeps all-time explicit when requested in the URL", async () => {
    renderTransactionsRoute("/transactions?date_range=all");

    expect(await screen.findByText("All time")).toBeInTheDocument();
    expect(screen.getByTestId("transactions-location-search")).toHaveTextContent("date_range=all");
    const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(calls.some((url) => url.includes("/api/v1/transactions?") && !url.includes("purchased_from="))).toBe(true);
  });

  it("keeps receipt wording for the receipt upload action only", async () => {
    renderTransactionsRoute("/transactions");

    expect(await screen.findByRole("link", { name: "Add Receipt" })).toHaveAttribute("href", "/add");
    await waitFor(() => {
      expect(screen.getByTestId("transactions-location-search")).toHaveTextContent("purchased_from=");
    });
  });

  it("surfaces the categorization agent on the transactions page", async () => {
    renderTransactionsRoute("/transactions");

    expect(await screen.findByText("Categorization agent")).toBeInTheDocument();
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Categorize uncategorized" })).toBeEnabled();
    expect(screen.getByText("gpt-5.4-mini")).toBeInTheDocument();
  });
});
