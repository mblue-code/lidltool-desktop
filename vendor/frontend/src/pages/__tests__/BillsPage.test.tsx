import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BillsPage } from "@/pages/BillsPage";
import { formatEurFromCents } from "@/utils/format";

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

  it("updates summary cards from refreshed bills and calendar data even if overview lags", async () => {
    const today = new Date();
    const todayIso = today.toISOString().slice(0, 10);
    const currentYear = today.getFullYear();
    const currentMonth = today.getMonth() + 1;
    const createdBill = {
      id: "bill-qa-rent",
      user_id: "u1",
      name: "QA Rent",
      merchant_canonical: "qa rent",
      merchant_alias_pattern: "QA RENT",
      category: "housing",
      frequency: "monthly",
      interval_value: 1,
      amount_cents: 120000,
      amount_tolerance_pct: 0.1,
      currency: "EUR",
      anchor_date: todayIso,
      active: true,
      notes: null,
      created_at: `${todayIso}T12:00:00Z`,
      updated_at: `${todayIso}T12:00:00Z`
    };
    let bills: typeof createdBill[] = [];
    let calendarDays: Array<{
      date: string;
      items: Array<{
        occurrence_id: string;
        bill_id: string;
        bill_name: string;
        status: string;
        expected_amount_cents: number | null;
        actual_amount_cents: number | null;
      }>;
      count: number;
      total_expected_cents: number;
    }> = [];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = init?.method ?? "GET";

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                count: bills.length,
                total: bills.length,
                limit: 200,
                offset: 0,
                items: bills
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills/analytics/overview") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                active_bills: 0,
                due_this_week: 0,
                overdue: 0,
                monthly_committed_cents: 0,
                status_counts: {},
                currency: "EUR"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "GET" && url.pathname === "/api/v1/recurring-bills/analytics/calendar") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                year: currentYear,
                month: currentMonth,
                days: calendarDays,
                count: calendarDays.length
              },
              warnings: [],
              error: null
            })
          };
        }

        if (method === "POST" && url.pathname === "/api/v1/recurring-bills") {
          bills = [createdBill];
          calendarDays = [
            {
              date: todayIso,
              items: [
                {
                  occurrence_id: "occ-qa-rent",
                  bill_id: createdBill.id,
                  bill_name: createdBill.name,
                  status: "due",
                  expected_amount_cents: createdBill.amount_cents,
                  actual_amount_cents: null
                }
              ],
              count: 1,
              total_expected_cents: createdBill.amount_cents
            }
          ];

          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: createdBill,
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request ${method} ${url.pathname}`);
      })
    );

    renderBillsRoute();

    fireEvent.click(await screen.findByRole("button", { name: "Add bill" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "QA Rent" } });
    fireEvent.change(screen.getByLabelText("Amount (cents)"), { target: { value: "120000" } });
    fireEvent.change(screen.getByLabelText("Merchant (canonical)"), { target: { value: "qa rent" } });
    fireEvent.click(screen.getByRole("button", { name: "Create bill" }));

    await waitFor(() => {
      expect(screen.getByText("QA Rent")).toBeInTheDocument();
      expect(screen.getAllByText(formatEurFromCents(120000)).length).toBeGreaterThan(0);
      expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    });
  });
});
