import type * as React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DateRangeProvider } from "@/app/date-range-context";
import { I18nProvider } from "@/i18n";
import { MerchantsPage } from "../MerchantsPage";

const mocks = vi.hoisted(() => ({
  fetchConnectorsMock: vi.fn(),
  fetchMerchantSummaryMock: vi.fn()
}));

vi.mock("@/api/connectors", () => ({
  fetchConnectors: mocks.fetchConnectorsMock
}));

vi.mock("@/api/merchants", () => ({
  fetchMerchantSummary: mocks.fetchMerchantSummaryMock
}));

function renderPage(ui: React.JSX.Element): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false }
    }
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <DateRangeProvider>{ui}</DateRangeProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MerchantsPage", () => {
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
        },
        clear: () => {
          storage.clear();
        }
      }
    });

    mocks.fetchConnectorsMock.mockResolvedValue({
      generated_at: "2026-04-22T08:00:00Z",
      viewer: { is_admin: true },
      operator_actions: { can_rescan: true, can_reload: true },
      summary: { total_connectors: 5, by_status: {} },
      connectors: [
        {
          source_id: "amazon_de",
          plugin_id: null,
          display_name: "Amazon",
          origin: "builtin",
          origin_label: "builtin",
          runtime_kind: null,
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "disabled",
          config_state: "complete",
          maturity: "preview",
          maturity_label: "preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: null,
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "preview",
            visibility: "default",
            description: "",
            actions: {
              primary: { kind: null, enabled: false, href: null },
              secondary: { kind: null, enabled: false, href: null },
              operator: {
                full_sync: false,
                rescan: false,
                reload: false,
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
            primary: { kind: null, enabled: false, href: null },
            secondary: { kind: null, enabled: false, href: null },
            operator: {
              full_sync: false,
              rescan: false,
              reload: false,
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
            auth_state: "ready",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "idle",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: null,
              status_detail: null,
              trust_class: null,
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: []
            },
            release: {
              maturity: "preview",
              label: "Preview",
              support_posture: "",
              description: "",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "builtin",
              runtime_kind: null,
              search_path: null,
              origin_path: null,
              origin_directory: null
            },
            diagnostics: [],
            manual_commands: {}
          }
        },
        {
          source_id: "amazon_fr",
          plugin_id: null,
          display_name: "Amazon",
          origin: "builtin",
          origin_label: "builtin",
          runtime_kind: null,
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "disabled",
          config_state: "complete",
          maturity: "preview",
          maturity_label: "preview",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: null,
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "preview",
            visibility: "default",
            description: "",
            actions: {
              primary: { kind: null, enabled: false, href: null },
              secondary: { kind: null, enabled: false, href: null },
              operator: {
                full_sync: false,
                rescan: false,
                reload: false,
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
            primary: { kind: null, enabled: false, href: null },
            secondary: { kind: null, enabled: false, href: null },
            operator: {
              full_sync: false,
              rescan: false,
              reload: false,
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
            auth_state: "ready",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "idle",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: null,
              status_detail: null,
              trust_class: null,
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: []
            },
            release: {
              maturity: "preview",
              label: "Preview",
              support_posture: "",
              description: "",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "builtin",
              runtime_kind: null,
              search_path: null,
              origin_path: null,
              origin_directory: null
            },
            diagnostics: [],
            manual_commands: {}
          }
        },
        {
          source_id: "lidl_plus_de",
          plugin_id: null,
          display_name: "Lidl Plus",
          origin: "builtin",
          origin_label: "builtin",
          runtime_kind: null,
          install_origin: "builtin",
          install_state: "installed",
          enable_state: "enabled",
          config_state: "complete",
          maturity: "verified",
          maturity_label: "verified",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: null,
          status_detail: null,
          last_sync_summary: "Connected and ready",
          last_synced_at: "2026-04-21T08:00:00Z",
          ui: {
            status: "connected",
            visibility: "default",
            description: "",
            actions: {
              primary: { kind: null, enabled: false, href: null },
              secondary: { kind: null, enabled: false, href: null },
              operator: {
                full_sync: false,
                rescan: false,
                reload: false,
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
            primary: { kind: null, enabled: false, href: null },
            secondary: { kind: null, enabled: false, href: null },
            operator: {
              full_sync: false,
              rescan: false,
              reload: false,
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
            auth_state: "ready",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "idle",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: null,
              status_detail: null,
              trust_class: null,
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: []
            },
            release: {
              maturity: "verified",
              label: "Verified",
              support_posture: "",
              description: "",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "builtin",
              runtime_kind: null,
              search_path: null,
              origin_path: null,
              origin_directory: null
            },
            diagnostics: [],
            manual_commands: {}
          }
        },
        {
          source_id: "rossmann_de",
          plugin_id: "rossmann",
          display_name: "Rossmann",
          origin: "marketplace",
          origin_label: "marketplace",
          runtime_kind: null,
          install_origin: "marketplace",
          install_state: "installed",
          enable_state: "disabled",
          config_state: "complete",
          maturity: "working",
          maturity_label: "working",
          supports_bootstrap: true,
          supports_sync: true,
          supports_live_session: false,
          supports_live_session_bootstrap: false,
          trust_class: null,
          status_detail: null,
          last_sync_summary: null,
          last_synced_at: null,
          ui: {
            status: "preview",
            visibility: "default",
            description: "",
            actions: {
              primary: { kind: null, enabled: false, href: null },
              secondary: { kind: null, enabled: false, href: null },
              operator: {
                full_sync: false,
                rescan: false,
                reload: false,
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
            primary: { kind: null, enabled: false, href: null },
            secondary: { kind: null, enabled: false, href: null },
            operator: {
              full_sync: false,
              rescan: false,
              reload: false,
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
            auth_state: "ready",
            latest_sync_output: [],
            latest_bootstrap_output: [],
            latest_sync_status: "idle",
            latest_bootstrap_status: "idle",
            block_reason: null,
            policy: {
              blocked: false,
              block_reason: null,
              status: null,
              status_detail: null,
              trust_class: null,
              external_runtime_enabled: true,
              external_receipt_plugins_enabled: true,
              allowed_trust_classes: []
            },
            release: {
              maturity: "working",
              label: "Working",
              support_posture: "",
              description: "",
              default_visibility: "default",
              graduation_requirements: []
            },
            origin: {
              kind: "marketplace",
              runtime_kind: null,
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

    mocks.fetchMerchantSummaryMock.mockResolvedValue({
      period: {
        from_date: "2026-04-19",
        to_date: "2026-04-25"
      },
      count: 0,
      items: []
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("deduplicates builtin merchants and hides inactive external plugins from the merchant grid", async () => {
    renderPage(<MerchantsPage />);

    expect(await screen.findByText("Connected merchant grid")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("Amazon")).toHaveLength(1);
      expect(screen.getByText("Lidl Plus")).toBeInTheDocument();
      expect(screen.queryByText("Rossmann")).not.toBeInTheDocument();
    });
  });
});
