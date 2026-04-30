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
  confirmConnectorBootstrapMock: vi.fn(),
  reloadConnectorsMock: vi.fn(),
  startConnectorBootstrapMock: vi.fn(),
  startConnectorSyncMock: vi.fn(),
  submitConnectorConfigMock: vi.fn()
}));

vi.mock("@/api/connectors", () => ({
  cancelConnectorBootstrap: mocks.cancelConnectorBootstrapMock,
  confirmConnectorBootstrap: mocks.confirmConnectorBootstrapMock,
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

function defaultBootstrapStatus(sourceId: string): any {
  return {
    source_id: sourceId,
    status: "idle" as const,
    command: null,
    pid: null,
    started_at: null,
    finished_at: null,
    return_code: null,
    output_tail: [],
    can_cancel: false
  };
}

function makeDefaultConnectorsPayload(): any {
  return {
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
  };
}

describe("ConnectorsPage", () => {
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
    mocks.confirmConnectorBootstrapMock.mockResolvedValue({
      source_id: "amazon_de",
      confirmed: true,
      auth_status: {
        source_id: "amazon_de",
        state: "connected",
        detail: "Sign-in captured",
        reauth_required: false,
        needs_connection: false,
        available_actions: [],
        implemented_actions: [],
        metadata: {},
        diagnostics: {},
        bootstrap: null
      }
    });

    mocks.fetchConnectorsMock.mockResolvedValue(makeDefaultConnectorsPayload());

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
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) =>
      defaultBootstrapStatus(sourceId)
    );
    mocks.fetchConnectorAuthStatusMock.mockResolvedValue({
      source_id: "kaufland_de",
      state: "connected",
      detail: null,
      available_actions: ["sync"]
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
    const getExternalBrowserPreferenceMock = vi.fn().mockResolvedValue({
      preferredBrowser: "system_default",
      options: [
        { id: "system_default", available: true },
        { id: "arc", available: true },
        { id: "atlas", available: true },
        { id: "google_chrome", available: true }
      ]
    });
    const setExternalBrowserPreferenceMock = vi.fn().mockImplementation(async (preferredBrowser: string) => ({
      preferredBrowser,
      options: [
        { id: "system_default", available: true },
        { id: "arc", available: true },
        { id: "atlas", available: true },
        { id: "google_chrome", available: true }
      ]
    }));
    const openExternalUrlMock = vi.fn().mockResolvedValue(undefined);
    const consumePendingConnectorCallbacksMock = vi.fn().mockResolvedValue([]);
    const onConnectorCallbackMock = vi.fn().mockImplementation(() => vi.fn());

    Object.defineProperty(window, "desktopApi", {
      configurable: true,
      value: {
        installReceiptPluginFromDialog: installReceiptPluginFromDialogMock,
        installReceiptPluginFromCatalogEntry: installReceiptPluginFromCatalogEntryMock,
        enableReceiptPlugin: enableReceiptPluginMock,
        disableReceiptPlugin: vi.fn(),
        getExternalBrowserPreference: getExternalBrowserPreferenceMock,
        setExternalBrowserPreference: setExternalBrowserPreferenceMock,
        openExternalUrl: openExternalUrlMock,
        consumePendingConnectorCallbacks: consumePendingConnectorCallbacksMock,
        onConnectorCallback: onConnectorCallbackMock,
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
    vi.useRealTimers();
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

  it("uses non-invasive auth status checks when the connector page loads", async () => {
    renderPage();

    await waitFor(() => {
      expect(mocks.fetchConnectorAuthStatusMock).toHaveBeenCalledWith("amazon_de", {
        validateSession: false
      });
    });
  });

  it("keeps catalog-only external connectors out of the installed stores list", async () => {
    const payload = makeDefaultConnectorsPayload();
    payload.connectors.push({
      source_id: "rewe_de",
      plugin_id: "local.rewe_de",
      display_name: "REWE",
      origin: "catalog",
      origin_label: "Catalog",
      runtime_kind: "subprocess_python",
      install_origin: null,
      install_state: "catalog_only",
      enable_state: "disabled",
      config_state: "not_required",
      maturity: "preview",
      maturity_label: "Preview",
      supports_bootstrap: true,
      supports_sync: true,
      supports_live_session: false,
      supports_live_session_bootstrap: false,
      trust_class: "community_verified",
      status_detail: "Available as an optional desktop pack.",
      last_sync_summary: null,
      last_synced_at: null,
      ui: {
        status: "setup_required",
        visibility: "default",
        description: "Install and set up REWE before the first sync.",
        actions: {
          primary: { kind: "set_up", enabled: true },
          secondary: { kind: null, enabled: false },
          operator: {
            full_sync: false,
            rescan: true,
            reload: true,
            install: true,
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
        secondary: { kind: null, enabled: false },
        operator: {
          full_sync: false,
          rescan: true,
          reload: true,
          install: true,
          enable: false,
          disable: false,
          uninstall: false,
          configure: false,
          manual_commands: {}
        }
      },
      advanced: {
        source_exists: false,
        stale: false,
        stale_reason: null,
        auth_state: "not_available",
        latest_sync_output: [],
        latest_bootstrap_output: [],
        latest_sync_status: "idle",
        latest_bootstrap_status: "idle",
        block_reason: null,
        policy: {
          blocked: false,
          block_reason: null,
          status: "disabled",
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
          description: "Optional desktop pack.",
          default_visibility: "default",
          graduation_requirements: []
        },
        origin: {
          kind: "catalog",
          runtime_kind: "subprocess_python",
          search_path: null,
          origin_path: null,
          origin_directory: null
        },
        diagnostics: [],
        manual_commands: {}
      }
    });
    mocks.fetchConnectorsMock.mockResolvedValue(payload);

    renderPage();

    expect(await screen.findByText("Connectors")).toBeInTheDocument();
    expect(screen.queryByText("REWE")).not.toBeInTheDocument();
    expect(await screen.findByText("Trusted connectors you can add")).toBeInTheDocument();
  });

  it("promotes import actions right after successful setup and does not stay stuck on Set up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const initialPayload = makeDefaultConnectorsPayload();
    const updatedPayload = makeDefaultConnectorsPayload();
    updatedPayload.connectors[1] = {
      ...updatedPayload.connectors[1],
      ui: {
        ...updatedPayload.connectors[1].ui,
        status: "ready",
        description: "Kaufland ready"
      },
      actions: {
        ...updatedPayload.connectors[1].actions,
        primary: { kind: "sync_now", enabled: true }
      },
      advanced: {
        ...updatedPayload.connectors[1].advanced,
        auth_state: "connected"
      }
    };
    let kauflandBootstrapCalls = 0;
    mocks.fetchConnectorsMock
      .mockImplementationOnce(async () => initialPayload)
      .mockImplementation(async () => updatedPayload);
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => {
      if (sourceId !== "kaufland_de") {
        return defaultBootstrapStatus(sourceId);
      }
      kauflandBootstrapCalls += 1;
      if (kauflandBootstrapCalls === 1) {
        return defaultBootstrapStatus(sourceId);
      }
      if (kauflandBootstrapCalls === 2) {
        return {
          ...defaultBootstrapStatus(sourceId),
          status: "running",
          can_cancel: true
        };
      }
      return {
        ...defaultBootstrapStatus(sourceId),
        status: "succeeded",
        finished_at: "2026-04-01T09:05:00Z"
      };
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Set up" }));
    fireEvent.click(await screen.findByRole("button", { name: "Save and continue" }));

    await waitFor(() => {
      expect(mocks.startConnectorBootstrapMock).toHaveBeenCalledWith("kaufland_de");
    });

    await vi.advanceTimersByTimeAsync(3_100);

    await waitFor(() => {
      expect(kauflandBootstrapCalls).toBeGreaterThanOrEqual(3);
    });

    expect((await screen.findAllByText("Sign-in complete")).length).toBeGreaterThan(0);
    expect(
      screen.getByText("Your sign-in was saved. Next, either import new receipts or run the one-time full history import.")
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Import full history" }).length).toBeGreaterThan(0);
  });

  it("shows a short-lived success banner after sync completion and auto-dismisses it", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const runningPayload = makeDefaultConnectorsPayload();
    runningPayload.summary = { total_connectors: 3, by_status: { ready: 1, syncing: 1, setup_required: 1 } };
    runningPayload.connectors[1] = {
      ...runningPayload.connectors[1],
      ui: {
        ...runningPayload.connectors[1].ui,
        status: "syncing",
        description: "Kaufland sync"
      },
      actions: {
        ...runningPayload.connectors[1].actions,
        primary: { kind: "sync_now", enabled: true }
      },
      advanced: {
        ...runningPayload.connectors[1].advanced,
        auth_state: "connected",
        latest_sync_status: "running",
        latest_sync_output: ["stage=processing seen=2 new=1"]
      }
    };
    const finishedPayload = makeDefaultConnectorsPayload();
    finishedPayload.connectors[1] = {
      ...finishedPayload.connectors[1],
      ui: {
        ...finishedPayload.connectors[1].ui,
        status: "ready",
        description: "Kaufland ready"
      },
      actions: {
        ...finishedPayload.connectors[1].actions,
        primary: { kind: "sync_now", enabled: true }
      },
      last_synced_at: "2026-04-01T09:10:00Z",
      last_sync_summary: "1 new receipt(s), 0 new item(s), 1 checked",
      advanced: {
        ...finishedPayload.connectors[1].advanced,
        auth_state: "connected",
        latest_sync_status: "succeeded",
        latest_sync_output: []
      }
    };
    mocks.fetchConnectorsMock
      .mockImplementationOnce(async () => runningPayload)
      .mockImplementation(async () => finishedPayload);

    renderPage();

    expect(await screen.findByText("Import running")).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(2_100);

    expect(await screen.findByText("Import finished")).toBeInTheDocument();
    expect(screen.queryByText("Import running")).not.toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(60_100);

    await waitFor(() => {
      expect(screen.queryByText("Import finished")).not.toBeInTheDocument();
    });
  });

  it("shows immediate import-start feedback before the connector list catches up", async () => {
    const payload = makeDefaultConnectorsPayload();
    payload.connectors[1] = {
      ...payload.connectors[1],
      ui: {
        ...payload.connectors[1].ui,
        status: "ready",
        description: "Kaufland ready"
      },
      actions: {
        ...payload.connectors[1].actions,
        primary: { kind: "sync_now", enabled: true }
      },
      advanced: {
        ...payload.connectors[1].advanced,
        auth_state: "connected",
        latest_sync_status: "idle",
        latest_sync_output: []
      }
    };
    mocks.fetchConnectorsMock.mockResolvedValue(payload);
    mocks.startConnectorSyncMock.mockResolvedValue({
      source_id: "kaufland_de",
      reused: false,
      sync: {
        source_id: "kaufland_de",
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

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Import receipts" }));

    expect(await screen.findByText("Import starting")).toBeInTheDocument();
    expect(
      screen.getByText("The import was accepted and is being prepared in the background. The first live update can take a few seconds.")
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Starting import…" })).toBeDisabled();
  });

  it("localizes the DM onboarding modal fully in German", async () => {
    window.localStorage.setItem("app.locale", "de");

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Zuerst prüfen" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Bevor Sie DM aktivieren")).toBeInTheDocument();
    expect(within(dialog).getByText("dm beim ersten Lauf bewusst langsam angehen")).toBeInTheDocument();
    expect(within(dialog).getByText("Erwartete Dauer")).toBeInTheDocument();
    expect(within(dialog).getByText("Ersten Import starten")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Jetzt nicht" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Anbindung aktivieren" })).toBeInTheDocument();
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

  it("localizes setup field labels and helper text for German connector dialogs", async () => {
    window.localStorage.setItem("app.locale", "de");
    mocks.fetchConnectorsMock.mockResolvedValueOnce({
      generated_at: "2026-04-01T09:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "rossmann_de",
          plugin_id: "local.rossmann_de",
          display_name: "Rossmann",
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
              kind: "local_path",
              runtime_kind: "subprocess_python",
              search_path: "/tmp/plugins",
              origin_path: "/tmp/plugins/rossmann_de/manifest.json",
              origin_directory: "/tmp/plugins/rossmann_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorConfigMock.mockResolvedValueOnce({
      source_id: "rossmann_de",
      plugin_id: "local.rossmann_de",
      display_name: "Rossmann",
      install_origin: "local_path",
      config_state: "required",
      fields: [
        {
          key: "email",
          label: "Rossmann email",
          description: "Rossmann account email address used once during Set up.",
          input_kind: "text",
          required: false,
          sensitive: false,
          operator_only: false,
          value: ""
        },
        {
          key: "password",
          label: "Rossmann password",
          description: "Rossmann account password used during Set up or reauth only.",
          input_kind: "password",
          required: false,
          sensitive: true,
          operator_only: false,
          value: ""
        }
      ]
    });

    renderPage();

    const rossmannCard = (await screen.findByText("Rossmann")).closest('[class*="rounded-xl"]');
    expect(rossmannCard).not.toBeNull();
    fireEvent.click(within(rossmannCard as HTMLElement).getByRole("button", { name: "Einrichten" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("Rossmann E-Mail")).toBeInTheDocument();
    expect(
      await within(dialog).findByText(
        "Die E-Mail-Adresse des Rossmann-Kontos wird nur einmal während der Einrichtung verwendet."
      )
    ).toBeInTheDocument();
    expect(await within(dialog).findByLabelText("Rossmann Passwort")).toBeInTheDocument();
    expect(
      await within(dialog).findByText(
        "Das Passwort des Rossmann-Kontos wird nur während der Einrichtung oder erneuten Anmeldung verwendet."
      )
    ).toBeInTheDocument();
    expect(await within(dialog).findByRole("button", { name: "Abbrechen" })).toBeInTheDocument();
  });

  it("localizes Amazon, Kaufland, and REWE settings fields for German desktop sessions", async () => {
    window.localStorage.setItem("app.locale", "de");

    const payload = makeDefaultConnectorsPayload();
    payload.connectors[1] = {
      ...payload.connectors[1],
      ui: {
        ...payload.connectors[1].ui,
        status: "connected",
        description: "Kaufland ready",
        actions: {
          ...payload.connectors[1].ui.actions,
          primary: { kind: "sync_now", enabled: true },
          operator: {
            ...payload.connectors[1].ui.actions.operator,
            configure: true
          }
        }
      },
      actions: {
        ...payload.connectors[1].actions,
        primary: { kind: "sync_now", enabled: true },
        operator: {
          ...payload.connectors[1].actions.operator,
          configure: true
        }
      }
    };
    payload.connectors.push({
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
        description: "REWE ready",
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
          origin_path: "/tmp/plugins/rewe_de/manifest.json",
          origin_directory: "/tmp/plugins/rewe_de"
        },
        diagnostics: [],
        manual_commands: {}
      }
    });
    payload.summary = {
      total_connectors: payload.connectors.length,
      by_status: { ready: 3, setup_required: 1 }
    };

    mocks.fetchConnectorsMock.mockResolvedValueOnce(payload);
    mocks.fetchConnectorConfigMock.mockImplementation(async (sourceId: string) => {
      if (sourceId === "amazon_de") {
        return {
          source_id: "amazon_de",
          plugin_id: "community.amazon_de",
          display_name: "Amazon",
          install_origin: "local_path",
          config_state: "complete",
          fields: [
            {
              key: "years",
              label: "Years to scan",
              description: "Optional. Defaults to one year for the first import.",
              placeholder: "1",
              input_kind: "text",
              required: false,
              sensitive: false,
              operator_only: false,
              value: "1"
            },
            {
              key: "headless",
              label: "Headless sync",
              description: "Keep Amazon sync hidden in the browser.",
              input_kind: "boolean",
              required: false,
              sensitive: false,
              operator_only: false,
              value: true
            }
          ]
        };
      }
      if (sourceId === "kaufland_de") {
        return {
          source_id: "kaufland_de",
          plugin_id: "local.kaufland_de",
          display_name: "Kaufland",
          install_origin: "local_path",
          config_state: "complete",
          fields: [
            {
              key: "store_name",
              label: "Store label",
              description: "Optional label for Kaufland receipts.",
              input_kind: "text",
              required: false,
              sensitive: false,
              operator_only: false,
              value: ""
            },
            {
              key: "country_code",
              label: "Receipt country",
              description: "Country used for Kaufland receipt sync.",
              input_kind: "text",
              required: false,
              sensitive: false,
              operator_only: false,
              value: "DE"
            }
          ]
        };
      }
      return {
        source_id: "rewe_de",
        plugin_id: "local.rewe_de",
        display_name: "REWE",
        install_origin: "local_path",
        config_state: "complete",
        fields: [
          {
            key: "store_name",
            label: "Store label",
            description: "Optional label for imported REWE receipts.",
            input_kind: "text",
            required: false,
            sensitive: false,
            operator_only: false,
            value: ""
          },
          {
            key: "headless",
            label: "Headless sync",
            description: "Run REWE sync without a visible browser window.",
            input_kind: "boolean",
            required: false,
            sensitive: false,
            operator_only: false,
            value: true
          },
          {
            key: "chrome_profile_name",
            label: "Chrome profile name",
            description: "Profile name inside the Chrome user-data directory.",
            input_kind: "text",
            required: false,
            sensitive: false,
            operator_only: false,
            value: "Default"
          }
        ]
      };
    });

    renderPage();

    const amazonCard = (await screen.findByText("Amazon")).closest('[class*="rounded-xl"]');
    expect(amazonCard).not.toBeNull();
    fireEvent.click(within(amazonCard as HTMLElement).getByText(/^(More options|Weitere Optionen)$/));
    fireEvent.click(within(amazonCard as HTMLElement).getByRole("button", { name: /^(Settings|Einstellungen)$/ }));

    let dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("Zu prüfende Jahre")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "Wie viele Amazon-Bestelljahre geprüft werden. Mehr Jahre dauern deutlich länger; rechnen Sie grob mit mehreren Minuten pro Jahr."
      )
    ).toBeInTheDocument();
    expect(within(dialog).getByText("Import im Hintergrund ausführen")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /^(Abbrechen|Cancel)$/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    const kauflandCard = (await screen.findByText("Kaufland")).closest('[class*="rounded-xl"]');
    expect(kauflandCard).not.toBeNull();
    fireEvent.click(within(kauflandCard as HTMLElement).getByText(/^(More options|Weitere Optionen)$/));
    fireEvent.click(within(kauflandCard as HTMLElement).getByRole("button", { name: /^(Settings|Einstellungen)$/ }));

    dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("Filialbezeichnung")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Belegland")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /^(Abbrechen|Cancel)$/ }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    const reweCard = (await screen.findByText("REWE")).closest('[class*="rounded-xl"]');
    expect(reweCard).not.toBeNull();
    fireEvent.click(within(reweCard as HTMLElement).getByText(/^(More options|Weitere Optionen)$/));
    fireEvent.click(within(reweCard as HTMLElement).getByRole("button", { name: /^(Settings|Einstellungen)$/ }));

    dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("Filialbezeichnung")).toBeInTheDocument();
    expect(within(dialog).getByText("Headless-Synchronisierung")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Chrome-Profilname")).toBeInTheDocument();
  });

  it("hides stale REWE bootstrap browser messaging once durable REWE auth is connected", async () => {
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

  it("explains the PENNY browser handoff while sign-in is still running", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-26T18:10:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "penny_de",
          plugin_id: "local.penny_de",
          display_name: "PENNY",
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
            status: "setup_required",
            visibility: "default",
            description: "PENNY setup",
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
            auth_state: "bootstrap_running",
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
              origin_path: "/tmp/plugins/penny_de/manifest.json",
              origin_directory: "/tmp/plugins/penny_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: "running",
      command: "python -m lidltool.cli connectors auth bootstrap --source-id penny_de",
      pid: 4321,
      started_at: "2026-04-26T18:09:45Z",
      finished_at: null,
      return_code: null,
      output_tail: ["Waiting for auth step: login_required"],
      can_cancel: true
    }));

    renderPage();

    expect(await screen.findByText("PENNY")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Finish the PENNY login in your browser. If the browser ends on a PENNY redirect or not-found page, return here; that still counts as a successful handoff."
      )
    ).toBeInTheDocument();
  });

  it("lets PENNY open the login in the user's browser and accept a pasted callback URL", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-27T10:20:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "penny_de",
          plugin_id: "local.penny_de",
          display_name: "PENNY",
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
            status: "setup_required",
            visibility: "default",
            description: "PENNY setup",
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
            auth_state: "bootstrap_running",
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
              origin_path: "/tmp/plugins/penny_de/manifest.json",
              origin_directory: "/tmp/plugins/penny_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorBootstrapStatusMock.mockResolvedValue({
      source_id: "penny_de",
      status: "running",
      command: "python -m lidltool.cli connectors auth bootstrap --source-id penny_de",
      pid: 4321,
      started_at: "2026-04-27T10:19:45Z",
      finished_at: null,
      return_code: null,
      output_tail: ["Waiting for auth step: login_required"],
      can_cancel: true
    });
    mocks.fetchConnectorAuthStatusMock.mockResolvedValue({
      source_id: "penny_de",
      state: "bootstrap_running",
      detail: "Shared browser auth is waiting for the Penny OAuth callback.",
      reauth_required: false,
      needs_connection: false,
      available_actions: ["cancel_auth", "confirm_auth"],
      implemented_actions: ["start_auth", "cancel_auth", "confirm_auth"],
      metadata: {
        flow_id: "flow-1",
        auth_start_url: "https://account.penny.de/realms/penny/protocol/openid-connect/auth?flow=1",
        manual_callback_supported: true
      },
      diagnostics: {},
      bootstrap: {
        source_id: "penny_de",
        status: "running",
        started_at: "2026-04-27T10:19:45Z",
        finished_at: null,
        return_code: null,
        can_cancel: true
      }
    });
    mocks.confirmConnectorBootstrapMock.mockResolvedValue({
      source_id: "penny_de",
      confirmed: true,
      auth_status: {
        source_id: "penny_de",
        state: "connected",
        detail: "Stored Penny OAuth state for direct Penny eBon backend access.",
        reauth_required: false,
        needs_connection: false,
        available_actions: ["start_auth"],
        implemented_actions: ["start_auth", "cancel_auth", "confirm_auth"],
        metadata: {},
        diagnostics: {},
        bootstrap: null
      }
    });

    renderPage();

    expect(await screen.findByText("PENNY")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open in your browser" }));
    await waitFor(() =>
      expect(window.desktopApi?.openExternalUrl).toHaveBeenCalledWith(
        "https://account.penny.de/realms/penny/protocol/openid-connect/auth?flow=1"
      )
    );

    fireEvent.change(screen.getByLabelText("Callback URL"), {
      target: {
        value: "https://www.penny.de/app/login?code=test-code&state=flow-1"
      }
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue with pasted URL" }));

    await waitFor(() =>
      expect(mocks.confirmConnectorBootstrapMock).toHaveBeenCalledWith(
        "penny_de",
        "https://www.penny.de/app/login?code=test-code&state=flow-1"
      )
    );
  });

  it("makes Lidl a real-browser handoff with a callback fallback and browser preference", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-27T21:10:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { setup_required: 1 } },
      connectors: [
        {
          source_id: "lidl_plus_de",
          plugin_id: "builtin.lidl_plus_de",
          display_name: "Lidl Plus",
          origin: "built_in",
          origin_label: "Built in",
          runtime_kind: "builtin",
          install_origin: "bundled",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "complete",
          maturity: "preview",
          maturity_label: "Preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: true,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "setup_required",
            visibility: "default",
            description: "Lidl setup",
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
            auth_state: "bootstrap_running",
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
              kind: "bundled",
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
    mocks.fetchConnectorBootstrapStatusMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      status: "running",
      command: "desktop:manual-oauth",
      pid: null,
      started_at: "2026-04-27T21:09:45Z",
      finished_at: null,
      return_code: null,
      output_tail: ["Waiting for Lidl callback in the desktop app."],
      can_cancel: true,
      remote_login_url: "https://accounts.lidl.com/connect/authorize?flow=1"
    });
    mocks.fetchConnectorAuthStatusMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      state: "bootstrap_running",
      detail: "Waiting for Lidl callback in the desktop app.",
      reauth_required: false,
      needs_connection: false,
      available_actions: ["cancel_auth", "confirm_auth"],
      implemented_actions: ["start_auth", "cancel_auth", "confirm_auth"],
      metadata: {
        flow_id: "flow-lidl",
        auth_start_url: "https://accounts.lidl.com/connect/authorize?flow=1",
        manual_callback_supported: true,
        callback_url_prefixes: ["com.lidlplus.app://callback"]
      },
      diagnostics: {},
      bootstrap: {
        source_id: "lidl_plus_de",
        status: "running",
        started_at: "2026-04-27T21:09:45Z",
        finished_at: null,
        return_code: null,
        can_cancel: true
      }
    });
    mocks.confirmConnectorBootstrapMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      confirmed: true,
      auth_status: {
        source_id: "lidl_plus_de",
        state: "connected",
        detail: "Lidl sign-in captured successfully",
        reauth_required: false,
        needs_connection: false,
        available_actions: ["start_auth"],
        implemented_actions: ["start_auth", "cancel_auth", "confirm_auth"],
        metadata: {},
        diagnostics: {},
        bootstrap: null
      }
    });
    vi.mocked(window.desktopApi!.consumePendingConnectorCallbacks!).mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("Lidl Plus")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Lidl always uses a real browser instead of the old embedded sign-in window. By default it opens your system browser, or you can pick another installed browser here."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText("If the browser finishes but the app does not connect, paste the callback URL here.")
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("com.lidlplus.app://callback?code=...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Lidl in your default browser" })).toBeInTheDocument();
  });

  it("shows a Lidl success popup when the desktop app already confirmed the callback", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-28T00:40:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { connected: 1 } },
      connectors: [
        {
          source_id: "lidl_plus_de",
          plugin_id: "builtin.lidl_plus_de",
          display_name: "Lidl Plus",
          origin: "builtin",
          origin_label: "Built in",
          runtime_kind: "builtin",
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "complete",
          maturity: "verified",
          maturity_label: "Verified",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: "official",
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "connected",
            visibility: "default",
            description: "Lidl is connected",
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
              configure: false,
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
            latest_bootstrap_status: "succeeded",
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
              maturity: "verified",
              label: "Verified",
              support_posture: "Verified",
              description: "Built-in connector.",
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
    mocks.fetchConnectorBootstrapStatusMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      status: "succeeded",
      command: "desktop:manual-oauth",
      pid: null,
      started_at: "2026-04-28T00:39:00Z",
      finished_at: "2026-04-28T00:39:20Z",
      return_code: 0,
      output_tail: ["Lidl sign-in finished"],
      can_cancel: false,
      remote_login_url: null
    });
    mocks.fetchConnectorAuthStatusMock.mockResolvedValue({
      source_id: "lidl_plus_de",
      state: "connected",
      detail: "Lidl sign-in captured successfully",
      reauth_required: false,
      needs_connection: false,
      available_actions: ["sync"],
      implemented_actions: ["start_auth", "cancel_auth", "confirm_auth"],
      metadata: {},
      diagnostics: {},
      bootstrap: null
    });
    vi.mocked(window.desktopApi!.consumePendingConnectorCallbacks!).mockResolvedValue([
      {
        url: "com.lidlplus.app://callback?code=test-code",
        sourceId: "lidl_plus_de",
        confirmed: true,
        confirmedAt: "2026-04-28T00:39:20Z",
        detail: "Lidl sign-in captured successfully"
      }
    ]);

    renderPage();

    expect(await screen.findByText("Lidl sign-in saved")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Lidl sign-in was saved. The browser may still show the code page. That is normal."
      )
    ).toBeInTheDocument();
    expect(mocks.confirmConnectorBootstrapMock).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Import receipts" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import full history" })).toBeInTheDocument();
  });

  it("shows a PENNY-specific success message after the callback is captured", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-26T18:15:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { ready: 1 } },
      connectors: [
        {
          source_id: "penny_de",
          plugin_id: "local.penny_de",
          display_name: "PENNY",
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
            description: "PENNY is ready to import receipts.",
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
            latest_bootstrap_status: "succeeded",
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
              origin_path: "/tmp/plugins/penny_de/manifest.json",
              origin_directory: "/tmp/plugins/penny_de"
            },
            diagnostics: [],
            manual_commands: {}
          }
        }
      ]
    });
    mocks.fetchConnectorBootstrapStatusMock.mockImplementation(async (sourceId: string) => ({
      source_id: sourceId,
      status: "succeeded",
      command: "python -m lidltool.cli connectors auth bootstrap --source-id penny_de",
      pid: null,
      started_at: "2026-04-26T18:14:10Z",
      finished_at: "2026-04-26T18:14:40Z",
      return_code: 0,
      output_tail: ["Browser callback captured"],
      can_cancel: false
    }));

    renderPage();

    expect(await screen.findByText("PENNY")).toBeInTheDocument();
    expect(screen.getAllByText("Sign-in complete").length).toBeGreaterThan(0);
    expect(
      await screen.findByText(
        "PENNY sign-in was captured successfully. If the browser ended on a PENNY redirect or not-found page, you can ignore it and continue here with the first import."
      )
    ).toBeInTheDocument();
  });

  it("keeps REWE in setup when bootstrap or sync-looking UI signals exist without durable auth", async () => {
    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-18T17:05:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_reload: true, can_rescan: true },
      summary: { total_connectors: 1, by_status: { connected: 1 } },
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
            auth_state: "not_connected",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "succeeded",
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
      status: sourceId === "rewe_de" ? "succeeded" : "idle",
      command: "python -m lidltool.cli connectors auth bootstrap --source-id rewe_de",
      pid: null,
      started_at: "2026-04-18T17:04:50Z",
      finished_at: "2026-04-18T17:05:00Z",
      return_code: 0,
      output_tail:
        sourceId === "rewe_de"
          ? ["rewe.trace event=confirm_auth.captured_storage_state state_file=/tmp/rewe_storage_state.json"]
          : [],
      can_cancel: false
    }));

    renderPage();

    expect(await screen.findByText("REWE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Set up" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import receipts" })).not.toBeInTheDocument();
    expect(screen.queryByText("The saved Chrome-backed REWE sign-in is ready for the next import.")).not.toBeInTheDocument();
    expect(screen.queryByText("Next step after sign-in")).not.toBeInTheDocument();
    expect(
      screen.getByText("Open REWE in normal Chrome, sign in there, leave the tab open, then press Set up.")
    ).toBeInTheDocument();
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
    expect(within(dialog).getByText("Take dm slowly on the first run")).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        "If dm rejects the first sign-in attempt, start setup once more. A second attempt can still succeed without changing your credentials."
      )
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
