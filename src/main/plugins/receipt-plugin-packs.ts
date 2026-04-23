import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, renameSync, rmSync, statSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

import type {
  ConnectorCatalogEntry,
  ReceiptPluginPackInfo,
  ReceiptPluginPackListResult,
  ReceiptPluginPackStatus
} from "../../shared/contracts.ts";
import {
  normalizePackPath,
  sanitizeSegment,
  verifyInstalledRecord,
} from "./receipt-plugin-pack-integrity.ts";
import {
  prepareReceiptPluginPackInstall,
  type ReceiptPluginCatalogContext,
  type ReceiptPluginInstallContext
} from "./receipt-plugin-pack-install.ts";
import {
  normalizeTrustClass,
  readPackState as readPackStateFile,
  type StoredReceiptPluginPackRecord,
  type StoredReceiptPluginPackState,
  writePackState
} from "./receipt-plugin-pack-state.ts";
import type { ConnectorTrustClass } from "../../shared/contracts.ts";
import type { TrustedDistributionPolicy } from "../trusted-distribution.ts";

export interface ValidatedManifestSnapshot {
  pluginId: string;
  sourceId: string;
  displayName: string;
  pluginVersion: string;
  pluginFamily: "receipt";
  runtimeKind: string;
  pluginOrigin: string;
  trustClass: ConnectorTrustClass;
  entrypoint: string | null;
  supportedHostKinds: string[];
  minCoreVersion: string | null;
  maxCoreVersion: string | null;
  compatibilityStatus: "compatible" | "incompatible" | "invalid";
  compatibilityReason: string | null;
  onboarding: ReceiptPluginPackInfo["onboarding"];
}

interface InstallResult {
  action: "installed" | "updated" | "reinstalled";
  pack: ReceiptPluginPackInfo;
}

export interface ReceiptPluginRuntimePolicy {
  activePluginSearchPaths: string[];
  allowedTrustClasses: string[];
}

export interface ReceiptPluginStorageLayout {
  root: string;
  installs: string;
  staging: string;
  stateFile: string;
}

export interface ReceiptPluginPackManagerOptions {
  rootDir: string;
  validateManifest: (manifestPath: string) => Promise<ValidatedManifestSnapshot>;
  fetchImpl?: typeof fetch;
}

const STATE_FILE = "state.json";
export class ReceiptPluginPackManager {
  private readonly rootDir: string;
  private readonly validateManifest: ReceiptPluginPackManagerOptions["validateManifest"];
  private readonly fetchImpl: typeof fetch;

  constructor(options: ReceiptPluginPackManagerOptions) {
    this.rootDir = resolve(options.rootDir);
    this.validateManifest = options.validateManifest;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  getStorageLayout(): ReceiptPluginStorageLayout {
    return {
      root: this.rootDir,
      installs: join(this.rootDir, "installs"),
      staging: join(this.rootDir, "staging"),
      stateFile: join(this.rootDir, STATE_FILE)
    };
  }

  async listPacks(context: ReceiptPluginCatalogContext = {}): Promise<ReceiptPluginPackListResult> {
    this.ensureStorageLayout();
    const state = this.readState();
    const packs = await Promise.all(
      Object.values(state.packs)
        .sort((left, right) => left.displayName.localeCompare(right.displayName))
        .map(async (record) => await this.buildPackInfo(record, context))
    );
    return {
      storageDir: this.rootDir,
      urlInstallSupported: true,
      activePluginSearchPaths: (await this.getRuntimePolicy(context)).activePluginSearchPaths,
      packs
    };
  }

  async installFromFile(
    filePath: string,
    context: Partial<ReceiptPluginInstallContext> = {}
  ): Promise<InstallResult> {
    this.ensureStorageLayout();
    const sourcePath = resolve(filePath);
    if (!existsSync(sourcePath) || !statSync(sourcePath).isFile()) {
      throw new Error(`Plugin pack file was not found: ${sourcePath}`);
    }

    const installContext = this.normalizeInstallContext(context, basename(sourcePath), sourcePath);
    const state = this.readState();
    const prepared = await this.prepareInstall(sourcePath, installContext);
    const prior = state.packs[prepared.validation.pluginId] ?? null;
    const now = new Date().toISOString();
    const safePluginId = sanitizeSegment(prepared.validation.pluginId);
    const pluginRoot = join(this.getStorageLayout().installs, safePluginId);
    const targetDir = join(pluginRoot, prepared.validation.pluginVersion);
    const backupDir = join(
      this.getStorageLayout().staging,
      `backup-${safePluginId}-${randomBytes(6).toString("hex")}`
    );

    try {
      if (existsSync(pluginRoot)) {
        renameSync(pluginRoot, backupDir);
      }
      mkdirSync(pluginRoot, { recursive: true });
      renameSync(prepared.stagingDir, targetDir);
    } catch (error) {
      rmSync(pluginRoot, { recursive: true, force: true });
      if (existsSync(backupDir)) {
        renameSync(backupDir, pluginRoot);
      }
      rmSync(prepared.stagingDir, { recursive: true, force: true });
      throw error;
    }

    rmSync(backupDir, { recursive: true, force: true });

    const record: StoredReceiptPluginPackRecord = {
      pluginId: prepared.validation.pluginId,
      sourceId: prepared.validation.sourceId,
      displayName: prepared.validation.displayName,
      version: prepared.validation.pluginVersion,
      pluginFamily: "receipt",
      runtimeKind: prepared.validation.runtimeKind,
      pluginOrigin: prepared.validation.pluginOrigin,
      trustClass: normalizeTrustClass(prepared.validation.trustClass),
      enabled: prior?.enabled ?? false,
      installPath: targetDir,
      manifestPath: join(targetDir, normalizePackPath(prepared.metadata.manifest_path)),
      runtimeRoot: join(targetDir, normalizePackPath(prepared.metadata.runtime_root)),
      importedFileName: installContext.importedFileName,
      importedFromPath: installContext.importedFromPath,
      installedAt: prior?.installedAt ?? now,
      updatedAt: now,
      archiveSha256: prepared.archiveSha256,
      signatureStatus: prepared.signatureStatus,
      signingKeyId: prepared.signingKeyId,
      supportedHostKinds: [...prepared.validation.supportedHostKinds],
      minCoreVersion: prepared.validation.minCoreVersion,
      maxCoreVersion: prepared.validation.maxCoreVersion,
      installedVia: installContext.installSource,
      catalogEntryId: installContext.catalogEntry?.entry_id ?? null,
      catalogDownloadUrl: installContext.catalogEntry?.download_url ?? null
    };

    state.packs[record.pluginId] = record;
    this.writeState(state);

    const pack = await this.buildPackInfo(record, installContext);
    const action =
      prior === null
        ? "installed"
        : prior.version === record.version
          ? "reinstalled"
          : "updated";

    return { action, pack };
  }

  async installFromUrl(
    catalogEntry: ConnectorCatalogEntry,
    context: ReceiptPluginCatalogContext
  ): Promise<InstallResult> {
    this.ensureStorageLayout();
    if (catalogEntry.entry_type !== "desktop_pack") {
      throw new Error(`Catalog entry ${catalogEntry.entry_id} is not a desktop pack.`);
    }
    if (!catalogEntry.download_url) {
      throw new Error(`Catalog entry ${catalogEntry.entry_id} does not expose a download_url.`);
    }
    if (catalogEntry.availability.blocked_by_policy) {
      throw new Error(
        catalogEntry.availability.block_reason ??
          `Catalog entry ${catalogEntry.entry_id} is blocked by trusted distribution policy.`
      );
    }
    if (!context.trustPolicy) {
      throw new Error("Trusted URL installs require a verified distribution policy.");
    }

    const response = await this.fetchImpl(catalogEntry.download_url);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status} while downloading ${catalogEntry.download_url}`);
    }

    const downloadPath = join(
      this.getStorageLayout().staging,
      `download-${randomBytes(6).toString("hex")}.zip`
    );
    writeFileSync(downloadPath, Buffer.from(await response.arrayBuffer()));
    try {
      return await this.installFromFile(downloadPath, {
        installSource: "catalog_url",
        catalogEntry,
        trustPolicy: context.trustPolicy,
        catalogEntries: context.catalogEntries
      });
    } finally {
      rmSync(downloadPath, { force: true });
    }
  }

  async setEnabled(
    pluginId: string,
    enabled: boolean,
    context: ReceiptPluginCatalogContext = {}
  ): Promise<ReceiptPluginPackInfo> {
    this.ensureStorageLayout();
    const state = this.readState();
    const record = state.packs[pluginId];
    if (!record) {
      throw new Error(`Installed plugin was not found: ${pluginId}`);
    }

    if (enabled) {
      const packInfo = await this.buildPackInfo(record, context);
      if (packInfo.status !== "disabled" && packInfo.status !== "enabled") {
        throw new Error(
          packInfo.trustReason ??
            packInfo.compatibilityReason ??
            `Plugin ${pluginId} cannot be enabled while status=${packInfo.status}.`
        );
      }
    }

    record.enabled = enabled;
    record.updatedAt = new Date().toISOString();
    this.writeState(state);
    return await this.buildPackInfo(record, context);
  }

  async uninstall(pluginId: string): Promise<{ removedPath: string | null }> {
    this.ensureStorageLayout();
    const state = this.readState();
    const record = state.packs[pluginId];
    if (!record) {
      return { removedPath: null };
    }
    delete state.packs[pluginId];
    this.writeState(state);
    const pluginRoot = dirname(record.installPath);
    rmSync(pluginRoot, { recursive: true, force: true });
    return { removedPath: pluginRoot };
  }

  async getRuntimePolicy(context: ReceiptPluginCatalogContext = {}): Promise<ReceiptPluginRuntimePolicy> {
    this.ensureStorageLayout();
    const state = this.readState();
    const allowedTrustClasses = new Set<string>();
    const activePluginSearchPaths: string[] = [];

    for (const record of Object.values(state.packs)) {
      if (!record.enabled) {
        continue;
      }
      const pack = await this.buildPackInfo(record, context);
      if (pack.status !== "enabled") {
        continue;
      }
      activePluginSearchPaths.push(record.installPath);
      allowedTrustClasses.add(record.trustClass);
    }

    return {
      activePluginSearchPaths: activePluginSearchPaths.sort(),
      allowedTrustClasses: [...allowedTrustClasses].sort()
    };
  }

  private normalizeInstallContext(
    context: Partial<ReceiptPluginInstallContext>,
    importedFileName: string,
    importedFromPath: string
  ): ReceiptPluginInstallContext & { importedFileName: string; importedFromPath: string } {
    return {
      installSource: context.installSource ?? "manual_file",
      catalogEntry: context.catalogEntry ?? null,
      trustPolicy: context.trustPolicy,
      catalogEntries: context.catalogEntries,
      importedFileName,
      importedFromPath
    };
  }

  private async prepareInstall(
    sourcePath: string,
    context: ReceiptPluginInstallContext
  ) {
    return await prepareReceiptPluginPackInstall({
      sourcePath,
      storageStagingDir: this.getStorageLayout().staging,
      validateManifest: this.validateManifest,
      context
    });
  }

  private async buildPackInfo(
    record: StoredReceiptPluginPackRecord,
    context: ReceiptPluginCatalogContext = {}
  ): Promise<ReceiptPluginPackInfo> {
    const verification = verifyInstalledRecord(record, context.trustPolicy);
    const compatibility =
      verification.integrityStatus === "verified"
        ? await this.safeValidateInstalledManifest(record.manifestPath)
        : null;

    let trustStatus = verification.trustStatus;
    let trustReason = verification.trustReason;
    let compatibilityStatus: ReceiptPluginPackInfo["compatibilityStatus"] = "invalid";
    let compatibilityReason: string | null = "Installed pack failed integrity validation.";
    const diagnostics = [...verification.diagnostics];

    if (compatibility) {
      compatibilityStatus = compatibility.compatibilityStatus;
      compatibilityReason = compatibility.compatibilityReason;
      if (compatibility.compatibilityStatus !== "compatible") {
        trustStatus = trustStatus === "revoked" || trustStatus === "signature_invalid" ? trustStatus : "incompatible";
        trustReason = compatibility.compatibilityReason;
        if (compatibility.compatibilityReason) {
          diagnostics.push(compatibility.compatibilityReason);
        }
      }
    }

    let status: ReceiptPluginPackStatus;
    if (trustStatus === "revoked") {
      status = "revoked";
    } else if (verification.integrityStatus !== "verified" || trustStatus === "signature_invalid") {
      status = "invalid";
    } else if (compatibilityStatus === "incompatible" || compatibilityStatus === "invalid") {
      status = compatibilityStatus === "incompatible" ? "incompatible" : "invalid";
    } else {
      status = record.enabled ? "enabled" : "disabled";
    }

    return {
      pluginId: record.pluginId,
      sourceId: record.sourceId,
      displayName: record.displayName,
      version: record.version,
      pluginFamily: "receipt",
      runtimeKind: record.runtimeKind,
      pluginOrigin: record.pluginOrigin,
      trustClass: record.trustClass,
      enabled: record.enabled,
      status,
      installPath: record.installPath,
      manifestPath: record.manifestPath,
      runtimeRoot: record.runtimeRoot,
      importedFileName: record.importedFileName,
      importedFromPath: record.importedFromPath,
      installedAt: record.installedAt,
      updatedAt: record.updatedAt,
      archiveSha256: record.archiveSha256,
      integrityStatus: verification.integrityStatus,
      signatureStatus: record.signatureStatus,
      trustStatus,
      trustReason,
      signingKeyId: record.signingKeyId,
      compatibilityStatus,
      compatibilityReason,
      installedVia: record.installedVia,
      catalogEntryId: record.catalogEntryId,
      catalogDownloadUrl: record.catalogDownloadUrl,
      onboarding: compatibility?.onboarding ?? null,
      diagnostics
    };
  }

  private async safeValidateInstalledManifest(
    manifestPath: string
  ): Promise<ValidatedManifestSnapshot | null> {
    try {
      return await this.validateManifest(manifestPath);
    } catch (error) {
      return {
        pluginId: "unknown",
        sourceId: "unknown",
        displayName: basename(dirname(manifestPath)),
        pluginVersion: "unknown",
        pluginFamily: "receipt",
        runtimeKind: "unknown",
        pluginOrigin: "external",
        trustClass: "community_unsigned",
        entrypoint: null,
        supportedHostKinds: [],
        minCoreVersion: null,
        maxCoreVersion: null,
        compatibilityStatus: "invalid",
        compatibilityReason: String(error),
        onboarding: null
      };
    }
  }

  private ensureStorageLayout(): void {
    const layout = this.getStorageLayout();
    mkdirSync(layout.root, { recursive: true });
    mkdirSync(layout.installs, { recursive: true });
    mkdirSync(layout.staging, { recursive: true });
  }

  private readState(): StoredReceiptPluginPackState {
    const { stateFile } = this.getStorageLayout();
    return readPackStateFile(stateFile);
  }

  private writeState(state: StoredReceiptPluginPackState): void {
    writePackState(this.getStorageLayout().stateFile, state);
  }
}
