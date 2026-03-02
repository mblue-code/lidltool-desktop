import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toPng } from "html-to-image";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PatternsPage } from "../PatternsPage";

vi.mock("html-to-image", () => ({
  toPng: vi.fn(async () => "data:image/png;base64,AAAA")
}));

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <output data-testid="patterns-location">{`${location.pathname}${location.search}`}</output>;
}

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/patterns"]}>
        <Routes>
          <Route
            path="/patterns"
            element={
              <>
                <PatternsPage />
                <LocationProbe />
              </>
            }
          />
          <Route path="/transactions" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("PatternsPage", () => {
  const calls: string[] = [];

  beforeEach(() => {
    calls.length = 0;
    vi.restoreAllMocks();
    vi.mocked(toPng).mockResolvedValue("data:image/png;base64,AAAA");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        calls.push(url.pathname);

        if (url.pathname === "/api/v1/sources") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                sources: [
                  {
                    id: "lidl_plus_de",
                    kind: "lidl_de",
                    display_name: "Lidl",
                    status: "healthy",
                    enabled: true
                  },
                  {
                    id: "amazon_de",
                    kind: "amazon",
                    display_name: "Amazon",
                    status: "healthy",
                    enabled: true
                  }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/heatmap/weekday") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                value: "gross",
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                source_kinds: ["lidl_de"],
                tz_offset_minutes: 0,
                points: [
                  { date: "2026-01-01", weekday: 3, week: 1, value_cents: 1000, count: 1, value: 1000 },
                  { date: "2026-01-02", weekday: 4, week: 1, value_cents: 500, count: 1, value: 500 }
                ],
                weekday_totals: [
                  { weekday: 0, value_cents: 0, count: 0, value: 0 },
                  { weekday: 1, value_cents: 0, count: 0, value: 0 },
                  { weekday: 2, value_cents: 0, count: 0, value: 0 },
                  { weekday: 3, value_cents: 1000, count: 1, value: 1000 },
                  { weekday: 4, value_cents: 500, count: 1, value: 500 },
                  { weekday: 5, value_cents: 0, count: 0, value: 0 },
                  { weekday: 6, value_cents: 0, count: 0, value: 0 }
                ]
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/heatmap/hour") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                value: "gross",
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                source_kind: "lidl_de",
                tz_offset_minutes: 0,
                points: Array.from({ length: 24 }, (_, hour) => ({
                  hour,
                  value_cents: hour === 18 ? 2200 : 0,
                  count: hour === 18 ? 2 : 0,
                  value: hour === 18 ? 2200 : 0
                })),
                totals: {
                  value_cents: 2200,
                  count: 2
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/heatmap/matrix") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                value: "gross",
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                source_kind: "lidl_de",
                tz_offset_minutes: 0,
                grid: Array.from({ length: 7 * 24 }, (_, index) => ({
                  weekday: Math.floor(index / 24),
                  hour: index % 24,
                  value_cents: index === 5 ? 900 : 0,
                  count: index === 5 ? 1 : 0,
                  value: index === 5 ? 900 : 0
                })),
                weekday_totals: Array.from({ length: 7 }, (_, weekday) => ({
                  weekday,
                  value_cents: weekday === 0 ? 900 : 0,
                  count: weekday === 0 ? 1 : 0,
                  value: weekday === 0 ? 900 : 0
                })),
                hour_totals: Array.from({ length: 24 }, (_, hour) => ({
                  hour,
                  value_cents: hour === 5 ? 900 : 0,
                  count: hour === 5 ? 1 : 0,
                  value: hour === 5 ? 900 : 0
                })),
                grand_total: {
                  value_cents: 900,
                  count: 1
                }
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/patterns") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                shopping_frequency: [],
                basket_size_distribution: [],
                impulse_indicator: { one_time_items: 1, unique_items: 2, one_time_share: 0.5 },
                spend_velocity: [
                  { date: "2026-01-30", rolling_7d_cents: 3000, rolling_30d_cents: 12000 }
                ],
                seasonal_patterns: []
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/analytics/price-index") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                grain: "month",
                date_from: "2026-01-01",
                date_to: "2026-02-01",
                points: [{ period: "2026-01", source_kind: "lidl_de", index: 95.3, product_count: 2 }]
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${url.pathname}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("renders heatmap, velocity and price index sections", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Timing Patterns")).toBeInTheDocument();
      expect(screen.getByText("Yearly")).toBeInTheDocument();
      expect(screen.getByText("Retailer Price Index (Recent)")).toBeInTheDocument();
      expect(screen.getByText("2026-01")).toBeInTheDocument();
      expect(screen.getByText("lidl_de")).toBeInTheDocument();
    });
  });

  it("switches to hourly view and loads hourly endpoint", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Hourly" }));

    await waitFor(() => {
      expect(calls).toContain("/api/v1/analytics/heatmap/hour");
    });
  });

  it("navigates to transactions on heatmap cell click with timing filters", async () => {
    renderPage();
    const sourceSelect = (await screen.findByLabelText("Source")) as HTMLSelectElement;
    await waitFor(() => {
      expect(sourceSelect.querySelectorAll("option").length).toBeGreaterThan(1);
    });
    fireEvent.change(sourceSelect, { target: { value: "lidl_de" } });
    expect(sourceSelect.value).toBe("lidl_de");
    const thursdayCell = await screen.findByLabelText(/Thu value 1000 count 1/i);
    fireEvent.click(thursdayCell);

    await waitFor(() => {
      const location = screen.getByTestId("patterns-location").textContent || "";
      expect(location).toContain("/transactions?");
      expect(location).toContain("weekday=3");
      expect(location).toContain("source_kind=lidl_de");
      expect(location).toContain("tz_offset_minutes=");
    });
  });

  it("exports CSV and PNG for current timing panel", async () => {
    renderPage();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURLMock = vi.fn((value: Blob | MediaSource) => {
      void value;
      return "blob:timing";
    });
    const revokeObjectURLMock = vi.fn();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURLMock });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURLMock });
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    try {
      await screen.findByLabelText(/Thu value 1000 count 1/i);
      const exportCsvButton = await screen.findByRole("button", { name: "Export CSV" });
      const exportPngButton = await screen.findByRole("button", { name: "Export PNG" });
      expect(exportCsvButton).toBeEnabled();
      expect(exportPngButton).toBeEnabled();

      fireEvent.click(exportCsvButton);
      await waitFor(() => {
        expect(createObjectURLMock).toHaveBeenCalled();
      });
      const firstCreateObjectUrlCall = createObjectURLMock.mock.calls[0];
      expect(firstCreateObjectUrlCall).toBeDefined();
      const csvBlob = firstCreateObjectUrlCall[0] as Blob;
      const csvContent = await csvBlob.text();
      expect(csvContent).toContain("meta,view=yearly");
      expect(csvContent).toContain("date,weekday,week,value_cents,count,value");

      fireEvent.click(exportPngButton);
      await waitFor(() => {
        expect(toPng).toHaveBeenCalled();
      });
      expect(clickSpy).toHaveBeenCalled();
    } finally {
      Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectURL });
      Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectURL });
      clickSpy.mockRestore();
    }
  });
});
