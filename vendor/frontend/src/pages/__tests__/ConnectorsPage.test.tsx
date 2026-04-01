import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ConnectorsPage } from "../ConnectorsPage";

const mocks = vi.hoisted(() => ({
  fetchConnectorsMock: vi.fn(),
  fetchConnectorConfigMock: vi.fn(),
  reloadConnectorsMock: vi.fn(),
  startConnectorBootstrapMock: vi.fn(),
  startConnectorSyncMock: vi.fn(),
  submitConnectorConfigMock: vi.fn()
}));

vi.mock("@/api/connectors", () => ({
  fetchConnectors: mocks.fetchConnectorsMock,
  fetchConnectorConfig: mocks.fetchConnectorConfigMock,
  reloadConnectors: mocks.reloadConnectorsMock,
  startConnectorBootstrap: mocks.startConnectorBootstrapMock,
  startConnectorSync: mocks.startConnectorSyncMock,
  submitConnectorConfig: mocks.submitConnectorConfigMock
}));

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <ConnectorsPage />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ConnectorsPage", () => {
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
    window.localStorage.setItem("app.locale", "en");

    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { ready: 1 } },
      connectors: [
        {
          source_id: "amazon_de",
          plugin_id: "community.amazon_de",
          display_name: "Amazon",
          origin: "local_path",
          origin_label: "External",
          runtime_kind: "python",
          install_origin: "local_path",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "complete",
          maturity: "preview",
          maturity_label: "Preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: true,
          supports_live_session_bootstrap: true,
          trust_class: "community_verified",
          status_detail: "Stored from a desktop receipt pack.",
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "connected",
            visibility: "default",
            description: "Occasional local Amazon sync.",
            actions: {
              primary: { kind: "reconnect", enabled: true },
              secondary: { kind: "view_receipts", href: "/receipts", enabled: true },
              operator: {
                full_sync: true,
                rescan: true,
                reload: true,
                install: false,
                enable: false,
                disable: false,
                uninstall: false,
                configure: true,
                manual_commands: {}
              }
            }
          },
          actions: {
            primary: { kind: "reconnect", enabled: true },
            secondary: { kind: "view_receipts", href: "/receipts", enabled: true },
            operator: {
              full_sync: true,
              rescan: true,
              reload: true,
              install: false,
              enable: false,
              disable: false,
              uninstall: false,
              configure: true,
              manual_commands: {}
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
              trust_class: "community_verified",
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["community_verified"]
            },
            release: {
              maturity: "preview",
              label: "Preview",
              support_posture: "Preview",
              description: "Desktop-managed pack.",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "local_path",
              runtime_kind: "python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/amazon",
              origin_directory: "/tmp/plugins"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorConfigMock.mockResolvedValue({
      source_id: "amazon_de",
      plugin_id: "community.amazon_de",
      display_name: "Amazon",
      install_origin: "local_path",
      config_state: "complete",
      fields: [
        {
          key: "domain",
          label: "Domain",
          input_kind: "text",
          required: true,
          sensitive: false,
          operator_only: false,
          value: "amazon.de"
        }
      ]
    });
    mocks.reloadConnectorsMock.mockResolvedValue({});
    mocks.startConnectorBootstrapMock.mockResolvedValue({
      source_id: "amazon_de",
      reused: false,
      bootstrap: {
        source_id: "amazon_de",
        status: "running",
        command: null,
        pid: null,
        started_at: null,
        finished_at: null,
        return_code: null,
        output_tail: [],
        can_cancel: true
      }
    });
    mocks.startConnectorSyncMock.mockResolvedValue({
      source_id: "amazon_de",
      reused: false,
      sync: {
        source_id: "amazon_de",
        status: "running",
        command: null,
        pid: null,
        started_at: null,
        finished_at: null,
        return_code: null,
        output_tail: [],
        can_cancel: true
      }
    });
    mocks.submitConnectorConfigMock.mockResolvedValue({
      source_id: "amazon_de",
      plugin_id: "community.amazon_de",
      display_name: "Amazon",
      install_origin: "local_path",
      config_state: "complete",
      fields: []
    });

    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        getReleaseMetadata: vi.fn().mockResolvedValue({
          active_release_variant: { display_name: "Desktop Universal Shell" },
          selected_market_profile: { display_name: "Germany" },
          discovery_catalog: {
            entries: [
              {
                entry_id: "connector.amazon",
                entry_type: "connector",
                display_name: "Amazon",
                summary: "Desktop-managed connector",
                description: null,
                trust_class: "community_verified",
                current_version: "1.4.0",
                support_policy: {
                  display_name: "Community verified",
                  ui_label: "Community verified",
                  diagnostics_expectation: "Conservative desktop trust checks apply.",
                  update_expectations: "Updates depend on catalog availability.",
                  maintainer_support: "Best effort by community maintainers."
                },
                official_bundle_ids: [],
                market_profile_ids: ["dach_starter"],
                release_variant_ids: ["desktop_universal_shell"],
                install_methods: ["manual_import"],
                plugin_id: "community.amazon_de",
                source_id: "amazon_de"
              }
            ]
          }
        }),
        listReceiptPlugins: vi.fn().mockResolvedValue({
          activePluginSearchPaths: ["/tmp/plugins"],
          packs: [
            {
              pluginId: "community.amazon_de",
              sourceId: "amazon_de",
              displayName: "Amazon",
              version: "1.2.0",
              trustClass: "community_verified",
              enabled: true,
              status: "enabled",
              trustStatus: "trusted",
              trustReason: null,
              compatibilityReason: null,
              installedVia: "manual_file",
              catalogEntryId: "connector.amazon"
            },
            {
              pluginId: "community.rewe_de",
              sourceId: "rewe_de",
              displayName: "REWE",
              version: "0.9.0",
              trustClass: "community_unsigned",
              enabled: false,
              status: "disabled",
              trustStatus: "unsigned",
              trustReason: null,
              compatibilityReason: null,
              installedVia: "manual_file",
              catalogEntryId: null
            }
          ]
        })
      }
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders desktop-native trust and stored-pack sections", async () => {
    renderPage();

    expect(await screen.findByText("Connectors")).toBeInTheDocument();
    expect(screen.getByText("Desktop pack management stays native")).toBeInTheDocument();
    expect(await screen.findByText("Amazon")).toBeInTheDocument();
    expect(await screen.findByText("Electron-managed connector")).toBeInTheDocument();
    expect(await screen.findByText("Stored receipt packs")).toBeInTheDocument();
    expect(await screen.findByText("REWE")).toBeInTheDocument();
    expect(await screen.findByText("Update available in control center")).toBeInTheDocument();
  });

  it("saves connector settings before continuing setup", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Settings" }));
    fireEvent.change(await screen.findByLabelText("Domain"), {
      target: { value: "amazon.com" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => {
      expect(mocks.submitConnectorConfigMock).toHaveBeenCalledWith("amazon_de", {
        values: {
          domain: "amazon.com"
        },
        clear_secret_keys: undefined
      });
    });
  });
});
