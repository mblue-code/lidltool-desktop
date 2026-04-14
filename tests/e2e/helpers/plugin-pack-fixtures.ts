import { createHash, generateKeyPairSync, sign as signBuffer } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { once } from "node:events";
import JSZip from "jszip";

import { buildReceiptPackSignaturePayload, type ReceiptPackSignatureDocument } from "../../../src/main/trusted-distribution.ts";

type FixtureVersion = "1.0.0" | "1.1.0";

type FixtureServer = {
  trustedCatalogPath: string;
  trustRootsPath: string;
  setCatalogVersion: (version: FixtureVersion) => void;
  close: () => Promise<void>;
};

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

function sha256(value: string | Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

function baseManifest(pluginVersion: FixtureVersion): Record<string, unknown> {
  return {
    manifest_version: "1",
    plugin_id: "community.fixture_receipt_de",
    source_id: "fixture_receipt_de",
    display_name: "Fixture Receipt",
    merchant_name: "Fixture Market",
    country_code: "DE",
    plugin_version: pluginVersion,
    connector_api_version: "1",
    plugin_family: "receipt",
    runtime_kind: "subprocess_python",
    plugin_origin: "external",
    maintainer: "fixture",
    license: "MIT",
    auth_kind: "none",
    capabilities: ["healthcheck", "historical_sync"],
    trust_class: "community_verified",
    install_status: "installed",
    entrypoint: "payload/connector.py:FixtureConnector",
    onboarding: {
      title: "Fixture onboarding",
      summary: "Fixture Receipt is ready after a quick sign-in.",
      expected_speed: "Usually quick for the fixture connector.",
      caution: "Leave the app open until the first import finishes.",
      steps: [
        {
          title: "Enable the connector",
          description: "Turn it on after import so the desktop runtime can load it."
        }
      ]
    },
    compatibility: {
      supported_host_kinds: ["electron"],
      min_core_version: "0.1.0",
      max_core_version: null
    }
  };
}

async function buildPluginPack(
  pluginVersion: FixtureVersion,
  signingKey: ReturnType<typeof generateKeyPairSync>["privateKey"]
): Promise<Uint8Array> {
  const manifest = baseManifest(pluginVersion);
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
          signature_path: "signature.json"
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
    [...files.entries()].map(([fileName, contents]) => [fileName, sha256(contents)])
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
    signature: signBuffer(null, Buffer.from(payload, "utf-8"), signingKey).toString("base64")
  };
  files.set("signature.json", JSON.stringify(signature, null, 2));

  const zip = new JSZip();
  for (const [fileName, contents] of files.entries()) {
    zip.file(fileName, contents);
  }
  return await zip.generateAsync({ type: "uint8array" });
}

function notFound(response: ServerResponse): void {
  response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  response.end("not found");
}

export async function startTrustedPackFixtureServer(): Promise<FixtureServer> {
  const fixtureRoot = mkdtempSync(join(tmpdir(), "desktop-pack-e2e-"));
  const trustedCatalogPath = join(fixtureRoot, "trusted-catalog.json");
  const trustRootsPath = join(fixtureRoot, "trust-roots.json");
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
  writeFileSync(trustRootsPath, JSON.stringify(trustRoots, null, 2), "utf-8");

  const packArchives = new Map<FixtureVersion, Uint8Array>([
    ["1.0.0", await buildPluginPack("1.0.0", privateKey)],
    ["1.1.0", await buildPluginPack("1.1.0", privateKey)]
  ]);

  let activeVersion: FixtureVersion = "1.0.0";
  let baseUrl = "";

  function writeCatalogEnvelope(): void {
    const payload = {
      schema_version: "1",
      envelope_type: "connector_catalog",
      catalog_id: "connector_catalog",
      source_kind: "bundled_signed",
      published_at: "2026-04-01T00:00:00Z",
      expires_at: null,
      catalog: {
        schema_version: "1",
        catalog_id: "connector_catalog",
        source_kind: "repo_static",
        entries: [
          {
            entry_id: "desktop-pack.fixture",
            entry_type: "desktop_pack",
            plugin_id: "community.fixture_receipt_de",
            source_id: "fixture_receipt_de",
            display_name: "Fixture Receipt",
            summary: "Signed fixture receipt pack for desktop E2E validation.",
            trust_class: "community_verified",
            maintainer: "fixture",
            source: "fixture",
            supported_products: ["desktop"],
            supported_markets: ["DE"],
            current_version: activeVersion,
            compatibility: {
              min_core_version: "0.1.0",
              max_core_version: null,
              supported_host_kinds: ["electron"],
              notes: []
            },
            install_methods: ["download_url"],
            docs_url: null,
            homepage_url: null,
            download_url: `${baseUrl}/packs/fixture-${activeVersion}.zip`,
            release_notes_summary:
              activeVersion === "1.1.0" ? "Fixture update with a newer signed version for desktop E2E." : null,
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
            pack_format: "zip"
          }
        ]
      },
      revocations: {
        key_ids: [],
        archive_sha256: [],
        plugin_versions: [],
        entry_ids: []
      }
    };
    const signaturePayload = stableStringify(payload);
    writeFileSync(
      trustedCatalogPath,
      JSON.stringify(
        {
          ...payload,
          signatures: [
            {
              key_id: "fixture-root",
              algorithm: "ed25519",
              payload_sha256: sha256(signaturePayload),
              signature: signBuffer(null, Buffer.from(signaturePayload, "utf-8"), privateKey).toString("base64")
            }
          ]
        },
        null,
        2
      ),
      "utf-8"
    );
  }

  function handleRequest(request: IncomingMessage, response: ServerResponse): void {
    const url = new URL(request.url ?? "/", baseUrl || "http://127.0.0.1");
    if (url.pathname === "/packs/fixture-1.0.0.zip" || url.pathname === "/packs/fixture-1.1.0.zip") {
      const version = url.pathname.includes("1.1.0") ? "1.1.0" : "1.0.0";
      const archive = packArchives.get(version);
      if (!archive) {
        notFound(response);
        return;
      }
      response.writeHead(200, { "content-type": "application/zip" });
      response.end(Buffer.from(archive));
      return;
    }
    notFound(response);
  }

  const server = createServer(handleRequest);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  if (!address || typeof address === "string") {
    await new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (error) {
          reject(error);
          return;
        }
        resolve();
      });
    });
    rmSync(fixtureRoot, { recursive: true, force: true });
    throw new Error("Fixture server could not determine its listening address.");
  }
  baseUrl = `http://127.0.0.1:${address.port}`;
  writeCatalogEnvelope();

  return {
    trustedCatalogPath,
    trustRootsPath,
    setCatalogVersion: (version: FixtureVersion) => {
      activeVersion = version;
      writeCatalogEnvelope();
    },
    close: async () => {
      await new Promise<void>((resolve, reject) => {
        server.close((error) => {
          if (error) {
            reject(error);
            return;
          }
          resolve();
        });
      });
      rmSync(fixtureRoot, { recursive: true, force: true });
    }
  };
}
