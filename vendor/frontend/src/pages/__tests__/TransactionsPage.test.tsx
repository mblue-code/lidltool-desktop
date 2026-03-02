import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TransactionsPage } from "../TransactionsPage";

function LocationProbe(): JSX.Element {
  const location = useLocation();
  return <output data-testid="transactions-location-search">{location.search}</output>;
}

function latestFetchUrl(): string {
  const calls = vi.mocked(fetch).mock.calls;
  if (calls.length === 0) {
    return "";
  }
  return String(calls[calls.length - 1][0]);
}

function renderTransactionsRoute(initialEntry = "/transactions"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/transactions"
            element={
              <>
                <TransactionsPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TransactionsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const baseItems = [
      {
        id: "tx-large",
        purchased_at: "2026-01-10T10:00:00Z",
        source_id: "lidl",
        source_transaction_id: "1",
        store_name: "Store Large",
        total_gross_cents: 2400,
        discount_total_cents: 100,
        currency: "EUR"
      },
      {
        id: "tx-small",
        purchased_at: "2026-01-11T10:00:00Z",
        source_id: "lidl",
        source_transaction_id: "2",
        store_name: "Store Small",
        total_gross_cents: 900,
        discount_total_cents: 50,
        currency: "EUR"
      }
    ];

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = new URL(String(input));
        const method = (init?.method || "GET").toUpperCase();
        if (method === "POST" && url.pathname === "/api/v1/transactions/manual") {
          return {
            ok: true,
            json: async () => ({
              ok: true,
              result: {
                transaction_id: "tx-manual-1",
                source_id: "manual_entry",
                source_transaction_id: "manual-idem:abc123",
                reused: false,
                transaction: {
                  id: "tx-manual-1",
                  source_id: "manual_entry",
                  source_transaction_id: "manual-idem:abc123",
                  purchased_at: "2026-02-20T09:30:00.000Z",
                  merchant_name: "MediaMarkt",
                  total_gross_cents: 199900,
                  currency: "EUR",
                  discount_total_cents: null
                }
              },
              warnings: [],
              error: null
            })
          };
        }
        const sortBy = url.searchParams.get("sort_by") || "purchased_at";
        const sortDir = url.searchParams.get("sort_dir") || "desc";
        const direction = sortDir === "asc" ? 1 : -1;

        const items = [...baseItems].sort((left, right) => {
          if (sortBy === "total_gross_cents") {
            return (left.total_gross_cents - right.total_gross_cents) * direction;
          }
          return (new Date(left.purchased_at).valueOf() - new Date(right.purchased_at).valueOf()) * direction;
        });

        return {
          ok: true,
          json: async () => ({
            ok: true,
            result: {
              count: items.length,
              total: items.length,
              limit: 25,
              offset: 0,
              items
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

  it("shows filter chips and applies URL-driven sort order", async () => {
    renderTransactionsRoute(
      "/transactions?query=milk&year=2025&sort=total_gross_cents&direction=asc"
    );

    await waitFor(() => {
      expect(screen.getByText(/Search:\s*milk/)).toBeInTheDocument();
      expect(screen.getByText(/Year:\s*2025/)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Store Small")).toBeInTheDocument();
      expect(screen.getByText("Store Large")).toBeInTheDocument();
    });
    const detailLinks = screen.getAllByRole("link", { name: "Details" });
    expect(detailLinks[0]).toHaveAttribute("href", "/transactions/tx-small");
    expect(detailLinks[1]).toHaveAttribute("href", "/transactions/tx-large");

    await waitFor(() => {
      expect(fetch).toHaveBeenCalled();
    });
    const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(calls.some((url) => url.includes("sort_by=total_gross_cents"))).toBe(true);
    expect(calls.some((url) => url.includes("sort_dir=asc"))).toBe(true);
  });

  it("removes a single filter chip and keeps input values synchronized with URL state", async () => {
    renderTransactionsRoute("/transactions?query=milk&merchant_name=Store%20One&offset=25");

    await waitFor(() => {
      expect(screen.getByText(/Search:\s*milk/)).toBeInTheDocument();
      expect(screen.getByText(/Merchant:\s*Store One/)).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Search")).toHaveValue("milk");
    expect(screen.getByLabelText("Merchant")).toHaveValue("Store One");

    fireEvent.click(screen.getByRole("button", { name: "Remove Search filter" }));

    await waitFor(() => {
      expect(screen.queryByText(/Search:\s*milk/)).not.toBeInTheDocument();
    });

    expect(screen.getByLabelText("Search")).toHaveValue("");
    expect(screen.getByLabelText("Merchant")).toHaveValue("Store One");
    expect(screen.getByTestId("transactions-location-search")).toHaveTextContent(
      /\?merchant_name=Store\+One&offset=0/
    );

    const latestRequest = latestFetchUrl();
    expect(latestRequest).toContain("merchant_name=Store+One");
    expect(latestRequest).not.toContain("query=milk");
    expect(latestRequest).toContain("offset=0");
  });

  it("clear all resets visible inputs and removes all filter query params", async () => {
    renderTransactionsRoute(
      "/transactions?query=milk&source_id=lidl&merchant_name=Store%20One&year=2025&month=2&min_total_cents=100&max_total_cents=2400"
    );

    await waitFor(() => {
      expect(screen.getByText(/Search:\s*milk/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));

    await waitFor(() => {
      expect(screen.queryByText(/Search:\s*milk/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Source:\s*lidl/)).not.toBeInTheDocument();
      expect(screen.queryByText(/Merchant:\s*Store One/)).not.toBeInTheDocument();
    });

    expect(screen.getByLabelText("Search")).toHaveValue("");
    expect(screen.getByLabelText("Source")).toHaveValue("");
    expect(screen.getByLabelText("Merchant")).toHaveValue("");
    expect(screen.getByLabelText("Year")).toHaveValue(null);
    expect(screen.getByLabelText("Month")).toHaveValue(null);
    expect(screen.getByLabelText("Min total cents")).toHaveValue(null);
    expect(screen.getByLabelText("Max total cents")).toHaveValue(null);
    expect(screen.getByTestId("transactions-location-search")).toHaveTextContent("?offset=0");

    const latestRequest = latestFetchUrl();
    expect(latestRequest).toContain("offset=0");
    expect(latestRequest).not.toContain("query=milk");
    expect(latestRequest).not.toContain("source_id=lidl");
    expect(latestRequest).not.toContain("merchant_name=Store+One");
    expect(latestRequest).not.toContain("year=2025");
    expect(latestRequest).not.toContain("month=2");
    expect(latestRequest).not.toContain("min_total_cents=100");
    expect(latestRequest).not.toContain("max_total_cents=2400");
  });

  it("reads timing drilldown filters from URL and forwards them to the transactions API", async () => {
    renderTransactionsRoute(
      "/transactions?source_kind=lidl_de&weekday=3&hour=20&tz_offset_minutes=120"
    );

    await waitFor(() => {
      expect(screen.getByText(/Source kind:\s*lidl_de/)).toBeInTheDocument();
      expect(screen.getByText(/Weekday:\s*3/)).toBeInTheDocument();
      expect(screen.getByText(/Hour:\s*20/)).toBeInTheDocument();
      expect(screen.getByText(/TZ offset:\s*120/)).toBeInTheDocument();
    });

    expect(screen.getByLabelText("Source kind")).toHaveValue("lidl_de");
    expect(screen.getByLabelText("Weekday (0-6)")).toHaveValue(3);
    expect(screen.getByLabelText("Hour (0-23)")).toHaveValue(20);
    expect(screen.getByLabelText("TZ offset minutes")).toHaveValue(120);

    const latestRequest = latestFetchUrl();
    expect(latestRequest).toContain("source_kind=lidl_de");
    expect(latestRequest).toContain("weekday=3");
    expect(latestRequest).toContain("hour=20");
    expect(latestRequest).toContain("tz_offset_minutes=120");
  });

  it("submits one-off purchase form and shows success state", async () => {
    renderTransactionsRoute("/transactions");

    fireEvent.change(screen.getByLabelText("Purchased at (one-off)"), {
      target: { value: "2026-02-20T10:30" }
    });
    fireEvent.change(screen.getByLabelText("Merchant (one-off)"), {
      target: { value: "MediaMarkt" }
    });
    fireEvent.change(screen.getByLabelText("Total cents (one-off)"), {
      target: { value: "199900" }
    });
    fireEvent.change(screen.getByLabelText("Item (optional)"), {
      target: { value: "Laptop" }
    });
    fireEvent.change(screen.getByLabelText("Item total cents (optional)"), {
      target: { value: "199900" }
    });
    fireEvent.change(screen.getByLabelText("Idempotency key (optional)"), {
      target: { value: "manual-laptop-1" }
    });

    fireEvent.click(screen.getByRole("button", { name: "Add one-off purchase" }));

    await waitFor(() => {
      expect(screen.getByText("Transaction saved")).toBeInTheDocument();
      expect(screen.getByText(/New transaction created\./)).toBeInTheDocument();
      expect(screen.getByText("manual_entry")).toBeInTheDocument();
    });

    const postCall = vi.mocked(fetch).mock.calls.find((call) => {
      const url = new URL(String(call[0]));
      const method = (call[1]?.method || "GET").toUpperCase();
      return url.pathname === "/api/v1/transactions/manual" && method === "POST";
    });
    expect(postCall).toBeDefined();

    const body = JSON.parse(String(postCall?.[1]?.body));
    expect(body).toMatchObject({
      merchant_name: "MediaMarkt",
      total_gross_cents: 199900,
      idempotency_key: "manual-laptop-1"
    });
    expect(Array.isArray(body.items)).toBe(true);
    expect(body.items[0]).toMatchObject({
      name: "Laptop",
      line_total_cents: 199900
    });
  });
});
