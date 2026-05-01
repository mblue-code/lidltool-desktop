import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportsPage } from "../ReportsPage";

const mocks = vi.hoisted(() => ({
  fetchDashboardYearsMock: vi.fn(),
  fetchMerchantSummaryMock: vi.fn(),
  fetchReportPatternsMock: vi.fn(),
  fetchReportTemplatesMock: vi.fn(),
  fetchSourcesMock: vi.fn(),
  useDateRangeContextMock: vi.fn()
}));

vi.mock("@/api/dashboard", () => ({
  fetchDashboardYears: mocks.fetchDashboardYearsMock
}));

vi.mock("@/api/merchants", () => ({
  fetchMerchantSummary: mocks.fetchMerchantSummaryMock
}));

vi.mock("@/api/reports", () => ({
  fetchReportPatterns: mocks.fetchReportPatternsMock,
  fetchReportTemplates: mocks.fetchReportTemplatesMock
}));

vi.mock("@/api/sources", () => ({
  fetchSources: mocks.fetchSourcesMock
}));

vi.mock("@/app/date-range-context", () => ({
  useDateRangeContext: mocks.useDateRangeContextMock
}));

vi.mock("@/i18n", () => ({
  useI18n: () => ({
    locale: "en" as const,
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? key.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""))
        : key
  }),
  resolveIntlLocale: () => "en-US",
  localizeNode: (node: unknown) => node
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <ReportsPage />
    </QueryClientProvider>
  );
}

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useDateRangeContextMock.mockReturnValue({
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      setPreset: vi.fn(),
      setCustomRange: vi.fn()
    });
    mocks.fetchDashboardYearsMock.mockResolvedValue({
      years: [2023, 2024, 2025, 2026],
      min_year: 2023,
      max_year: 2026,
      latest_year: 2026
    });
    mocks.fetchReportTemplatesMock.mockResolvedValue({
      templates: [
        {
          slug: "monthly-overview",
          title: "Monthly overview",
          description: "Summary",
          payload: { total_cents: 12345 }
        }
      ]
    });
    mocks.fetchSourcesMock.mockResolvedValue({
      sources: [
        { id: "lidl_plus_de", display_name: "Lidl Plus DE", kind: "connector", status: "ready", enabled: true },
        { id: "rewe_de", display_name: "Rewe DE", kind: "connector", status: "ready", enabled: true }
      ]
    });
    mocks.fetchMerchantSummaryMock.mockResolvedValue({
      items: [
        { merchant: "Lidl", receipt_count: 2, spend_cents: 12345, last_purchased_at: "2026-04-10T10:00:00Z", source_ids: ["lidl_plus_de"] },
        { merchant: "REWE", receipt_count: 1, spend_cents: 4500, last_purchased_at: "2026-04-11T11:00:00Z", source_ids: ["rewe_de"] }
      ]
    });
    mocks.fetchReportPatternsMock.mockResolvedValue({
      daily_heatmap: [{ date: "2026-04-10", amount_cents: 12345, count: 2 }],
      weekday_heatmap: [{ weekday: 4, amount_cents: 12345, count: 2 }],
      weekday_hour_matrix: [{ weekday: 5, hour: 18, amount_cents: 12345, count: 2 }],
      merchant_profiles: [],
      merchant_comparison: [{ merchant: "Lidl", amount_cents: 12345, count: 2 }],
      insights: [{ kind: "top_merchant", merchant: "Lidl", amount_cents: 12345 }]
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders localized pattern recognition sections and keeps JSON export available", async () => {
    renderPage();

    expect(await screen.findByText("pages.reports.patterns.title")).toBeInTheDocument();
    expect(screen.getByText("Date range")).toBeInTheDocument();
    expect(screen.getByText("Weekly heatmap")).toBeInTheDocument();
    expect(screen.getByText("Weekly hourly heatmap")).toBeInTheDocument();
    expect(screen.getByText("pages.reports.patterns.merchantComparison")).toBeInTheDocument();
    expect(await screen.findByText("Lidl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "pages.reports.exportJson" })).toBeInTheDocument();

    await waitFor(() => {
      expect(mocks.fetchReportPatternsMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        valueMode: "amount"
      });
    });
  });
});
