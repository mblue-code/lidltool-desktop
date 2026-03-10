import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign as signBuffer } from "node:crypto";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { resolveDesktopReleaseMetadata } from "../src/main/release-metadata.ts";

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort((left, right) => left.localeCompare(right));
  return `{${keys.map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(",")}}`;
}

function createCatalogRoot(): string {
  const root = mkdtempSync(join(tmpdir(), "desktop-release-metadata-"));
  const connectorsDir = join(root, "src", "lidltool", "connectors");
  mkdirSync(connectorsDir, { recursive: true });
  writeFileSync(
    join(connectorsDir, "official_market_catalog.json"),
    JSON.stringify(
      {
        schema_version: "1",
        support_policies: [
          {
            support_class: "official",
            display_name: "Official",
            shipping_policy: "ships",
            ui_label: "Official",
            diagnostics_expectation: "standard",
            update_expectations: "core",
            maintainer_support: "full"
          },
          {
            support_class: "community_verified",
            display_name: "Community verified",
            shipping_policy: "signed",
            ui_label: "Verified",
            diagnostics_expectation: "standard",
            update_expectations: "catalog",
            maintainer_support: "best_effort"
          }
        ],
        bundles: [
          {
            bundle_id: "official.de_receipts_core",
            display_name: "Official Germany Receipts Core",
            market: "DE",
            region: "Germany",
            connector_plugin_ids: ["builtin.amazon_de"],
            supported_products: ["desktop"],
            default_state: { self_hosted: "available", desktop: "available" },
            support_class: "official",
            support_level: "maintained",
            release_channel: "stable",
            description: "fixture"
          }
        ],
        profiles: [
          {
            profile_id: "global_shell",
            display_name: "Global",
            market: "global",
            description: "fixture",
            supported_products: ["desktop"],
            default_bundle_ids: [],
            recommended_bundle_ids: ["official.de_receipts_core"],
            default_connector_plugin_ids: [],
            recommended_connector_plugin_ids: [],
            excluded_plugin_families: ["offer"],
            out_of_scope_notes: []
          },
          {
            profile_id: "dach_starter",
            display_name: "DACH",
            market: "DACH",
            description: "fixture",
            supported_products: ["desktop"],
            default_bundle_ids: ["official.de_receipts_core"],
            recommended_bundle_ids: [],
            default_connector_plugin_ids: [],
            recommended_connector_plugin_ids: [],
            excluded_plugin_families: ["offer"],
            out_of_scope_notes: []
          }
        ],
        release_variants: [
          {
            variant_id: "desktop_universal_shell",
            display_name: "Universal",
            product: "desktop",
            edition_kind: "universal_shell",
            default_market_profile_id: "global_shell",
            selectable_market_profile_ids: ["global_shell", "dach_starter"],
            preloaded_bundle_ids: ["official.de_receipts_core"],
            optional_bundle_ids: [],
            release_channel: "stable",
            description: "fixture"
          },
          {
            variant_id: "desktop_dach_edition",
            display_name: "DACH",
            product: "desktop",
            edition_kind: "regional_edition",
            default_market_profile_id: "dach_starter",
            selectable_market_profile_ids: ["dach_starter"],
            preloaded_bundle_ids: ["official.de_receipts_core"],
            optional_bundle_ids: [],
            release_channel: "stable",
            description: "fixture"
          }
        ]
      },
      null,
      2
    ),
    "utf-8"
  );
  return root;
}

function createSignedCatalogFixture(options: { revokeEntryId?: string; tamperSignature?: boolean } = {}) {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const trustRoots = {
    schema_version: "1",
    roots: [
      {
        key_id: "fixture-root",
        label: "Fixture Root",
        algorithm: "ed25519",
        scopes: ["catalog", "pack"],
        allowed_pack_trust_classes: ["official", "community_verified"],
        public_key_pem: publicKey.export({ type: "spki", format: "pem" }).toString()
      }
    ],
    blocklist: {
      key_ids: [],
      archive_sha256: [],
      plugin_versions: [],
      entry_ids: []
    }
  };

  const envelope = {
    schema_version: "1",
    envelope_type: "connector_catalog",
    catalog_id: "connector_catalog",
    source_kind: "bundled_signed",
    published_at: "2026-03-09T00:00:00Z",
    expires_at: null,
    catalog: {
      schema_version: "1",
      catalog_id: "connector_catalog",
      source_kind: "repo_static",
      entries: [
        {
          entry_id: "connector.builtin.amazon_de",
          entry_type: "connector",
          plugin_id: "builtin.amazon_de",
          source_id: "amazon_de",
          display_name: "Amazon",
          summary: "fixture connector",
          trust_class: "official",
          maintainer: "fixture",
          source: "fixture",
          supported_products: ["desktop"],
          supported_markets: ["DE"],
          current_version: "1.0.0",
          install_methods: ["built_in"]
        },
        {
          entry_id: "desktop-pack.fixture",
          entry_type: "desktop_pack",
          plugin_id: "community.fixture_receipt_de",
          source_id: "fixture_receipt_de",
          display_name: "Fixture Pack",
          summary: "fixture pack",
          trust_class: "community_verified",
          maintainer: "fixture",
          source: "fixture",
          supported_products: ["desktop"],
          supported_markets: ["DE"],
          current_version: "1.1.0",
          install_methods: ["manual_import", "download_url"],
          download_url: "https://example.test/fixture.zip"
        }
      ]
    },
    revocations: {
      key_ids: [],
      archive_sha256: [],
      plugin_versions: [],
      entry_ids: options.revokeEntryId
        ? [{ entry_id: options.revokeEntryId, reason: "Fixture revocation" }]
        : []
    }
  };
  const payload = stableStringify(envelope);
  const signature = signBuffer(null, Buffer.from(payload, "utf-8"), privateKey).toString("base64");
  return {
    trustRoots,
    envelope: {
      ...envelope,
      signatures: [
        {
          key_id: "fixture-root",
          algorithm: "ed25519",
          payload_sha256: options.tamperSignature ? "deadbeef" : createHash("sha256").update(payload).digest("hex"),
          signature
        }
      ]
    }
  };
}

test("falls back to the universal desktop shell and verifies signed catalog metadata", async () => {
  const root = createCatalogRoot();
  const { trustRoots, envelope } = createSignedCatalogFixture();
  try {
    const metadata = await resolveDesktopReleaseMetadata({
      repoRootHint: root,
      trustedCatalogOverride: envelope,
      trustRootsOverride: trustRoots
    });
    assert.equal(metadata.active_release_variant_id, "desktop_universal_shell");
    assert.equal(metadata.selected_market_profile_id, "global_shell");
    assert.equal(metadata.discovery_catalog.verification_status, "trusted");
    assert.equal(metadata.discovery_catalog.signed_by_key_id, "fixture-root");
    assert.equal(metadata.discovery_catalog.entries.length, 2);
    assert.equal(metadata.discovery_catalog.diagnostics.length, 0);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("selects an explicit regional desktop edition when requested", async () => {
  const root = createCatalogRoot();
  const { trustRoots, envelope } = createSignedCatalogFixture();
  try {
    const metadata = await resolveDesktopReleaseMetadata({
      repoRootHint: root,
      requestedReleaseVariantId: "desktop_dach_edition",
      trustedCatalogOverride: envelope,
      trustRootsOverride: trustRoots
    });
    assert.equal(metadata.active_release_variant_id, "desktop_dach_edition");
    assert.equal(metadata.selected_market_profile_id, "dach_starter");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("fails closed when the signed desktop catalog signature is invalid", async () => {
  const root = createCatalogRoot();
  const { trustRoots, envelope } = createSignedCatalogFixture({ tamperSignature: true });
  try {
    const metadata = await resolveDesktopReleaseMetadata({
      repoRootHint: root,
      trustedCatalogOverride: envelope,
      trustRootsOverride: trustRoots
    });
    assert.equal(metadata.discovery_catalog.entries.length, 0);
    assert.equal(metadata.discovery_catalog.verification_status, "signature_invalid");
    assert.match(metadata.discovery_catalog.verification_reason ?? "", /signature/i);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("surfaces revoked catalog entries without trusting them for install", async () => {
  const root = createCatalogRoot();
  const { trustRoots, envelope } = createSignedCatalogFixture({ revokeEntryId: "desktop-pack.fixture" });
  try {
    const metadata = await resolveDesktopReleaseMetadata({
      repoRootHint: root,
      trustedCatalogOverride: envelope,
      trustRootsOverride: trustRoots
    });
    const revokedEntry = metadata.discovery_catalog.entries.find((entry) => entry.entry_id === "desktop-pack.fixture");
    assert.ok(revokedEntry);
    assert.equal(revokedEntry?.availability.blocked_by_policy, true);
    assert.equal(revokedEntry?.availability.block_reason, "Fixture revocation");
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

test("falls back to a local desktop shell profile when market metadata is missing", async () => {
  const root = mkdtempSync(join(tmpdir(), "desktop-release-metadata-empty-"));
  try {
    const metadata = await resolveDesktopReleaseMetadata({
      repoRootHint: root
    });
    assert.equal(metadata.active_release_variant_id, "desktop_local_shell_recovery");
    assert.equal(metadata.selected_market_profile_id, "desktop_local_only");
    assert.equal(metadata.discovery_catalog.entries.length, 0);
    assert.equal(metadata.discovery_catalog.verification_status, "unsigned");
    assert.match(metadata.discovery_catalog.verification_reason ?? "", /metadata is unavailable/i);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
