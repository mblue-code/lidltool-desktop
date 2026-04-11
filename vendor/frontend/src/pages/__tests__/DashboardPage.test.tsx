import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "../DashboardPage";

function renderDashboardRoute(initialEntry = "/"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DashboardPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));

        if (url.pathname === "/api/v1/dashboard/cards") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                totals: {
                  receipt_count: 8,
                  paid_cents: 26400,
                  paid_currency: "EUR",
                  saved_cents: 3200,
                  saved_currency: "EUR",
                  gross_cents: 29600,
                  gross_currency: "EUR",
                  savings_rate: 0.1081
                }
              },
              warnings: ["Using estimated savings baseline"],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/dashboard/trends") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                points: [
                  {
                    year: 2026,
                    month: 2,
                    period_key: "2026-02",
                    paid_cents: 26400,
                    saved_cents: 3200,
                    savings_rate: 0.1081
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/dashboard/savings-breakdown") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                view: url.searchParams.get("view") || "native",
                by_type: [
                  {
                    type: "promotion",
                    saved_cents: 1800,
                    saved_currency: "EUR",
                    discount_events: 4
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/dashboard/retailer-composition") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                retailers: [
                  {
                    source_id: "lidl",
                    retailer: "Lidl",
                    paid_cents: 26400,
                    saved_cents: 3200,
                    paid_share: 1,
                    saved_share: 1,
                    savings_rate: 0.1081
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/sources") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                sources: [
                  {
                    id: "lidl",
                    kind: "connector",
                    display_name: "Lidl",
                    status: "healthy",
                    enabled: true
                  }
                ]
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
                    date: "2026-02-12",
                    items: [
                      {
                        occurrence_id: "occ-1",
                        bill_id: "bill-1",
                        bill_name: "Netflix",
                        status: "upcoming",
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

        if (url.pathname === "/api/v1/recurring-bills/analytics/forecast") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                months: 3,
                points: [
                  { period: "2026-02", projected_cents: 1299, currency: "EUR" },
                  { period: "2026-03", projected_cents: 1399, currency: "EUR" },
                  { period: "2026-04", projected_cents: 1499, currency: "EUR" }
                ],
                total_projected_cents: 4197,
                currency: "EUR"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/deposits") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                date_from: url.searchParams.get("from_date") ?? "2026-02-01",
                date_to: url.searchParams.get("to_date") ?? "2026-02-29",
                total_paid_cents: 2675,
                total_returned_cents: 0,
                net_outstanding_cents: 2675,
                monthly: [
                  {
                    month: "2026-02",
                    paid_cents: 2675,
                    returned_cents: 0,
                    net_cents: 2675
                  }
                ]
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

  it("reads URL-persisted filters, shows month names, and applies updated year in requests", async () => {
    renderDashboardRoute("/?year=2024&month=3&view=normalized&breakdown=table");

    await waitFor(() => {
      expect(screen.getByDisplayValue("2024")).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Month" })).toHaveTextContent("March");
      expect(screen.getByText("Backend warnings")).toBeInTheDocument();
      expect(screen.getByText("Spend total")).toBeInTheDocument();
      expect(screen.getByText("Before savings")).toBeInTheDocument();
      expect(screen.getByText("Spend excludes deposit; VAT-exclusive totals only when tax data is available.")).toBeInTheDocument();
    });

    await waitFor(() => {
      const initialCalls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(initialCalls.some((url) => url.includes("/api/v1/dashboard/cards?year=2024&month=3"))).toBe(true);
      expect(
        initialCalls.some(
          (url) => url.includes("/api/v1/analytics/deposits?from_date=2024-03-01&to_date=2024-03-31")
        )
      ).toBe(true);
      expect(
        initialCalls.some(
          (url) => url.includes("/api/v1/dashboard/savings-breakdown?year=2024&month=3&view=normalized")
        )
      ).toBe(true);
    });

    fireEvent.change(screen.getByLabelText("Year"), { target: { value: "2025" } });

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes("/api/v1/dashboard/cards?year=2025&month=3"))).toBe(true);
      expect(
        calls.some((url) => url.includes("/api/v1/analytics/deposits?from_date=2025-03-01&to_date=2025-03-31"))
      ).toBe(true);
    });
  });

  it("toggles breakdown table mode and exports visible table rows as JSON and CSV", async () => {
    const createObjectUrlSpy = vi.fn(() => "blob:mock");
    const revokeObjectUrlSpy = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectUrlSpy,
      configurable: true
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectUrlSpy,
      configurable: true
    });

    renderDashboardRoute("/?year=2026&month=2&view=native&breakdown=chart");

    await waitFor(() => {
      expect(screen.getByText("Savings by discount type (native)")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Chart" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Table" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Table" }));

    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: "Type" })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: "Events" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    await waitFor(() => {
      expect(createObjectUrlSpy).toHaveBeenCalledTimes(2);
      expect(revokeObjectUrlSpy).toHaveBeenCalledTimes(2);
      expect(screen.getByText("Exported CSV snapshot.")).toBeInTheDocument();
    });
  });

  it("passes the active retailer filter to deposit analytics and refreshes data on demand", async () => {
    renderDashboardRoute("/?year=2026&month=2&retailers=lidl");

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(
        calls.some(
          (url) =>
            url.includes("/api/v1/analytics/deposits?from_date=2026-02-01&to_date=2026-02-28&source_ids=lidl")
        )
      ).toBe(true);
      expect(screen.getByRole("button", { name: "Refresh data" })).toBeInTheDocument();
    });

    const depositCallsBefore = vi
      .mocked(fetch)
      .mock.calls.filter((call) => String(call[0]).includes("/api/v1/analytics/deposits")).length;

    fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));

    await waitFor(() => {
      const depositCallsAfter = vi
        .mocked(fetch)
        .mock.calls.filter((call) => String(call[0]).includes("/api/v1/analytics/deposits")).length;
      expect(depositCallsAfter).toBeGreaterThan(depositCallsBefore);
    });
  });
});
