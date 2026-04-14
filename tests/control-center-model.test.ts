import assert from "node:assert/strict";
import test from "node:test";

import type {
  DesktopReleaseMetadata,
  DesktopRuntimeDiagnostics,
  ReceiptPluginPackInfo
} from "../src/shared/contracts.ts";
import {
  compareVersions,
  describeCatalogEntry,
  describeControlCenterMode,
  describeInstalledPack
} from "../src/renderer/control-center-model.ts";

function baseRuntimeDiagnostics(
  overrides: Partial<DesktopRuntimeDiagnostics> = {}
): DesktopRuntimeDiagnostics {
  return {
    environment: "packaged",
    fullAppReady: true,
    frontendDistPath: "/Applications/LidlTool Desktop.app/Contents/Resources/frontend-dist",
    frontendDistStatus: "ready",
    backendSourcePath: "/Applications/LidlTool Desktop.app/Contents/Resources/backend-src",
    backendSourceStatus: "ready",
    backendCommand: "/Applications/LidlTool Desktop.app/Contents/Resources/backend-venv/bin/lidltool",
    backendCommandSource: "bundled",
    backendCommandStatus: "ready",
    ...overrides
  };
}

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
      default_bundle_ids: [],
      recommended_bundle_ids: [],
      default_connector_plugin_ids: [],
      recommended_connector_plugin_ids: [],
      excluded_plugin_families: ["offer"],
      out_of_scope_notes: []
    },
    official_bundles: [],
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
          entry_id: "desktop-pack.fixture",
          entry_type: "desktop_pack",
          plugin_id: "community.fixture_receipt_de",
          source_id: "fixture_receipt_de",
          display_name: "Fixture Receipt",
          summary: "fixture",
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

test("control center mode prefers startup failure messaging", () => {
  const mode = describeControlCenterMode("Backend did not start.", baseRuntimeDiagnostics());
  assert.equal(mode.label, "Reduced mode");
  assert.match(mode.title, /did not open automatically/i);
});

test("control center mode explains missing full app assets", () => {
  const mode = describeControlCenterMode(
    null,
    baseRuntimeDiagnostics({ fullAppReady: false, frontendDistStatus: "missing" })
  );
  assert.equal(mode.label, "Control center only");
  assert.match(mode.detail, /occasional local sync/i);
});

test("installed pack status surfaces blocked incompatible packs", () => {
  const blocked = describeInstalledPack(
    basePack({
      status: "incompatible",
      compatibilityStatus: "incompatible",
      compatibilityReason: "host_kind_not_supported"
    })
  );
  assert.equal(blocked.label, "Blocked");
  assert.match(blocked.detail, /host_kind_not_supported/i);
});

test("catalog entry reports trusted update availability", () => {
  const metadata = baseReleaseMetadata();
  const descriptor = describeCatalogEntry(metadata.discovery_catalog.entries[0]!, basePack());
  assert.equal(descriptor.label, "Update available");
  assert.match(descriptor.detail, /1.2.0/);
});

test("version comparison handles dotted semver values", () => {
  assert.equal(compareVersions("1.2.0", "1.2.0"), 0);
  assert.equal(compareVersions("1.2.0", "1.2.1"), -1);
  assert.equal(compareVersions("1.10.0", "1.2.0"), 1);
});
