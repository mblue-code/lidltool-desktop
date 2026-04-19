import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { DashboardPage } from "../DashboardPage";

const localStorageState = new Map<string, string>();

function renderDashboardRoute(initialEntry = "/", options?: { withI18n?: boolean; locale?: "en" | "de" }): void {
  if (options?.locale) {
    localStorageState.set("app.locale", options.locale);
  }
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  const page = (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );

  render(
    options?.withI18n ? <I18nProvider>{page}</I18nProvider> : page
  );
}

describe("DashboardPage", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorageState.clear();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => localStorageState.get(key) ?? null,
        setItem: (key: string, value: string) => {
          localStorageState.set(key, value);
        },
        removeItem: (key: string) => {
          localStorageState.delete(key);
        },
        clear: () => {
          localStorageState.clear();
        }
      }
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));

        if (url.pathname === "/api/v1/auth/me") {
          const preferredLocale = localStorageState.get("app.locale") === "de" ? "de" : "en";
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                user_id: "user-1",
                username: "tester",
                display_name: "Tester",
                is_admin: true,
                preferred_locale: preferredLocale
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/dashboard/years") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                years: [2017, 2018, 2019, 2024, 2026],
                min_year: 2017,
                max_year: 2026,
                latest_year: 2026
              },
              warnings: [],
              error: null
            })
          };
        }

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

        if (url.pathname === "/api/v1/analytics/deposits") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                date_from: url.searchParams.get("from_date") || "2024-03-01",
                date_to: url.searchParams.get("to_date") || "2024-03-31",
                total_paid_cents: url.searchParams.get("source_ids") === "lidl" ? 300 : 0,
                total_returned_cents: 0,
                net_outstanding_cents: url.searchParams.get("source_ids") === "lidl" ? 300 : 0,
                monthly: []
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

        throw new Error(`Unexpected request ${url.pathname}`);
      })
    );
  });

  it("reads URL-persisted filters, shows month names, and applies updated year in requests", async () => {
    renderDashboardRoute("/?year=2024&month=3&view=normalized&breakdown=table&retailers=lidl");

    await waitFor(() => {
      expect(screen.getByDisplayValue("2024")).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Month" })).toHaveTextContent("March");
      expect(screen.getByText("Backend warnings")).toBeInTheDocument();
      expect(screen.getByText("Available: 2017-2026")).toBeInTheDocument();
      expect(screen.getByText("Spend")).toBeInTheDocument();
      expect(screen.queryByText("Net spend")).not.toBeInTheDocument();
    });

    await waitFor(() => {
      const initialCalls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(initialCalls.some((url) => url.includes("/api/v1/dashboard/cards?year=2024&month=3"))).toBe(true);
      expect(
        initialCalls.some(
          (url) => url.includes("/api/v1/dashboard/savings-breakdown?year=2024&month=3&view=normalized")
        )
      ).toBe(true);
      expect(
        initialCalls.some(
          (url) =>
            url.includes(
              "/api/v1/analytics/deposits?from_date=2024-03-01&to_date=2024-03-31&source_ids=lidl"
            )
        )
      ).toBe(true);
    });

    fireEvent.change(screen.getByLabelText("Year"), { target: { value: "2025" } });

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes("/api/v1/dashboard/cards?year=2025&month=3"))).toBe(true);
    });
  });

  it("renders concise trend copy without repeated gross/net wording", async () => {
    renderDashboardRoute("/?year=2026&month=2&spend=net");

    await waitFor(() => {
      expect(screen.getByText("Spending trend (last 6 months)")).toBeInTheDocument();
      expect(screen.getAllByText(/€264\.00/).length).toBeGreaterThan(0);
      expect(screen.getByText(/€32\.00 saved/).textContent).not.toContain("|");
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

  it("renders the simplified German dashboard wording when German is active", async () => {
    renderDashboardRoute("/?year=2026&month=2&retailers=lidl", { withI18n: true, locale: "de" });

    await waitFor(() => {
      expect(screen.getByText("Ausgaben")).toBeInTheDocument();
      expect(screen.getByText("Pfand im Zeitraum:")).toBeInTheDocument();
      expect(screen.getByText("Ausgabenverlauf (letzte 6 Monate)")).toBeInTheDocument();
      expect(screen.getByText(/32,00.*gespart/)).toBeInTheDocument();
      expect(screen.getByText("Verfügbar: 2017-2026")).toBeInTheDocument();
    });
  });
});
