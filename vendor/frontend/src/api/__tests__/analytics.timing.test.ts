import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchHourHeatmap, fetchTimingMatrix, fetchWeekdayHeatmap } from "@/api/analytics";

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

describe("analytics timing api", () => {
  it("maps weekday timing params to query string", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        expect(url.pathname).toBe("/api/v1/analytics/heatmap/weekday");
        expect(url.searchParams.get("from_date")).toBe("2026-02-01");
        expect(url.searchParams.get("to_date")).toBe("2026-02-28");
        expect(url.searchParams.get("value")).toBe("count");
        expect(url.searchParams.get("source_kind")).toBe("lidl_de");
        expect(url.searchParams.get("tz_offset_minutes")).toBe("120");
        return {
          ok: true,
          json: async () =>
            okEnvelope({
              value: "count",
              date_from: "2026-02-01",
              date_to: "2026-02-28",
              source_kinds: ["lidl_de"],
              tz_offset_minutes: 120,
              points: [
                {
                  date: "2026-02-01",
                  weekday: 6,
                  week: 5,
                  value_cents: 0,
                  count: 2,
                  value: 2
                }
              ],
              weekday_totals: [
                { weekday: 0, value_cents: 0, count: 0, value: 0 },
                { weekday: 1, value_cents: 0, count: 0, value: 0 },
                { weekday: 2, value_cents: 0, count: 0, value: 0 },
                { weekday: 3, value_cents: 0, count: 0, value: 0 },
                { weekday: 4, value_cents: 0, count: 0, value: 0 },
                { weekday: 5, value_cents: 0, count: 0, value: 0 },
                { weekday: 6, value_cents: 0, count: 2, value: 2 }
              ]
            })
        };
      })
    );

    const result = await fetchWeekdayHeatmap({
      fromDate: "2026-02-01",
      toDate: "2026-02-28",
      value: "count",
      sourceKind: "lidl_de",
      tzOffsetMinutes: 120
    });
    expect(result.value).toBe("count");
    expect(result.points[0]?.count).toBe(2);
  });

  it("fetches hour heatmap with runtime-validated payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        expect(url.pathname).toBe("/api/v1/analytics/heatmap/hour");
        return {
          ok: true,
          json: async () =>
            okEnvelope({
              value: "net",
              date_from: "2026-02-01",
              date_to: "2026-02-28",
              source_kind: "amazon",
              tz_offset_minutes: 0,
              points: Array.from({ length: 24 }, (_, hour) => ({
                hour,
                value_cents: hour === 20 ? 4200 : 0,
                count: hour === 20 ? 3 : 0,
                value: hour === 20 ? 4200 : 0
              })),
              totals: {
                value_cents: 4200,
                count: 3
              }
            })
        };
      })
    );

    const result = await fetchHourHeatmap({ value: "net", sourceKind: "amazon" });
    expect(result.points).toHaveLength(24);
    expect(result.totals.count).toBe(3);
  });

  it("rejects matrix payload drift via schema validation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () =>
          okEnvelope({
            value: "gross",
            date_from: "2026-02-01",
            date_to: "2026-02-28",
            source_kind: null,
            tz_offset_minutes: 0,
            grid: [],
            weekday_totals: [],
            hour_totals: [],
            grand_total: {
              value_cents: 0
            }
          })
      }))
    );

    await expect(fetchTimingMatrix()).rejects.toThrow("Invalid API payload");
  });
});
