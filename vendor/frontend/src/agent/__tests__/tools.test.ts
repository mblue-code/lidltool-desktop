import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn()
  }
}));

import { ALL_TOOLS } from "@/agent/tools";
import { apiClient } from "@/lib/api-client";

function getShoppingHeatmapTool() {
  const tool = ALL_TOOLS.find((candidate) => candidate.name === "get_shopping_heatmap");
  if (!tool) {
    throw new Error("get_shopping_heatmap tool not found");
  }
  return tool;
}

describe("get_shopping_heatmap tool", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.get).mockResolvedValue({ ok: true });
  });

  it("defaults to weekday endpoint", async () => {
    const tool = getShoppingHeatmapTool();
    await tool.execute("call-1", {});

    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/analytics/heatmap/weekday",
      expect.anything(),
      {}
    );
  });

  it("routes to hour endpoint with timing params", async () => {
    const tool = getShoppingHeatmapTool();
    await tool.execute("call-2", {
      view: "hour",
      from_date: "2026-01-01",
      to_date: "2026-01-31",
      value: "count",
      source_kind: "amazon",
      tz_offset_minutes: 60
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/analytics/heatmap/hour",
      expect.anything(),
      {
        from_date: "2026-01-01",
        to_date: "2026-01-31",
        value: "count",
        source_kind: "amazon",
        tz_offset_minutes: 60
      }
    );
  });

  it("maps legacy year/month inputs to matrix date window", async () => {
    const tool = getShoppingHeatmapTool();
    await tool.execute("call-3", {
      view: "matrix",
      year: 2024,
      month: 2
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/analytics/heatmap/matrix",
      expect.anything(),
      {
        from_date: "2024-02-01",
        to_date: "2024-02-29"
      }
    );
  });
});
