import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BudgetPage } from "../BudgetPage";
import { formatEurFromCents } from "@/utils/format";

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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

type MockCashflowItem = {
  id: string;
  user_id: string;
  effective_date: string;
  direction: "inflow" | "outflow";
  category: string;
  amount_cents: number;
  currency: string;
  description: string | null;
  source_type: string;
  linked_transaction_id: string | null;
  is_reconciled: boolean;
  linked_transaction: {
    id: string;
    purchased_at: string;
    merchant_name: string | null;
    total_gross_cents: number;
    currency: string;
  } | null;
  linked_recurring_occurrence_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

describe("BudgetPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    let cashflowItems: MockCashflowItem[] = [
      {
        id: "cf-1",
        user_id: "u1",
        effective_date: "2026-02-01",
        direction: "inflow",
        category: "salary",
        amount_cents: 320000,
        currency: "EUR",
        description: "Monthly salary",
        source_type: "manual",
        linked_transaction_id: null,
        is_reconciled: false,
        linked_transaction: null,
        linked_recurring_occurrence_id: null,
        notes: null,
        created_at: "2026-02-01T10:00:00Z",
        updated_at: "2026-02-01T10:00:00Z"
      },
      {
        id: "cf-2",
        user_id: "u1",
        effective_date: "2026-02-14",
        direction: "outflow",
        category: "groceries",
        amount_cents: 8400,
        currency: "EUR",
        description: "Weekly grocery cash",
        source_type: "manual",
        linked_transaction_id: null,
        is_reconciled: false,
        linked_transaction: null,
        linked_recurring_occurrence_id: null,
        notes: null,
        created_at: "2026-02-14T10:00:00Z",
        updated_at: "2026-02-14T10:00:00Z"
      }
    ];
    const receiptCandidates = [
      {
        id: "tx-1",
        purchased_at: "2026-02-14T09:15:00Z",
        source_id: "manual_entry",
        user_id: "u1",
        source_transaction_id: "receipt-1",
        store_name: "Lidl Berlin",
        total_gross_cents: 8400,
        discount_total_cents: 0,
        currency: "EUR"
      },
      {
        id: "tx-2",
        purchased_at: "2026-02-12T18:00:00Z",
        source_id: "manual_entry",
        user_id: "u1",
        source_transaction_id: "receipt-2",
        store_name: "Rewe",
        total_gross_cents: 1995,
        discount_total_cents: 0,
        currency: "EUR"
      }
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();
        const monthMatch = url.pathname.match(/^\/api\/v1\/budget\/months\/(\d{4})\/(\d{1,2})(?:\/summary)?$/);
        const year = monthMatch ? Number(monthMatch[1]) : 2026;
        const monthNumber = monthMatch ? Number(monthMatch[2]) : 2;

        if (/^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}$/.test(url.pathname) && method === "GET") {
          return jsonResponse({
            year,
            month: monthNumber,
            planned_income_cents: 320000,
            target_savings_cents: 30000,
            opening_balance_cents: 120000,
            currency: "EUR",
            notes: "Focus on savings"
          });
        }

        if (/^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}$/.test(url.pathname) && method === "PUT") {
          const body = JSON.parse(String(init?.body));
          return jsonResponse({
            year,
            month: monthNumber,
            planned_income_cents: body.planned_income_cents,
            target_savings_cents: body.target_savings_cents,
            opening_balance_cents: body.opening_balance_cents,
            currency: "EUR",
            notes: body.notes
          });
        }

        if (/^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}\/summary$/.test(url.pathname) && method === "GET") {
          const reconciledCount = cashflowItems.filter((item) => item.linked_transaction_id !== null).length;
          const manualOutflowCents = cashflowItems
            .filter((item) => item.direction === "outflow" && item.linked_transaction_id === null)
            .reduce((total, item) => total + item.amount_cents, 0);
          const totalOutflowCents = 84000 + manualOutflowCents;
          const actualIncomeCents = cashflowItems
            .filter((item) => item.direction === "inflow")
            .reduce((total, item) => total + item.amount_cents, 0);
          return jsonResponse({
            period: { year, month: monthNumber },
            month: {
              year,
              month: monthNumber,
              planned_income_cents: 320000,
              target_savings_cents: 30000,
              opening_balance_cents: 120000,
              currency: "EUR",
              notes: "Focus on savings"
            },
            totals: {
              planned_income_cents: 320000,
              actual_income_cents: actualIncomeCents,
              income_basis_cents: 320000,
              income_basis: "planned_income",
              target_savings_cents: 30000,
              opening_balance_cents: 120000,
              receipt_spend_cents: 84000,
              manual_outflow_cents: manualOutflowCents,
              total_outflow_cents: totalOutflowCents,
              recurring_expected_cents: 65000,
              recurring_paid_cents: 52000,
              available_cents: 340000,
              remaining_cents: 340000 - totalOutflowCents,
              saved_cents: 320000 - totalOutflowCents,
              savings_delta_cents: 2500
            },
            budget_rules: [
              {
                rule_id: "rule-1",
                scope_type: "category",
                scope_value: "groceries",
                period: "monthly",
                budget_cents: 40000,
                spent_cents: 28000,
                remaining_cents: 12000,
                utilization: 0.7,
                projected_spent_cents: 38000,
                projected_utilization: 0.95,
                over_budget: false,
                projected_over_budget: false
              }
            ],
            recurring: {
              count: 2,
              paid_count: 1,
              unpaid_count: 1,
              items: [
                {
                  occurrence_id: "occ-1",
                  bill_id: "bill-1",
                  bill_name: "Netflix",
                  due_date: "2026-02-15",
                  status: "paid",
                  expected_amount_cents: 1299,
                  actual_amount_cents: 1299
                },
                {
                  occurrence_id: "occ-2",
                  bill_id: "bill-2",
                  bill_name: "Internet",
                  due_date: "2026-02-20",
                  status: "due",
                  expected_amount_cents: 4500,
                  actual_amount_cents: null
                }
              ]
            },
            cashflow: {
              count: cashflowItems.length,
              inflow_count: cashflowItems.filter((item) => item.direction === "inflow").length,
              outflow_count: cashflowItems.filter((item) => item.direction === "outflow").length,
              reconciled_count: reconciledCount
            }
          });
        }

        if (url.pathname === "/api/v1/cashflow-entries" && method === "GET") {
          const direction = url.searchParams.get("direction");
          const category = url.searchParams.get("category");
          const reconciled = url.searchParams.get("reconciled");
          const items = cashflowItems.filter((item) => {
            if (direction && item.direction !== direction) {
              return false;
            }
            if (category && item.category.toLowerCase() !== category.toLowerCase()) {
              return false;
            }
            if (reconciled === "true" && item.linked_transaction_id === null) {
              return false;
            }
            if (reconciled === "false" && item.linked_transaction_id !== null) {
              return false;
            }
            return true;
          });
          return jsonResponse({
            count: items.length,
            total: items.length,
            items
          });
        }

        if (url.pathname === "/api/v1/cashflow-entries" && method === "POST") {
          const body = JSON.parse(String(init?.body));
          const createdItem = {
            id: "cf-created",
            user_id: "u1",
            effective_date: body.effective_date,
            direction: body.direction,
            category: body.category,
            amount_cents: body.amount_cents,
            currency: body.currency,
            description: body.description,
            source_type: body.source_type,
            linked_transaction_id: null,
            is_reconciled: false,
            linked_transaction: null,
            linked_recurring_occurrence_id: null,
            notes: body.notes,
            created_at: "2026-02-15T12:00:00Z",
            updated_at: "2026-02-15T12:00:00Z"
          };
          cashflowItems = [createdItem, ...cashflowItems];
          return jsonResponse(createdItem);
        }

        if (url.pathname === "/api/v1/cashflow-entries/cf-2" && method === "PATCH") {
          const body = JSON.parse(String(init?.body));
          const existing = cashflowItems.find((item) => item.id === "cf-2");
          if (!existing) {
            throw new Error("Missing cashflow entry cf-2");
          }
          const linkedTransactionId =
            Object.prototype.hasOwnProperty.call(body, "linked_transaction_id")
              ? body.linked_transaction_id
              : existing.linked_transaction_id;
          const linkedTransaction =
            linkedTransactionId === null
              ? null
              : receiptCandidates.find((candidate) => candidate.id === linkedTransactionId) ?? null;
          const updatedItem = {
            ...existing,
            effective_date: body.effective_date ?? existing.effective_date,
            direction: body.direction ?? existing.direction,
            category: body.category ?? existing.category,
            amount_cents: body.amount_cents ?? existing.amount_cents,
            currency: body.currency ?? existing.currency,
            description: body.description ?? existing.description,
            source_type: body.source_type ?? existing.source_type,
            linked_transaction_id: linkedTransactionId,
            is_reconciled: linkedTransactionId !== null,
            linked_transaction: linkedTransaction
              ? {
                  id: linkedTransaction.id,
                  purchased_at: linkedTransaction.purchased_at,
                  merchant_name: linkedTransaction.store_name,
                  total_gross_cents: linkedTransaction.total_gross_cents,
                  currency: linkedTransaction.currency
                }
              : null,
            linked_recurring_occurrence_id:
              body.linked_recurring_occurrence_id ?? existing.linked_recurring_occurrence_id,
            notes: Object.prototype.hasOwnProperty.call(body, "notes") ? body.notes : existing.notes,
            updated_at: "2026-02-15T12:00:00Z"
          };
          cashflowItems = cashflowItems.map((item) => (item.id === updatedItem.id ? updatedItem : item));
          return jsonResponse(updatedItem);
        }

        if (url.pathname === "/api/v1/cashflow-entries/cf-2" && method === "DELETE") {
          cashflowItems = cashflowItems.filter((item) => item.id !== "cf-2");
          return jsonResponse({ deleted: true, id: "cf-2" });
        }

        if (url.pathname === "/api/v1/transactions" && method === "GET") {
          const query = url.searchParams.get("query")?.toLowerCase().trim();
          const items = receiptCandidates.filter((candidate) =>
            query ? candidate.store_name.toLowerCase().includes(query) : true
          );
          return jsonResponse({
            count: items.length,
            total: items.length,
            limit: 8,
            offset: 0,
            items
          });
        }

        if (url.pathname === "/api/v1/analytics/budget-rules" && method === "GET") {
          return jsonResponse({
            items: [
              {
                rule_id: "rule-1",
                scope_type: "category",
                scope_value: "groceries",
                period: "monthly",
                amount_cents: 40000,
                currency: "EUR",
                active: true,
                created_at: "2026-02-01T00:00:00Z",
                updated_at: "2026-02-01T00:00:00Z"
              }
            ],
            count: 1
          });
        }

        if (url.pathname === "/api/v1/analytics/budget" && method === "GET") {
          return jsonResponse({
            period: { year: 2026, month: 2 },
            rows: [
              {
                rule_id: "rule-1",
                scope_type: "category",
                scope_value: "groceries",
                period: "monthly",
                budget_cents: 40000,
                spent_cents: 28000,
                remaining_cents: 12000,
                utilization: 0.7,
                projected_spent_cents: 38000,
                projected_utilization: 0.95,
                over_budget: false,
                projected_over_budget: false
              }
            ],
            count: 1
          });
        }

        if (url.pathname === "/api/v1/analytics/budget-rules" && method === "POST") {
          return jsonResponse({
            rule_id: "rule-2",
            scope_type: "source_kind",
            scope_value: "manual",
            period: "monthly",
            amount_cents: 25000,
            currency: "EUR",
            active: true,
            created_at: "2026-02-15T12:00:00Z",
            updated_at: "2026-02-15T12:00:00Z"
          });
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}${url.search}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the monthly summary and recurring overview", async () => {
    renderPage();

    expect(await screen.findByText("Budget")).toBeInTheDocument();
    expect(screen.getByText("Monthly Budget Settings")).toBeInTheDocument();
    expect(await screen.findByText("Netflix")).toBeInTheDocument();
    expect(screen.getAllByText("Focus on savings").length).toBeGreaterThan(0);
  });

  it("saves the month settings and cash-flow entries", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Planned income (EUR)"), { target: { value: "3500.00" } });
    fireEvent.change(screen.getByLabelText("Target savings (EUR)"), { target: { value: "500.00" } });
    fireEvent.change(screen.getByLabelText("Opening balance (EUR)"), { target: { value: "1250.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save month settings" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          return (call[1]?.method ?? "GET") === "PUT" && /^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}$/.test(url.pathname);
        })
      ).toBe(true);
    });

    fireEvent.change(screen.getByLabelText("Amount (EUR)", { selector: "#cashflow-amount" }), {
      target: { value: "19.95" }
    });
    fireEvent.change(screen.getByLabelText("Description", { selector: "#cashflow-description" }), {
      target: { value: "Coffee cash" }
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[1]);

    await waitFor(() => {
      expect(screen.getByDisplayValue("Weekly grocery cash")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("Amount (EUR)", { selector: "#cashflow-amount" }), {
      target: { value: "22.00" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Update entry" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          return (call[1]?.method ?? "GET") === "PATCH" && url.pathname === "/api/v1/cashflow-entries/cf-2";
        })
      ).toBe(true);
    });
  });

  it("supports quick-add presets, filters, and receipt reconciliation", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Cash expense/i }));

    expect(screen.getByDisplayValue("cash")).toBeInTheDocument();
    expect(screen.getByDisplayValue("manual_cash")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Cash expense")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Category filter"), { target: { value: "groceries" } });

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          return (
            (call[1]?.method ?? "GET") === "GET" &&
            url.pathname === "/api/v1/cashflow-entries" &&
            url.searchParams.get("category") === "groceries"
          );
        })
      ).toBe(true);
    });

    fireEvent.click(screen.getByRole("button", { name: "Link receipt" }));

    expect(await screen.findByText("Link receipt to Weekly grocery cash")).toBeInTheDocument();
    expect(await screen.findByText("Lidl Berlin")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Use receipt" })[0]);

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          if ((call[1]?.method ?? "GET") !== "PATCH" || url.pathname !== "/api/v1/cashflow-entries/cf-2") {
            return false;
          }
          const body = JSON.parse(String(call[1]?.body));
          return body.linked_transaction_id === "tx-1";
        })
      ).toBe(true);
    });

    expect(await screen.findByRole("button", { name: "Unlink receipt" })).toBeInTheDocument();
  });

  it("keeps the budget rule create flow available", async () => {
    renderPage();

    fireEvent.change(screen.getByLabelText("Scope value"), { target: { value: "manual" } });
    fireEvent.change(screen.getByLabelText("Amount (EUR)", { selector: "#budget-rule-amount" }), {
      target: { value: "250.00" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Add budget rule" }));

    await waitFor(() => {
      expect(
        vi.mocked(fetch).mock.calls.some((call) => {
          const url = new URL(String(call[0]));
          return (call[1]?.method ?? "GET") === "POST" && url.pathname === "/api/v1/analytics/budget-rules";
        })
      ).toBe(true);
    });
  });

  it("refreshes the outflow summary after creating a manual cash entry", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Cash expense/i }));
    fireEvent.change(screen.getByLabelText("Amount (EUR)", { selector: "#cashflow-amount" }), {
      target: { value: "50.00" }
    });
    fireEvent.change(screen.getByLabelText("Description", { selector: "#cashflow-description" }), {
      target: { value: "Manual cash outflow" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Add entry" }));

    await waitFor(() => {
      expect(screen.getByText(/Created cash-flow entry\./)).toBeInTheDocument();
      expect(
        screen.getByText(
          new RegExp(`Receipts ${formatEurFromCents(84_000)} .* manual ${formatEurFromCents(13_400)}`)
        )
      ).toBeInTheDocument();
    });
  });

  it("derives summary cards from recurring items and cash-flow rows when summary totals lag", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();
        const monthMatch = url.pathname.match(/^\/api\/v1\/budget\/months\/(\d{4})\/(\d{1,2})(?:\/summary)?$/);
        const year = monthMatch ? Number(monthMatch[1]) : 2026;
        const monthNumber = monthMatch ? Number(monthMatch[2]) : 4;

        if (/^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}$/.test(url.pathname) && method === "GET") {
          return jsonResponse({
            year,
            month: monthNumber,
            planned_income_cents: 320000,
            target_savings_cents: 50000,
            opening_balance_cents: 25000,
            currency: "EUR",
            notes: "QA April budget"
          });
        }

        if (/^\/api\/v1\/budget\/months\/\d{4}\/\d{1,2}\/summary$/.test(url.pathname) && method === "GET") {
          return jsonResponse({
            period: { year, month: monthNumber },
            month: {
              year,
              month: monthNumber,
              planned_income_cents: 320000,
              target_savings_cents: 50000,
              opening_balance_cents: 25000,
              currency: "EUR",
              notes: "QA April budget"
            },
            totals: {
              planned_income_cents: 320000,
              actual_income_cents: 0,
              income_basis_cents: 0,
              income_basis: "planned_income",
              target_savings_cents: 50000,
              opening_balance_cents: 25000,
              receipt_spend_cents: 0,
              manual_outflow_cents: 0,
              total_outflow_cents: 0,
              recurring_expected_cents: 0,
              recurring_paid_cents: 0,
              available_cents: 0,
              remaining_cents: 0,
              saved_cents: 0,
              savings_delta_cents: 0
            },
            budget_rules: [],
            recurring: {
              count: 3,
              paid_count: 0,
              unpaid_count: 0,
              items: [
                {
                  occurrence_id: "occ-rent",
                  bill_id: "bill-rent",
                  bill_name: "QA Rent",
                  due_date: "2026-04-21",
                  status: "due",
                  expected_amount_cents: 120000,
                  actual_amount_cents: null
                },
                {
                  occurrence_id: "occ-streaming",
                  bill_id: "bill-streaming",
                  bill_name: "QA Streaming",
                  due_date: "2026-04-21",
                  status: "due",
                  expected_amount_cents: 1099,
                  actual_amount_cents: null
                },
                {
                  occurrence_id: "occ-internet",
                  bill_id: "bill-internet",
                  bill_name: "QA Internet Provider",
                  due_date: "2026-04-21",
                  status: "due",
                  expected_amount_cents: 4499,
                  actual_amount_cents: null
                }
              ]
            },
            cashflow: {
              count: 0,
              inflow_count: 0,
              outflow_count: 0,
              reconciled_count: 0
            }
          });
        }

        if (url.pathname === "/api/v1/cashflow-entries" && method === "GET") {
          return jsonResponse({
            count: 1,
            total: 1,
            items: [
              {
                id: "cf-manual",
                user_id: "u1",
                effective_date: "2026-04-21",
                direction: "outflow",
                category: "manual-adjustments",
                amount_cents: 23000,
                currency: "EUR",
                description: "QA manual outflow",
                source_type: "manual",
                linked_transaction_id: null,
                is_reconciled: false,
                linked_transaction: null,
                linked_recurring_occurrence_id: null,
                notes: "desktop retest",
                created_at: "2026-04-21T10:00:00Z",
                updated_at: "2026-04-21T10:00:00Z"
              }
            ]
          });
        }

        if (url.pathname === "/api/v1/analytics/budget-rules" && method === "GET") {
          return jsonResponse({ items: [], count: 0, total: 0 });
        }

        if (url.pathname === "/api/v1/analytics/budget" && method === "GET") {
          return jsonResponse({ rows: [] });
        }

        if (url.pathname === "/api/v1/transactions" && method === "GET") {
          return jsonResponse({ items: [], count: 0, total: 0, limit: 8, offset: 0 });
        }

        throw new Error(`Unexpected request ${method} ${url.pathname}`);
      })
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("QA Rent")).toBeInTheDocument();
      expect(screen.getByText(formatEurFromCents(125_598))).toBeInTheDocument();
      expect(
        screen.getByText(
          new RegExp(`Receipts ${escapeRegExp(formatEurFromCents(0))} .* manual ${escapeRegExp(formatEurFromCents(23_000))}`)
        )
      ).toBeInTheDocument();
      expect(
        screen.getByText(new RegExp(`Forecast ${escapeRegExp(formatEurFromCents(125_598))}`))
      ).toBeInTheDocument();
    });
  });
});
