import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/i18n";
import { ConnectorsPage } from "../ConnectorsPage";

const mocks = vi.hoisted(() => ({
  fetchConnectorsMock: vi.fn(),
  fetchConnectorAuthStatusMock: vi.fn(),
  fetchConnectorBootstrapStatusMock: vi.fn(),
  fetchConnectorConfigMock: vi.fn(),
  cancelConnectorBootstrapMock: vi.fn(),
  reloadConnectorsMock: vi.fn(),
  startConnectorBootstrapMock: vi.fn(),
  startConnectorSyncMock: vi.fn(),
  submitConnectorConfigMock: vi.fn()
}));

vi.mock("@/api/connectors", () => ({
  cancelConnectorBootstrap: mocks.cancelConnectorBootstrapMock,
  fetchConnectorAuthStatus: mocks.fetchConnectorAuthStatusMock,
  fetchConnectorBootstrapStatus: mocks.fetchConnectorBootstrapStatusMock,
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
    mocks.fetchConnectorAuthStatusMock.mockResolvedValue({
      source_id: "amazon_de",
      state: "connected",
      detail: null,
      available_actions: []
    });
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => ({
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
    mocks.cancelConnectorBootstrapMock.mockResolvedValue({
      source_id: "amazon_de",
      canceled: true,
      bootstrap: null
    });

    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 3, by_status: { ready: 1, setup_required: 2 } },
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
        },
        {
          source_id: "kaufland_de",
          plugin_id: "local.kaufland_de",
          display_name: "Kaufland",
          origin: "local_path",
          origin_label: "Local plugin",
          runtime_kind: "subprocess_python",
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
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "setup_required",
            visibility: "default",
            description: "Kaufland setup",
            actions: {
              primary: { kind: "set_up", enabled: true },
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
                manual_commands: {}
              }
            }
          },
          actions: {
            primary: { kind: "set_up", enabled: true },
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
              manual_commands: {}
            }
          },
          advanced: {
            source_exists: true,
            stale: false,
            stale_reason: null,
            auth_state: "not_connected",
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
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["official"]
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
              runtime_kind: "subprocess_python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/kaufland_de/manifest.json",
              origin_directory: "/tmp/plugins/kaufland_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        },
        {
          source_id: "rossmann_de",
          plugin_id: "builtin.rossmann_de",
          display_name: "Rossmann",
          origin: "builtin",
          origin_label: "Built-in",
          runtime_kind: "builtin",
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "complete",
          maturity: "preview",
          maturity_label: "Preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: true,
          supports_live_session_bootstrap: true,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "setup_required",
            visibility: "default",
            description: "Rossmann setup",
            actions: {
              primary: { kind: "set_up", enabled: true },
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
                manual_commands: {}
              }
            }
          },
          actions: {
            primary: { kind: "set_up", enabled: true },
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
              manual_commands: {}
            }
          },
          advanced: {
            source_exists: true,
            stale: false,
            stale_reason: null,
            auth_state: "not_connected",
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
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["official"]
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
              kind: "builtin",
              runtime_kind: "builtin",
              search_path: null,
              origin_path: null,
              origin_directory: null
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

    const installReceiptPluginFromDialogMock = vi.fn().mockResolvedValue({
      action: "installed",
      pack: {
        pluginId: "community.edeka_de",
        sourceId: "edeka_de",
        displayName: "EDEKA",
        version: "0.3.0",
        trustClass: "community_unsigned",
        enabled: false,
        status: "disabled",
        trustStatus: "unsigned",
        trustReason: null,
        compatibilityReason: null,
        installedVia: "manual_file",
        catalogEntryId: null,
        onboarding: {
          title: "Sign in by email link",
          summary: "EDEKA signs you in through a short email confirmation flow before the first import.",
          expectedSpeed: "Usually quick once the email arrives and the confirmation link is opened.",
          caution:
            "Use the same browser window the app opened for you, so the confirmation code lands in the right place.",
          steps: [
            {
              title: "Enter your email address",
              description: "Type your email address into the EDEKA sign-in page in the browser window opened by the app."
            },
            {
              title: "Open the email link",
              description: "EDEKA will send you an email with a login link. Open that link to continue."
            },
            {
              title: "Copy the code back",
              description: "After opening the link, EDEKA shows a code. Enter that code back into the original browser window."
            },
            {
              title: "Wait for the window to close",
              description:
                "After the link is accepted, the browser window should close automatically and the connector can continue."
            }
          ]
        }
      },
      restartedBackend: false,
      backendStatus: null
    });

    const installReceiptPluginFromCatalogEntryMock = vi.fn().mockResolvedValue({
      action: "updated",
      pack: {
        pluginId: "community.amazon_de",
        sourceId: "amazon_de",
        displayName: "Amazon",
        version: "1.4.0",
        trustClass: "community_verified",
        enabled: true,
        status: "enabled",
        trustStatus: "trusted",
        trustReason: null,
        compatibilityReason: null,
        installedVia: "catalog_url",
        catalogEntryId: "connector.amazon",
        onboarding: null
      },
      restartedBackend: true,
      backendStatus: { running: true }
    });

    const enableReceiptPluginMock = vi.fn().mockImplementation(async (pluginId: string) => ({
      pack: {
        pluginId,
        sourceId: pluginId === "community.edeka_de" ? "edeka_de" : "dm_de",
        displayName: pluginId === "community.edeka_de" ? "EDEKA" : "DM",
        version: pluginId === "community.edeka_de" ? "0.3.0" : "0.1.0",
        trustClass: "community_unsigned",
        enabled: true,
        status: "enabled",
        trustStatus: "unsigned",
        trustReason: null,
        compatibilityReason: null,
        installedVia: "manual_file",
        catalogEntryId: null,
        onboarding:
          pluginId === "community.edeka_de"
            ? {
                title: "Sign in by email link",
                summary: "EDEKA signs you in through a short email confirmation flow before the first import.",
                expectedSpeed: "Usually quick once the email arrives and the confirmation link is opened.",
                caution:
                  "Use the same browser window the app opened for you, so the confirmation code lands in the right place.",
                steps: [
                  {
                    title: "Enter your email address",
                    description:
                      "Type your email address into the EDEKA sign-in page in the browser window opened by the app."
                  },
                  {
                    title: "Open the email link",
                    description: "EDEKA will send you an email with a login link. Open that link to continue."
                  },
                  {
                    title: "Copy the code back",
                    description:
                      "After opening the link, EDEKA shows a code. Enter that code back into the original browser window."
                  },
                  {
                    title: "Wait for the window to close",
                    description:
                      "After the link is accepted, the browser window should close automatically and the connector can continue."
                  }
                ]
              }
            : {
                title: "Slow and careful by design",
                summary:
                  "DM intentionally moves slower during scraping so the retailer site sees more normal browsing behavior.",
                expectedSpeed: "Noticeably slower than most other connectors. The first run can take a while.",
                caution: "This slower pace helps reduce the chance that the retailer blocks the session.",
                steps: [
                  {
                    title: "Keep the app open",
                    description: "Let the first import finish without rushing it."
                  }
                ]
              }
      },
      restartedBackend: true,
      backendStatus: { running: true }
    }));

    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        installReceiptPluginFromDialog: installReceiptPluginFromDialogMock,
        installReceiptPluginFromCatalogEntry: installReceiptPluginFromCatalogEntryMock,
        enableReceiptPlugin: enableReceiptPluginMock,
        disableReceiptPlugin: vi.fn(),
        uninstallReceiptPlugin: vi.fn().mockResolvedValue({
          pluginId: "community.dm_de",
          removedPath: "/tmp/plugins/dm",
          restartedBackend: true,
          backendStatus: { running: true }
        }),
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
              },
              {
                entry_id: "connector.dm",
                entry_type: "desktop_pack",
                display_name: "DM",
                summary: "DM desktop connector",
                description: null,
                trust_class: "community_unsigned",
                current_version: "0.1.0",
                support_policy: {
                  display_name: "Community unsigned",
                  ui_label: "Community unsigned",
                  diagnostics_expectation: "Desktop checks still apply.",
                  update_expectations: "Updates depend on manual imports.",
                  maintainer_support: "Community maintained."
                },
                official_bundle_ids: [],
                market_profile_ids: ["dach_starter"],
                release_variant_ids: ["desktop_universal_shell"],
                install_methods: ["manual_import"],
                plugin_id: "community.dm_de",
                source_id: "dm_de"
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
              catalogEntryId: "connector.amazon",
              onboarding: null
            },
            {
              pluginId: "community.dm_de",
              sourceId: "dm_de",
              displayName: "DM",
              version: "0.1.0",
              trustClass: "community_unsigned",
              enabled: false,
              status: "disabled",
              trustStatus: "unsigned",
              trustReason: null,
              compatibilityReason: null,
              installedVia: "manual_file",
              catalogEntryId: "connector.dm",
              onboarding: {
                title: "Slow and careful by design",
                summary:
                  "DM intentionally moves slower during scraping so the retailer site sees more normal browsing behavior.",
                expectedSpeed: "Noticeably slower than most other connectors. The first run can take a while.",
                caution: "This slower pace helps reduce the chance that the retailer blocks the session.",
                steps: [
                  {
                    title: "Keep the app open",
                    description: "Let the first import finish without rushing it."
                  }
                ]
              }
            }
          ]
        })
      }
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the simpler activation-first connector layout", async () => {
    renderPage();

    expect(await screen.findByText("Connectors")).toBeInTheDocument();
    expect(screen.queryByText("Start here")).not.toBeInTheDocument();
    expect(await screen.findByText("Finish adding connectors")).toBeInTheDocument();
    expect(screen.getByText("Your stores")).toBeInTheDocument();
    expect(await screen.findByText("Amazon")).toBeInTheDocument();
    expect(await screen.findByText("Kaufland")).toBeInTheDocument();
    expect(screen.queryByText("Rossmann")).not.toBeInTheDocument();
    expect((await screen.findAllByText("DM")).length).toBeGreaterThan(0);
    expect(await screen.findByText("Trusted connectors you can add")).toBeInTheDocument();
    expect(await screen.findByText("Needs attention")).toBeInTheDocument();
    expect(screen.queryByText("Preview")).not.toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Add connector file" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Sign in again" })).toBeInTheDocument();
    expect((await screen.findAllByText("More options")).length).toBeGreaterThan(0);
  });

  it("saves connector settings before continuing setup", async () => {
    renderPage();

    const amazonCard = (await screen.findByText("Amazon")).closest('[class*="rounded-xl"]');
    expect(amazonCard).not.toBeNull();
    fireEvent.click(within(amazonCard as HTMLElement).getByText("More options"));
    fireEvent.click(within(amazonCard as HTMLElement).getByRole("button", { name: "Settings" }));
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

  it("opens the config dialog before reconnecting a connector with auth settings", async () => {
    renderPage();

    const amazonCard = (await screen.findByText("Amazon")).closest('[class*="rounded-xl"]');
    expect(amazonCard).not.toBeNull();
    fireEvent.click(within(amazonCard as HTMLElement).getByRole("button", { name: "Sign in again" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByLabelText("Domain")).toBeInTheDocument();
    expect(mocks.startConnectorBootstrapMock).not.toHaveBeenCalled();
  });

  it("opens the config dialog before setup when a connector requires saved credentials", async () => {
    mocks.fetchConnectorsMock.mockResolvedValueOnce({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "configurable_shop",
          plugin_id: "local.configurable_shop",
          display_name: "Configurable Shop",
          origin: "local_path",
          origin_label: "Local plugin",
          runtime_kind: "subprocess_python",
          install_origin: "local_path",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "required",
          maturity: "preview",
          maturity_label: "Preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "setup_required",
            visibility: "default",
            description: "Needs credentials first.",
            actions: {
              primary: { kind: "set_up", enabled: true },
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
            primary: { kind: "set_up", enabled: true },
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
            auth_state: "not_connected",
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
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["official"]
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
              runtime_kind: "subprocess_python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/configurable_shop/manifest.json",
              origin_directory: "/tmp/plugins/configurable_shop"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorConfigMock.mockResolvedValueOnce({
      source_id: "configurable_shop",
      plugin_id: "local.configurable_shop",
      display_name: "Configurable Shop",
      install_origin: "local_path",
      config_state: "required",
      fields: [
        {
          key: "email",
          label: "Email",
          input_kind: "text",
          required: true,
          sensitive: false,
          operator_only: false,
          value: ""
        }
      ]
    });

    renderPage();

    const card = (await screen.findByText("Configurable Shop")).closest('[class*="rounded-xl"]');
    expect(card).not.toBeNull();
    fireEvent.click(within(card as HTMLElement).getByRole("button", { name: "Set up" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(mocks.startConnectorBootstrapMock).not.toHaveBeenCalled();
  });

  it("opens setup fields from the primary Set up action before starting bootstrap", async () => {
    mocks.fetchConnectorsMock.mockResolvedValueOnce({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "netto_plus_de",
          plugin_id: "local.netto_plus_de",
          display_name: "Netto Plus",
          origin: "local_path",
          origin_label: "External",
          runtime_kind: "subprocess_python",
          install_origin: "local_path",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "required",
          maturity: "preview",
          maturity_label: "Preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "setup_required",
            visibility: "default",
            description: "Finish the Netto Plus setup before syncing.",
            actions: {
              primary: { kind: "set_up", enabled: true },
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
            primary: { kind: "set_up", enabled: true },
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
            auth_state: "not_connected",
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
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["official"]
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
              runtime_kind: "subprocess_python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/netto_plus_de/manifest.json",
              origin_directory: "/tmp/plugins/netto_plus_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorConfigMock.mockResolvedValueOnce({
      source_id: "netto_plus_de",
      plugin_id: "local.netto_plus_de",
      display_name: "Netto Plus",
      install_origin: "local_path",
      config_state: "required",
      fields: [
        {
          key: "session_bundle_file",
          label: "Netto Plus session bundle",
          input_kind: "text",
          required: true,
          sensitive: false,
          operator_only: false,
          value: null
        }
      ]
    });

    renderPage();

    const nettoCard = (await screen.findByText("Netto Plus")).closest('[class*="rounded-xl"]');
    expect(nettoCard).not.toBeNull();
    fireEvent.click(within(nettoCard as HTMLElement).getByRole("button", { name: "Set up" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("Netto Plus session bundle"), {
      target: { value: "/tmp/netto-session-bundle.json" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => {
      expect(mocks.submitConnectorConfigMock).toHaveBeenCalledWith("netto_plus_de", {
        values: {
          session_bundle_file: "/tmp/netto-session-bundle.json"
        },
        clear_secret_keys: undefined
      });
      expect(mocks.startConnectorBootstrapMock).toHaveBeenCalledWith("netto_plus_de");
    });
  });

  it("hides stale REWE bootstrap browser messaging once the saved Chrome-backed session is already usable", async () => {
    mocks.fetchConnectorsMock.mockResolvedValueOnce({
      generated_at: "2026-04-18T17:05:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { ready: 1 } },
      connectors: [
        {
          source_id: "rewe_de",
          plugin_id: "local.rewe_de",
          display_name: "REWE",
          origin: "local_path",
          origin_label: "External",
          runtime_kind: "subprocess_python",
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
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "connected",
            visibility: "default",
            description: "REWE is ready to import receipts.",
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
                configure: true,
                manual_commands: {}
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
            latest_bootstrap_status: "running",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: "enabled",
              status_detail: null,
              trust_class: "official",
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: ["official"]
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
              runtime_kind: "subprocess_python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/rewe_de/manifest.json",
              origin_directory: "/tmp/plugins/rewe_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: sourceId === "rewe_de" ? "running" : "idle",
      command: "python -m lidltool.cli connectors auth bootstrap --source-id rewe_de",
      pid: sourceId === "rewe_de" ? 1234 : null,
      started_at: sourceId === "rewe_de" ? "2026-04-18T17:04:50Z" : null,
      finished_at: null,
      return_code: null,
      output_tail:
        sourceId === "rewe_de"
          ? ["Waiting for auth step: login_required"]
          : [],
      can_cancel: sourceId === "rewe_de"
    }));

    renderPage();

    expect(await screen.findByText("REWE")).toBeInTheDocument();
    expect(screen.getByText("The saved Chrome-backed REWE sign-in is ready for the next import.")).toBeInTheDocument();
    expect(screen.queryByText("Sign-in in progress")).not.toBeInTheDocument();
    expect(screen.queryByText(/Finish sign-in in the browser window opened by the desktop app/i)).not.toBeInTheDocument();
  });

  it("opens fast onboarding after import and lets the user enable the connector immediately", async () => {
    renderPage();

    const importButton = await screen.findByRole("button", { name: "Add connector file" });
    await waitFor(() => {
      expect(importButton).not.toBeDisabled();
    });
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(window.desktopApi?.installReceiptPluginFromDialog).toHaveBeenCalled();
    });

    expect(await screen.findByText("Before you turn on EDEKA")).toBeInTheDocument();
    expect(screen.getByText("Sign in by email link")).toBeInTheDocument();
    expect(screen.getByText("Enter your email address")).toBeInTheDocument();
    expect(screen.getByText("Open the email link")).toBeInTheDocument();
    expect(screen.getByText("Copy the code back")).toBeInTheDocument();
    expect(screen.getByText("Wait for the window to close")).toBeInTheDocument();

    const enableButton = await screen.findByRole("button", { name: "Enable connector" });
    fireEvent.click(enableButton);

    await waitFor(() => {
      expect(window.desktopApi?.enableReceiptPlugin).toHaveBeenCalledWith("community.edeka_de");
    });
  });

  it("shows slow DM guidance before enabling a slower scraper", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Review first" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Before you turn on DM")).toBeInTheDocument();
    expect(within(dialog).getByText("Slow and careful by design")).toBeInTheDocument();
    expect(
      within(dialog).getByText("This slower pace helps reduce the chance that the retailer blocks the session.")
    ).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: "Enable connector" }));

    await waitFor(() => {
      expect(window.desktopApi?.enableReceiptPlugin).toHaveBeenCalledWith("community.dm_de");
    });
  });

  it("shows a direct enable button for newly imported disabled packs", async () => {
    renderPage();

    const importButton = await screen.findByRole("button", { name: "Add connector file" });
    await waitFor(() => {
      expect(importButton).not.toBeDisabled();
    });
    fireEvent.click(importButton);

    const enableButtons = await screen.findAllByRole("button", { name: "Enable connector" });
    expect(enableButtons.length).toBeGreaterThan(0);
  });
});
