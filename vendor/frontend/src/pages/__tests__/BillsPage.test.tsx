import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BillsPage } from "@/pages/BillsPage";

function jsonResponse(result: unknown): { ok: true; json: () => Promise<unknown> } {
  return {
    ok: true,
    json: async () => ({
      ok: true,
      result,
      warnings: [],
      error: null
    })
  };
}

function renderBillsRoute(initialEntry = "/bills"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
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

    let bills = [
      {
        id: "bill-1",
        user_id: "u1",
        name: "Netflix",
        merchant_canonical: "netflix",
        merchant_alias_pattern: null,
        category: "subscriptions",
        frequency: "monthly" as const,
        interval_value: 1,
        amount_cents: 1299,
        amount_tolerance_pct: 0.1,
        currency: "EUR",
        anchor_date: "2026-02-15",
        active: true,
        notes: null,
        created_at: "2026-02-01T00:00:00Z",
        updated_at: "2026-02-01T00:00:00Z"
      }
    ];
    let occurrencesByBillId: Record<string, Array<{
      id: string;
      bill_id: string;
      due_date: string;
      status: "upcoming" | "due" | "paid" | "overdue" | "skipped" | "unmatched";
      expected_amount_cents: number | null;
      actual_amount_cents: number | null;
      notes: string | null;
      created_at: string;
      updated_at: string;
      matches: unknown[];
    }>> = {
      "bill-1": [
        {
          id: "occ-1",
          bill_id: "bill-1",
          due_date: "2026-02-15",
          status: "due",
          expected_amount_cents: 1299,
          actual_amount_cents: null,
          notes: null,
          created_at: "2026-02-01T00:00:00Z",
          updated_at: "2026-02-01T00:00:00Z",
          matches: []
        },
        {
          id: "occ-2",
          bill_id: "bill-1",
          due_date: "2026-03-15",
          status: "upcoming",
          expected_amount_cents: 1299,
          actual_amount_cents: null,
          notes: null,
          created_at: "2026-02-01T00:00:00Z",
          updated_at: "2026-02-01T00:00:00Z",
          matches: []
        }
      ]
    };

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/recurring-bills" && method === "GET") {
          return jsonResponse({
            count: bills.length,
            total: bills.length,
            limit: 200,
            offset: 0,
            items: bills
          });
        }

        if (url.pathname === "/api/v1/recurring-bills" && method === "POST") {
          const body = JSON.parse(String(init?.body));
          const createdBill = {
            id: "bill-2",
            user_id: "u1",
            name: body.name,
            merchant_canonical: body.merchant_canonical,
            merchant_alias_pattern: body.merchant_alias_pattern,
            category: body.category,
            frequency: body.frequency,
            interval_value: body.interval_value,
            amount_cents: body.amount_cents,
            amount_tolerance_pct: body.amount_tolerance_pct,
            currency: body.currency,
            anchor_date: body.anchor_date,
            active: body.active,
            notes: body.notes,
            created_at: "2026-02-20T12:00:00Z",
            updated_at: "2026-02-20T12:00:00Z"
          };
          bills = [createdBill, ...bills];
          occurrencesByBillId["bill-2"] = [
            {
              id: "occ-created",
              bill_id: "bill-2",
              due_date: body.anchor_date,
              status: "upcoming",
              expected_amount_cents: body.amount_cents,
              actual_amount_cents: null,
              notes: null,
              created_at: "2026-02-20T12:00:00Z",
              updated_at: "2026-02-20T12:00:00Z",
              matches: []
            }
          ];
          return jsonResponse(createdBill);
        }

        if (url.pathname === "/api/v1/recurring-bills/bill-1" && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          bills = bills.map((bill) =>
            bill.id === "bill-1"
              ? {
                  ...bill,
                  ...body,
                  updated_at: "2026-02-20T12:00:00Z"
                }
              : bill
          );
          occurrencesByBillId["bill-1"] = occurrencesByBillId["bill-1"].map((occurrence) => ({
            ...occurrence,
            expected_amount_cents: body.amount_cents ?? occurrence.expected_amount_cents,
            updated_at: "2026-02-20T12:00:00Z"
          }));
          return jsonResponse(bills.find((bill) => bill.id === "bill-1"));
        }

        if (url.pathname === "/api/v1/recurring-bills/analytics/overview") {
          return jsonResponse({
            active_bills: bills.filter((bill) => bill.active).length,
            due_this_week: 1,
            overdue: 0,
            monthly_committed_cents: bills.reduce((total, bill) => total + (bill.amount_cents ?? 0), 0),
            status_counts: { due: 1, upcoming: 1 },
            currency: "EUR"
          });
        }

        if (url.pathname === "/api/v1/recurring-bills/analytics/calendar") {
          const month = Number(url.searchParams.get("month") ?? "2");
          const year = Number(url.searchParams.get("year") ?? "2026");
          const days = Object.values(occurrencesByBillId)
            .flat()
            .filter((occurrence) => {
              const [occYear, occMonth] = occurrence.due_date.split("-").map(Number);
              return occYear === year && occMonth === month;
            })
            .reduce<Record<string, { date: string; items: Array<{
              occurrence_id: string;
              bill_id: string;
              bill_name: string;
              status: string;
              expected_amount_cents: number | null;
              actual_amount_cents: number | null;
            }>; count: number; total_expected_cents: number }>>((accumulator, occurrence) => {
              const bill = bills.find((candidate) => candidate.id === occurrence.bill_id);
              if (!bill) {
                return accumulator;
              }
              const existing = accumulator[occurrence.due_date] ?? {
                date: occurrence.due_date,
                items: [],
                count: 0,
                total_expected_cents: 0
              };
              existing.items.push({
                occurrence_id: occurrence.id,
                bill_id: occurrence.bill_id,
                bill_name: bill.name,
                status: occurrence.status,
                expected_amount_cents: occurrence.expected_amount_cents,
                actual_amount_cents: occurrence.actual_amount_cents
              });
              existing.count += 1;
              existing.total_expected_cents += occurrence.expected_amount_cents ?? 0;
              accumulator[occurrence.due_date] = existing;
              return accumulator;
            }, {});
          return jsonResponse({
            year,
            month,
            days: Object.values(days).sort((left, right) => left.date.localeCompare(right.date)),
            count: Object.keys(days).length
          });
        }

        if (url.pathname === "/api/v1/recurring-bills/bill-1/occurrences") {
          return jsonResponse({
            count: occurrencesByBillId["bill-1"].length,
            total: occurrencesByBillId["bill-1"].length,
            limit: 100,
            offset: 0,
            items: occurrencesByBillId["bill-1"]
          });
        }

        if (url.pathname === "/api/v1/recurring-bills/bill-2/occurrences") {
          return jsonResponse({
            count: occurrencesByBillId["bill-2"].length,
            total: occurrencesByBillId["bill-2"].length,
            limit: 100,
            offset: 0,
            items: occurrencesByBillId["bill-2"]
          });
        }

        throw new Error(`Unexpected request ${method} ${url.pathname}${url.search}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders recurring overview and bill table", async () => {
    renderBillsRoute("/bills?month=2026-02");

    await waitFor(() => {
      expect(screen.getByText("Recurring Bills")).toBeInTheDocument();
      expect(screen.getByText("Netflix")).toBeInTheDocument();
      expect(screen.getByText("Monthly committed")).toBeInTheDocument();
    });
  });

  it("creates a recurring bill on the first save and opens its generated occurrence", async () => {
    renderBillsRoute("/bills?month=2026-02");

    fireEvent.click(await screen.findByRole("button", { name: "Add bill" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Internet" } });
    fireEvent.change(screen.getByLabelText("Amount (EUR)"), { target: { value: "350.00" } });
    fireEvent.change(screen.getByLabelText("Anchor date"), { target: { value: "2026-02-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Create bill" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          if ((call[1]?.method ?? "GET") !== "POST" || url.pathname !== "/api/v1/recurring-bills") {
            return false;
          }
          const body = JSON.parse(String(call[1]?.body));
          return body.amount_cents === 35000;
        })
      ).toBe(true);
    });

    expect(await screen.findByText("Occurrences: Internet")).toBeInTheDocument();
    expect(screen.getByText("Expected €350.00")).toBeInTheDocument();
  });

  it("updates bill amounts in euros and supports calendar navigation and drill-down", async () => {
    renderBillsRoute("/bills?month=2026-02&bill=bill-1");

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Amount (EUR)"), { target: { value: "350.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          if ((call[1]?.method ?? "GET") !== "PATCH" || url.pathname !== "/api/v1/recurring-bills/bill-1") {
            return false;
          }
          const body = JSON.parse(String(call[1]?.body));
          return body.amount_cents === 35000;
        })
      ).toBe(true);
    });

    expect(await screen.findAllByText("Expected €350.00")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          return (
            (call[1]?.method ?? "GET") === "GET" &&
            url.pathname === "/api/v1/recurring-bills/analytics/calendar" &&
            url.searchParams.get("month") === "3"
          );
        })
      ).toBe(true);
    });

    fireEvent.click(await screen.findByRole("button", { name: /2026-03-15/i }));

    expect(await screen.findByText("Due on Mar 15, 2026")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Netflix/i }));

    expect(await screen.findByText("Occurrences: Netflix")).toBeInTheDocument();
  });
});
