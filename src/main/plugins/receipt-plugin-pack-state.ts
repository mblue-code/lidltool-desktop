import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import type {
  ConnectorTrustClass,
  ReceiptPluginInstallSource,
  ReceiptPluginPackInfo
} from "../../shared/contracts.ts";

export type StoredTrustClass = ConnectorTrustClass;

export interface StoredReceiptPluginPackRecord {
  pluginId: string;
  sourceId: string;
  displayName: string;
  version: string;
  pluginFamily: "receipt";
  runtimeKind: string;
  pluginOrigin: string;
  trustClass: StoredTrustClass;
  enabled: boolean;
  installPath: string;
  manifestPath: string;
  runtimeRoot: string;
  importedFileName: string;
  importedFromPath: string;
  installedAt: string;
  updatedAt: string;
  archiveSha256: string;
  signatureStatus: ReceiptPluginPackInfo["signatureStatus"];
  signingKeyId: string | null;
  supportedHostKinds: string[];
  minCoreVersion: string | null;
  maxCoreVersion: string | null;
  installedVia: ReceiptPluginInstallSource;
  catalogEntryId: string | null;
  catalogDownloadUrl: string | null;
}

export interface StoredReceiptPluginPackState {
  version: 2;
  packs: Record<string, StoredReceiptPluginPackRecord>;
}

export const PACK_STATE_VERSION = 2 as const;

export function normalizeTrustClass(value: string): StoredTrustClass {
  if (
    value === "official" ||
    value === "community_verified" ||
    value === "community_unsigned" ||
    value === "local_custom"
  ) {
    return value;
  }
  throw new Error(`Unsupported imported plugin trust class: ${value}`);
}

export function readPackState(stateFile: string): StoredReceiptPluginPackState {
  if (!existsSync(stateFile)) {
    return { version: PACK_STATE_VERSION, packs: {} };
  }
  try {
    const raw = JSON.parse(readFileSync(stateFile, "utf-8")) as Partial<StoredReceiptPluginPackState>;
    const packs = typeof raw.packs === "object" && raw.packs ? raw.packs : {};
    const normalizedPacks = Object.fromEntries(
      Object.entries(packs).flatMap(([pluginId, value]) => {
        if (!value || typeof value !== "object") {
          return [];
        }
        const record = value as Partial<StoredReceiptPluginPackRecord>;
        if (typeof record.installPath !== "string" || typeof record.manifestPath !== "string") {
          return [];
        }
        return [
          [
            pluginId,
            {
              pluginId,
              sourceId: typeof record.sourceId === "string" ? record.sourceId : "unknown",
              displayName: typeof record.displayName === "string" ? record.displayName : pluginId,
              version: typeof record.version === "string" ? record.version : "unknown",
              pluginFamily: "receipt",
              runtimeKind: typeof record.runtimeKind === "string" ? record.runtimeKind : "unknown",
              pluginOrigin: typeof record.pluginOrigin === "string" ? record.pluginOrigin : "external",
              trustClass:
                typeof record.trustClass === "string"
                  ? normalizeTrustClass(record.trustClass)
                  : "community_unsigned",
              enabled: record.enabled === true,
              installPath: record.installPath,
              manifestPath: record.manifestPath,
              runtimeRoot: typeof record.runtimeRoot === "string" ? record.runtimeRoot : dirname(record.manifestPath),
              importedFileName: typeof record.importedFileName === "string" ? record.importedFileName : pluginId,
              importedFromPath: typeof record.importedFromPath === "string" ? record.importedFromPath : record.installPath,
              installedAt: typeof record.installedAt === "string" ? record.installedAt : new Date(0).toISOString(),
              updatedAt: typeof record.updatedAt === "string" ? record.updatedAt : new Date(0).toISOString(),
              archiveSha256: typeof record.archiveSha256 === "string" ? record.archiveSha256 : "",
              signatureStatus:
                record.signatureStatus === "verified" ||
                record.signatureStatus === "signature_invalid" ||
                record.signatureStatus === "revoked" ||
                record.signatureStatus === "unsigned"
                  ? record.signatureStatus
                  : "unsigned",
              signingKeyId: typeof record.signingKeyId === "string" ? record.signingKeyId : null,
              supportedHostKinds: Array.isArray(record.supportedHostKinds)
                ? record.supportedHostKinds.filter((item): item is string => typeof item === "string")
                : [],
              minCoreVersion: typeof record.minCoreVersion === "string" ? record.minCoreVersion : null,
              maxCoreVersion: typeof record.maxCoreVersion === "string" ? record.maxCoreVersion : null,
              installedVia:
                record.installedVia === "catalog_url" || record.installedVia === "manual_file"
                  ? record.installedVia
                  : "manual_file",
              catalogEntryId: typeof record.catalogEntryId === "string" ? record.catalogEntryId : null,
              catalogDownloadUrl: typeof record.catalogDownloadUrl === "string" ? record.catalogDownloadUrl : null
            } satisfies StoredReceiptPluginPackRecord
          ]
        ];
      })
    ) as Record<string, StoredReceiptPluginPackRecord>;
    return {
      version: PACK_STATE_VERSION,
      packs: normalizedPacks
    };
  } catch {
    return { version: PACK_STATE_VERSION, packs: {} };
  }
}

export function writePackState(stateFile: string, state: StoredReceiptPluginPackState): void {
  writeFileSync(stateFile, JSON.stringify(state, null, 2), "utf-8");
}
