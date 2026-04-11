import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OffersPage } from "../OffersPage";

const toastMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn()
}));

const aiMocks = vi.hoisted(() => ({
  fetchAISettings: vi.fn(),
  fetchAIAgentConfig: vi.fn()
}));

const offersMocks = vi.hoisted(() => ({
  deleteOfferSource: vi.fn(),
  deleteOfferWatchlist: vi.fn(),
  fetchOfferAlerts: vi.fn(),
  fetchOfferMatches: vi.fn(),
  fetchOfferMerchantItems: vi.fn(),
  fetchOfferRefreshRuns: vi.fn(),
  fetchOfferSources: vi.fn(),
  fetchOffersOverview: vi.fn(),
  fetchOfferWatchlists: vi.fn(),
  patchOfferAlert: vi.fn(),
  postOfferRefresh: vi.fn(),
  updateOfferWatchlist: vi.fn()
}));

const automationsMocks = vi.hoisted(() => ({
  fetchAutomationRules: vi.fn()
}));

const agentMocks = vi.hoisted(() => ({
  prompt: vi.fn(),
  subscribe: vi.fn(() => () => undefined),
  createSpendingAgent: vi.fn()
}));

vi.mock("sonner", () => ({
  toast: toastMocks
}));

vi.mock("@/api/aiSettings", () => ({
  fetchAISettings: aiMocks.fetchAISettings,
  fetchAIAgentConfig: aiMocks.fetchAIAgentConfig
}));

vi.mock("@/api/offers", () => ({
  deleteOfferSource: offersMocks.deleteOfferSource,
  deleteOfferWatchlist: offersMocks.deleteOfferWatchlist,
  fetchOfferAlerts: offersMocks.fetchOfferAlerts,
  fetchOfferMatches: offersMocks.fetchOfferMatches,
  fetchOfferMerchantItems: offersMocks.fetchOfferMerchantItems,
  fetchOfferRefreshRuns: offersMocks.fetchOfferRefreshRuns,
  fetchOfferSources: offersMocks.fetchOfferSources,
  fetchOffersOverview: offersMocks.fetchOffersOverview,
  fetchOfferWatchlists: offersMocks.fetchOfferWatchlists,
  patchOfferAlert: offersMocks.patchOfferAlert,
  postOfferRefresh: offersMocks.postOfferRefresh,
  updateOfferWatchlist: offersMocks.updateOfferWatchlist
}));

vi.mock("@/api/automations", () => ({
  fetchAutomationRules: automationsMocks.fetchAutomationRules
}));

vi.mock("@/agent", () => ({
  createSpendingAgent: agentMocks.createSpendingAgent
}));

let testQueryClient: QueryClient | null = null;

function renderOffersPage(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0
      },
      mutations: {
        retry: false,
        gcTime: 0
      }
    }
  });
  testQueryClient = queryClient;

  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <OffersPage />
      </QueryClientProvider>
    </MemoryRouter>
  );

  return queryClient;
}

describe("OffersPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    toastMocks.success.mockReset();
    toastMocks.error.mockReset();
    aiMocks.fetchAISettings.mockReset();
    aiMocks.fetchAIAgentConfig.mockReset();
    offersMocks.deleteOfferSource.mockReset();
    offersMocks.deleteOfferWatchlist.mockReset();
    offersMocks.fetchOfferAlerts.mockReset();
    offersMocks.fetchOfferMatches.mockReset();
    offersMocks.fetchOfferMerchantItems.mockReset();
    offersMocks.fetchOfferRefreshRuns.mockReset();
    offersMocks.fetchOfferSources.mockReset();
    offersMocks.fetchOffersOverview.mockReset();
    offersMocks.fetchOfferWatchlists.mockReset();
    offersMocks.patchOfferAlert.mockReset();
    offersMocks.postOfferRefresh.mockReset();
    offersMocks.updateOfferWatchlist.mockReset();
    automationsMocks.fetchAutomationRules.mockReset();
    agentMocks.prompt.mockReset();
    agentMocks.subscribe.mockReset();
    agentMocks.createSpendingAgent.mockReset();
    HTMLElement.prototype.scrollIntoView = vi.fn();

    aiMocks.fetchAISettings.mockResolvedValue({
      enabled: true,
      base_url: "https://example.test",
      model: "gpt-5.2-codex",
      api_key_set: false,
      oauth_provider: "openai-codex",
      oauth_connected: true,
      remote_enabled: true,
      local_runtime_enabled: false,
      local_runtime_ready: false,
      local_runtime_status: "disabled"
    });
    aiMocks.fetchAIAgentConfig.mockResolvedValue({
      proxy_url: "",
      auth_token: "token",
      model: "gpt-5.2-codex",
      default_model: "gpt-5.2-codex",
      local_model: "gpt-5.2-codex",
      preferred_model: "gpt-5.2-codex",
      oauth_provider: "openai-codex",
      oauth_connected: true,
      available_models: [
        {
          id: "gpt-5.2-codex",
          label: "GPT-5.2 Codex",
          source: "oauth",
          enabled: true,
          description: "Connected ChatGPT model"
        }
      ]
    });
    agentMocks.createSpendingAgent.mockReturnValue({
      prompt: agentMocks.prompt,
      subscribe: agentMocks.subscribe,
      state: { messages: [] }
    });
    agentMocks.prompt.mockResolvedValue(undefined);
    agentMocks.subscribe.mockReturnValue(() => undefined);
    offersMocks.fetchOffersOverview.mockResolvedValue({
      counts: {
        watchlists: 0,
        active_matches: 0,
        unread_alerts: 0
      },
      sources: [],
      recent_refresh_runs: [],
      last_refresh_at: null
    });
    offersMocks.fetchOfferSources.mockResolvedValue({
      items: [
        {
          id: "source-1",
          source_id: "rewe_berlin",
          plugin_id: "agent.user_defined",
          display_name: "REWE Berlin",
          merchant_name: "REWE",
          country_code: "DE",
          runtime_kind: "agent_url",
          merchant_url: "https://example.test/rewe-berlin",
          active: true,
          notes: null,
          active_offer_count: 3,
          total_offer_count: 8,
          latest_refresh: null
        }
      ]
    });
    offersMocks.fetchOfferWatchlists.mockResolvedValue({
      count: 0,
      items: []
    });
    offersMocks.fetchOfferMatches.mockResolvedValue({
      count: 0,
      items: []
    });
    offersMocks.fetchOfferAlerts.mockResolvedValue({
      count: 0,
      items: []
    });
    offersMocks.fetchOfferRefreshRuns.mockResolvedValue({
      count: 0,
      items: []
    });
    offersMocks.fetchOfferMerchantItems.mockResolvedValue({
      count: 0,
      items: []
    });
    automationsMocks.fetchAutomationRules.mockResolvedValue({
      count: 0,
      total: 0,
      limit: 200,
      offset: 0,
      items: []
    });
  });

  afterEach(() => {
    testQueryClient?.clear();
    testQueryClient = null;
    cleanup();
  });

  it("renders the offer agent workflow when AI is enabled", async () => {
    renderOffersPage();

    await waitFor(() => {
      expect(screen.getByText("Ask Agent to Set Up Offers")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(agentMocks.createSpendingAgent).toHaveBeenCalled();
    });

    expect(screen.getByText("Offer setup runs through the AI assistant")).toBeInTheDocument();
    expect(screen.getByText(/Offer sources:/)).toBeInTheDocument();
  });

  it("routes setup requests through the offer agent", async () => {
    renderOffersPage();

    await waitFor(() => {
      expect(agentMocks.createSpendingAgent).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Let agent handle it" })).toBeInTheDocument();
    });

    fireEvent.change(
      screen.getByPlaceholderText(
        "Example: Add an offer source for https://www.edeka.de/maerkte/402268/angebote/ and watch for diapers every Monday at 20:00."
      ),
      {
        target: { value: "Watch for oat milk at REWE and refresh every Monday at 08:00." }
      }
    );
    fireEvent.click(screen.getByRole("button", { name: "Let agent handle it" }));

    await waitFor(() => {
      expect(agentMocks.prompt).toHaveBeenCalledWith(
        "Watch for oat milk at REWE and refresh every Monday at 08:00."
      );
    });
  });

  it("blocks the assistant workflow when AI is disabled", async () => {
    aiMocks.fetchAISettings.mockResolvedValueOnce({
      enabled: false,
      base_url: null,
      model: "gpt-5.2-codex",
      api_key_set: false,
      oauth_provider: null,
      oauth_connected: false,
      remote_enabled: false,
      local_runtime_enabled: false,
      local_runtime_ready: false,
      local_runtime_status: "disabled"
    });

    renderOffersPage();

    await waitFor(() => {
      expect(screen.getAllByText("AI assistant required").length).toBeGreaterThan(0);
    });

    expect(screen.getByRole("button", { name: "Refresh selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Let agent handle it" })).toBeDisabled();
  });

  it("summarizes long refresh failures in the source card", async () => {
    offersMocks.fetchOfferRefreshRuns.mockResolvedValueOnce({
      count: 1,
      items: [
        {
          id: "run-1",
          user_id: null,
          rule_id: null,
          trigger_kind: "manual",
          status: "failed",
          source_count: 1,
          source_ids: ["rewe_berlin"],
          started_at: "2026-04-03T12:24:46.830121+00:00",
          finished_at: "2026-04-03T12:24:47.205073+00:00",
          created_at: "2026-04-03T12:24:46.830121+00:00",
          updated_at: "2026-04-03T12:24:47.205073+00:00",
          error: "1 source refresh(es) failed",
          totals: {
            offers_seen: 0,
            inserted: 0,
            updated: 0,
            blocked: 0,
            matched: 0,
            alerts_created: 0
          },
          source_results: [
            {
              source_id: "rewe_berlin",
              status: "failed",
              error:
                "Client error '403 Forbidden' for url 'https://example.test/rewe-berlin'\nFor more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403",
              offers_seen: 0,
              inserted: 0,
              updated: 0,
              blocked: 0,
              matched: 0,
              alerts_created: 0
            }
          ],
          success_count: 0,
          failure_count: 1
        }
      ]
    });

    renderOffersPage();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Merchant page blocked the old direct HTTP fetch with 403. Retry after the browser-backed refresh runtime is available."
        )
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByText(/developer\.mozilla\.org\/en-US\/docs\/Web\/HTTP\/Status\/403/)
    ).not.toBeInTheDocument();
  });
});
