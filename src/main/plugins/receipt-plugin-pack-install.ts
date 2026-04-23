import { randomBytes } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import JSZip from "jszip";

import type {
  ConnectorCatalogEntry,
  ConnectorVerificationStatus,
  ReceiptPluginPackInfo,
  ReceiptPluginInstallSource
} from "../../shared/contracts.ts";
import {
  emptyTrustPolicy,
  normalizePackPath,
  parseJsonFile,
  type IntegrityMetadataFile,
  type PackMetadataFile,
  sha256
} from "./receipt-plugin-pack-integrity.ts";
import type { ValidatedManifestSnapshot } from "./receipt-plugin-packs.ts";
import {
  verifyReceiptPackSignature,
  type ReceiptPackSignatureDocument,
  type TrustedDistributionPolicy
} from "../trusted-distribution.ts";

export interface InstallPreparedPack {
  metadata: PackMetadataFile;
  validation: ValidatedManifestSnapshot;
  archiveSha256: string;
  signatureStatus: ReceiptPluginPackInfo["signatureStatus"];
  signingKeyId: string | null;
  trustStatus: ConnectorVerificationStatus;
  trustReason: string | null;
  diagnostics: string[];
  stagingDir: string;
}

export interface ReceiptPluginCatalogContext {
  trustPolicy?: TrustedDistributionPolicy;
  catalogEntries?: ConnectorCatalogEntry[];
}

export interface ReceiptPluginInstallContext extends ReceiptPluginCatalogContext {
  installSource: ReceiptPluginInstallSource;
  catalogEntry?: ConnectorCatalogEntry | null;
}

interface PrepareReceiptPluginPackInstallOptions {
  sourcePath: string;
  storageStagingDir: string;
  validateManifest: (manifestPath: string) => Promise<ValidatedManifestSnapshot>;
  context: ReceiptPluginInstallContext;
}

const PACK_METADATA_FILE = "plugin-pack.json";
const INTEGRITY_METADATA_FILE = "integrity.json";

export async function prepareReceiptPluginPackInstall(
  options: PrepareReceiptPluginPackInstallOptions
): Promise<InstallPreparedPack> {
  const archiveBuffer = readFileSync(options.sourcePath);
  const archiveSha256 = sha256(archiveBuffer);
  const zip = await JSZip.loadAsync(archiveBuffer, { createFolders: false });
  const files = Object.values(zip.files).filter((entry) => !entry.dir);
  const fileNames = files.map((entry) => entry.name);
  const archiveContents = new Map<string, Buffer>();

  if (!fileNames.includes(PACK_METADATA_FILE)) {
    throw new Error(`Plugin pack is missing ${PACK_METADATA_FILE}.`);
  }
  if (!fileNames.includes(INTEGRITY_METADATA_FILE)) {
    throw new Error(`Plugin pack is missing ${INTEGRITY_METADATA_FILE}.`);
  }
  if (!fileNames.includes("manifest.json")) {
    throw new Error("Plugin pack is missing manifest.json.");
  }

  for (const fileName of fileNames) {
    normalizePackPath(fileName);
  }

  for (const entry of files) {
    archiveContents.set(entry.name, await entry.async("nodebuffer"));
  }

  const metadata = parseJsonFile<PackMetadataFile>(archiveContents, PACK_METADATA_FILE);
  if (metadata.pack_version !== "1") {
    throw new Error(`Unsupported plugin pack version: ${metadata.pack_version}`);
  }
  if (metadata.plugin_family !== "receipt") {
    throw new Error("Desktop plugin packs only support receipt connectors in Sprint 12.");
  }

  const integrity = parseJsonFile<IntegrityMetadataFile>(archiveContents, INTEGRITY_METADATA_FILE);
  if (integrity.algorithm !== "sha256") {
    throw new Error(`Unsupported integrity algorithm: ${integrity.algorithm}`);
  }

  const manifestPath = normalizePackPath(metadata.manifest_path);
  if (!fileNames.includes(manifestPath)) {
    throw new Error(`Plugin pack manifest path is missing from archive: ${manifestPath}`);
  }

  const runtimeRoot = normalizePackPath(metadata.runtime_root);
  if (!fileNames.some((entry) => entry.startsWith(`${runtimeRoot}/`))) {
    throw new Error(`Plugin pack runtime payload directory is empty: ${runtimeRoot}`);
  }

  const signaturePath = metadata.signature_path ? normalizePackPath(metadata.signature_path) : null;
  if (signaturePath && !fileNames.includes(signaturePath)) {
    throw new Error(`Plugin pack signature path is missing from archive: ${signaturePath}`);
  }

  const integrityFiles = Object.keys(integrity.files).sort();
  const expectedFiles = fileNames
    .filter((entry) => entry !== INTEGRITY_METADATA_FILE && entry !== signaturePath)
    .sort();
  if (JSON.stringify(integrityFiles) !== JSON.stringify(expectedFiles)) {
    throw new Error("Plugin pack integrity metadata does not match the archive file set.");
  }

  const stagingDir = join(options.storageStagingDir, `pack-${randomBytes(6).toString("hex")}`);
  mkdirSync(stagingDir, { recursive: true });

  try {
    for (const entry of files) {
      const normalizedName = normalizePackPath(entry.name);
      const contents = archiveContents.get(entry.name);
      if (!contents) {
        throw new Error(`Plugin pack file could not be read: ${entry.name}`);
      }
      if (normalizedName !== INTEGRITY_METADATA_FILE && normalizedName !== signaturePath) {
        const expectedHash = integrity.files[normalizedName];
        if (!expectedHash) {
          throw new Error(`Missing integrity hash for ${normalizedName}`);
        }
        if (sha256(contents) !== expectedHash.toLowerCase()) {
          throw new Error(`Integrity validation failed for ${normalizedName}`);
        }
      }
      const outputPath = join(stagingDir, normalizedName);
      mkdirSync(dirname(outputPath), { recursive: true });
      writeFileSync(outputPath, contents);
    }

    const validation = await options.validateManifest(join(stagingDir, manifestPath));
    if (validation.pluginFamily !== "receipt") {
      throw new Error("Desktop plugin packs only support receipt connectors in Sprint 12.");
    }
    if (validation.pluginId !== metadata.plugin_id) {
      throw new Error("Plugin pack metadata plugin_id does not match manifest plugin_id.");
    }
    if (validation.pluginVersion !== metadata.plugin_version) {
      throw new Error("Plugin pack metadata plugin_version does not match manifest plugin_version.");
    }
    if (validation.compatibilityStatus !== "compatible") {
      throw new Error(
        validation.compatibilityReason || "Plugin pack is not compatible with the desktop host."
      );
    }
    if (validation.entrypoint) {
      const entrypointModule = validation.entrypoint.split(":", 1)[0] ?? "";
      if (entrypointModule.trim() && (entrypointModule.includes("/") || entrypointModule.endsWith(".py"))) {
        const entrypointPath = resolve(join(stagingDir, entrypointModule.trim()));
        if (!existsSync(entrypointPath)) {
          throw new Error(`Plugin runtime entrypoint was not found inside the pack: ${entrypointModule}`);
        }
      }
    }

    const metadataSha256 = sha256(archiveContents.get(PACK_METADATA_FILE) ?? Buffer.alloc(0));
    const manifestSha256 = sha256(archiveContents.get(manifestPath) ?? Buffer.alloc(0));
    const integritySha256 = sha256(archiveContents.get(INTEGRITY_METADATA_FILE) ?? Buffer.alloc(0));
    const signatureDocument = signaturePath
      ? parseJsonFile<ReceiptPackSignatureDocument>(archiveContents, signaturePath)
      : null;
    const signatureVerification = verifyReceiptPackSignature({
      archiveSha256,
      pluginId: validation.pluginId,
      pluginVersion: validation.pluginVersion,
      trustClass: validation.trustClass,
      metadataSha256,
      manifestSha256,
      integritySha256,
      integrityFiles: integrity.files,
      signatureDocument,
      trustPolicy: options.context.trustPolicy ?? emptyTrustPolicy()
    });

    if (signatureVerification.signatureStatus === "signature_invalid") {
      throw new Error(signatureVerification.trustReason ?? "Plugin pack signature verification failed.");
    }
    if (signatureVerification.signatureStatus === "revoked") {
      throw new Error(signatureVerification.trustReason ?? "Plugin pack is revoked by trusted distribution policy.");
    }
    if (
      signatureVerification.signatureStatus === "unsigned" &&
      (validation.trustClass === "official" || validation.trustClass === "community_verified")
    ) {
      throw new Error(`Unsigned plugin packs cannot claim trust_class='${validation.trustClass}'.`);
    }

    if (options.context.catalogEntry) {
      assertTrustedCatalogInstall(
        options.context.catalogEntry,
        validation,
        signatureVerification.trustStatus
      );
    }

    return {
      metadata,
      validation,
      archiveSha256,
      signatureStatus: signatureVerification.signatureStatus,
      signingKeyId: signatureVerification.signingKeyId,
      trustStatus: signatureVerification.trustStatus,
      trustReason: signatureVerification.trustReason,
      diagnostics: [...signatureVerification.diagnostics],
      stagingDir
    };
  } catch (error) {
    rmSync(stagingDir, { recursive: true, force: true });
    throw error;
  }
}

export function assertTrustedCatalogInstall(
  catalogEntry: ConnectorCatalogEntry,
  validation: ValidatedManifestSnapshot,
  trustStatus: ConnectorVerificationStatus
): void {
  if (catalogEntry.entry_type !== "desktop_pack") {
    throw new Error(`Catalog entry ${catalogEntry.entry_id} is not a desktop pack.`);
  }
  if (catalogEntry.availability.blocked_by_policy) {
    throw new Error(
      catalogEntry.availability.block_reason ??
        `Catalog entry ${catalogEntry.entry_id} is blocked by trusted distribution policy.`
    );
  }
  if (trustStatus !== "trusted") {
    throw new Error("Trusted URL installs require a verified plugin-pack signature.");
  }
  if (catalogEntry.plugin_id !== validation.pluginId) {
    throw new Error(`Catalog entry ${catalogEntry.entry_id} does not match plugin ${validation.pluginId}.`);
  }
  if (catalogEntry.trust_class !== validation.trustClass) {
    throw new Error(`Catalog entry ${catalogEntry.entry_id} trust_class does not match the plugin manifest.`);
  }
  if (catalogEntry.current_version && catalogEntry.current_version !== validation.pluginVersion) {
    throw new Error(
      `Catalog entry ${catalogEntry.entry_id} expected version ${catalogEntry.current_version}, got ${validation.pluginVersion}.`
    );
  }
}
