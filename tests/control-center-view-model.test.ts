import assert from "node:assert/strict";
import test from "node:test";

import type { DesktopReleaseMetadata, ReceiptPluginPackInfo } from "../src/shared/contracts.ts";
import { buildControlCenterViewModel } from "../src/renderer/control-center-view-model.ts";

function basePack(overrides: Partial<ReceiptPluginPackInfo> = {}): ReceiptPluginPackInfo {
  return {
    pluginId: "community.fixture_receipt_de",
    sourceId: "fixture_receipt_de",
    displayName: "Fixture Receipt",
    version: "1.0.0",
    pluginFamily: "receipt",
    runtimeKind: "subprocess_python",
    pluginOrigin: "external",
    trustClass: "community_verified",
    enabled: false,
    status: "disabled",
    installPath: "/tmp/fixture/install",
    manifestPath: "/tmp/fixture/install/manifest.json",
    runtimeRoot: "/tmp/fixture/install/payload",
    importedFileName: "fixture.zip",
    importedFromPath: "/tmp/fixture.zip",
    installedAt: "2026-03-10T00:00:00Z",
    updatedAt: "2026-03-10T00:00:00Z",
    archiveSha256: "abc",
    integrityStatus: "verified",
    signatureStatus: "verified",
    trustStatus: "trusted",
    trustReason: null,
    signingKeyId: "fixture-root",
    compatibilityStatus: "compatible",
    compatibilityReason: null,
    installedVia: "catalog_url",
    catalogEntryId: "desktop-pack.fixture",
    catalogDownloadUrl: "https://example.test/fixture.zip",
    onboarding: null,
    diagnostics: [],
    ...overrides
  };
}

function baseReleaseMetadata(): DesktopReleaseMetadata {
  return {
    schema_version: "1",
    product: "desktop",
    requested_release_variant_id: null,
    active_release_variant_id: "desktop_universal_shell",
    active_release_variant: {
      variant_id: "desktop_universal_shell",
      display_name: "Universal",
      product: "desktop",
      edition_kind: "universal_shell",
      default_market_profile_id: "global_shell",
      selectable_market_profile_ids: ["global_shell"],
      preloaded_bundle_ids: [],
      optional_bundle_ids: [],
      release_channel: "stable",
      description: "fixture"
    },
    requested_market_profile_id: "global_shell",
    selected_market_profile_id: "global_shell",
    selected_market_profile: {
      profile_id: "global_shell",
      display_name: "Global",
      market: "global",
      description: "fixture",
      supported_products: ["desktop"],
      default_bundle_ids: ["bundle.default"],
      recommended_bundle_ids: ["bundle.recommended"],
      default_connector_plugin_ids: [],
      recommended_connector_plugin_ids: [],
      excluded_plugin_families: ["offer"],
      out_of_scope_notes: []
    },
    official_bundles: [
      {
        bundle_id: "bundle.default",
        display_name: "Default Bundle",
        market: "DE",
        region: null,
        connector_plugin_ids: [],
        supported_products: ["desktop"],
        default_state: { self_hosted: "disabled", desktop: "available" },
        support_class: "official",
        support_level: "project",
        release_channel: "stable",
        description: null
      },
      {
        bundle_id: "bundle.recommended",
        display_name: "Recommended Bundle",
        market: "DE",
        region: null,
        connector_plugin_ids: [],
        supported_products: ["desktop"],
        default_state: { self_hosted: "disabled", desktop: "available" },
        support_class: "official",
        support_level: "project",
        release_channel: "stable",
        description: null
      }
    ],
    market_profiles: [],
    release_variants: [],
    support_policies: [],
    discovery_catalog: {
      schema_version: "1",
      catalog_id: "fixture",
      source_kind: "bundled_signed",
      verification_status: "trusted",
      verification_reason: null,
      signed_by_key_id: "fixture-root",
      published_at: "2026-03-09T00:00:00Z",
      entries: [
        {
          entry_id: "connector.fixture",
          entry_type: "connector",
          plugin_id: "community.fixture_receipt_de",
          source_id: "fixture_receipt_de",
          display_name: "Fixture Connector",
          summary: "fixture connector",
          description: null,
          trust_class: "community_verified",
          maintainer: "fixture",
          source: "fixture",
          supported_products: ["desktop"],
          supported_markets: ["DE"],
          current_version: "1.2.0",
          compatibility: {
            min_core_version: "0.1.0",
            max_core_version: null,
            supported_host_kinds: ["electron"],
            notes: []
          },
          install_methods: ["manual_import"],
          docs_url: null,
          homepage_url: null,
          download_url: null,
          release_notes_summary: null,
          support_policy: null,
          official_bundle_ids: [],
          market_profile_ids: ["global_shell"],
          release_variant_ids: ["desktop_universal_shell"],
          availability: {
            catalog_listed: true,
            discovered_locally: false,
            local_status: null,
            enabled_locally: false,
            blocked_by_policy: false,
            block_reason: null,
            officially_bundled: false,
            manual_install_supported: true
          }
        },
        {
          entry_id: "desktop-pack.fixture.old",
          entry_type: "desktop_pack",
          plugin_id: "community.fixture_receipt_de",
          source_id: "fixture_receipt_de",
          display_name: "Fixture Receipt",
          summary: "fixture old",
          description: null,
          trust_class: "community_verified",
          maintainer: "fixture",
          source: "fixture",
          supported_products: ["desktop"],
          supported_markets: ["DE"],
          current_version: "1.1.0",
          compatibility: {
            min_core_version: "0.1.0",
            max_core_version: null,
            supported_host_kinds: ["electron"],
            notes: []
          },
          install_methods: ["manual_import", "download_url"],
          docs_url: null,
          homepage_url: null,
          download_url: "https://example.test/fixture-old.zip",
          release_notes_summary: null,
          support_policy: null,
          official_bundle_ids: [],
          market_profile_ids: ["global_shell"],
          release_variant_ids: ["desktop_universal_shell"],
          availability: {
            catalog_listed: true,
            discovered_locally: false,
            local_status: null,
            enabled_locally: false,
            blocked_by_policy: false,
            block_reason: null,
            officially_bundled: false,
            manual_install_supported: true
          },
          pack_format: "zip"
        },
        {
          entry_id: "desktop-pack.fixture",
          entry_type: "desktop_pack",
          plugin_id: "community.fixture_receipt_de",
          source_id: "fixture_receipt_de",
          display_name: "Fixture Receipt",
          summary: "fixture current",
          description: null,
          trust_class: "community_verified",
          maintainer: "fixture",
          source: "fixture",
          supported_products: ["desktop"],
          supported_markets: ["DE"],
          current_version: "1.2.0",
          compatibility: {
            min_core_version: "0.1.0",
            max_core_version: null,
            supported_host_kinds: ["electron"],
            notes: []
          },
          install_methods: ["manual_import", "download_url"],
          docs_url: null,
          homepage_url: null,
          download_url: "https://example.test/fixture.zip",
          release_notes_summary: null,
          support_policy: null,
          official_bundle_ids: [],
          market_profile_ids: ["global_shell"],
          release_variant_ids: ["desktop_universal_shell"],
          availability: {
            catalog_listed: true,
            discovered_locally: false,
            local_status: null,
            enabled_locally: false,
            blocked_by_policy: false,
            block_reason: null,
            officially_bundled: false,
            manual_install_supported: true
          },
          pack_format: "zip"
        }
      ],
      diagnostics: []
    },
    supports_optional_receipt_packs: true
  };
}

test("view model indexes installed packs against the newest trusted desktop pack entry", () => {
  const viewModel = buildControlCenterViewModel(baseReleaseMetadata(), [basePack()], "en");
  const installedRow = viewModel.installedPackRows[0];

  assert.equal(installedRow?.updateTarget?.entry_id, "desktop-pack.fixture");
  assert.equal(installedRow?.packStatus.label, "Installed");
  assert.match(installedRow?.profileSummary ?? "", /current market profile/i);
});

test("view model builds trusted pack rows from indexed installed packs", () => {
  const viewModel = buildControlCenterViewModel(baseReleaseMetadata(), [basePack()], "en");
  const trustedRow = viewModel.trustedPackRows.find((row) => row.entry.entry_id === "desktop-pack.fixture");

  assert.ok(trustedRow);
  assert.equal(trustedRow.installedPack?.pluginId, "community.fixture_receipt_de");
  assert.equal(trustedRow.trustedUrlInstallAllowed, true);
  assert.equal(trustedRow.updateAvailable, true);
});

test("view model merges default sources, catalog connectors, and enabled packs", () => {
  const viewModel = buildControlCenterViewModel(
    baseReleaseMetadata(),
    [
      basePack({
        pluginId: "community.dm_pack",
        sourceId: "dm_de",
        displayName: "dm Connector",
        status: "enabled",
        enabled: true
      })
    ],
    "en"
  );

  assert.equal(viewModel.installedEnabledCount, 1);
  assert.ok(viewModel.sourceOptions.some((option) => option.id === "fixture_receipt_de" && option.label === "Fixture Connector (DE)"));
  assert.ok(viewModel.sourceOptions.some((option) => option.id === "dm_de" && option.label === "dm Connector (DE)"));
  assert.deepEqual(viewModel.defaultBundleLabels, ["Default Bundle"]);
  assert.deepEqual(viewModel.recommendedBundleLabels, ["Recommended Bundle"]);
});
