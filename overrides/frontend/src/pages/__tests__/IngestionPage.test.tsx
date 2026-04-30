import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "@/i18n";
import { IngestionPage } from "../IngestionPage";

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  render(
    <MemoryRouter initialEntries={["/ingestion"]}>
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <IngestionPage />
        </I18nProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("IngestionPage", () => {
  beforeEach(() => {
    const storage = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
        removeItem: (key: string) => {
          storage.delete(key);
        }
      }
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the review-first intake workspace", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Ingestion" })).toBeInTheDocument();
    expect(screen.getByLabelText("Input")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Create proposal/ })).toBeInTheDocument();
    expect(screen.getByText("Review First")).toBeInTheDocument();
    expect(screen.getByText(/No proposals yet/)).toBeInTheDocument();
  });
});
