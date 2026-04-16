import { createHash, randomBytes } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync
} from "node:fs";
import { basename, dirname, join, normalize, resolve } from "node:path";
import JSZip from "jszip";

import type {
  ConnectorCatalogEntry,
  ConnectorTrustClass,
  ConnectorVerificationStatus,
  ReceiptPluginInstallSource,
  ReceiptPluginPackInfo,
  ReceiptPluginPackListResult,
  ReceiptPluginPackStatus
} from "../../shared/contracts.ts";
import {
  verifyReceiptPackSignature,
  type ReceiptPackSignatureDocument,
  type TrustedDistributionPolicy
} from "../trusted-distribution.ts";

type StoredTrustClass = ConnectorTrustClass;

interface PackMetadataFile {
  pack_version: "1";
  plugin_id: string;
  plugin_version: string;
  plugin_family: "receipt";
  manifest_path: string;
  runtime_root: string;
  signature_path?: string;
}

interface IntegrityMetadataFile {
  algorithm: "sha256";
  files: Record<string, string>;
}

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

interface StoredReceiptPluginPackRecord {
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

interface StoredReceiptPluginPackState {
  version: 2;
  packs: Record<string, StoredReceiptPluginPackRecord>;
}

interface InstallPreparedPack {
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

export interface ReceiptPluginCatalogContext {
  trustPolicy?: TrustedDistributionPolicy;
  catalogEntries?: ConnectorCatalogEntry[];
}

interface ReceiptPluginInstallContext extends ReceiptPluginCatalogContext {
  installSource: ReceiptPluginInstallSource;
  catalogEntry?: ConnectorCatalogEntry | null;
}

export interface ReceiptPluginPackManagerOptions {
  rootDir: string;
  validateManifest: (manifestPath: string) => Promise<ValidatedManifestSnapshot>;
  fetchImpl?: typeof fetch;
}

const PACK_METADATA_FILE = "plugin-pack.json";
const INTEGRITY_METADATA_FILE = "integrity.json";
const STATE_FILE = "state.json";
const PACK_STATE_VERSION = 2 as const;

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
  ): Promise<InstallPreparedPack> {
    const archiveBuffer = readFileSync(sourcePath);
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

    const stagingDir = join(
      this.getStorageLayout().staging,
      `pack-${randomBytes(6).toString("hex")}`
    );
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

      const validation = await this.validateManifest(join(stagingDir, manifestPath));
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
      const signatureDocument = signaturePath ? parseJsonFile<ReceiptPackSignatureDocument>(archiveContents, signaturePath) : null;
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
        trustPolicy: context.trustPolicy ?? emptyTrustPolicy()
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
        throw new Error(
          `Unsigned plugin packs cannot claim trust_class='${validation.trustClass}'.`
        );
      }

      if (context.catalogEntry) {
        this.assertTrustedCatalogInstall(context.catalogEntry, validation, signatureVerification.trustStatus);
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

  private assertTrustedCatalogInstall(
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

  private writeState(state: StoredReceiptPluginPackState): void {
    writeFileSync(this.getStorageLayout().stateFile, JSON.stringify(state, null, 2), "utf-8");
  }
}

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

function emptyTrustPolicy(): TrustedDistributionPolicy {
  return {
    rootKeys: [],
    blockedKeyIds: new Map(),
    blockedArchiveSha256: new Map(),
    revokedPluginVersions: new Map(),
    revokedEntryIds: new Map()
  };
}

function verifyInstalledRecord(
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

  const packMetadataPath = join(record.installPath, PACK_METADATA_FILE);
  const integrityMetadataPath = join(record.installPath, INTEGRITY_METADATA_FILE);
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

function parseJsonFile<T>(archiveContents: Map<string, Buffer>, fileName: string): T {
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

function normalizePackPath(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    throw new Error("Plugin pack paths must not be empty.");
  }
  const normalized = normalize(trimmed).replaceAll("\\", "/");
  if (/^[A-Za-z]:/.test(normalized)) {
    throw new Error(`Plugin pack path must not use a drive prefix: ${value}`);
  }
  if (normalized.startsWith("/") || normalized.startsWith("../") || normalized.includes("/../")) {
    throw new Error(`Plugin pack path escapes the install root: ${value}`);
  }
  if (normalized === "." || normalized.includes("/./")) {
    throw new Error(`Plugin pack path is invalid: ${value}`);
  }
  return normalized;
}

function sanitizeSegment(value: string): string {
  return value.replace(/[^a-z0-9._-]/gi, "_");
}

function sha256(value: Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}
