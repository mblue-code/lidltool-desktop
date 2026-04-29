import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportsPage } from "../ReportsPage";

const mocks = vi.hoisted(() => ({
  fetchReportTemplatesMock: vi.fn(),
  useDateRangeContextMock: vi.fn()
}));

vi.mock("@/api/reports", () => ({
  fetchReportTemplates: mocks.fetchReportTemplatesMock
}));

vi.mock("@/app/date-range-context", () => ({
  useDateRangeContext: mocks.useDateRangeContextMock
}));

vi.mock("@/i18n", () => ({
  useI18n: () => ({
    locale: "en" as const
  }),
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
      preset: "this_month",
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      comparisonFromDate: "2026-03-01",
      comparisonToDate: "2026-03-31",
      setPreset: vi.fn(),
      setCustomRange: vi.fn()
    });
    mocks.fetchReportTemplatesMock.mockResolvedValue({
      templates: [
        {
          slug: "monthly-overview",
          title: "Monthly overview",
          description: "Summary",
          payload: {
            total_cents: 12345,
            categories: [{ category: "groceries", amount_cents: 12345 }]
          }
        }
      ]
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("foregrounds CSV export and keeps JSON as raw data", async () => {
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURLMock = vi.fn((value: Blob | MediaSource) => {
      void value;
      return "blob:report-csv";
    });
    const revokeObjectURLMock = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURLMock });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURLMock });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      renderPage();

      const csvButton = await screen.findByRole("button", { name: "Export CSV" });
      expect(screen.getByRole("button", { name: "Raw JSON" })).toBeInTheDocument();
      expect(screen.getByText(/CSV is the user-facing export view/)).toBeInTheDocument();

      fireEvent.click(csvButton);

      await waitFor(() => {
        expect(createObjectURLMock).toHaveBeenCalled();
      });
      const blob = createObjectURLMock.mock.calls[0]?.[0] as Blob;
      expect(await blob.text()).toContain("category,amount_cents");
      expect(clickSpy).toHaveBeenCalled();
      await waitFor(() => {
        expect(revokeObjectURLMock).toHaveBeenCalledWith("blob:report-csv");
      });
    } finally {
      clickSpy.mockRestore();
      Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectURL });
      Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectURL });
    }
  });
});
