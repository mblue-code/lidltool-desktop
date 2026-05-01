import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchReportPatterns } from "@/api/reports";

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
});
