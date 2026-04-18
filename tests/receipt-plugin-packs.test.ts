import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { createHash, generateKeyPairSync, sign as signBuffer } from "node:crypto";
import { createServer } from "node:http";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import JSZip from "jszip";

import type { ConnectorCatalogEntry } from "../src/shared/contracts.ts";
import {
  ReceiptPluginPackManager,
  type ReceiptPluginPackInfo,
  type ValidatedManifestSnapshot
} from "../src/main/plugins/receipt-plugin-packs.ts";
import {
  buildReceiptPackSignaturePayload,
  type ReceiptPackSignatureDocument,
  type TrustedDistributionPolicy
} from "../src/main/trusted-distribution.ts";

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function baseManifest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    plugin_id: "community.fixture_receipt_de",
    source_id: "fixture_receipt_de",
    display_name: "Fixture Receipt",
    plugin_version: "1.0.0",
    plugin_family: "receipt",
    runtime_kind: "subprocess_python",
    plugin_origin: "external",
    trust_class: "community_unsigned",
    entrypoint: "payload/connector.py:FixtureConnector",
    compatibility: {
      supported_host_kinds: ["electron"],
      min_core_version: "0.1.0",
      max_core_version: null
    },
    onboarding: {
      title: "Fixture onboarding",
      summary: "Fixture Receipt needs a quick sign-in before the first import.",
      expected_speed: "Usually quick for small test data sets.",
      caution: "Keep the window open until the first import finishes.",
      steps: [
        {
          title: "Turn it on",
          description: "Enable the connector after import so the desktop runtime can load it."
        },
        {
          title: "Run the first import",
          description: "Start a sync after setup to confirm the pack works."
        }
      ]
    },
    ...overrides
  };
}

function createTrustPolicy() {
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  const policy: TrustedDistributionPolicy = {
    rootKeys: [
      {
        key_id: "fixture-root",
        label: "Fixture Root",
        algorithm: "ed25519",
        scopes: ["catalog", "pack"],
        allowed_pack_trust_classes: ["official", "community_verified"],
        public_key_pem: publicKey.export({ type: "spki", format: "pem" }).toString()
      }
    ],
    blockedKeyIds: new Map(),
    blockedArchiveSha256: new Map(),
    revokedPluginVersions: new Map(),
    revokedEntryIds: new Map()
  };
  return { policy, privateKey };
}

async function buildPluginPack(
  manifest: Record<string, unknown>,
  overrides: {
    badHashFor?: string;
    signingKey?: ReturnType<typeof createTrustPolicy>["privateKey"];
    tamperSignature?: boolean;
  } = {}
): Promise<Uint8Array> {
  const files = new Map<string, string>([
    [
      "plugin-pack.json",
      JSON.stringify(
        {
          pack_version: "1",
          plugin_id: manifest.plugin_id,
          plugin_version: manifest.plugin_version,
          plugin_family: "receipt",
          manifest_path: "manifest.json",
          runtime_root: "payload",
          ...(overrides.signingKey ? { signature_path: "signature.json" } : {})
        },
        null,
        2
      )
    ],
    ["manifest.json", JSON.stringify(manifest, null, 2)],
    [
      "payload/connector.py",
      [
        "class FixtureConnector:",
        "    def invoke_action(self, request):",
        "        return {'ok': True, 'plugin_family': 'receipt', 'action': request['action'], 'warnings': [], 'output': {}}"
      ].join("\n")
    ]
  ]);

  const integrityFiles = Object.fromEntries(
    [...files.entries()].map(([fileName, contents]) => [
      fileName,
      fileName === overrides.badHashFor ? sha256("corrupted") : sha256(contents)
    ])
  );

  const integrityJson = JSON.stringify(
    {
      algorithm: "sha256",
      files: integrityFiles
    },
    null,
    2
  );
  files.set("integrity.json", integrityJson);

  if (overrides.signingKey) {
    const payload = buildReceiptPackSignaturePayload({
      pluginId: String(manifest.plugin_id),
      pluginVersion: String(manifest.plugin_version),
      pluginFamily: "receipt",
      metadataSha256: sha256(files.get("plugin-pack.json") ?? ""),
      manifestSha256: sha256(files.get("manifest.json") ?? ""),
      integritySha256: sha256(integrityJson),
      integrityFiles
    });
    const signature: ReceiptPackSignatureDocument = {
      schema_version: "1",
      signature_type: "receipt_plugin_pack",
      key_id: "fixture-root",
      algorithm: "ed25519",
      payload_sha256: sha256(payload),
      signature: signBuffer(null, Buffer.from(payload, "utf-8"), overrides.signingKey).toString("base64")
    };
    if (overrides.tamperSignature) {
      signature.signature = signBuffer(null, Buffer.from(`${payload}.tampered`, "utf-8"), overrides.signingKey).toString("base64");
    }
    files.set("signature.json", JSON.stringify(signature, null, 2));
  }

  const zip = new JSZip();
  for (const [fileName, contents] of files.entries()) {
    zip.file(fileName, contents);
  }
  return await zip.generateAsync({ type: "uint8array" });
}

async function validateManifestFixture(manifestPath: string): Promise<ValidatedManifestSnapshot> {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as Record<string, any>;
  const supportedHostKinds = Array.isArray(manifest.compatibility?.supported_host_kinds)
    ? manifest.compatibility.supported_host_kinds.map((item: unknown) => String(item))
    : [];
  return {
    pluginId: String(manifest.plugin_id),
    sourceId: String(manifest.source_id),
    displayName: String(manifest.display_name),
    pluginVersion: String(manifest.plugin_version),
    pluginFamily: "receipt",
    runtimeKind: String(manifest.runtime_kind),
    pluginOrigin: String(manifest.plugin_origin),
    trustClass: String(manifest.trust_class) as ValidatedManifestSnapshot["trustClass"],
    entrypoint: typeof manifest.entrypoint === "string" ? manifest.entrypoint : null,
    supportedHostKinds,
    minCoreVersion:
      typeof manifest.compatibility?.min_core_version === "string" ? manifest.compatibility.min_core_version : null,
    maxCoreVersion:
      typeof manifest.compatibility?.max_core_version === "string" ? manifest.compatibility.max_core_version : null,
    compatibilityStatus: supportedHostKinds.includes("electron") ? "compatible" : "incompatible",
    compatibilityReason: supportedHostKinds.includes("electron") ? null : "host_kind_not_supported",
    onboarding:
      manifest.onboarding && typeof manifest.onboarding === "object"
        ? {
            title: typeof manifest.onboarding.title === "string" ? manifest.onboarding.title : null,
            summary: typeof manifest.onboarding.summary === "string" ? manifest.onboarding.summary : null,
            expectedSpeed:
              typeof manifest.onboarding.expected_speed === "string"
                ? manifest.onboarding.expected_speed
                : null,
            caution: typeof manifest.onboarding.caution === "string" ? manifest.onboarding.caution : null,
            steps: Array.isArray(manifest.onboarding.steps)
              ? manifest.onboarding.steps.flatMap((step: unknown) => {
                  if (!step || typeof step !== "object") {
                    return [];
                  }
                  const candidate = step as Record<string, unknown>;
                  if (typeof candidate.title !== "string" || typeof candidate.description !== "string") {
                    return [];
                  }
                  return [{ title: candidate.title, description: candidate.description }];
                })
              : []
          }
        : null
  };
}

function createManagerRoot(): string {
  return mkdtempSync(join(tmpdir(), "receipt-plugin-packs-"));
}

function createManager(rootDir: string): ReceiptPluginPackManager {
  return new ReceiptPluginPackManager({
    rootDir,
    validateManifest: validateManifestFixture
  });
}

function trustedCatalogEntry(overrides: Partial<ConnectorCatalogEntry> = {}): ConnectorCatalogEntry {
  return {
    entry_id: "desktop-pack.fixture",
    entry_type: "desktop_pack",
    plugin_id: "community.fixture_receipt_de",
    source_id: "fixture_receipt_de",
    display_name: "Fixture Receipt",
    summary: "fixture",
    description: null,
    trust_class: "community_verified",
    maintainer: "fixture",
    source: "fixture catalog",
    supported_products: ["desktop"],
    supported_markets: ["DE"],
    current_version: "1.0.0",
    compatibility: {
      min_core_version: "0.1.0",
      max_core_version: null,
      supported_host_kinds: ["electron"],
      notes: []
    },
    install_methods: ["download_url"],
    docs_url: null,
    homepage_url: null,
    download_url: "http://127.0.0.1/fixture.zip",
    release_notes_summary: null,
    support_policy: null,
    official_bundle_ids: [],
    market_profile_ids: [],
    release_variant_ids: [],
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
    pack_format: "zip",
    ...overrides
  };
}

test("installs, enables, lists, and uninstalls manual unsigned receipt plugin packs", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const packPath = join(rootDir, "fixture-plugin.zip");
  writeFileSync(packPath, await buildPluginPack(baseManifest()));

  try {
    const install = await manager.installFromFile(packPath);
    assert.equal(install.action, "installed");
    assert.equal(install.pack.enabled, false);
    assert.equal(install.pack.status, "disabled");
    assert.equal(install.pack.trustStatus, "unsigned");
    assert.equal(install.pack.onboarding?.title, "Fixture onboarding");
    assert.equal(install.pack.onboarding?.steps.length, 2);

    let list = await manager.listPacks();
    assert.equal(list.packs.length, 1);
    assert.equal(list.activePluginSearchPaths.length, 0);
    assert.equal(list.urlInstallSupported, true);

    const toggled = await manager.setEnabled("community.fixture_receipt_de", true);
    assert.equal(toggled.enabled, true);

    list = await manager.listPacks();
    assert.equal(list.packs.length, 1);
    assert.equal(list.packs[0]?.status, "enabled");
    const runtimePolicy = await manager.getRuntimePolicy();
    assert.equal(runtimePolicy.activePluginSearchPaths.length, 1);
    assert.equal(runtimePolicy.activePluginSearchPaths[0], list.packs[0]?.installPath);
    assert.equal(runtimePolicy.allowedTrustClasses[0], "community_unsigned");

    const uninstall = await manager.uninstall("community.fixture_receipt_de");
    assert.ok(uninstall.removedPath);

    list = await manager.listPacks();
    assert.equal(list.packs.length, 0);
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths.length, 0);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("rejects plugin packs with failing integrity hashes", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const packPath = join(rootDir, "fixture-plugin-invalid.zip");
  writeFileSync(packPath, await buildPluginPack(baseManifest(), { badHashFor: "payload/connector.py" }));

  try {
    await assert.rejects(async () => await manager.installFromFile(packPath), /Integrity validation failed/);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("drops tampered installed packs from runtime policy and reports them invalid", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const packPath = join(rootDir, "fixture-plugin-tamper.zip");
  writeFileSync(packPath, await buildPluginPack(baseManifest()));

  try {
    const install = await manager.installFromFile(packPath);
    await manager.setEnabled(install.pack.pluginId, true);

    const runtimeFile = join(install.pack.runtimeRoot, "connector.py");
    writeFileSync(runtimeFile, "tampered");

    const list = await manager.listPacks();
    const pack = list.packs[0] as ReceiptPluginPackInfo;
    assert.equal(pack.status, "invalid");
    assert.equal(pack.integrityStatus, "failed");
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths.length, 0);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("installs and updates a trusted receipt pack from a catalog URL", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const { policy, privateKey } = createTrustPolicy();

  const versionOne = await buildPluginPack(
    baseManifest({ plugin_version: "1.0.0", trust_class: "community_verified" }),
    { signingKey: privateKey }
  );
  const versionTwo = await buildPluginPack(
    baseManifest({ plugin_version: "1.1.0", trust_class: "community_verified" }),
    { signingKey: privateKey }
  );

  let currentPayload = Buffer.from(versionOne);
  const server = createServer((_, response) => {
    response.statusCode = 200;
    response.setHeader("content-type", "application/zip");
    response.end(currentPayload);
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", () => resolve()));
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;

  try {
    const install = await manager.installFromUrl(
      trustedCatalogEntry({ download_url: `http://127.0.0.1:${port}/fixture.zip`, current_version: "1.0.0" }),
      { trustPolicy: policy }
    );
    assert.equal(install.action, "installed");
    assert.equal(install.pack.trustStatus, "trusted");
    assert.equal(install.pack.signatureStatus, "verified");
    assert.equal(install.pack.installedVia, "catalog_url");

    currentPayload = Buffer.from(versionTwo);
    const update = await manager.installFromUrl(
      trustedCatalogEntry({ download_url: `http://127.0.0.1:${port}/fixture.zip`, current_version: "1.1.0" }),
      { trustPolicy: policy }
    );
    assert.equal(update.action, "updated");
    assert.equal(update.pack.version, "1.1.0");
    assert.equal(update.pack.trustStatus, "trusted");
  } finally {
    server.close();
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("blocks tampered or revoked trusted receipt packs", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const { policy, privateKey } = createTrustPolicy();
  const packPath = join(rootDir, "fixture-plugin-signed.zip");
  writeFileSync(
    packPath,
    await buildPluginPack(baseManifest({ trust_class: "community_verified" }), {
      signingKey: privateKey,
      tamperSignature: true
    })
  );

  try {
    await assert.rejects(
      async () =>
        await manager.installFromFile(packPath, {
          trustPolicy: policy,
          installSource: "manual_file"
        }),
      /signature/i
    );

    const revokedPolicy: TrustedDistributionPolicy = {
      ...policy,
      revokedPluginVersions: new Map([["community.fixture_receipt_de@1.0.0", "Fixture revocation"]])
    };
    const trustedPack = join(rootDir, "fixture-plugin-revoked.zip");
    writeFileSync(
      trustedPack,
      await buildPluginPack(baseManifest({ trust_class: "community_verified" }), {
        signingKey: privateKey
      })
    );
    await assert.rejects(
      async () =>
        await manager.installFromFile(trustedPack, {
          trustPolicy: revokedPolicy,
          installSource: "manual_file"
        }),
      /Fixture revocation/
    );
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("reference receipt plugin template builds a desktop pack that installs cleanly", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const templateDir = fileURLToPath(
    new URL("../../../examples/reference_receipt_plugin_template/", import.meta.url)
  );
  const outputDir = join(rootDir, "built-pack");
  const build = spawnSync(
    "python3",
    [join(templateDir, "build_desktop_pack.py"), "--output-dir", outputDir],
    { encoding: "utf-8" }
  );

  try {
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.action, "installed");
    assert.equal(install.pack.sourceId, "reference_template_receipt_de");
    assert.equal(install.pack.status, "disabled");
    assert.equal(install.pack.integrityStatus, "verified");

    const enabled = await manager.setEnabled(install.pack.pluginId, true);
    assert.equal(enabled.status, "enabled");
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths[0], enabled.installPath);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("kaufland receipt plugin builds a desktop pack that installs cleanly", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const pluginDir = fileURLToPath(new URL("../../../plugins/kaufland_de/", import.meta.url));
  const outputDir = join(rootDir, "kaufland-pack");
  const build = spawnSync(
    "python3",
    [join(pluginDir, "build_desktop_pack.py"), "--output-dir", outputDir],
    { encoding: "utf-8" }
  );

  try {
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.action, "installed");
    assert.equal(install.pack.sourceId, "kaufland_de");
    assert.equal(install.pack.status, "disabled");
    assert.equal(install.pack.integrityStatus, "verified");

    const enabled = await manager.setEnabled(install.pack.pluginId, true);
    assert.equal(enabled.status, "enabled");
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths[0], enabled.installPath);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("netto plus receipt plugin builds a desktop pack that installs cleanly", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const pluginDir = fileURLToPath(new URL("../../../plugins/netto_plus_de/", import.meta.url));
  const outputDir = join(rootDir, "netto-plus-pack");
  const build = spawnSync(
    "python3",
    [join(pluginDir, "build_desktop_pack.py"), "--output-dir", outputDir],
    { encoding: "utf-8" }
  );

  try {
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.action, "installed");
    assert.equal(install.pack.sourceId, "netto_plus_de");
    assert.equal(install.pack.status, "disabled");
    assert.equal(install.pack.integrityStatus, "verified");

    const enabled = await manager.setEnabled(install.pack.pluginId, true);
    assert.equal(enabled.status, "enabled");
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths[0], enabled.installPath);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});

test("rewe receipt plugin builds a desktop pack that installs cleanly", async () => {
  const rootDir = createManagerRoot();
  const manager = createManager(rootDir);
  const pluginDir = fileURLToPath(new URL("../../../plugins/rewe_de/", import.meta.url));
  const outputDir = join(rootDir, "rewe-pack");
  const build = spawnSync(
    "python3",
    [join(pluginDir, "build_desktop_pack.py"), "--output-dir", outputDir],
    { encoding: "utf-8" }
  );

  try {
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.action, "installed");
    assert.equal(install.pack.sourceId, "rewe_de");
    assert.equal(install.pack.pluginId, "local.rewe_de");
    assert.equal(install.pack.status, "disabled");
    assert.equal(install.pack.runtimeKind, "subprocess_python");
    assert.equal(install.pack.integrityStatus, "verified");

    const enabled = await manager.setEnabled(install.pack.pluginId, true);
    assert.equal(enabled.status, "enabled");
    assert.equal((await manager.getRuntimePolicy()).activePluginSearchPaths[0], enabled.installPath);
  } finally {
    rmSync(rootDir, { recursive: true, force: true });
  }
});
