import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    window.localStorage.setItem("app.locale", "de");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/recurring-bills" && method === "GET") {
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

        if (url.pathname === "/api/v1/recurring-bills" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                id: "bill-2",
                user_id: "u1",
                name: "Spotify",
                merchant_canonical: null,
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
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/recurring-bills/bill-1" && method === "PATCH") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                id: "bill-1",
                user_id: "u1",
                name: "Netflix",
                merchant_canonical: "netflix",
                merchant_alias_pattern: null,
                category: "subscriptions",
                frequency: "monthly",
                interval_value: 1,
                amount_cents: 1549,
                amount_tolerance_pct: 0.1,
                currency: "EUR",
                anchor_date: "2026-01-15",
                active: true,
                notes: null,
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z"
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

        throw new Error(`Unexpected request ${method} ${url.pathname}`);
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

  it("submits fixed bill amounts as cents from euro input", async () => {
    renderBillsRoute();

    fireEvent.click(await screen.findByRole("button", { name: "Add bill" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Spotify" } });
    fireEvent.change(screen.getByPlaceholderText("12,99"), { target: { value: "12,99" } });
    fireEvent.click(screen.getByRole("button", { name: "Create bill" }));

    await waitFor(() => {
      const postCall = vi.mocked(fetch).mock.calls.find((call) => {
        const url = new URL(String(call[0]));
        return url.pathname === "/api/v1/recurring-bills" && (call[1]?.method ?? "GET").toUpperCase() === "POST";
      });
      expect(postCall).toBeDefined();
    });

    const postCall = vi.mocked(fetch).mock.calls.find((call) => {
      const url = new URL(String(call[0]));
      return url.pathname === "/api/v1/recurring-bills" && (call[1]?.method ?? "GET").toUpperCase() === "POST";
    });

    expect(postCall).toBeDefined();
    expect(JSON.parse(String(postCall?.[1]?.body))).toMatchObject({
      name: "Spotify",
      amount_cents: 1299,
      currency: "EUR"
    });
  });

  it("formats existing cents back into euro input on edit and supports dot decimals", async () => {
    renderBillsRoute();

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));

    const amountInput = await screen.findByDisplayValue("12,99");
    expect(amountInput).toHaveValue("12,99");

    fireEvent.change(amountInput, { target: { value: "15.49" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      const patchCall = vi.mocked(fetch).mock.calls.find((call) => {
        const url = new URL(String(call[0]));
        return url.pathname === "/api/v1/recurring-bills/bill-1" && (call[1]?.method ?? "GET").toUpperCase() === "PATCH";
      });
      expect(patchCall).toBeDefined();
    });

    const patchCall = vi.mocked(fetch).mock.calls.find((call) => {
      const url = new URL(String(call[0]));
      return url.pathname === "/api/v1/recurring-bills/bill-1" && (call[1]?.method ?? "GET").toUpperCase() === "PATCH";
    });

    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      amount_cents: 1549
    });
  });

  it("rejects fixed bill amounts with more than two decimals", async () => {
    renderBillsRoute();

    fireEvent.click(await screen.findByRole("button", { name: "Add bill" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Spotify" } });
    fireEvent.change(screen.getByPlaceholderText("12,99"), { target: { value: "12,999" } });
    fireEvent.click(screen.getByRole("button", { name: "Create bill" }));

    await waitFor(() => {
      expect(
        screen.getByText("Amount must be a positive EUR value with at most two decimal places for fixed bills.")
      ).toBeInTheDocument();
    });

    const postCalls = vi.mocked(fetch).mock.calls.filter((call) => {
      const url = new URL(String(call[0]));
      return url.pathname === "/api/v1/recurring-bills" && (call[1]?.method ?? "GET").toUpperCase() === "POST";
    });
    expect(postCalls).toHaveLength(0);
  });

  it("clears and disables the amount input for variable bills", async () => {
    renderBillsRoute();

    fireEvent.click(await screen.findByRole("button", { name: "Add bill" }));

    const amountInput = screen.getByPlaceholderText("12,99");
    fireEvent.change(amountInput, { target: { value: "12,99" } });
    fireEvent.change(screen.getByLabelText("Amount mode"), { target: { value: "variable" } });

    expect(amountInput).toBeDisabled();
    expect(amountInput).toHaveValue("");
  });
});
