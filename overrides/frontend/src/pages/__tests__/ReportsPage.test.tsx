import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportsPage } from "../ReportsPage";

const mocks = vi.hoisted(() => ({
  fetchReportPatternsMock: vi.fn(),
  fetchReportTemplatesMock: vi.fn(),
  useDateRangeContextMock: vi.fn()
}));

vi.mock("@/api/reports", () => ({
  fetchReportPatterns: mocks.fetchReportPatternsMock,
  fetchReportTemplates: mocks.fetchReportTemplatesMock
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
      toDate: "2026-04-30"
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
    mocks.fetchReportPatternsMock.mockResolvedValue({
      daily_heatmap: [{ date: "2026-04-10", amount_cents: 12345, count: 2 }],
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
    expect(screen.getByText("pages.reports.patterns.dailyHeatmap")).toBeInTheDocument();
    expect(screen.getByText("pages.reports.patterns.weekdayHour")).toBeInTheDocument();
    expect(screen.getByText("pages.reports.patterns.merchantComparison")).toBeInTheDocument();
    expect(await screen.findByText("Lidl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "pages.reports.exportJson" })).toBeInTheDocument();

    await waitFor(() => {
      expect(mocks.fetchReportPatternsMock).toHaveBeenCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        valueMode: "amount"
      });
    });
  });
});
