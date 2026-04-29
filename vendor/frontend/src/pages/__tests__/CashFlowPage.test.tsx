import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CashFlowPage } from "../CashFlowPage";

const mocks = vi.hoisted(() => ({
  fetchBudgetSummaryMock: vi.fn(),
  fetchCashflowEntriesMock: vi.fn(),
  fetchRecurringCalendarMock: vi.fn()
}));

vi.mock("@/api/budget", () => ({
  fetchBudgetSummary: mocks.fetchBudgetSummaryMock,
  fetchCashflowEntries: mocks.fetchCashflowEntriesMock
}));

vi.mock("@/api/recurringBills", () => ({
  fetchRecurringCalendar: mocks.fetchRecurringCalendarMock
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CashFlowPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CashFlowPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
        },
        clear: () => {
          storage.clear();
        }
      }
    });

    mocks.fetchBudgetSummaryMock.mockResolvedValue({
      period: { year: 2026, month: 4 },
      month: null,
      totals: {
        planned_income_cents: 0,
        actual_income_cents: 0,
        income_basis_cents: 0,
        income_basis: "planned_income",
        target_savings_cents: 0,
        opening_balance_cents: 0,
        receipt_spend_cents: 0,
        manual_outflow_cents: 0,
        total_outflow_cents: 50_159,
        recurring_expected_cents: 0,
        recurring_paid_cents: 0,
        available_cents: 0,
        remaining_cents: 0,
        saved_cents: 0,
        savings_delta_cents: 0
      },
      budget_rules: [],
      recurring: {
        count: 0,
        paid_count: 0,
        unpaid_count: 0,
        items: []
      },
      cashflow: {
        count: 0,
        inflow_count: 0,
        outflow_count: 0,
        reconciled_count: 0
      }
    });
    mocks.fetchCashflowEntriesMock.mockResolvedValue({
      items: [
        {
          id: "cash-1",
          user_id: "user-1",
          effective_date: "2026-04-01",
          direction: "outflow",
          category: "cash",
          amount_cents: 24_900,
          currency: "EUR",
          description: "Bargeldausgabe",
          source_type: "manual_cash",
          linked_transaction_id: null,
          is_reconciled: false,
          linked_transaction: null,
          linked_recurring_occurrence_id: null,
          notes: null,
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z"
        }
      ],
      total: 1
    });
    mocks.fetchRecurringCalendarMock.mockResolvedValue({ year: 2026, month: 4, days: [], count: 0 });
  });

  it("uses its own current month and shows summary outflow including receipts", async () => {
    renderPage();

    await waitFor(() => {
      expect(mocks.fetchBudgetSummaryMock).toHaveBeenCalledWith(2026, 4);
      expect(mocks.fetchCashflowEntriesMock).toHaveBeenCalledWith(2026, 4);
      expect(mocks.fetchRecurringCalendarMock).toHaveBeenCalledWith({ year: 2026, month: 4 });
    });
    expect(await screen.findByText(/501[,.]59/)).toBeInTheDocument();
  });
});
