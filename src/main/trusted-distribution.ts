import { createHash, createPublicKey, verify as verifySignature } from "node:crypto";

import type {
  ConnectorCatalogDiagnostic,
  ConnectorMarketProfile,
  ConnectorReleaseVariant,
  ConnectorSupportPolicy,
  ConnectorTrustClass,
  ConnectorVerificationStatus,
  DesktopConnectorCatalog,
  OfficialConnectorBundle,
  ReceiptPluginSignatureStatus
} from "../shared/contracts.ts";
import bundledConnectorCatalogEnvelope from "./trusted-distribution/bundled-connector-catalog.json" with { type: "json" };
import trustRootsDocument from "./trusted-distribution/trust-roots.json" with { type: "json" };
import { loadDesktopConnectorCatalog, type RawCatalogRoot } from "./connector-catalog.ts";

type SigningScope = "catalog" | "pack";
type SignatureAlgorithm = "ed25519";

interface TrustRootDefinition {
  key_id: string;
  label: string;
  algorithm: SignatureAlgorithm;
  scopes: SigningScope[];
  allowed_pack_trust_classes: ConnectorTrustClass[];
  public_key_pem: string;
}

interface RevokedKeyRecord {
  key_id: string;
  reason: string;
}

interface RevokedArchiveRecord {
  sha256: string;
  reason: string;
}

interface RevokedPluginVersionRecord {
  plugin_id: string;
  version: string;
  reason: string;
}

interface RevokedEntryRecord {
  entry_id: string;
  reason: string;
}

interface TrustRootsDocument {
  schema_version: "1";
  roots: TrustRootDefinition[];
  blocklist?: {
    key_ids?: RevokedKeyRecord[];
    archive_sha256?: RevokedArchiveRecord[];
    plugin_versions?: RevokedPluginVersionRecord[];
    entry_ids?: RevokedEntryRecord[];
  };
}

interface CatalogSignatureRecord {
  key_id: string;
  algorithm: SignatureAlgorithm;
  payload_sha256: string;
  signature: string;
}

interface CatalogRevocationBundle {
  key_ids?: RevokedKeyRecord[];
  archive_sha256?: RevokedArchiveRecord[];
  plugin_versions?: RevokedPluginVersionRecord[];
  entry_ids?: RevokedEntryRecord[];
}

interface SignedConnectorCatalogEnvelope {
  schema_version: "1";
  envelope_type: "connector_catalog";
  catalog_id: string;
  source_kind: DesktopConnectorCatalog["source_kind"];
  published_at: string;
  expires_at: string | null;
  catalog: RawCatalogRoot;
  revocations?: CatalogRevocationBundle;
  signatures: CatalogSignatureRecord[];
}

export interface TrustedDistributionPolicy {
  rootKeys: TrustRootDefinition[];
  blockedKeyIds: ReadonlyMap<string, string>;
  blockedArchiveSha256: ReadonlyMap<string, string>;
  revokedPluginVersions: ReadonlyMap<string, string>;
  revokedEntryIds: ReadonlyMap<string, string>;
}

export interface ReceiptPackSignatureDocument {
  schema_version: "1";
  signature_type: "receipt_plugin_pack";
  key_id: string;
  algorithm: SignatureAlgorithm;
  payload_sha256: string;
  signature: string;
}

export interface VerifiedReceiptPackSignature {
  signatureStatus: ReceiptPluginSignatureStatus;
  trustStatus: ConnectorVerificationStatus;
  trustReason: string | null;
  signingKeyId: string | null;
  diagnostics: string[];
}

export interface LoadTrustedDesktopCatalogOptions {
  marketCatalog: {
    support_policies: ConnectorSupportPolicy[];
    bundles: OfficialConnectorBundle[];
    profiles: ConnectorMarketProfile[];
    release_variants: ConnectorReleaseVariant[];
  };
  remoteCatalogUrl?: string | null;
  fetchImpl?: typeof fetch;
  bundledEnvelopeOverride?: unknown;
  trustRootsOverride?: unknown;
}

interface VerifiedCatalogEnvelope {
  catalogEnvelope: SignedConnectorCatalogEnvelope;
  diagnostics: ConnectorCatalogDiagnostic[];
  signingKeyId: string;
  trustPolicy: TrustedDistributionPolicy;
}

const DEFAULT_FETCH_IMPL = fetch;

function buildDiagnostic(code: string, message: string, entryId: string | null = null): ConnectorCatalogDiagnostic {
  return {
    severity: "error",
    code,
    message,
    entry_id: entryId
  };
}

function sha256Hex(value: Buffer | Uint8Array | string): string {
  return createHash("sha256").update(value).digest("hex");
}

function normalizeReasonMap<Key extends string>(
  values: ReadonlyArray<{ reason: string } & Record<Key, string>> | undefined,
  keyName: Key,
  normalizer: (value: string) => string = (value) => value
): Map<string, string> {
  const mapped = new Map<string, string>();
  for (const value of values ?? []) {
    const identifier = typeof value[keyName] === "string" ? value[keyName].trim() : "";
    const reason = typeof value.reason === "string" ? value.reason.trim() : "";
    if (!identifier || !reason) {
      continue;
    }
    mapped.set(normalizer(identifier), reason);
  }
  return mapped;
}

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

function parseTrustRootsDocument(rawDocument: unknown): TrustRootsDocument {
  const parsed = rawDocument as Partial<TrustRootsDocument>;
  if (parsed?.schema_version !== "1" || !Array.isArray(parsed.roots)) {
    throw new Error("Desktop trust roots document is invalid.");
  }
  return parsed as TrustRootsDocument;
}

function buildBasePolicy(rawDocument: unknown): TrustedDistributionPolicy {
  const parsed = parseTrustRootsDocument(rawDocument);
  const revokedPluginVersions = new Map<string, string>();
  for (const entry of parsed.blocklist?.plugin_versions ?? []) {
    const pluginId = entry.plugin_id.trim();
    const version = entry.version.trim();
    const reason = entry.reason.trim();
    if (!pluginId || !version || !reason) {
      continue;
    }
    revokedPluginVersions.set(`${pluginId}@${version}`, reason);
  }
  return {
    rootKeys: parsed.roots,
    blockedKeyIds: normalizeReasonMap(parsed.blocklist?.key_ids, "key_id"),
    blockedArchiveSha256: normalizeReasonMap(parsed.blocklist?.archive_sha256, "sha256", (value) =>
      value.toLowerCase()
    ),
    revokedPluginVersions,
    revokedEntryIds: normalizeReasonMap(parsed.blocklist?.entry_ids, "entry_id")
  };
}

function mergeTrustPolicy(
  basePolicy: TrustedDistributionPolicy,
  revocations: CatalogRevocationBundle | undefined
): TrustedDistributionPolicy {
  const blockedKeyIds = new Map(basePolicy.blockedKeyIds);
  const blockedArchiveSha256 = new Map(basePolicy.blockedArchiveSha256);
  const revokedPluginVersions = new Map(basePolicy.revokedPluginVersions);
  const revokedEntryIds = new Map(basePolicy.revokedEntryIds);

  for (const entry of revocations?.key_ids ?? []) {
    if (entry.key_id.trim() && entry.reason.trim()) {
      blockedKeyIds.set(entry.key_id.trim(), entry.reason.trim());
    }
  }
  for (const entry of revocations?.archive_sha256 ?? []) {
    if (entry.sha256.trim() && entry.reason.trim()) {
      blockedArchiveSha256.set(entry.sha256.trim().toLowerCase(), entry.reason.trim());
    }
  }
  for (const entry of revocations?.plugin_versions ?? []) {
    if (entry.plugin_id.trim() && entry.version.trim() && entry.reason.trim()) {
      revokedPluginVersions.set(`${entry.plugin_id.trim()}@${entry.version.trim()}`, entry.reason.trim());
    }
  }
  for (const entry of revocations?.entry_ids ?? []) {
    if (entry.entry_id.trim() && entry.reason.trim()) {
      revokedEntryIds.set(entry.entry_id.trim(), entry.reason.trim());
    }
  }

  return {
    rootKeys: [...basePolicy.rootKeys],
    blockedKeyIds,
    blockedArchiveSha256,
    revokedPluginVersions,
    revokedEntryIds
  };
}

function parseCatalogEnvelope(rawEnvelope: unknown): SignedConnectorCatalogEnvelope {
  const envelope = rawEnvelope as Partial<SignedConnectorCatalogEnvelope>;
  if (
    envelope?.schema_version !== "1" ||
    envelope?.envelope_type !== "connector_catalog" ||
    typeof envelope.catalog_id !== "string" ||
    typeof envelope.published_at !== "string" ||
    !Array.isArray(envelope.signatures) ||
    typeof envelope.catalog !== "object" ||
    envelope.catalog === null
  ) {
    throw new Error("Trusted desktop connector catalog envelope is invalid.");
  }
  return envelope as SignedConnectorCatalogEnvelope;
}

function buildCatalogSigningPayload(envelope: SignedConnectorCatalogEnvelope): string {
  return stableStringify({
    schema_version: envelope.schema_version,
    envelope_type: envelope.envelope_type,
    catalog_id: envelope.catalog_id,
    source_kind: envelope.source_kind,
    published_at: envelope.published_at,
    expires_at: envelope.expires_at,
    catalog: envelope.catalog,
    revocations: envelope.revocations ?? {}
  });
}

function verifyDetachedSignature(
  payload: string,
  keyPem: string,
  signatureBase64: string
): boolean {
  return verifySignature(null, Buffer.from(payload, "utf-8"), createPublicKey(keyPem), Buffer.from(signatureBase64, "base64"));
}

function verifyCatalogEnvelope(
  rawEnvelope: unknown,
  basePolicy: TrustedDistributionPolicy,
  expectedSourceKind: DesktopConnectorCatalog["source_kind"]
): VerifiedCatalogEnvelope {
  const diagnostics: ConnectorCatalogDiagnostic[] = [];
  const envelope = parseCatalogEnvelope(rawEnvelope);
  if (envelope.source_kind !== expectedSourceKind) {
    throw new Error(`Trusted connector catalog source_kind must be '${expectedSourceKind}'.`);
  }
  if (envelope.expires_at) {
    const expiry = Date.parse(envelope.expires_at);
    if (!Number.isFinite(expiry) || expiry <= Date.now()) {
      throw new Error(`Trusted connector catalog expired at ${envelope.expires_at}.`);
    }
  }

  const payload = buildCatalogSigningPayload(envelope);
  const payloadSha256 = sha256Hex(payload);

  for (const signature of envelope.signatures) {
    const root = basePolicy.rootKeys.find((candidate) => candidate.key_id === signature.key_id);
    if (!root || !root.scopes.includes("catalog") || root.algorithm !== signature.algorithm) {
      continue;
    }
    if (basePolicy.blockedKeyIds.has(signature.key_id)) {
      throw new Error(basePolicy.blockedKeyIds.get(signature.key_id) ?? `Catalog signing key ${signature.key_id} is blocked.`);
    }
    if (signature.payload_sha256.toLowerCase() !== payloadSha256) {
      diagnostics.push(
        buildDiagnostic(
          "catalog_signature_invalid",
          `Trusted connector catalog signature hash mismatch for key '${signature.key_id}'.`
        )
      );
      continue;
    }
    if (!verifyDetachedSignature(payload, root.public_key_pem, signature.signature)) {
      diagnostics.push(
        buildDiagnostic(
          "catalog_signature_invalid",
          `Trusted connector catalog signature verification failed for key '${signature.key_id}'.`
        )
      );
      continue;
    }

    const trustPolicy = mergeTrustPolicy(basePolicy, envelope.revocations);
    if (trustPolicy.blockedKeyIds.has(signature.key_id)) {
      throw new Error(
        trustPolicy.blockedKeyIds.get(signature.key_id) ??
          `Catalog signing key ${signature.key_id} is blocked by catalog policy.`
      );
    }
    return {
      catalogEnvelope: envelope,
      diagnostics,
      signingKeyId: signature.key_id,
      trustPolicy
    };
  }

  throw new Error(
    diagnostics[0]?.message ?? "Trusted connector catalog does not contain a valid trusted signature."
  );
}

async function fetchRemoteCatalogEnvelope(
  remoteCatalogUrl: string,
  fetchImpl: typeof fetch
): Promise<unknown> {
  const response = await fetchImpl(remoteCatalogUrl);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} while fetching trusted connector catalog.`);
  }
  return await response.json();
}

function emptyCatalog(
  diagnostics: ConnectorCatalogDiagnostic[],
  verificationStatus: ConnectorVerificationStatus,
  verificationReason: string | null
): DesktopConnectorCatalog {
  return {
    schema_version: "1",
    catalog_id: "connector_catalog",
    source_kind: "repo_static",
    verification_status: verificationStatus,
    verification_reason: verificationReason,
    signed_by_key_id: null,
    published_at: null,
    entries: [],
    diagnostics
  };
}

export async function loadTrustedDesktopCatalog(
  options: LoadTrustedDesktopCatalogOptions
): Promise<{ catalog: DesktopConnectorCatalog; trustPolicy: TrustedDistributionPolicy }> {
  const basePolicy = buildBasePolicy(options.trustRootsOverride ?? trustRootsDocument);
  const diagnostics: ConnectorCatalogDiagnostic[] = [];
  let selected: VerifiedCatalogEnvelope | null = null;

  try {
    selected = verifyCatalogEnvelope(
      options.bundledEnvelopeOverride ?? bundledConnectorCatalogEnvelope,
      basePolicy,
      "bundled_signed"
    );
  } catch (error) {
    diagnostics.push(buildDiagnostic("catalog_signature_invalid", String(error)));
  }

  const remoteCatalogUrl = options.remoteCatalogUrl?.trim() ?? "";
  if (remoteCatalogUrl) {
    try {
      const remoteEnvelope = await fetchRemoteCatalogEnvelope(remoteCatalogUrl, options.fetchImpl ?? DEFAULT_FETCH_IMPL);
      selected = verifyCatalogEnvelope(remoteEnvelope, basePolicy, "remote_signed");
    } catch (error) {
      diagnostics.push(buildDiagnostic("catalog_remote_load_failed", String(error)));
    }
  }

  if (!selected) {
    return {
      catalog: emptyCatalog(
        diagnostics.length > 0 ? diagnostics : [buildDiagnostic("catalog_signature_invalid", "No trusted catalog is available.")],
        "signature_invalid",
        diagnostics[0]?.message ?? "No trusted catalog is available."
      ),
      trustPolicy: basePolicy
    };
  }

  const catalog = loadDesktopConnectorCatalog(selected.catalogEnvelope.catalog, options.marketCatalog, {
    catalogId: selected.catalogEnvelope.catalog_id,
    sourceKind: selected.catalogEnvelope.source_kind,
    verificationStatus: "trusted",
    verificationReason: null,
    signedByKeyId: selected.signingKeyId,
    publishedAt: selected.catalogEnvelope.published_at,
    diagnostics: [...diagnostics, ...selected.diagnostics],
    revokedEntryIds: selected.trustPolicy.revokedEntryIds,
    revokedPluginVersions: selected.trustPolicy.revokedPluginVersions
  });

  return {
    catalog,
    trustPolicy: selected.trustPolicy
  };
}

export function buildReceiptPackSignaturePayload(options: {
  pluginId: string;
  pluginVersion: string;
  pluginFamily: "receipt";
  metadataSha256: string;
  manifestSha256: string;
  integritySha256: string;
  integrityFiles: Record<string, string>;
}): string {
  return stableStringify({
    schema_version: "1",
    signature_type: "receipt_plugin_pack",
    plugin_id: options.pluginId,
    plugin_version: options.pluginVersion,
    plugin_family: options.pluginFamily,
    metadata_sha256: options.metadataSha256,
    manifest_sha256: options.manifestSha256,
    integrity_sha256: options.integritySha256,
    integrity_files: Object.fromEntries(
      Object.entries(options.integrityFiles)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([fileName, hash]) => [fileName, hash.toLowerCase()])
    )
  });
}

export function verifyReceiptPackSignature(options: {
  archiveSha256: string;
  pluginId: string;
  pluginVersion: string;
  trustClass: ConnectorTrustClass;
  metadataSha256: string;
  manifestSha256: string;
  integritySha256: string;
  integrityFiles: Record<string, string>;
  signatureDocument: unknown | null;
  trustPolicy: TrustedDistributionPolicy;
}): VerifiedReceiptPackSignature {
  const diagnostics: string[] = [];
  const revocationKey = `${options.pluginId}@${options.pluginVersion}`;

  if (options.trustPolicy.blockedArchiveSha256.has(options.archiveSha256.toLowerCase())) {
    return {
      signatureStatus: "revoked",
      trustStatus: "revoked",
      trustReason:
        options.trustPolicy.blockedArchiveSha256.get(options.archiveSha256.toLowerCase()) ??
        "Plugin pack archive hash is blocked.",
      signingKeyId: null,
      diagnostics
    };
  }

  if (options.trustPolicy.revokedPluginVersions.has(revocationKey)) {
    return {
      signatureStatus: "revoked",
      trustStatus: "revoked",
      trustReason:
        options.trustPolicy.revokedPluginVersions.get(revocationKey) ??
        `Plugin pack ${revocationKey} is revoked.`,
      signingKeyId: null,
      diagnostics
    };
  }

  if (!options.signatureDocument) {
    return {
      signatureStatus: "unsigned",
      trustStatus: "unsigned",
      trustReason: "Plugin pack is unsigned.",
      signingKeyId: null,
      diagnostics
    };
  }

  const signature = options.signatureDocument as Partial<ReceiptPackSignatureDocument>;
  if (
    signature.schema_version !== "1" ||
    signature.signature_type !== "receipt_plugin_pack" ||
    typeof signature.key_id !== "string" ||
    typeof signature.payload_sha256 !== "string" ||
    typeof signature.signature !== "string" ||
    signature.algorithm !== "ed25519"
  ) {
    return {
      signatureStatus: "signature_invalid",
      trustStatus: "signature_invalid",
      trustReason: "Plugin pack signature metadata is invalid.",
      signingKeyId: typeof signature.key_id === "string" ? signature.key_id : null,
      diagnostics
    };
  }

  if (options.trustPolicy.blockedKeyIds.has(signature.key_id)) {
    return {
      signatureStatus: "revoked",
      trustStatus: "revoked",
      trustReason: options.trustPolicy.blockedKeyIds.get(signature.key_id) ?? `Signing key ${signature.key_id} is blocked.`,
      signingKeyId: signature.key_id,
      diagnostics
    };
  }

  const root = options.trustPolicy.rootKeys.find(
    (candidate) => candidate.key_id === signature.key_id && candidate.scopes.includes("pack")
  );
  if (!root) {
    return {
      signatureStatus: "signature_invalid",
      trustStatus: "signature_invalid",
      trustReason: `Signing key ${signature.key_id} is not trusted for plugin packs.`,
      signingKeyId: signature.key_id,
      diagnostics
    };
  }

  if (!root.allowed_pack_trust_classes.includes(options.trustClass)) {
    return {
      signatureStatus: "signature_invalid",
      trustStatus: "signature_invalid",
      trustReason: `Signing key ${signature.key_id} cannot endorse trust_class='${options.trustClass}'.`,
      signingKeyId: signature.key_id,
      diagnostics
    };
  }

  const payload = buildReceiptPackSignaturePayload({
    pluginId: options.pluginId,
    pluginVersion: options.pluginVersion,
    pluginFamily: "receipt",
    metadataSha256: options.metadataSha256,
    manifestSha256: options.manifestSha256,
    integritySha256: options.integritySha256,
    integrityFiles: options.integrityFiles
  });

  if (signature.payload_sha256.toLowerCase() !== sha256Hex(payload)) {
    return {
      signatureStatus: "signature_invalid",
      trustStatus: "signature_invalid",
      trustReason: "Plugin pack signature payload hash does not match the verified archive contents.",
      signingKeyId: signature.key_id,
      diagnostics
    };
  }

  if (!verifyDetachedSignature(payload, root.public_key_pem, signature.signature)) {
    return {
      signatureStatus: "signature_invalid",
      trustStatus: "signature_invalid",
      trustReason: `Plugin pack signature verification failed for key '${signature.key_id}'.`,
      signingKeyId: signature.key_id,
      diagnostics
    };
  }

  return {
    signatureStatus: "verified",
    trustStatus: "trusted",
    trustReason: null,
    signingKeyId: signature.key_id,
    diagnostics
  };
}
