import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as pageLoaders from "@/app/page-loaders";
import { AccessScopeProvider } from "@/app/scope-provider";
import { setRequestScope } from "@/lib/request-scope";
import { AppShell } from "../AppShell";

const STUB_USER = { user_id: "u1", username: "admin", display_name: null, is_admin: true };

function renderShell(initialEntry = "/receipts"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <AccessScopeProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/" element={<AppShell user={STUB_USER} />}>
              <Route path="receipts" element={<p>Receipts content</p>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AccessScopeProvider>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setRequestScope("personal");
  });

  afterEach(() => {
    cleanup();
  });

  it("renders skip navigation and main landmark", () => {
    renderShell();

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute(
      "href",
      "#main-content"
    );
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Receipts" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByText("Receipts content")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Data scope" })).toBeInTheDocument();
  });

  it("prefetches route modules when a nav link is hovered", () => {
    const preloadRouteModuleSpy = vi
      .spyOn(pageLoaders, "preloadRouteModule")
      .mockImplementation(() => undefined);

    renderShell();
    fireEvent.mouseEnter(screen.getAllByRole("link", { name: "Automations" })[0]);

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/automations");
  });

  it("prefetches route modules when a nav link receives focus", () => {
    const preloadRouteModuleSpy = vi
      .spyOn(pageLoaders, "preloadRouteModule")
      .mockImplementation(() => undefined);

    renderShell();
    fireEvent.focus(screen.getAllByRole("link", { name: "Reliability" })[0]);

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/reliability");
  });

  it("opens the side chat panel from the footer button without leaving the current page", () => {
    renderShell();

    expect(screen.queryByRole("heading", { name: "AI Assistant" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByRole("heading", { name: "AI Assistant" })).toBeInTheDocument();
    expect(screen.getByText("Receipts content")).toBeInTheDocument();
  });
});
