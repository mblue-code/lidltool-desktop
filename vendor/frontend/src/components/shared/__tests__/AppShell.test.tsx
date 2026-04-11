import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as aiSettingsApi from "@/api/aiSettings";
import * as connectorsApi from "@/api/connectors";
import * as pageLoaders from "@/app/page-loaders";
import { AccessScopeProvider } from "@/app/scope-provider";
import {
  DesktopCapabilitiesProvider,
  DesktopRouteGate,
  createDesktopRedirectNotice,
  getDefaultDesktopCapabilities
} from "@/lib/desktop-capabilities";
import { setRequestScope } from "@/lib/request-scope";
import { AppShell } from "../AppShell";

vi.mock("@/components/ChatPanel", () => ({
  ChatPanel: ({ open }: { open: boolean }) => (open ? <div role="dialog" aria-label="AI Assistant" /> : null)
}));

const STUB_USER = { user_id: "u1", username: "admin", display_name: null, is_admin: true, preferred_locale: null };

function RouteLocationState() {
  const location = useLocation();

  return (
    <>
      <p>Current route: {location.pathname}</p>
      <p>Current search: {location.search || "(none)"}</p>
      <p>Current hash: {location.hash || "(none)"}</p>
    </>
  );
}

function renderShell(initialEntry = "/receipts"): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <AccessScopeProvider>
        <DesktopCapabilitiesProvider capabilities={getDefaultDesktopCapabilities()}>
          <MemoryRouter initialEntries={[initialEntry]}>
            <Routes>
              <Route path="/" element={<AppShell user={STUB_USER} />}>
                <Route path="receipts" element={<p>Receipts content</p>} />
                <Route index element={<RouteLocationState />} />
                <Route
                  path="offers"
                  element={
                    <DesktopRouteGate>
                      <p>Offers content</p>
                    </DesktopRouteGate>
                  }
                />
                <Route
                  path="automations"
                  element={
                    <DesktopRouteGate>
                      <p>Automations content</p>
                    </DesktopRouteGate>
                  }
                />
                <Route
                  path="automation-inbox"
                  element={
                    <DesktopRouteGate>
                      <p>Automation inbox content</p>
                    </DesktopRouteGate>
                  }
                />
                <Route
                  path="reliability"
                  element={
                    <DesktopRouteGate>
                      <p>Reliability content</p>
                    </DesktopRouteGate>
                  }
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </DesktopCapabilitiesProvider>
      </AccessScopeProvider>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setRequestScope("personal");
    window.localStorage?.removeItem?.("app.global_sync_banner.dismissed");
    window.localStorage?.removeItem?.("layout.chat_panel_width");
    window.localStorage?.removeItem?.("layout.advanced_nav_open");
    vi.spyOn(aiSettingsApi, "fetchAISettings").mockResolvedValue({
      enabled: true,
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      api_key_set: true,
      oauth_provider: "openai-codex",
      oauth_connected: true,
      remote_enabled: true,
      local_runtime_enabled: false,
      local_runtime_ready: false,
      local_runtime_status: "unavailable"
    });
    vi.spyOn(connectorsApi, "fetchConnectorSyncStatus").mockResolvedValue({
      source_id: "lidl_plus_de",
      status: "idle",
      command: null,
      pid: null,
      started_at: null,
      finished_at: null,
      return_code: null,
      output_tail: [],
      can_cancel: false
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders desktop shell landmarks and primary controls", () => {
    renderShell();

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Receipts" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByText("Receipts content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preferences" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Add Receipt" })[0]).toBeInTheDocument();
  });

  it("keeps unsupported desktop routes out of the visible nav", () => {
    renderShell();

    expect(screen.queryByRole("link", { name: "Offers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Automations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Reliability" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Show advanced tools" }));

    expect(screen.getAllByRole("link", { name: "Products" })[0]).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Chat" })[0]).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Offers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Automations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Reliability" })).not.toBeInTheDocument();
  });

  it.each([
    {
      route: "/offers?from=deep-link#details",
      requestedPath: "/offers",
      noticePattern: /This route remains out of scope for the desktop product\./,
      reason: "desktop_out_of_scope"
    },
    {
      route: "/automations?from=deep-link#details",
      requestedPath: "/automations",
      noticePattern:
        /Automations and the automation inbox stay in the self-hosted product because they require a persistent scheduler host\./,
      reason: "scheduler_host_required"
    },
    {
      route: "/automation-inbox?from=deep-link#details",
      requestedPath: "/automation-inbox",
      noticePattern:
        /Automations and the automation inbox stay in the self-hosted product because they require a persistent scheduler host\./,
      reason: "scheduler_host_required"
    },
    {
      route: "/reliability?from=deep-link#details",
      requestedPath: "/reliability",
      noticePattern:
        /Reliability and operator-facing routes stay in the self-hosted product and are not exposed inside Electron\./,
      reason: "operator_surface"
    }
  ])(
    "redirects direct navigation for $requestedPath through the capability policy",
    ({ route, requestedPath, noticePattern, reason }) => {
      renderShell(route);

      expect(screen.getByText("Current route: /")).toBeInTheDocument();
      expect(screen.getByText("Current search: ?from=deep-link")).toBeInTheDocument();
      expect(screen.getByText("Current hash: #details")).toBeInTheDocument();
      expect(screen.getByText("Not available in desktop")).toBeInTheDocument();
      expect(screen.getByText(noticePattern)).toBeInTheDocument();
      expect(screen.getByText(`Requested route: ${requestedPath}.`)).toBeInTheDocument();

      expect(
        createDesktopRedirectNotice(requestedPath, getDefaultDesktopCapabilities().routes.find((entry) => entry.route === requestedPath) ?? null)
      ).toMatchObject({
        requestedPath,
        redirectTo: "/",
        availability: "unsupported",
        reason
      });
    }
  );

  it("dismisses the unsupported route notice without changing the redirected destination", () => {
    renderShell("/offers?from=deep-link#details");

    fireEvent.click(screen.getByRole("button", { name: "Dismiss notice" }));

    expect(screen.queryByText("Requested route: /offers.")).not.toBeInTheDocument();
    expect(screen.getByText("Current route: /")).toBeInTheDocument();
    expect(screen.getByText("Current search: ?from=deep-link")).toBeInTheDocument();
    expect(screen.getByText("Current hash: #details")).toBeInTheDocument();
  });

  it("prefetches visible primary route modules when a nav link is hovered", () => {
    const preloadRouteModuleSpy = vi.spyOn(pageLoaders, "preloadRouteModule").mockImplementation(() => undefined);

    renderShell();
    fireEvent.mouseEnter(screen.getAllByRole("link", { name: "Connectors" })[0]);

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/connectors");
  });

  it("prefetches visible advanced route modules when focused", () => {
    const preloadRouteModuleSpy = vi.spyOn(pageLoaders, "preloadRouteModule").mockImplementation(() => undefined);

    renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Show advanced tools" }));
    fireEvent.focus(screen.getAllByRole("link", { name: "Chat" })[0]);

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/chat");
  });

  it("opens the side chat panel from the footer button without leaving the current page", () => {
    renderShell();

    expect(screen.queryByRole("dialog", { name: "AI Assistant" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByRole("dialog", { name: "AI Assistant" })).toBeInTheDocument();
    expect(screen.getByText("Receipts content")).toBeInTheDocument();
  });

  it("shows stage-specific sync feedback instead of zeroed metrics during authentication", async () => {
    vi.spyOn(connectorsApi, "fetchConnectorSyncStatus").mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: sourceId === "edeka_de" ? "running" : "idle",
      command: null,
      pid: sourceId === "edeka_de" ? 42 : null,
      started_at: sourceId === "edeka_de" ? "2026-04-11T13:08:20Z" : null,
      finished_at: null,
      return_code: null,
      output_tail: sourceId === "edeka_de" ? ["stage=authenticating detail=checking_saved_session"] : [],
      can_cancel: sourceId === "edeka_de"
    }));

    renderShell();

    expect(await screen.findByText("EDEKA sync")).toBeInTheDocument();
    expect(screen.getByText("Checking saved sign-in...")).toBeInTheDocument();
    expect(screen.queryByText(/pages=0/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/seen=0/i)).not.toBeInTheDocument();
  });
});
