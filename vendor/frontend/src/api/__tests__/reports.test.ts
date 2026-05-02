import { afterEach, describe, expect, it, vi } from "vitest";

import { buildWorkspaceComparisonSankey, fetchReportPatterns, fetchReportSankey } from "@/api/reports";

function okEnvelope(result: unknown): Record<string, unknown> {
  return {
    ok: true,
    result,
    warnings: [],
    error: null
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("reports api", () => {
  it("maps multiple merchants and sources into the pattern query string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        expect(url.pathname).toBe("/api/v1/reports/patterns");
        expect(url.searchParams.get("from_date")).toBe("2026-04-01");
        expect(url.searchParams.get("to_date")).toBe("2026-04-30");
        expect(url.searchParams.get("merchants")).toBe("Lidl,REWE");
        expect(url.searchParams.get("source_ids")).toBe("lidl_plus_de,rewe_de");
        expect(url.searchParams.get("finance_category_id")).toBe("groceries");
        expect(url.searchParams.get("direction")).toBe("outflow");
        expect(url.searchParams.get("value_mode")).toBe("count");
        return {
          ok: true,
          json: async () =>
            okEnvelope({
              period: { from_date: "2026-04-01", to_date: "2026-04-30" },
              value_mode: "count",
              daily_heatmap: [],
              weekday_heatmap: Array.from({ length: 7 }, (_, weekday) => ({
                weekday,
                amount_cents: 0,
                count: 0
              })),
              weekday_hour_matrix: [],
              merchant_profiles: [],
              merchant_comparison: [],
              insights: []
            })
        };
      })
    );

    const result = await fetchReportPatterns({
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      merchants: ["Lidl", "REWE"],
      financeCategoryId: "groceries",
      direction: "outflow",
      sourceIds: ["lidl_plus_de", "rewe_de"],
      valueMode: "count"
    });

    expect(result.weekday_heatmap).toHaveLength(7);
    expect(result.value_mode).toBe("count");
  });

  it("maps the dedicated sankey query string with mode and filters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        expect(url.pathname).toBe("/api/v1/reports/sankey");
        expect(url.searchParams.get("from_date")).toBe("2026-04-01");
        expect(url.searchParams.get("to_date")).toBe("2026-04-30");
        expect(url.searchParams.get("merchants")).toBe("Lidl,REWE");
        expect(url.searchParams.get("source_ids")).toBe("lidl_plus_de,rewe_de");
        expect(url.searchParams.get("finance_category_id")).toBe("groceries");
        expect(url.searchParams.get("direction")).toBe("outflow");
        expect(url.searchParams.get("mode")).toBe("outflow_only");
        expect(url.searchParams.get("breakdown")).toBe("source");
        expect(url.searchParams.get("top_n")).toBe("8");
        return {
          ok: true,
          json: async () =>
            okEnvelope({
              period: { from_date: "2026-04-01", to_date: "2026-04-30" },
              mode: "outflow_only",
              breakdown: "source",
              model: {
                kind: "outflow_category_to_source",
                transaction_provenance_supported: false
              },
              flags: {
                aggregated_inflows: false,
                aggregated_categories: false,
                aggregated_merchants: false,
                aggregated_subcategories: false,
                aggregated_sources: true,
                manual_inflows_excluded_by_source_filter: true,
                synthetic_inflow_bucket: false
              },
              summary: {
                total_outflow_cents: 12345,
                total_inflow_basis_cents: 0,
                node_count: 2,
                link_count: 1
              },
              nodes: [
                {
                  id: "category:groceries",
                  label: "groceries",
                  kind: "outflow_category",
                  layer: 0,
                  amount_cents: 12345,
                  category_id: "groceries"
                },
                {
                  id: "source:lidl_plus_de",
                  label: "Lidl Plus DE",
                  kind: "source",
                  layer: 1,
                  amount_cents: 12345,
                  source_id: "lidl_plus_de"
                }
              ],
              links: [
                {
                  source: "category:groceries",
                  target: "source:lidl_plus_de",
                  value_cents: 12345,
                  kind: "category_to_source"
                }
              ]
            })
        };
      })
    );

    const result = await fetchReportSankey({
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      merchants: ["Lidl", "REWE"],
      financeCategoryId: "groceries",
      direction: "outflow",
      sourceIds: ["lidl_plus_de", "rewe_de"],
      mode: "outflow_only",
      breakdown: "source",
      topN: 8
    });

    expect(result.mode).toBe("outflow_only");
    expect(result.breakdown).toBe("source");
    expect(result.summary.total_outflow_cents).toBe(12345);
  });

  it("supports overriding the request scope for sankey fetches", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        expect(url.searchParams.get("scope")).toBe("group:household-1");
        return {
          ok: true,
          json: async () =>
            okEnvelope({
              period: { from_date: "2026-04-01", to_date: "2026-04-30" },
              mode: "outflow_only",
              breakdown: "merchant",
              model: {
                kind: "outflow_category_to_merchant",
                transaction_provenance_supported: false
              },
              flags: {
                aggregated_inflows: false,
                aggregated_categories: false,
                aggregated_merchants: false,
                aggregated_subcategories: false,
                aggregated_sources: false,
                manual_inflows_excluded_by_source_filter: false,
                synthetic_inflow_bucket: false
              },
              summary: {
                total_outflow_cents: 1000,
                total_inflow_basis_cents: 0,
                node_count: 2,
                link_count: 1
              },
              nodes: [
                {
                  id: "category:groceries",
                  label: "groceries",
                  kind: "outflow_category",
                  layer: 0,
                  amount_cents: 1000,
                  category_id: "groceries"
                },
                {
                  id: "merchant:Lidl",
                  label: "Lidl",
                  kind: "merchant",
                  layer: 1,
                  amount_cents: 1000,
                  merchant_name: "Lidl"
                }
              ],
              links: [
                {
                  source: "category:groceries",
                  target: "merchant:Lidl",
                  value_cents: 1000,
                  kind: "category_to_merchant"
                }
              ]
            })
        };
      })
    );

    await fetchReportSankey({
      fromDate: "2026-04-01",
      toDate: "2026-04-30",
      mode: "outflow_only",
      breakdown: "merchant",
      scopeOverride: "group:household-1",
    });
  });

  it("merges personal and shared-group sankeys into one workspace compare graph", () => {
    const personal = {
      period: { from_date: "2026-04-01", to_date: "2026-04-30" },
      mode: "outflow_only" as const,
      breakdown: "merchant" as const,
      model: { kind: "outflow_category_to_merchant", transaction_provenance_supported: false },
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
        total_outflow_cents: 1200,
        total_inflow_basis_cents: 0,
        node_count: 2,
        link_count: 1,
      },
      nodes: [
        { id: "category:groceries", label: "groceries", kind: "outflow_category", layer: 0, amount_cents: 1200, category_id: "groceries" },
        { id: "merchant:Lidl", label: "Lidl", kind: "merchant", layer: 1, amount_cents: 1200, merchant_name: "Lidl" },
      ],
      links: [
        { source: "category:groceries", target: "merchant:Lidl", value_cents: 1200, kind: "category_to_merchant" },
      ],
    };
    const group = {
      ...personal,
      summary: {
        total_outflow_cents: 800,
        total_inflow_basis_cents: 0,
        node_count: 2,
        link_count: 1,
      },
      nodes: [
        { id: "category:groceries", label: "groceries", kind: "outflow_category", layer: 0, amount_cents: 800, category_id: "groceries" },
        { id: "merchant:Lidl", label: "Lidl", kind: "merchant", layer: 1, amount_cents: 800, merchant_name: "Lidl" },
      ],
      links: [
        { source: "category:groceries", target: "merchant:Lidl", value_cents: 800, kind: "category_to_merchant" },
      ],
    };

    const merged = buildWorkspaceComparisonSankey({
      breakdown: "merchant",
      personal,
      group,
      groupLabel: "Household",
      personalLabel: "Personal",
    });

    expect(merged.mode).toBe("outflow_only");
    expect(merged.summary.total_outflow_cents).toBe(2000);
    expect(merged.nodes.find((node) => node.id === "workspace:personal")?.label).toBe("Personal");
    expect(merged.nodes.find((node) => node.id === "workspace:shared_group")?.label).toBe("Household");
    expect(merged.links.find((link) => link.source === "workspace:personal" && link.target === "category:groceries")?.value_cents).toBe(1200);
    expect(merged.links.find((link) => link.source === "workspace:shared_group" && link.target === "category:groceries")?.value_cents).toBe(800);
    expect(merged.links.find((link) => link.source === "category:groceries" && link.target === "merchant:Lidl")?.value_cents).toBe(2000);
  });
});
