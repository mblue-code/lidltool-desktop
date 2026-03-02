import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BillsPage } from "@/pages/BillsPage";

function renderBillsRoute(initialEntry = "/bills"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/bills" element={<BillsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("BillsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));

        if (url.pathname === "/api/v1/recurring-bills") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: 1,
                total: 1,
                limit: 200,
                offset: 0,
                items: [
                  {
                    id: "bill-1",
                    user_id: "u1",
                    name: "Netflix",
                    merchant_canonical: "netflix",
                    merchant_alias_pattern: null,
                    category: "subscriptions",
                    frequency: "monthly",
                    interval_value: 1,
                    amount_cents: 1299,
                    amount_tolerance_pct: 0.1,
                    currency: "EUR",
                    anchor_date: "2026-01-15",
                    active: true,
                    notes: null,
                    created_at: "2026-02-01T00:00:00Z",
                    updated_at: "2026-02-01T00:00:00Z"
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/recurring-bills/analytics/overview") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                active_bills: 1,
                due_this_week: 1,
                overdue: 0,
                monthly_committed_cents: 1299,
                status_counts: { due: 1 },
                currency: "EUR"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/recurring-bills/analytics/calendar") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                year: 2026,
                month: 2,
                days: [
                  {
                    date: "2026-02-15",
                    items: [
                      {
                        occurrence_id: "occ-1",
                        bill_id: "bill-1",
                        bill_name: "Netflix",
                        status: "due",
                        expected_amount_cents: 1299,
                        actual_amount_cents: null
                      }
                    ],
                    count: 1,
                    total_expected_cents: 1299
                  }
                ],
                count: 1
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request ${url.pathname}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders recurring overview and bill table", async () => {
    renderBillsRoute();

    await waitFor(() => {
      expect(screen.getByText("Recurring Bills")).toBeInTheDocument();
      expect(screen.getByText("Netflix")).toBeInTheDocument();
      expect(screen.getByText("Monthly committed")).toBeInTheDocument();
    });
  });
});
