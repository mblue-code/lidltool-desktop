import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import { join, normalize } from "node:path";

import type {
  ConnectorVerificationStatus,
  ReceiptPluginPackInfo
} from "../../shared/contracts.ts";
import type {
  StoredReceiptPluginPackRecord
} from "./receipt-plugin-pack-state.ts";
import type { TrustedDistributionPolicy } from "../trusted-distribution.ts";

export interface PackMetadataFile {
  pack_version: "1";
  plugin_id: string;
  plugin_version: string;
  plugin_family: "receipt";
  manifest_path: string;
  runtime_root: string;
  signature_path?: string;
}

export interface IntegrityMetadataFile {
  algorithm: "sha256";
  files: Record<string, string>;
}

export function emptyTrustPolicy(): TrustedDistributionPolicy {
  return {
    rootKeys: [],
    blockedKeyIds: new Map(),
    blockedArchiveSha256: new Map(),
    revokedPluginVersions: new Map(),
    revokedEntryIds: new Map()
  };
}

export function verifyInstalledRecord(
  record: StoredReceiptPluginPackRecord,
  trustPolicy?: TrustedDistributionPolicy
): {
  integrityStatus: ReceiptPluginPackInfo["integrityStatus"];
  trustStatus: ConnectorVerificationStatus;
  trustReason: string | null;
  diagnostics: string[];
} {
  const diagnostics: string[] = [];
  if (!existsSync(record.installPath)) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: "Installed plugin directory is missing.",
      diagnostics: ["Installed plugin directory is missing."]
    };
  }
  if (!existsSync(record.manifestPath)) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: "Installed plugin manifest is missing.",
      diagnostics: ["Installed plugin manifest is missing."]
    };
  }
  if (!existsSync(record.runtimeRoot) || !statSync(record.runtimeRoot).isDirectory()) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: "Installed plugin runtime payload is missing.",
      diagnostics: ["Installed plugin runtime payload is missing."]
    };
  }

  const packMetadataPath = join(record.installPath, "plugin-pack.json");
  const integrityMetadataPath = join(record.installPath, "integrity.json");
  if (!existsSync(packMetadataPath) || !existsSync(integrityMetadataPath)) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: "Installed plugin metadata files are missing.",
      diagnostics: ["Installed plugin metadata files are missing."]
    };
  }

  let integrity: IntegrityMetadataFile;
  try {
    integrity = JSON.parse(readFileSync(integrityMetadataPath, "utf-8")) as IntegrityMetadataFile;
  } catch (error) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: `Integrity metadata could not be parsed: ${String(error)}`,
      diagnostics: [`Integrity metadata could not be parsed: ${String(error)}`]
    };
  }

  for (const [relativePath, expectedHash] of Object.entries(integrity.files)) {
    const normalizedPath = normalizePackPath(relativePath);
    const fullPath = join(record.installPath, normalizedPath);
    if (!existsSync(fullPath) || !statSync(fullPath).isFile()) {
      diagnostics.push(`Installed plugin file is missing: ${normalizedPath}`);
      continue;
    }
    const actualHash = sha256(readFileSync(fullPath));
    if (actualHash !== expectedHash.toLowerCase()) {
      diagnostics.push(`Installed plugin file hash mismatch: ${normalizedPath}`);
    }
  }

  if (diagnostics.length > 0) {
    return {
      integrityStatus: "failed",
      trustStatus: "signature_invalid",
      trustReason: "Installed plugin integrity validation failed.",
      diagnostics
    };
  }

  const policy = trustPolicy ?? emptyTrustPolicy();
  if (policy.blockedArchiveSha256.has(record.archiveSha256.toLowerCase())) {
    return {
      integrityStatus: "verified",
      trustStatus: "revoked",
      trustReason: policy.blockedArchiveSha256.get(record.archiveSha256.toLowerCase()) ?? "Plugin archive hash is blocked.",
      diagnostics
    };
  }
  if (policy.revokedPluginVersions.has(`${record.pluginId}@${record.version}`)) {
    return {
      integrityStatus: "verified",
      trustStatus: "revoked",
      trustReason:
        policy.revokedPluginVersions.get(`${record.pluginId}@${record.version}`) ??
        `Plugin ${record.pluginId}@${record.version} is revoked.`,
      diagnostics
    };
  }
  if (record.signingKeyId && policy.blockedKeyIds.has(record.signingKeyId)) {
    return {
      integrityStatus: "verified",
      trustStatus: "revoked",
      trustReason: policy.blockedKeyIds.get(record.signingKeyId) ?? `Signing key ${record.signingKeyId} is blocked.`,
      diagnostics
    };
  }

  if (record.signatureStatus === "verified") {
    return {
      integrityStatus: "verified",
      trustStatus: "trusted",
      trustReason: null,
      diagnostics
    };
  }
  if (record.signatureStatus === "unsigned") {
    return {
      integrityStatus: "verified",
      trustStatus: "unsigned",
      trustReason: "Plugin pack was installed without a trusted signature.",
      diagnostics
    };
  }
  return {
    integrityStatus: "verified",
    trustStatus: record.signatureStatus === "revoked" ? "revoked" : "signature_invalid",
    trustReason:
      record.signatureStatus === "revoked"
        ? "Plugin pack was revoked by trusted distribution policy."
        : "Plugin pack signature is invalid.",
    diagnostics
  };
}

export function parseJsonFile<T>(archiveContents: Map<string, Buffer>, fileName: string): T {
  const contents = archiveContents.get(fileName);
  if (!contents) {
    throw new Error(`Plugin pack file is missing: ${fileName}`);
  }
  try {
    return JSON.parse(contents.toString("utf-8")) as T;
  } catch (error) {
    throw new Error(`Plugin pack file is not valid JSON (${fileName}): ${String(error)}`);
  }
}

export function normalizePackPath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error("Plugin pack paths must not be empty.");
  }
  const normalizedValue = normalize(trimmed).replaceAll("\\", "/");
  if (/^[A-Za-z]:/.test(normalizedValue)) {
    throw new Error(`Plugin pack path must not use a drive prefix: ${value}`);
  }
  if (normalizedValue.startsWith("/") || normalizedValue.startsWith("../") || normalizedValue.includes("/../")) {
    throw new Error(`Plugin pack path escapes the install root: ${value}`);
  }
  if (normalizedValue === "." || normalizedValue.includes("/./")) {
    throw new Error(`Plugin pack path is invalid: ${value}`);
  }
  return normalizedValue;
}

export function sanitizeSegment(value: string): string {
  return value.replace(/[^a-z0-9._-]/gi, "_");
}

export function sha256(value: Uint8Array | string): string {
  return createHash("sha256").update(value).digest("hex");
}
