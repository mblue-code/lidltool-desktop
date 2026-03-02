import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReliabilityPage } from "../ReliabilityPage";

function renderReliabilityRoute(initialEntry = "/reliability"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/reliability" element={<ReliabilityPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ReliabilityPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        if (url.pathname !== "/api/v1/reliability/slo") {
          throw new Error(`Unexpected request: ${url.pathname}`);
        }
        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              generated_at: "2026-02-19T12:00:00Z",
              window_hours: 24,
              thresholds: {
                sync_p95_target_ms: 2500,
                analytics_p95_target_ms: 2000,
                min_success_rate: 0.97
              },
              families: {
                analytics: {
                  routes: 2,
                  p95_duration_ms: 1200,
                  avg_success_rate: 0.985,
                  p95_target_ms: 2000,
                  slo_pass: true
                },
                sync: {
                  routes: 1,
                  p95_duration_ms: 3200,
                  avg_success_rate: 0.91,
                  p95_target_ms: 2500,
                  slo_pass: false
                }
              },
              endpoints: [
                {
                  route: "/api/v1/dashboard/cards",
                  count: 18,
                  success_rate: 0.99,
                  error_rate: 0.01,
                  p50_duration_ms: 800,
                  p95_duration_ms: 1200,
                  p99_duration_ms: 1500
                },
                {
                  route: "/api/v1/documents/upload",
                  count: 11,
                  success_rate: 0.91,
                  error_rate: 0.09,
                  p50_duration_ms: 1600,
                  p95_duration_ms: 3200,
                  p99_duration_ms: 4200
                }
              ]
            },
            warnings: [],
            error: null
          })
        };
      })
    );
  });

  it("renders SLO cards and endpoint health indicators", async () => {
    renderReliabilityRoute();

    expect(screen.getByRole("heading", { name: "Reliability Console" })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Endpoint Health")).toBeInTheDocument();
      expect(screen.getByText("/api/v1/dashboard/cards")).toBeInTheDocument();
      expect(screen.getByText("/api/v1/documents/upload")).toBeInTheDocument();
      expect(screen.getByText("SLO pass")).toBeInTheDocument();
      expect(screen.getByText("SLO fail")).toBeInTheDocument();
      expect(screen.getByText("Latency high")).toBeInTheDocument();
    });
  });
});
