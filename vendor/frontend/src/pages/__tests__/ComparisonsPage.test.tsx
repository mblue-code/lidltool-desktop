import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ComparisonsPage } from "../ComparisonsPage";

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ComparisonsPage />
    </QueryClientProvider>
  );
}

describe("ComparisonsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    if (typeof localStorage.removeItem === "function") {
      localStorage.removeItem("analytics.compare.basket.v1");
    }
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/compare/groups" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                items: [
                  {
                    group_id: "g1",
                    name: "Weekly Basket",
                    unit_standard: "€/pcs",
                    notes: null,
                    member_count: 0,
                    created_at: "2026-02-20T00:00:00Z"
                  }
                ],
                count: 1
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/price-index" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                grain: "month",
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                points: [{ period: "2026-01", source_kind: "lidl_de", index: 97.5, product_count: 2 }]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/products" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                items: [
                  {
                    product_id: "p1",
                    canonical_name: "Milk 1L",
                    brand: null,
                    default_unit: "l",
                    category_id: null,
                    gtin_ean: null,
                    alias_count: 1
                  }
                ],
                count: 1
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/basket-compare" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                net: true,
                basket_items: [{ product_id: "p1", quantity: 1 }],
                retailers: [
                  {
                    source_kind: "lidl_de",
                    total_cents: 120,
                    covered_items: 1,
                    missing_items: 0,
                    coverage_rate: 1,
                    line_items: []
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/compare/groups/g1/series" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                group: { group_id: "g1", name: "Weekly Basket", unit_standard: "€/pcs" },
                net: true,
                grain: "month",
                points: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/compare/groups/g1/members" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { group_id: "g1", product_id: "p1", weight: 1 },
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

  it("builds basket and requests basket comparison", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Find product"), { target: { value: "milk" } });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Milk 1L" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Milk 1L" }));
    fireEvent.click(screen.getByRole("button", { name: "Add selected product to basket" }));

    await waitFor(() => {
      expect(screen.getAllByText("Milk 1L").length).toBeGreaterThan(1);
    });

    fireEvent.click(screen.getByRole("button", { name: "Compare basket" }));

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => {
        const url = new URL(String(call[0]));
        return `${call[1]?.method ?? "GET"} ${url.pathname}`;
      });
      expect(calls.some((entry) => entry === "POST /api/v1/analytics/basket-compare")).toBe(true);
    });
  });
});
