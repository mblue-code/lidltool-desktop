import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { AISettingsPage } from "../AISettingsPage";
import { ChatWorkspacePage } from "../ChatWorkspacePage";
import { ConnectorsPage } from "../ConnectorsPage";
import { OffersPage } from "../OffersPage";
import { SetupPage } from "../SetupPage";
import { UsersSettingsPage } from "../UsersSettingsPage";

const mocks = vi.hoisted(() => ({
  fetchConnectorCascadeStatusMock: vi.fn(),
  fetchConnectorBootstrapStatusMock: vi.fn(),
  fetchConnectorSyncStatusMock: vi.fn(),
  startConnectorCascadeMock: vi.fn(),
  cancelConnectorCascadeMock: vi.fn(),
  retryConnectorCascadeMock: vi.fn(),
  startConnectorBootstrapMock: vi.fn(),
  cancelConnectorBootstrapMock: vi.fn(),
  startConnectorSyncMock: vi.fn(),
  fetchSourcesMock: vi.fn(),
  fetchProductsMock: vi.fn(),
  fetchOfferWatchlistsMock: vi.fn(),
  fetchOfferAlertsMock: vi.fn(),
  createOfferWatchlistMock: vi.fn(),
  refreshOffersMock: vi.fn(),
  patchOfferAlertMock: vi.fn(),
  fetchAISettingsMock: vi.fn(),
  fetchAIOAuthStatusMock: vi.fn(),
  saveAISettingsMock: vi.fn(),
  startAIOAuthMock: vi.fn(),
  disconnectAISettingsMock: vi.fn(),
  fetchAIAgentConfigMock: vi.fn(),
  fetchCurrentUserMock: vi.fn(),
  updateCurrentUserLocaleMock: vi.fn(),
  fetchUsersMock: vi.fn(),
  fetchAgentKeysMock: vi.fn(),
  createUserMock: vi.fn(),
  updateUserMock: vi.fn(),
  deleteUserMock: vi.fn(),
  createAgentKeyMock: vi.fn(),
  revokeAgentKeyMock: vi.fn(),
  runSystemBackupMock: vi.fn(),
  listChatThreadsMock: vi.fn(),
  listChatMessagesMock: vi.fn(),
  createChatThreadMock: vi.fn(),
  createChatMessageMock: vi.fn(),
  patchChatThreadMock: vi.fn(),
  persistChatRunMock: vi.fn(),
  createSpendingAgentMock: vi.fn()
}));

vi.mock("@/api/connectors", () => ({
  fetchConnectorCascadeStatus: mocks.fetchConnectorCascadeStatusMock,
  fetchConnectorBootstrapStatus: mocks.fetchConnectorBootstrapStatusMock,
  fetchConnectorSyncStatus: mocks.fetchConnectorSyncStatusMock,
  startConnectorCascade: mocks.startConnectorCascadeMock,
  cancelConnectorCascade: mocks.cancelConnectorCascadeMock,
  retryConnectorCascade: mocks.retryConnectorCascadeMock,
  startConnectorBootstrap: mocks.startConnectorBootstrapMock,
  cancelConnectorBootstrap: mocks.cancelConnectorBootstrapMock,
  startConnectorSync: mocks.startConnectorSyncMock
}));

vi.mock("@/api/sources", () => ({
  fetchSources: mocks.fetchSourcesMock
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

vi.mock("@/api/aiSettings", () => ({
  fetchAISettings: mocks.fetchAISettingsMock,
  fetchAIOAuthStatus: mocks.fetchAIOAuthStatusMock,
  saveAISettings: mocks.saveAISettingsMock,
  startAIOAuth: mocks.startAIOAuthMock,
  disconnectAISettings: mocks.disconnectAISettingsMock,
  fetchAIAgentConfig: mocks.fetchAIAgentConfigMock
}));

vi.mock("@/api/users", () => ({
  fetchCurrentUser: mocks.fetchCurrentUserMock,
  updateCurrentUserLocale: mocks.updateCurrentUserLocaleMock,
  fetchUsers: mocks.fetchUsersMock,
  fetchAgentKeys: mocks.fetchAgentKeysMock,
  createUser: mocks.createUserMock,
  updateUser: mocks.updateUserMock,
  deleteUser: mocks.deleteUserMock,
  createAgentKey: mocks.createAgentKeyMock,
  revokeAgentKey: mocks.revokeAgentKeyMock
}));

vi.mock("@/api/systemBackup", () => ({
  runSystemBackup: mocks.runSystemBackupMock
}));

vi.mock("@/api/chat", () => ({
  listChatThreads: mocks.listChatThreadsMock,
  listChatMessages: mocks.listChatMessagesMock,
  createChatThread: mocks.createChatThreadMock,
  createChatMessage: mocks.createChatMessageMock,
  patchChatThread: mocks.patchChatThreadMock,
  persistChatRun: mocks.persistChatRunMock
}));

vi.mock("@/agent", () => ({
  createSpendingAgent: mocks.createSpendingAgentMock
}));

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn()
  }
}));

const IDLE_BOOTSTRAP = {
  source_id: "",
  status: "idle" as const,
  command: null,
  pid: null,
  started_at: null,
  finished_at: null,
  return_code: null,
  output_tail: [],
  can_cancel: false,
  remote_login_url: null
};

const IDLE_SYNC = {
  source_id: "",
  status: "idle" as const,
  command: null,
  pid: null,
  started_at: null,
  finished_at: null,
  return_code: null,
  output_tail: [],
  can_cancel: false
};

function renderGerman(ui: JSX.Element): void {
  window.localStorage.setItem("app.locale", "de");
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>{ui}</I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("launch-critical route i18n smoke", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    mocks.fetchSourcesMock.mockResolvedValue({
      sources: [{ id: "lidl_plus_de", status: "healthy" }]
    });
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
        }
      ],
      count: 1
    });
    mocks.fetchOfferWatchlistsMock.mockResolvedValue({
      items: [],
      count: 0,
      total: 0,
      limit: 25,
      offset: 0
    });
    mocks.fetchOfferAlertsMock.mockResolvedValue({
      items: [],
      count: 0,
      total: 0,
      limit: 25,
      offset: 0,
      unread_count: 0
    });
    mocks.createOfferWatchlistMock.mockResolvedValue({});
    mocks.refreshOffersMock.mockResolvedValue({});
    mocks.patchOfferAlertMock.mockResolvedValue({});
    mocks.fetchConnectorCascadeStatusMock.mockResolvedValue({
      status: "idle",
      source_ids: [],
      full: false,
      started_at: null,
      finished_at: null,
      current_source_id: null,
      current_step: null,
      can_cancel: false,
      remote_login_url: null,
      summary: {
        total_sources: 0,
        completed: 0,
        failed: 0,
        canceled: 0,
        pending: 0,
        skipped: 0
      },
      sources: []
    });
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => ({
      ...IDLE_BOOTSTRAP,
      source_id: sourceId
    }));
    mocks.fetchConnectorSyncStatusMock.mockImplementation(async (sourceId: string) => ({
      ...IDLE_SYNC,
      source_id: sourceId
    }));

    mocks.fetchAISettingsMock.mockResolvedValue({
      enabled: true,
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
      api_key_set: true,
      oauth_provider: null,
      oauth_connected: false
    });
    mocks.fetchAIOAuthStatusMock.mockResolvedValue({ status: "pending", error: null });
    mocks.saveAISettingsMock.mockResolvedValue({ ok: true, error: null });
    mocks.startAIOAuthMock.mockResolvedValue({ auth_url: "https://example.com/oauth", expires_in: 300 });
    mocks.disconnectAISettingsMock.mockResolvedValue({ ok: true });
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "https://proxy.example.com",
      auth_token: "token",
      model: "Qwen/Qwen3.5-0.8B",
      default_model: "Qwen/Qwen3.5-0.8B",
      local_model: "Qwen/Qwen3.5-0.8B",
      preferred_model: "Qwen/Qwen3.5-0.8B",
      oauth_provider: null,
      oauth_connected: false,
      available_models: [
        {
          id: "Qwen/Qwen3.5-0.8B",
          label: "Qwen",
          source: "local",
          enabled: true
        }
      ]
    });

    mocks.fetchCurrentUserMock.mockResolvedValue({
      user_id: "u1",
      username: "admin",
      display_name: "Admin",
      is_admin: true
    });
    mocks.fetchUsersMock.mockResolvedValue({
      users: [
        {
          user_id: "u2",
          username: "anna",
          display_name: null,
          is_admin: false,
          created_at: "2026-03-08T12:00:00Z",
          updated_at: "2026-03-08T12:00:00Z"
        }
      ],
      count: 1
    });
    mocks.fetchAgentKeysMock.mockResolvedValue({
      keys: [
        {
          key_id: "k1",
          user_id: "u1",
          label: "CLI",
          key_prefix: "oc_123",
          is_active: true,
          last_used_at: null,
          expires_at: null,
          created_at: "2026-03-08T12:00:00Z"
        }
      ],
      count: 1
    });
    mocks.createUserMock.mockResolvedValue({});
    mocks.updateUserMock.mockResolvedValue({});
    mocks.deleteUserMock.mockResolvedValue({ user_id: "u2", deleted: true });
    mocks.createAgentKeyMock.mockResolvedValue({
      api_key: "secret",
      key: {
        key_id: "k2",
        user_id: "u1",
        label: "CLI",
        key_prefix: "oc_456",
        is_active: true,
        last_used_at: null,
        expires_at: null,
        created_at: "2026-03-08T12:00:00Z"
      }
    });
    mocks.revokeAgentKeyMock.mockResolvedValue({ key_id: "k1", revoked: true });
    mocks.runSystemBackupMock.mockResolvedValue({
      provider: "desktop",
      output_dir: "/tmp/backup",
      db_artifact: "/tmp/backup/lidltool.sqlite",
      token_artifact: null,
      documents_artifact: null,
      credential_key_artifact: null,
      export_artifact: null,
      export_records: null,
      manifest_path: "/tmp/backup/backup-manifest.json",
      copied: ["/tmp/backup/lidltool.sqlite"],
      skipped: []
    });
    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        runImport: vi.fn().mockResolvedValue({
          ok: true,
          command: "desktop:import",
          args: [],
          exitCode: 0,
          stdout: "",
          stderr: ""
        })
      }
    });

    mocks.listChatThreadsMock.mockResolvedValue({
      items: [
        {
          thread_id: "t1",
          user_id: "u1",
          title: "Wochenbudget",
          stream_status: "streaming",
          created_at: "2026-03-08T12:00:00Z",
          updated_at: "2026-03-08T12:30:00Z",
          archived_at: null
        }
      ],
      total: 1
    });
    mocks.listChatMessagesMock.mockResolvedValue({ items: [], total: 0 });
    mocks.createChatThreadMock.mockResolvedValue({});
    mocks.createChatMessageMock.mockResolvedValue({});
    mocks.patchChatThreadMock.mockResolvedValue({});
    mocks.persistChatRunMock.mockResolvedValue({});
    mocks.createSpendingAgentMock.mockReturnValue({
      subscribe: () => () => undefined,
      state: { messages: [] },
      replaceMessages: vi.fn(),
      prompt: vi.fn()
    });
  });

  afterEach(() => {
    cleanup();
    window.localStorage.removeItem("app.locale");
  });

  it("renders connectors copy in german", async () => {
    renderGerman(<ConnectorsPage />);

    expect(await screen.findByText("Anbindungen einrichten")).toBeInTheDocument();
    expect(screen.getAllByText("Alle synchronisieren").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Quellen öffnen").length).toBeGreaterThan(0);
  });

  it("renders ai settings copy in german", async () => {
    renderGerman(<AISettingsPage />);

    expect(await screen.findByText("KI-Assistent")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "API-Schlüssel" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Anmelden mit..." })).toBeInTheDocument();
  });

  it("renders user settings copy in german", async () => {
    renderGerman(<UsersSettingsPage />);

    expect(await screen.findByText("Benutzer und Agent-Schlüssel")).toBeInTheDocument();
    expect(await screen.findByText("Benutzer hinzufügen")).toBeInTheDocument();
    expect(screen.getByText("Schlüssel erstellen")).toBeInTheDocument();
    expect(screen.getByText("Benutzer")).toBeInTheDocument();
    expect(screen.getByText("Agent-API-Schlüssel")).toBeInTheDocument();
  });

  it("renders setup restore copy in german", async () => {
    renderGerman(<SetupPage />);

    expect(await screen.findByText("Aus Backup wiederherstellen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Backup wiederherstellen und anmelden" })).toBeInTheDocument();
  });

  it("renders chat workspace copy and statuses in german", async () => {
    renderGerman(<ChatWorkspacePage />);

    expect(await screen.findByText("Persistente Threads mit serverseitigem Verlauf.")).toBeInTheDocument();
    expect(await screen.findByText("Wochenbudget")).toBeInTheDocument();
    expect(screen.getAllByText("streamt").length).toBeGreaterThan(0);
    expect(screen.getByText("Neuer Chat")).toBeInTheDocument();
  });

  it("renders offers copy in german", async () => {
    renderGerman(<OffersPage />);

    expect(await screen.findByText("Watchlist hinzufügen")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Angebote aktualisieren" })).toBeInTheDocument();
    expect(screen.getByText("Nur konfigurierte Quellen")).toBeInTheDocument();
  });
});
