import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReportsPage } from "../ReportsPage";

const mocks = vi.hoisted(() => ({
  fetchDashboardYearsMock: vi.fn(),
  fetchMerchantSummaryMock: vi.fn(),
  fetchReportPatternsMock: vi.fn(),
  fetchReportSankeyMock: vi.fn(),
  fetchSharedGroupsMock: vi.fn(),
  fetchReportTemplatesMock: vi.fn(),
  fetchSourcesMock: vi.fn(),
  useAccessScopeMock: vi.fn(),
  useDateRangeContextMock: vi.fn(),
}));

vi.mock("@/api/dashboard", () => ({
  fetchDashboardYears: mocks.fetchDashboardYearsMock,
}));

vi.mock("@/api/merchants", () => ({
  fetchMerchantSummary: mocks.fetchMerchantSummaryMock,
}));

vi.mock("@/api/reports", async () => {
  const actual = await vi.importActual<typeof import("@/api/reports")>("@/api/reports");
  return {
    ...actual,
    fetchReportPatterns: mocks.fetchReportPatternsMock,
    fetchReportSankey: mocks.fetchReportSankeyMock,
    fetchReportTemplates: mocks.fetchReportTemplatesMock,
  };
});

vi.mock("@/api/shared-groups", () => ({
  fetchSharedGroups: mocks.fetchSharedGroupsMock,
}));

vi.mock("@/api/sources", () => ({
  fetchSources: mocks.fetchSourcesMock,
}));

vi.mock("@/app/date-range-context", () => ({
  useDateRangeContext: mocks.useDateRangeContextMock,
}));

vi.mock("@/app/scope-provider", () => ({
  useAccessScope: mocks.useAccessScopeMock,
}));

vi.mock("@/i18n", () => ({
  useI18n: () => ({
    locale: "en" as const,
    t: (key: string, values?: Record<string, unknown>) =>
      values
        ? key.replace(/\{(\w+)\}/g, (_, name) => String(values[name] ?? ""))
        : key,
  }),
  resolveIntlLocale: () => "en-US",
  localizeNode: (node: unknown) => node,
}));

function buildSankeyResponse(filters?: {
  fromDate?: string;
  toDate?: string;
  mode?: "combined" | "outflow_only";
  breakdown?: "merchant" | "subcategory_only" | "subcategory" | "subcategory_source" | "source";
  scopeOverride?: string;
}) {
  const yearlyWindow = filters?.fromDate === "2026-01-01";
  const scopedTotal = filters?.scopeOverride === "personal" ? 7000 : filters?.scopeOverride?.startsWith("group:") ? 9000 : 12000;
  const totalOutflow = yearlyWindow ? scopedTotal * 4 : scopedTotal;
  const totalBasis = yearlyWindow ? 96000 : 24000;
  const breakdown = filters?.breakdown ?? "merchant";
  const merchantNodes = [
    { id: "merchant:Lidl", label: "Lidl", kind: "merchant", layer: 2, amount_cents: totalOutflow, merchant_name: "Lidl" },
  ];
  const subcategoryNodes = [
    { id: "subcategory:groceries:fresh", label: "groceries:fresh", kind: "subcategory", layer: 2, amount_cents: totalOutflow, category_id: "groceries:fresh" },
    { id: "merchant:Lidl", label: "Lidl", kind: "merchant", layer: 3, amount_cents: totalOutflow, merchant_name: "Lidl" },
  ];
  const subcategoryOnlyNodes = [
    { id: "subcategory:groceries:meat", label: "groceries:meat", kind: "subcategory", layer: 2, amount_cents: totalOutflow, category_id: "groceries:meat" },
  ];
  const sourceNodes = [
    { id: "source:lidl_plus_de", label: "Lidl Plus DE", kind: "source", layer: 2, amount_cents: totalOutflow, source_id: "lidl_plus_de" },
  ];
  const subcategorySourceNodes = [
    { id: "subcategory:groceries:fresh", label: "groceries:fresh", kind: "subcategory", layer: 2, amount_cents: totalOutflow, category_id: "groceries:fresh" },
    { id: "source:lidl_plus_de", label: "Lidl Plus DE", kind: "source", layer: 3, amount_cents: totalOutflow, source_id: "lidl_plus_de" },
  ];
  const breakdownNodes = breakdown === "subcategory"
    ? subcategoryNodes
    : breakdown === "subcategory_source"
      ? subcategorySourceNodes
    : breakdown === "subcategory_only"
      ? subcategoryOnlyNodes
      : breakdown === "source"
        ? sourceNodes
        : merchantNodes;
  const breakdownLinks = breakdown === "subcategory"
    ? [
        { source: "category:groceries", target: "subcategory:groceries:fresh", value_cents: totalOutflow, kind: "category_to_subcategory" },
        { source: "subcategory:groceries:fresh", target: "merchant:Lidl", value_cents: totalOutflow, kind: "subcategory_to_merchant" },
      ]
    : breakdown === "subcategory_source"
      ? [
          { source: "category:groceries", target: "subcategory:groceries:fresh", value_cents: totalOutflow, kind: "category_to_subcategory" },
          { source: "subcategory:groceries:fresh", target: "source:lidl_plus_de", value_cents: totalOutflow, kind: "subcategory_to_source" },
        ]
    : breakdown === "subcategory_only"
      ? [
          { source: "category:groceries", target: "subcategory:groceries:meat", value_cents: totalOutflow, kind: "category_to_subcategory" },
        ]
    : breakdown === "source"
      ? [
          { source: "category:groceries", target: "source:lidl_plus_de", value_cents: totalOutflow, kind: "category_to_source" },
        ]
      : [
          { source: "category:groceries", target: "merchant:Lidl", value_cents: totalOutflow, kind: "category_to_merchant" },
        ];

  return {
    period: { from_date: filters?.fromDate ?? "2026-04-01", to_date: filters?.toDate ?? "2026-04-30" },
    mode: filters?.mode ?? "combined",
    breakdown,
    model: { kind: "period_proportional_inflow_to_outflow_category_merchant", transaction_provenance_supported: false },
    flags: {
      aggregated_inflows: false,
      aggregated_categories: false,
      aggregated_merchants: false,
      aggregated_subcategories: false,
      aggregated_sources: false,
      manual_inflows_excluded_by_source_filter: false,
      synthetic_inflow_bucket: false,
    },
    summary: {
      total_outflow_cents: totalOutflow,
      total_inflow_basis_cents: totalBasis,
      node_count: 2 + breakdownNodes.length,
      link_count: 1 + breakdownLinks.length,
    },
    nodes: [
      { id: "inflow:income:salary", label: "income:salary", kind: "inflow", layer: 0, amount_cents: totalOutflow, basis_amount_cents: totalBasis },
      { id: "category:groceries", label: "groceries", kind: "outflow_category", layer: 1, amount_cents: totalOutflow, category_id: "groceries" },
      ...breakdownNodes,
    ],
    links: [
      { source: "inflow:income:salary", target: "category:groceries", value_cents: totalOutflow, kind: "period_proportional_attribution" },
      ...breakdownLinks,
    ],
  };
}

function renderPage(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ReportsPage />
    </QueryClientProvider>,
  );
}

describe("ReportsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.useDateRangeContextMock.mockReturnValue({
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      setPreset: vi.fn(),
      setCustomRange: vi.fn(),
    });
    mocks.useAccessScopeMock.mockReturnValue({
      scope: "personal",
      workspace: { kind: "personal" },
      setScope: vi.fn(),
      setWorkspace: vi.fn(),
    });
    mocks.fetchDashboardYearsMock.mockResolvedValue({
      years: [2023, 2024, 2025, 2026],
      min_year: 2023,
      max_year: 2026,
      latest_year: 2026,
    });
    mocks.fetchSharedGroupsMock.mockResolvedValue({
      count: 1,
      groups: [
        {
          group_id: "group-1",
          name: "Household",
          group_type: "household",
          status: "active",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          created_by_user: null,
          viewer_role: "owner",
          viewer_membership_status: "active",
          can_manage: true,
          owner_count: 1,
          member_count: 2,
          members: [],
        },
      ],
    });
    mocks.fetchReportTemplatesMock.mockResolvedValue({
      templates: [
        {
          slug: "monthly-overview",
          title: "Monthly overview",
          description: "Summary",
          payload: { total_cents: 12345 },
        },
      ],
    });
    mocks.fetchSourcesMock.mockResolvedValue({
      sources: [
        { id: "lidl_plus_de", display_name: "Lidl Plus DE", kind: "connector", status: "ready", enabled: true },
        { id: "rewe_de", display_name: "Rewe DE", kind: "connector", status: "ready", enabled: true },
      ],
    });
    mocks.fetchMerchantSummaryMock.mockResolvedValue({
      items: [
        { merchant: "Lidl", receipt_count: 2, spend_cents: 12345, last_purchased_at: "2026-04-10T10:00:00Z", source_ids: ["lidl_plus_de"] },
        { merchant: "REWE", receipt_count: 1, spend_cents: 4500, last_purchased_at: "2026-04-11T11:00:00Z", source_ids: ["rewe_de"] },
      ],
    });
    mocks.fetchReportPatternsMock.mockResolvedValue({
      daily_heatmap: [{ date: "2026-04-10", amount_cents: 12345, count: 2 }],
      weekday_heatmap: [{ weekday: 4, amount_cents: 12345, count: 2 }],
      weekday_hour_matrix: [{ weekday: 5, hour: 18, amount_cents: 12345, count: 2 }],
      merchant_profiles: [],
      merchant_comparison: [{ merchant: "Lidl", amount_cents: 12345, count: 2, average_cents: 6173 }],
      insights: [{ kind: "top_merchant", merchant: "Lidl", amount_cents: 12345 }],
    });
    mocks.fetchReportSankeyMock.mockImplementation(async (filters?: { fromDate?: string; toDate?: string; mode?: "combined" | "outflow_only"; breakdown?: "merchant" | "subcategory_only" | "subcategory" | "subcategory_source" | "source"; scopeOverride?: string }) => (
      buildSankeyResponse(filters)
    ));
  });

  afterEach(() => {
    cleanup();
  });

  it("renders report sections and fetches the combined sankey by default", async () => {
    renderPage();

    expect(await screen.findByText("pages.reports.patterns.title")).toBeInTheDocument();
    expect(screen.getByText("Date range")).toBeInTheDocument();
    expect(screen.getByText("Weekly heatmap")).toBeInTheDocument();
    expect(screen.getByText("Weekly hourly heatmap")).toBeInTheDocument();
    expect(screen.getByText("Cashflow sankey")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Combined" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Export PNG" })).toBeInTheDocument();
    expect(screen.getByText("pages.reports.patterns.merchantComparison")).toBeInTheDocument();
    expect(await screen.findAllByText("Lidl")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "pages.reports.exportJson" })).toBeInTheDocument();

    await waitFor(() => {
      expect(mocks.fetchReportPatternsMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        valueMode: "amount",
      });
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "merchant",
        topN: 8,
      });
    });
  });

  it("switches the sankey mode and refetches with outflow-only", async () => {
    renderPage();

    const outflowTab = await screen.findByRole("tab", { name: "Outflow only" });
    fireEvent.click(outflowTab);

    await waitFor(() => {
      expect(outflowTab).toHaveAttribute("data-state", "active");
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "outflow_only",
        breakdown: "merchant",
        topN: 8,
      });
    });
  });

  it("switches the sankey breakdown and refetches with subcategory-only grouping", async () => {
    renderPage();

    const subcategoriesTab = await screen.findByRole("tab", { name: "Subcategories" });
    fireEvent.click(subcategoriesTab);

    await waitFor(() => {
      expect(subcategoriesTab).toHaveAttribute("data-state", "active");
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "subcategory_only",
        topN: 8,
      });
    });
  });

  it("switches the sankey breakdown and refetches with source grouping", async () => {
    renderPage();

    const sourceTab = await screen.findByRole("tab", { name: "Sources" });
    fireEvent.click(sourceTab);

    await waitFor(() => {
      expect(sourceTab).toHaveAttribute("data-state", "active");
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "source",
        topN: 8,
      });
    });
  });

  it("switches the sankey breakdown and refetches with subcategory-to-merchant grouping", async () => {
    renderPage();

    const subcategoryMerchantTab = await screen.findByRole("tab", { name: "Subcategories + merchants" });
    fireEvent.click(subcategoryMerchantTab);

    await waitFor(() => {
      expect(subcategoryMerchantTab).toHaveAttribute("data-state", "active");
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "subcategory",
        topN: 8,
      });
    });
  });

  it("switches the sankey breakdown and refetches with subcategory-to-source grouping", async () => {
    renderPage();

    const subcategorySourceTab = await screen.findByRole("tab", { name: "Subcategories + sources" });
    fireEvent.click(subcategorySourceTab);

    await waitFor(() => {
      expect(subcategorySourceTab).toHaveAttribute("data-state", "active");
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-30",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "subcategory_source",
        topN: 8,
      });
    });
  });

  it("offers sankey-specific time views and refetches the sankey window", async () => {
    mocks.useDateRangeContextMock.mockReturnValue({
      fromDate: "2026-04-14",
      toDate: "2026-04-20",
      setPreset: vi.fn(),
      setCustomRange: vi.fn(),
    });

    renderPage();

    const monthTab = await screen.findByRole("tab", { name: "Month" });
    const yearTab = screen.getByRole("tab", { name: "Year" });
    const avgMonthTab = screen.getByRole("tab", { name: "Avg month" });

    fireEvent.click(monthTab);

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-04-01",
        toDate: "2026-04-20",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "merchant",
        topN: 8,
      });
    });

    fireEvent.click(yearTab);

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenLastCalledWith({
        fromDate: "2026-01-01",
        toDate: "2026-04-20",
        merchants: [],
        financeCategoryId: undefined,
        direction: undefined,
        sourceIds: [],
        mode: "combined",
        breakdown: "merchant",
        topN: 8,
      });
    });

    fireEvent.click(avgMonthTab);

    await waitFor(() => {
      expect(avgMonthTab).toHaveAttribute("data-state", "active");
    });

    expect(screen.getByText("Avg month scales the year-to-date window down to one average month.")).toBeInTheDocument();
  });

  it("lets the user hide an individual sankey flow and reset the edited view", async () => {
    const { container } = renderPage();

    await screen.findByText("Cashflow sankey");
    await screen.findAllByText("Lidl");

    const flow = await waitFor(() => {
      const node = container.querySelector('[data-link-key="category:groceries->merchant:Lidl"]');
      expect(node).not.toBeNull();
      return node as Element;
    });

    fireEvent.click(flow);

    expect(await screen.findByText("Selected link")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Hide selected link" }));

    await waitFor(() => {
      expect(container.querySelector('[data-link-key="category:groceries->merchant:Lidl"]')).toBeNull();
    });

    expect(container.querySelector('[data-link-key="inflow:income:salary->category:groceries"]')).not.toBeNull();
    expect(screen.getByText("Click a flow band or node in the diagram to hide it from this view.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));

    await waitFor(() => {
      expect(container.querySelector('[data-link-key="category:groceries->merchant:Lidl"]')).not.toBeNull();
    });
  });

  it("supports renaming a sankey node for the current view", async () => {
    const { container } = renderPage();

    await screen.findByText("Cashflow sankey");
    const node = await waitFor(() => {
      const match = container.querySelector('[data-node-id="inflow:income:salary"]');
      expect(match).not.toBeNull();
      return match as Element;
    });

    fireEvent.doubleClick(node);

    const input = await screen.findByLabelText("Visible label");
    fireEvent.change(input, { target: { value: "Income" } });
    fireEvent.click(screen.getByRole("button", { name: "Save label" }));

    expect(screen.getAllByText("Income").length).toBeGreaterThan(0);
    await waitFor(() => {
      const renamedNode = container.querySelector('[data-node-id="inflow:income:salary"]');
      expect(renamedNode?.textContent ?? "").toContain("Income");
    });
    expect(screen.getByText("Renamed labels")).toBeInTheDocument();
  });

  it("loads separate personal and shared-group sankeys for workspace compare", async () => {
    const { container } = renderPage();

    const compareTab = await screen.findByRole("tab", { name: "Personal + shared group" });
    await waitFor(() => {
      expect(compareTab).not.toBeDisabled();
    });
    fireEvent.click(compareTab);

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenCalledWith(expect.objectContaining({
        scopeOverride: "personal",
        mode: "outflow_only",
      }));
    });

    await waitFor(() => {
      expect(mocks.fetchReportSankeyMock).toHaveBeenCalledWith(expect.objectContaining({
        scopeOverride: "group:group-1",
        mode: "outflow_only",
      }));
    });

    await waitFor(() => {
      const personalNode = container.querySelector('[data-node-id="workspace:personal"]');
      const sharedNode = container.querySelector('[data-node-id="workspace:shared_group"]');
      expect(personalNode?.textContent ?? "").toContain("Personal");
      expect(sharedNode?.textContent ?? "").toContain("Household");
    });
  });

  it("renders the sankey empty state when no nodes are available", async () => {
    mocks.fetchReportSankeyMock.mockResolvedValueOnce({
      ...buildSankeyResponse(),
      summary: {
        total_outflow_cents: 0,
        total_inflow_basis_cents: 0,
        node_count: 0,
        link_count: 0,
      },
      nodes: [],
      links: [],
    });

    renderPage();

    expect(await screen.findByText("No flow data is available for the current filters.")).toBeInTheDocument();
  });

  it("shows the sankey loading state before the dedicated query resolves", async () => {
    mocks.fetchReportSankeyMock.mockImplementationOnce(() => new Promise(() => {}));

    renderPage();

    expect(await screen.findByText("Loading sankey diagram...")).toBeInTheDocument();
  });

  it("does not keep stale sankey data visible while a new sankey view is loading", async () => {
    const dateRange = {
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      setPreset: vi.fn(),
      setCustomRange: vi.fn(),
    };
    mocks.useDateRangeContextMock.mockImplementation(() => dateRange);

    let resolveYearly: ((value: unknown) => void) | null = null;
    mocks.fetchReportSankeyMock.mockImplementation((filters?: { fromDate?: string; toDate?: string; mode?: "combined" | "outflow_only"; breakdown?: "merchant" | "subcategory_only" | "subcategory" | "source" }) => {
      if (filters?.fromDate === "2025-01-01" && filters?.toDate === "2025-12-31") {
        return new Promise((resolve) => {
          resolveYearly = resolve;
        });
      }
      return Promise.resolve(buildSankeyResponse(filters));
    });

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    const view = render(
      <QueryClientProvider client={queryClient}>
        <ReportsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Cashflow sankey")).toBeInTheDocument();
    expect(await screen.findByText("Sankey window: Apr 1, 2026 - Apr 30, 2026")).toBeInTheDocument();

    dateRange.fromDate = "2025-01-01";
    dateRange.toDate = "2025-12-31";

    view.rerender(
      <QueryClientProvider client={queryClient}>
        <ReportsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Loading sankey diagram...")).toBeInTheDocument();
    expect(screen.queryByText("Sankey window: Apr 1, 2026 - Apr 30, 2026")).not.toBeInTheDocument();
    expect(screen.getByText("Sankey window: Jan 1, 2025 - Dec 31, 2025")).toBeInTheDocument();

    if (!resolveYearly) {
      throw new Error("Expected yearly sankey request to be pending");
    }
    (resolveYearly as (value: unknown) => void)(buildSankeyResponse({ fromDate: "2025-01-01", toDate: "2025-12-31" }));

    await waitFor(() => {
      expect(screen.getByText("Sankey window: Jan 1, 2025 - Dec 31, 2025")).toBeInTheDocument();
    });
  });
});
