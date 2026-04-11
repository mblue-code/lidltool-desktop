import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { AISettingsPage } from "../AISettingsPage";
import { ChatWorkspacePage } from "../ChatWorkspacePage";
import { ConnectorsPage } from "../ConnectorsPage";
import { SetupPage } from "../SetupPage";
import { UsersSettingsPage } from "../UsersSettingsPage";

const mocks = vi.hoisted(() => ({
  fetchConnectorsMock: vi.fn(),
  fetchConnectorConfigMock: vi.fn(),
  reloadConnectorsMock: vi.fn(),
  fetchConnectorCascadeStatusMock: vi.fn(),
  fetchConnectorBootstrapStatusMock: vi.fn(),
  fetchConnectorSyncStatusMock: vi.fn(),
  submitConnectorConfigMock: vi.fn(),
  startConnectorCascadeMock: vi.fn(),
  cancelConnectorCascadeMock: vi.fn(),
  retryConnectorCascadeMock: vi.fn(),
  startConnectorBootstrapMock: vi.fn(),
  cancelConnectorBootstrapMock: vi.fn(),
  startConnectorSyncMock: vi.fn(),
  fetchSourcesMock: vi.fn(),
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
  fetchConnectors: mocks.fetchConnectorsMock,
  fetchConnectorConfig: mocks.fetchConnectorConfigMock,
  reloadConnectors: mocks.reloadConnectorsMock,
  fetchConnectorCascadeStatus: mocks.fetchConnectorCascadeStatusMock,
  fetchConnectorBootstrapStatus: mocks.fetchConnectorBootstrapStatusMock,
  fetchConnectorSyncStatus: mocks.fetchConnectorSyncStatusMock,
  submitConnectorConfig: mocks.submitConnectorConfigMock,
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

function renderGerman(ui: ReactElement): void {
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
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: {
        can_reload: true,
        can_rescan: true
      },
      summary: {
        total_connectors: 1,
        by_status: {
          ready: 1
        }
      },
      connectors: [
        {
          source_id: "lidl_plus_de",
          plugin_id: "builtin.lidl_plus_de",
          display_name: "Lidl Plus",
          origin: "builtin",
          origin_label: "Built-in",
          runtime_kind: "builtin",
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "not_required",
          maturity: "working",
          maturity_label: "Working",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: true,
          supports_live_session_bootstrap: true,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: "1 new receipt",
          last_synced_at: "2026-04-01T08:00:00Z",
          ui: {
            status: "ready",
            visibility: "default",
            description: "Desktop-ready connector.",
            actions: {
              primary: { kind: "sync_now", enabled: true },
              secondary: { kind: "view_receipts", href: "/receipts", enabled: true },
              operator: {
                full_sync: true,
                rescan: true,
                reload: true,
                install: false,
                enable: false,
                disable: false,
                uninstall: false,
                configure: false,
                manual_commands: {
                  sync: "lidltool sync"
                }
              }
            }
          },
          actions: {
            primary: { kind: "sync_now", enabled: true },
            secondary: { kind: "view_receipts", href: "/receipts", enabled: true },
            operator: {
              full_sync: true,
              rescan: true,
              reload: true,
              install: false,
              enable: false,
              disable: false,
              uninstall: false,
              configure: false,
              manual_commands: {
                sync: "lidltool sync"
              }
            }
          },
          advanced: {
            source_exists: true,
            stale: false,
            stale_reason: null,
            auth_state: "connected",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "idle",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: "enabled",
              status_detail: null,
              trust_class: "official",
              external_runtime_enabled: false,
              external_receipt_plugins_enabled: false,
              allowed_trust_classes: []
            },
            release: {
              maturity: "working",
              label: "Working",
              support_posture: "Usable",
              description: "Desktop-ready connector.",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "builtin",
              runtime_kind: "builtin",
              search_path: null,
              origin_path: null,
              origin_directory: null
            },
            diagnostics: [],
            manual_commands: {
              sync: "lidltool sync"
            }
          }
        }
      ]
    });
    mocks.fetchConnectorConfigMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      plugin_id: "builtin.lidl_plus_de",
      display_name: "Lidl Plus",
      install_origin: "builtin",
      config_state: "not_required",
      fields: []
    });
    mocks.reloadConnectorsMock.mockResolvedValue({});
    mocks.submitConnectorConfigMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      plugin_id: "builtin.lidl_plus_de",
      display_name: "Lidl Plus",
      install_origin: "builtin",
      config_state: "not_required",
      fields: []
    });
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
      oauth_connected: false,
      remote_enabled: true,
      local_runtime_enabled: false,
      local_runtime_ready: false,
      local_runtime_status: "unavailable"
    });
    mocks.fetchAIOAuthStatusMock.mockResolvedValue({ status: "pending", error: null });
    mocks.saveAISettingsMock.mockResolvedValue({ ok: true, error: null });
    mocks.startAIOAuthMock.mockResolvedValue({ auth_url: "https://example.com/oauth", expires_in: 300 });
    mocks.disconnectAISettingsMock.mockResolvedValue({ ok: true });
    mocks.fetchAIAgentConfigMock.mockResolvedValue({
      proxy_url: "https://proxy.example.com",
      auth_token: "token",
      model: "gpt-4o-mini",
      default_model: "gpt-4o-mini",
      local_model: "gpt-4o-mini",
      preferred_model: "gpt-4o-mini",
      oauth_provider: null,
      oauth_connected: false,
      available_models: [
        {
          id: "gpt-4o-mini",
          label: "GPT-4o mini",
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
        installReceiptPluginFromDialog: vi.fn().mockResolvedValue(null),
        installReceiptPluginFromCatalogEntry: vi.fn().mockResolvedValue({
          action: "installed",
          pack: {
            pluginId: "community.fixture",
            sourceId: "fixture_receipt_de",
            displayName: "Fixture Receipt",
            version: "1.0.0",
            trustClass: "community_verified",
            enabled: false,
            status: "disabled",
            trustStatus: "trusted",
            trustReason: null,
            compatibilityReason: null,
            installedVia: "catalog_url",
            catalogEntryId: "desktop-pack.fixture"
          },
          restartedBackend: false,
          backendStatus: null
        }),
        enableReceiptPlugin: vi.fn().mockResolvedValue({
          pack: {
            pluginId: "community.fixture",
            sourceId: "fixture_receipt_de",
            displayName: "Fixture Receipt",
            version: "1.0.0",
            trustClass: "community_verified",
            enabled: true,
            status: "enabled",
            trustStatus: "trusted",
            trustReason: null,
            compatibilityReason: null,
            installedVia: "catalog_url",
            catalogEntryId: "desktop-pack.fixture"
          },
          restartedBackend: false,
          backendStatus: null
        }),
        disableReceiptPlugin: vi.fn().mockResolvedValue({
          pack: {
            pluginId: "community.fixture",
            sourceId: "fixture_receipt_de",
            displayName: "Fixture Receipt",
            version: "1.0.0",
            trustClass: "community_verified",
            enabled: false,
            status: "disabled",
            trustStatus: "trusted",
            trustReason: null,
            compatibilityReason: null,
            installedVia: "catalog_url",
            catalogEntryId: "desktop-pack.fixture"
          },
          restartedBackend: false,
          backendStatus: null
        }),
        uninstallReceiptPlugin: vi.fn().mockResolvedValue({
          pluginId: "community.fixture",
          removedPath: null,
          restartedBackend: false,
          backendStatus: null
        }),
        getReleaseMetadata: vi.fn().mockResolvedValue({
          active_release_variant: { display_name: "Desktop Universal Shell" },
          selected_market_profile: { display_name: "Germany" },
          discovery_catalog: {
            entries: [
              {
                entry_id: "connector.builtin.lidl_plus_de",
                entry_type: "connector",
                display_name: "Lidl Plus",
                summary: "Official connector",
                description: null,
                trust_class: "official",
                current_version: "1.0.0",
                support_policy: {
                  display_name: "Official",
                  ui_label: "Official",
                  diagnostics_expectation: "Project-maintained desktop path.",
                  update_expectations: "Ships with desktop releases.",
                  maintainer_support: "Project-maintained."
                },
                official_bundle_ids: ["official.de_receipts_core"],
                market_profile_ids: ["dach_starter"],
                release_variant_ids: ["desktop_universal_shell"],
                install_methods: ["built_in"],
                plugin_id: "builtin.lidl_plus_de",
                source_id: "lidl_plus_de"
              }
            ]
          }
        }),
        listReceiptPlugins: vi.fn().mockResolvedValue({
          packs: [],
          activePluginSearchPaths: []
        }),
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

    expect(await screen.findByText("Anbindungen")).toBeInTheDocument();
    expect(screen.getByText("Desktop receipt packs can be managed here")).toBeInTheDocument();
    expect(await screen.findByText("Lidl Plus")).toBeInTheDocument();
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
    expect(screen.getByText("System-Backup")).toBeInTheDocument();
    expect(screen.getByText("Desktop-Wiederherstellung")).toBeInTheDocument();
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
});
