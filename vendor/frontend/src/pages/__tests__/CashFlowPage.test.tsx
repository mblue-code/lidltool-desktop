import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CashFlowPage } from "../CashFlowPage";

const mocks = vi.hoisted(() => ({
  fetchBudgetSummaryMock: vi.fn(),
  fetchCashflowEntriesMock: vi.fn(),
  fetchRecurringCalendarMock: vi.fn(),
  useDateRangeContextMock: vi.fn()
}));

vi.mock("@/api/budget", () => ({
  fetchBudgetSummary: mocks.fetchBudgetSummaryMock,
  fetchCashflowEntries: mocks.fetchCashflowEntriesMock
}));

vi.mock("@/api/recurringBills", () => ({
  fetchRecurringCalendar: mocks.fetchRecurringCalendarMock
}));

vi.mock("@/app/date-range-context", () => ({
  useDateRangeContext: mocks.useDateRangeContextMock
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

    mocks.useDateRangeContextMock.mockReturnValue({
      preset: "last_month",
      fromDate: "2026-03-01",
      toDate: "2026-03-31",
      comparisonFromDate: "2026-02-01",
      comparisonToDate: "2026-02-28",
      setPreset: vi.fn(),
      setCustomRange: vi.fn()
    });

    mocks.fetchBudgetSummaryMock.mockResolvedValue({
      period: { year: 2026, month: 3 },
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
    mocks.fetchCashflowEntriesMock.mockResolvedValue({ items: [], total: 0 });
    mocks.fetchRecurringCalendarMock.mockResolvedValue({ year: 2026, month: 3, days: [], count: 0 });
  });

  it("uses the shared date window month instead of the current clock month", async () => {
    renderPage();

    await waitFor(() => {
      expect(mocks.fetchBudgetSummaryMock).toHaveBeenCalledWith(2026, 3);
      expect(mocks.fetchCashflowEntriesMock).toHaveBeenCalledWith(2026, 3);
      expect(mocks.fetchRecurringCalendarMock).toHaveBeenCalledWith({ year: 2026, month: 3 });
    });
  });
});
