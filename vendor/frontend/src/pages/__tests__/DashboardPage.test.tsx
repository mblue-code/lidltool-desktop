import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPage } from "../DashboardPage";

const mocks = vi.hoisted(() => ({
  fetchDashboardOverviewMock: vi.fn(),
  useDateRangeContextMock: vi.fn()
}));

vi.mock("@/api/dashboard", () => ({
  fetchDashboardOverview: mocks.fetchDashboardOverviewMock
}));

vi.mock("@/app/date-range-context", () => ({
  useDateRangeContext: mocks.useDateRangeContextMock
}));

vi.mock("@/i18n", () => ({
  useI18n: () => ({
    locale: "en" as const,
    tText: (value: string) => value
  }),
  resolveIntlLocale: () => "en-US",
  localizeNode: (node: unknown) => node
}));

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

function dashboardOverview(overrides: Record<string, unknown> = {}) {
  return {
    period: {
      from_date: "2026-04-01",
      to_date: "2026-04-30",
      comparison_from_date: "2026-03-01",
      comparison_to_date: "2026-03-31"
    },
    kpis: {
      total_spending: { current_cents: 12345, previous_cents: 10000, delta_pct: 0.2345 },
      groceries: { current_cents: 9876, previous_cents: 8000, delta_pct: 0.2345 },
      cash_inflow: { current_cents: 250000, previous_cents: 240000, delta_pct: 0.0417 },
      cash_outflow: { current_cents: 54321, previous_cents: 50000, delta_pct: 0.0864 }
    },
    spending_overview: {
      total_cents: 12345,
      categories: [
        { category: "groceries", amount_cents: 12345, share: 1 }
      ]
    },
    cash_flow_summary: {
      points: [
        { date: "2026-04-10", inflow_cents: 10000, outflow_cents: 4000, net_cents: 6000 }
      ]
    },
    upcoming_bills: {
      count: 1,
      items: [
        { occurrence_id: "occ-1", bill_name: "Internet", due_date: "2026-04-25", expected_amount_cents: 4900 }
      ]
    },
    recent_grocery_transactions: {
      items: [
        { id: "tx-1", store_name: "QA Markt", source_id: "manual_entry", purchased_at: "2026-04-22T12:00:00Z", total_gross_cents: 12345 }
      ]
    },
    budget_progress: {
      items: [
        { rule_id: "rule-1", scope_value: "groceries", spent_cents: 12345, budget_cents: 30000, utilization: 0.4115 }
      ]
    },
    recent_activity: {
      count: 1,
      items: [
        { id: "activity-1", title: "Manual receipt added", subtitle: "QA Markt", amount_cents: 12345, occurred_at: "2026-04-22T12:00:00Z", href: "/transactions/tx-1" }
      ]
    },
    merchants: {
      count: 1,
      items: [
        { merchant: "QA Markt", receipt_count: 1, spend_cents: 12345 }
      ]
    },
    insight: {
      title: "Spend is concentrated in groceries",
      body: "Groceries account for the majority of the selected period.",
      href: "/groceries"
    },
    ...overrides
  };
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useDateRangeContextMock.mockReturnValue({
      preset: "this_month",
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      comparisonFromDate: "2026-03-01",
      comparisonToDate: "2026-03-31",
      setPreset: vi.fn(),
      setCustomRange: vi.fn()
    });
    mocks.fetchDashboardOverviewMock.mockResolvedValue(dashboardOverview());
  });

  afterEach(() => {
    cleanup();
  });

  it("loads the finance overview from the shared dashboard window", async () => {
    renderDashboardRoute();

    await waitFor(() => {
      expect(mocks.fetchDashboardOverviewMock).toHaveBeenCalledWith("2026-04-01", "2026-04-30");
    });

    expect(await screen.findByText("Your finance overview")).toBeInTheDocument();
    expect(screen.getByText("Spend is concentrated in groceries")).toBeInTheDocument();
    expect(screen.getByText("Manual receipt added")).toBeInTheDocument();
  });

  it("derives the hero date label from the selected dashboard range", async () => {
    mocks.useDateRangeContextMock.mockReturnValue({
      preset: "last_7_days",
      fromDate: "2026-04-21",
      toDate: "2026-04-27",
      comparisonFromDate: "2026-04-14",
      comparisonToDate: "2026-04-20",
      setPreset: vi.fn(),
      setCustomRange: vi.fn()
    });
    mocks.fetchDashboardOverviewMock.mockResolvedValueOnce(dashboardOverview({
      period: {
        from_date: "2026-04-01",
        to_date: "2026-04-30",
        comparison_from_date: "2026-03-01",
        comparison_to_date: "2026-03-31"
      }
    }));

    renderDashboardRoute();

    expect(await screen.findByText("Your finance overview")).toBeInTheDocument();
    expect(screen.getByText("Apr 21 - Apr 27")).toBeInTheDocument();
    expect(screen.queryByText("Apr 1 - Apr 30")).not.toBeInTheDocument();
  });

  it("shows a deliberate empty state instead of an empty spending donut", async () => {
    mocks.fetchDashboardOverviewMock.mockResolvedValueOnce(dashboardOverview({
      kpis: {
        total_spending: { current_cents: 0, previous_cents: 0, delta_pct: null },
        groceries: { current_cents: 0, previous_cents: 0, delta_pct: null },
        cash_inflow: { current_cents: 0, previous_cents: 0, delta_pct: null },
        cash_outflow: { current_cents: 0, previous_cents: 0, delta_pct: null }
      },
      spending_overview: {
        total_cents: 0,
        categories: []
      },
      cash_flow_summary: {
        points: []
      },
      upcoming_bills: { count: 0, items: [] },
      recent_grocery_transactions: { items: [] },
      budget_progress: { items: [] },
      recent_activity: { count: 0, items: [] },
      merchants: { count: 0, items: [] },
      insight: {
        title: "No spending yet",
        body: "Import receipts to populate the dashboard.",
        href: "/imports/ocr"
      }
    }));

    renderDashboardRoute();

    expect(await screen.findByText("No spending in the selected period yet")).toBeInTheDocument();
  });
});
