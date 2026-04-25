import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as aiSettingsApi from "@/api/aiSettings";
import * as connectorsApi from "@/api/connectors";
import * as notificationsApi from "@/api/notifications";
import * as sharedGroupsApi from "@/api/shared-groups";
import { DateRangeProvider } from "@/app/date-range-context";
import * as pageLoaders from "@/app/page-loaders";
import { AccessScopeProvider } from "@/app/scope-provider";
import {
  DesktopCapabilitiesProvider,
  DesktopRouteGate,
  createDesktopRedirectNotice,
  getDefaultDesktopCapabilities
} from "@/lib/desktop-capabilities";
import { setActiveWorkspace, setRequestScope } from "@/lib/request-scope";
import { AppShell } from "../AppShell";

vi.mock("@/components/ChatPanel", () => ({
  ChatPanel: ({ open }: { open: boolean }) => (open ? <div role="dialog" aria-label="AI Assistant" /> : null)
}));

const STUB_USER = {
  user_id: "u1",
  username: "admin",
  display_name: null,
  is_admin: true,
  preferred_locale: null,
  session: null,
  session_mode: null,
  available_auth_transports: [],
  auth_transport: null
};

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

function renderShell(
  initialEntry = "/transactions",
  options?: {
    queryClient?: QueryClient;
  }
): void {
  const queryClient =
    options?.queryClient ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false }
      }
    });

  render(
    <QueryClientProvider client={queryClient}>
      <AccessScopeProvider>
        <DateRangeProvider>
          <DesktopCapabilitiesProvider capabilities={getDefaultDesktopCapabilities()}>
            <MemoryRouter initialEntries={[initialEntry]}>
              <Routes>
                <Route path="/" element={<AppShell user={STUB_USER} />}>
                  <Route path="transactions" element={<p>Transactions content</p>} />
                  <Route path="groceries" element={<p>Purchases content</p>} />
                  <Route path="settings" element={<p>Settings content</p>} />
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
        </DateRangeProvider>
      </AccessScopeProvider>
    </QueryClientProvider>
  );
}

describe("AppShell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        openControlCenter: vi.fn()
      }
    });
    setRequestScope("personal");
    window.localStorage?.removeItem?.("app.global_sync_banner.dismissed");
    window.localStorage?.removeItem?.("layout.chat_panel_width");
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
    vi.spyOn(connectorsApi, "fetchConnectors").mockResolvedValue({
      generated_at: "2026-04-12T12:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 2, by_status: { ready: 2 } },
      connectors: [
        {
          source_id: "lidl_plus_de",
          display_name: "Lidl",
          supports_sync: true,
          install_state: "installed"
        } as unknown as connectorsApi.ConnectorDiscoveryRow,
        {
          source_id: "edeka_de",
          display_name: "EDEKA",
          supports_sync: true,
          install_state: "installed"
        } as unknown as connectorsApi.ConnectorDiscoveryRow
      ]
    });
    vi.spyOn(connectorsApi, "fetchConnectorSyncStatus").mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: "idle",
      command: null,
      pid: null,
      started_at: null,
      finished_at: null,
      return_code: null,
      output_tail: [],
      can_cancel: false
    }));
    vi.spyOn(notificationsApi, "fetchNotifications").mockResolvedValue({
      count: 0,
      unread_count: 0,
      items: []
    });
    vi.spyOn(sharedGroupsApi, "fetchSharedGroups").mockResolvedValue({
      count: 1,
      groups: [
        {
          group_id: "group-1",
          name: "Miller Household",
          group_type: "household",
          status: "active",
          created_at: "2026-04-12T12:00:00Z",
          updated_at: "2026-04-12T12:00:00Z",
          created_by_user: null,
          viewer_role: "owner",
          viewer_membership_status: "active",
          can_manage: true,
          owner_count: 1,
          member_count: 2,
          members: []
        }
      ]
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders desktop shell landmarks and primary controls", () => {
    renderShell();

    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Transactions" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByText("Transactions content")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Preferences" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Add Receipt" })[0]).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Purchases" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cash Flow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Personal")).toBeInTheDocument();
  });

  it("lists shared workspaces in preferences and keeps the active workspace visible", async () => {
    setActiveWorkspace({ kind: "shared-group", groupId: "group-1" });
    renderShell();

    expect(await screen.findByText("Miller Household")).toBeInTheDocument();

    fireEvent.pointerDown(screen.getByRole("button", { name: "Preferences" }));
    expect(screen.getByText("Household workspace · Miller Household")).toBeInTheDocument();
    expect(screen.getByRole("menuitemradio", { name: "Miller Household" })).toHaveAttribute("data-state", "checked");
  });

  it("offers a signed-in path back to the control center from preferences", () => {
    renderShell();

    fireEvent.pointerDown(screen.getByRole("button", { name: "Preferences" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Open control center" }));

    expect((window.desktopApi as { openControlCenter?: ReturnType<typeof vi.fn> } | undefined)?.openControlCenter).toHaveBeenCalledTimes(1);
  });

  it("links to the appearance editor from preferences", () => {
    renderShell();

    fireEvent.pointerDown(screen.getByRole("button", { name: "Preferences" }));
    expect(screen.getByRole("menuitem", { name: "Edit appearance" })).toBeInTheDocument();
  });

  it("hides the global sync banner when sync status refetch fails after cached running data", async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false }
      }
    });
    queryClient.setQueryData(["global-connector-sync-status", "lidl_plus_de"], {
      source_id: "lidl_plus_de",
      status: "running",
      command: "python -m lidltool.cli connectors sync --source-id lidl_plus_de",
      pid: 1234,
      started_at: "2026-04-15T10:00:00Z",
      finished_at: null,
      return_code: null,
      output_tail: ["stage=discovering seen=1/? queued=4"],
      can_cancel: true
    } satisfies connectorsApi.ConnectorSyncStatus);
    vi.spyOn(connectorsApi, "fetchConnectorSyncStatus").mockRejectedValue(new Error("sync status unavailable"));

    renderShell("/transactions", { queryClient });

    await waitFor(() => {
      expect(screen.queryByText("Lidl sync")).not.toBeInTheDocument();
      expect(screen.queryByText("Lidl-Synchronisierung")).not.toBeInTheDocument();
    });
  });

  it("keeps unsupported desktop routes out of the visible finance rail", () => {
    renderShell();

    expect(screen.queryByRole("link", { name: "Offers" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Automations" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Reliability" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Connectors" })[0]).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Open chat" })[0]).toBeInTheDocument();
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
    fireEvent.mouseEnter(screen.getByRole("link", { name: "Purchases" }));

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/groceries");
  });

  it("deduplicates Amazon in the sidebar and hides inactive external plugins", async () => {
    vi.spyOn(connectorsApi, "fetchConnectors").mockResolvedValue({
      generated_at: "2026-04-12T12:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 5, by_status: { ready: 4, setup_required: 1 } },
      connectors: [
        {
          source_id: "amazon_de",
          display_name: "Amazon",
          origin: "builtin",
          install_origin: "builtin",
          supports_sync: true,
          install_state: "installed",
          enable_state: "enabled",
          ui: { status: "connected" }
        } as unknown as connectorsApi.ConnectorDiscoveryRow,
        {
          source_id: "amazon_fr",
          display_name: "Amazon",
          origin: "builtin",
          install_origin: "builtin",
          supports_sync: true,
          install_state: "installed",
          enable_state: "enabled",
          ui: { status: "ready" }
        } as unknown as connectorsApi.ConnectorDiscoveryRow,
        {
          source_id: "amazon_gb",
          display_name: "Amazon",
          origin: "builtin",
          install_origin: "builtin",
          supports_sync: true,
          install_state: "installed",
          enable_state: "disabled",
          ui: { status: "setup_required" }
        } as unknown as connectorsApi.ConnectorDiscoveryRow,
        {
          source_id: "lidl_plus_de",
          display_name: "Lidl Plus",
          origin: "builtin",
          install_origin: "builtin",
          supports_sync: true,
          install_state: "installed",
          enable_state: "enabled",
          ui: { status: "ready" }
        } as unknown as connectorsApi.ConnectorDiscoveryRow,
        {
          source_id: "rossmann_de",
          display_name: "Rossmann",
          origin: "local_path",
          install_origin: "local_path",
          supports_sync: true,
          install_state: "installed",
          enable_state: "disabled",
          ui: { status: "ready" }
        } as unknown as connectorsApi.ConnectorDiscoveryRow
      ]
    });

    renderShell();

    expect(await screen.findByText("Amazon")).toBeInTheDocument();
    expect(screen.getByText("Lidl Plus")).toBeInTheDocument();
    expect(screen.queryByText("Rossmann")).not.toBeInTheDocument();
    expect(screen.getAllByText("Amazon")).toHaveLength(1);
    expect(screen.getByText("Amazon").closest("div")).toHaveClass("text-emerald-100");
  });

  it("prefetches visible shortcut route modules when focused", () => {
    const preloadRouteModuleSpy = vi.spyOn(pageLoaders, "preloadRouteModule").mockImplementation(() => undefined);

    renderShell();
    fireEvent.focus(screen.getAllByRole("link", { name: "Connectors" })[0]);

    expect(preloadRouteModuleSpy).toHaveBeenCalledWith("/connectors");
  });

  it("opens the side chat panel from the footer button without leaving the current page", () => {
    renderShell();

    expect(screen.queryByRole("dialog", { name: "AI Assistant" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open chat" }));

    expect(screen.getByRole("dialog", { name: "AI Assistant" })).toBeInTheDocument();
    expect(screen.getByText("Transactions content")).toBeInTheDocument();
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

  it("surfaces partial sync completion instead of a hard failure when receipts were already processed", async () => {
    vi.spyOn(connectorsApi, "fetchConnectors").mockResolvedValue({
      generated_at: "2026-04-18T17:10:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { ready: 1 } },
      connectors: [
        {
          source_id: "rewe_de",
          display_name: "REWE",
          supports_sync: true,
          install_state: "installed"
        } as unknown as connectorsApi.ConnectorDiscoveryRow
      ]
    });
    vi.spyOn(connectorsApi, "fetchConnectorSyncStatus").mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: "failed",
      command: "python -m lidltool.cli connectors sync --source-id rewe_de",
      pid: null,
      started_at: "2026-04-18T17:08:00Z",
      finished_at: "2026-04-18T17:08:15Z",
      return_code: 1,
      output_tail: ["stage=processing seen=2/? new=2 detail=preparing_import"],
      can_cancel: false
    }));

    renderShell();

    expect(await screen.findByText("REWE sync")).toBeInTheDocument();
    expect(screen.getByText("With issues")).toBeInTheDocument();
    expect(screen.getByText("2 processed")).toBeInTheDocument();
    expect(screen.getByText("The import already saved receipts, but a later follow-up step still needs attention.")).toBeInTheDocument();
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
  });
});
