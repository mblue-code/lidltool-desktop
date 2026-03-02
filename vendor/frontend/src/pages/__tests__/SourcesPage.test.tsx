import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourcesPage } from "../SourcesPage";

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });
  render(
    <QueryClientProvider client={queryClient}>
      <SourcesPage />
    </QueryClientProvider>
  );
}

describe("SourcesPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input));
        if (url.pathname !== "/api/v1/sources") {
          throw new Error(`Unexpected request: ${url.pathname}`);
        }
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

  afterEach(() => {
    cleanup();
  });

  it("renders source rows from API", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Lidl")).toBeInTheDocument();
      expect(screen.getByText("lidl_de")).toBeInTheDocument();
      expect(screen.getByText("healthy")).toBeInTheDocument();
    });
  });
});
