import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CashFlowPage } from "../CashFlowPage";

const mocks = vi.hoisted(() => ({
  fetchBudgetSummaryMock: vi.fn(),
  fetchCashflowEntriesMock: vi.fn(),
  fetchTransactionsMock: vi.fn()
}));

vi.mock("@/api/budget", () => ({
  fetchBudgetSummary: mocks.fetchBudgetSummaryMock,
  fetchCashflowEntries: mocks.fetchCashflowEntriesMock
}));

vi.mock("@/api/transactions", () => ({
  fetchTransactions: mocks.fetchTransactionsMock
}));

function renderPage(initialEntry = "/cashflow?year=2026&month=4"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <CashFlowPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("CashFlowPage", () => {
  afterEach(() => {
    cleanup();
  });

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
      count: 1,
      total: 1
    });
    mocks.fetchTransactionsMock.mockImplementation(({ direction, year, month }) => Promise.resolve({
      count: direction === "outflow" && year === 2026 && month === 4 ? 1 : 0,
      total: direction === "outflow" && year === 2026 && month === 4 ? 1 : 0,
      limit: 1000,
      offset: 0,
      summary: {
        count: direction === "outflow" && year === 2026 && month === 4 ? 1 : 0,
        total_cents: direction === "outflow" && year === 2026 && month === 4 ? 25_259 : 0,
        inflow_cents: 0,
        outflow_cents: direction === "outflow" && year === 2026 && month === 4 ? 25_259 : 0
      },
      items: direction === "outflow" && year === 2026 && month === 4 ? [
        {
          id: "tx-lidl",
          purchased_at: "2026-04-30T10:46:00Z",
          source_id: "lidl_plus_de",
          user_id: "user-1",
          source_transaction_id: "source-tx-lidl",
          store_name: "Lidl Isenbüttel",
          total_gross_cents: 25_259,
          discount_total_cents: 0,
          currency: "EUR",
          direction: "outflow",
          finance_category_id: "groceries"
        }
      ] : []
    }));
  });

  it("uses the selected month for totals and rows", async () => {
    renderPage();

    await waitFor(() => {
      expect(mocks.fetchBudgetSummaryMock).toHaveBeenCalledWith(2026, 4);
      expect(mocks.fetchCashflowEntriesMock).toHaveBeenCalledWith(2026, 4);
    });
    expect(mocks.fetchTransactionsMock).toHaveBeenCalledWith(expect.objectContaining({ direction: "outflow", year: 2026, month: 4 }));
    expect(await screen.findByText(/501[,.]59/)).toBeInTheDocument();
    expect(await screen.findByText("Lidl Isenbüttel")).toBeInTheDocument();
    expect(screen.getByText("Bargeldausgabe")).toBeInTheDocument();
  });

  it("updates the whole page when the month changes", async () => {
    mocks.fetchBudgetSummaryMock.mockImplementation((year: number, month: number) => Promise.resolve({
      period: { year, month },
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
        total_outflow_cents: month === 3 ? 11_024 : 50_159,
        recurring_expected_cents: 0,
        recurring_paid_cents: 0,
        available_cents: 0,
        remaining_cents: month === 3 ? 88_976 : 0,
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
    }));
    mocks.fetchCashflowEntriesMock.mockImplementation((year: number, month: number) => Promise.resolve({
      count: 1,
      total: 1,
      items: [
        {
          id: `cash-${year}-${month}`,
          user_id: "user-1",
          effective_date: month === 3 ? "2026-03-15" : "2026-04-01",
          direction: "outflow",
          category: "cash",
          amount_cents: month === 3 ? 11_024 : 24_900,
          currency: "EUR",
          description: month === 3 ? "March Manual" : "Bargeldausgabe",
          source_type: "manual_cash",
          linked_transaction_id: null,
          is_reconciled: false,
          linked_transaction: null,
          linked_recurring_occurrence_id: null,
          notes: null,
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z"
        }
      ]
    }));
    mocks.fetchTransactionsMock.mockImplementation(({ direction, year, month }) => Promise.resolve({
      count: direction === "outflow" ? 1 : 0,
      total: direction === "outflow" ? 1 : 0,
      limit: 1000,
      offset: 0,
      summary: {
        count: direction === "outflow" ? 1 : 0,
        total_cents: direction === "outflow" ? (month === 3 ? 11_024 : 25_259) : 0,
        inflow_cents: 0,
        outflow_cents: direction === "outflow" ? (month === 3 ? 11_024 : 25_259) : 0
      },
      items: direction === "outflow" ? [
        {
          id: `tx-${year}-${month}`,
          purchased_at: month === 3 ? "2026-03-30T10:46:00Z" : "2026-04-30T10:46:00Z",
          source_id: "lidl_plus_de",
          user_id: "user-1",
          source_transaction_id: `source-tx-${year}-${month}`,
          store_name: month === 3 ? "March Store" : "Lidl Isenbüttel",
          total_gross_cents: month === 3 ? 11_024 : 25_259,
          discount_total_cents: 0,
          currency: "EUR",
          direction: "outflow",
          finance_category_id: "groceries"
        }
      ] : []
    }));

    renderPage();

    await screen.findByText("April 2026");
    expect(await screen.findByText(/501[,.]59/)).toBeInTheDocument();
    expect(await screen.findByText("Lidl Isenbüttel")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Previous month" })[0]);

    await waitFor(() => {
      expect(mocks.fetchBudgetSummaryMock).toHaveBeenCalledWith(2026, 3);
      expect(mocks.fetchCashflowEntriesMock).toHaveBeenCalledWith(2026, 3);
      expect(mocks.fetchTransactionsMock).toHaveBeenCalledWith(expect.objectContaining({ direction: "outflow", year: 2026, month: 3 }));
    });
    expect(await screen.findByText("March 2026")).toBeInTheDocument();
    expect((await screen.findAllByText(/110[,.]24/)).length).toBeGreaterThan(0);
    expect(await screen.findByText("March Store")).toBeInTheDocument();
    expect(screen.getByText("March Manual")).toBeInTheDocument();
  });

  it("shows income rows on the income tab", async () => {
    mocks.fetchCashflowEntriesMock.mockResolvedValueOnce({
      count: 1,
      total: 1,
      items: [
        {
          id: "cash-income",
          user_id: "user-1",
          effective_date: "2026-04-28",
          direction: "inflow",
          category: "income",
          amount_cents: 260_814,
          currency: "EUR",
          description: "RUHRMEDIC GMBH",
          source_type: "manual",
          linked_transaction_id: null,
          is_reconciled: false,
          linked_transaction: null,
          linked_recurring_occurrence_id: null,
          notes: null,
          created_at: "2026-04-28T00:00:00Z",
          updated_at: "2026-04-28T00:00:00Z"
        }
      ]
    });
    renderPage("/cashflow?year=2026&month=4&view=inflow");

    expect(await screen.findByText("RUHRMEDIC GMBH")).toBeInTheDocument();
    expect(mocks.fetchTransactionsMock).toHaveBeenCalledWith(expect.objectContaining({ direction: "inflow", year: 2026, month: 4 }));
  });
});
