import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OffersPage } from "@/pages/OffersPage";

const mocks = vi.hoisted(() => ({
  fetchProductsMock: vi.fn(),
  fetchOfferWatchlistsMock: vi.fn(),
  fetchOfferAlertsMock: vi.fn(),
  createOfferWatchlistMock: vi.fn(),
  refreshOffersMock: vi.fn(),
  patchOfferAlertMock: vi.fn()
}));

vi.mock("@/api/products", () => ({
  fetchProducts: mocks.fetchProductsMock
}));

vi.mock("@/api/offers", () => ({
  fetchOfferWatchlists: mocks.fetchOfferWatchlistsMock,
  fetchOfferAlerts: mocks.fetchOfferAlertsMock,
  createOfferWatchlist: mocks.createOfferWatchlistMock,
  refreshOffers: mocks.refreshOffersMock,
  patchOfferAlert: mocks.patchOfferAlertMock
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

function renderOffersPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OffersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("OffersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.fetchProductsMock.mockResolvedValue({
      items: [
        {
          product_id: "coffee-1",
          canonical_name: "Coffee Beans",
          brand: "Acme",
          default_unit: null,
          category_id: "coffee",
          gtin_ean: null,
          alias_count: 2
        },
        {
          product_id: "milk-1",
          canonical_name: "Oat Milk",
          brand: null,
          default_unit: null,
          category_id: "dairy",
          gtin_ean: null,
          alias_count: 1
        },
        {
          product_id: "uncategorized-1",
          canonical_name: "Loose Tea",
          brand: null,
          default_unit: null,
          category_id: null,
          gtin_ean: null,
          alias_count: 0
        }
      ],
      count: 3
    });
    mocks.fetchOfferWatchlistsMock.mockResolvedValue({
      items: [
        {
          id: "watch-1",
          product_id: "coffee-1",
          query_text: null,
          source_id: "dm_de_offers",
          min_discount_percent: 20,
          max_price_cents: 999,
          active: true,
          notes: "Stock up",
          created_at: "2026-03-01T12:00:00Z",
          updated_at: "2026-03-01T12:00:00Z",
          product: {
            product_id: "coffee-1",
            canonical_name: "Coffee Beans",
            brand: "Acme",
            category_id: "coffee"
          }
        }
      ],
      count: 1
    });
    mocks.fetchOfferAlertsMock.mockResolvedValue({
      items: [],
      count: 0,
      total: 0,
      limit: 25,
      offset: 0,
      unread_count: 0
    });
    mocks.createOfferWatchlistMock.mockResolvedValue({
      id: "watch-new",
      product_id: "coffee-1",
      query_text: null,
      source_id: "dm_de_offers",
      min_discount_percent: 20,
      max_price_cents: 1299,
      active: true,
      notes: "Weekly restock",
      created_at: "2026-03-01T12:00:00Z",
      updated_at: "2026-03-01T12:00:00Z"
    });
    mocks.refreshOffersMock.mockResolvedValue({});
    mocks.patchOfferAlertMock.mockResolvedValue({
      id: "alert-1",
      title: "Coffee deal",
      read: true
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("supports category-first watchlist creation and parses euro input", async () => {
    renderOffersPage();

    expect(await screen.findByText("Configured sources only")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save watchlist" }));
    expect(await screen.findByText("Choose a product or enter a text query before saving.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("combobox", { name: "Category" }));
    fireEvent.click(screen.getByRole("option", { name: "coffee (1)" }));

    fireEvent.click(screen.getByRole("combobox", { name: "Product" }));
    fireEvent.click(screen.getByRole("option", { name: "Acme · Coffee Beans" }));

    fireEvent.change(screen.getByLabelText("Merchant preference"), { target: { value: "dm_de_offers" } });
    fireEvent.change(screen.getByLabelText("Minimum discount percent"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Max price"), { target: { value: "12,99" } });
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "Weekly restock" } });
    fireEvent.click(screen.getByRole("button", { name: "Save watchlist" }));

    await waitFor(() => {
      expect(mocks.createOfferWatchlistMock).toHaveBeenCalledTimes(1);
    });
    expect(mocks.createOfferWatchlistMock.mock.calls[0]?.[0]).toEqual({
      product_id: "coffee-1",
      query_text: undefined,
      source_id: "dm_de_offers",
      min_discount_percent: 20,
      max_price_cents: 1299,
      notes: "Weekly restock",
      active: true
    });
  });

  it("allows free-text watchlists without a product selection", async () => {
    renderOffersPage();

    fireEvent.change(screen.getByLabelText("Free-text query"), { target: { value: "coffee beans" } });
    fireEvent.click(screen.getByRole("button", { name: "Save watchlist" }));

    await waitFor(() => {
      expect(mocks.createOfferWatchlistMock).toHaveBeenCalledTimes(1);
    });
    expect(mocks.createOfferWatchlistMock.mock.calls[0]?.[0]).toEqual({
      product_id: undefined,
      query_text: "coffee beans",
      source_id: undefined,
      min_discount_percent: undefined,
      max_price_cents: undefined,
      notes: undefined,
      active: true
    });
  });

  it("shows a friendly message when the backend rejects a watchlist save", async () => {
    mocks.createOfferWatchlistMock.mockRejectedValueOnce({ status: 400 });

    renderOffersPage();

    fireEvent.change(screen.getByLabelText("Free-text query"), { target: { value: "tea" } });
    fireEvent.click(screen.getByRole("button", { name: "Save watchlist" }));

    expect(
      await screen.findByText("The watchlist could not be saved. Choose a product or enter a text query.")
    ).toBeInTheDocument();
  });
});
