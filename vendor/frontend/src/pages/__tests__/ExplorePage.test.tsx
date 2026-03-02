import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExplorePage } from "../ExplorePage";

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ExplorePage />
    </QueryClientProvider>
  );
}

describe("ExplorePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method ?? "GET").toUpperCase();

        if (url.pathname === "/api/v1/query/saved" && method === "GET") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: { items: [], count: 0 },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/query/run" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                columns: ["month", "net_total"],
                rows: [["2026-02", 400]],
                totals: { net_total: 400 },
                drilldown_token: "token",
                explain: "SELECT 1"
              },
              warnings: [],
              error: null
            })
          };
        }

        if (url.pathname === "/api/v1/query/saved" && method === "POST") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                query_id: "saved-1",
                name: "My Query",
                description: null,
                query_json: {},
                is_preset: false,
                created_at: "2026-02-20T00:00:00Z"
              },
              warnings: [],
              error: null
            })
          };
        }

        throw new Error(`Unexpected request: ${method} ${url.pathname}`);
      })
    );
  });

  afterEach(() => {
    cleanup();
  });

  it("runs a query and allows saving it", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => {
      expect(screen.getByText("2026-02")).toBeInTheDocument();
      expect(screen.getByText("400")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Saved query name"), {
      target: { value: "My Query" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save query" }));

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => {
        const url = new URL(String(call[0]));
        return `${call[1]?.method ?? "GET"} ${url.pathname}`;
      });
      expect(calls.some((entry) => entry === "POST /api/v1/query/saved")).toBe(true);
    });
  });
});
