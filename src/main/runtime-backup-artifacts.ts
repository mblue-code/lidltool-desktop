import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, join } from "node:path";

export function readBackupManifest(backupDir: string): Record<string, unknown> | null {
  const manifestPath = join(backupDir, "backup-manifest.json");
  if (!existsSync(manifestPath)) {
    return null;
  }
  try {
    const parsed = JSON.parse(readFileSync(manifestPath, "utf-8"));
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, unknown>;
    }
  } catch {
    return null;
  }
  return null;
}

export function resolveDbArtifact(
  backupDir: string,
  resolveUserPath: (value: string) => string
): string | null {
  const manifest = readBackupManifest(backupDir);
  const manifestCandidate = resolveManifestArtifactCandidate(backupDir, manifest, ["db_artifact", "dbArtifact"], resolveUserPath);
  if (manifestCandidate) {
    return manifestCandidate;
  }
  const direct = resolveBackupArtifact(backupDir, "lidltool.sqlite");
  if (direct) {
    return direct;
  }
  const timestamped = resolveLatestPatternMatch(backupDir, /^db-backup-.*\.sqlite$/);
  if (timestamped) {
    return timestamped;
  }
  return resolveLatestPatternMatch(backupDir, /\.sqlite$/);
}

export function resolveTokenArtifact(
  backupDir: string,
  resolveUserPath: (value: string) => string
): string | null {
  const manifest = readBackupManifest(backupDir);
  const manifestCandidate = resolveManifestArtifactCandidate(
    backupDir,
    manifest,
    ["token_artifact", "tokenArtifact"],
    resolveUserPath
  );
  if (manifestCandidate) {
    return manifestCandidate;
  }
  const direct = resolveBackupArtifact(backupDir, "token.json");
  if (direct) {
    return direct;
  }
  return resolveLatestPatternMatch(backupDir, /^token-backup-.*\.json$/);
}

export function resolveDocumentsArtifact(
  backupDir: string,
  resolveUserPath: (value: string) => string
): string | null {
  const manifest = readBackupManifest(backupDir);
  const manifestCandidate = resolveManifestArtifactCandidate(
    backupDir,
    manifest,
    ["documents_artifact", "documentsArtifact"],
    resolveUserPath
  );
  if (manifestCandidate && statSync(manifestCandidate).isDirectory()) {
    return manifestCandidate;
  }
  const direct = resolveBackupArtifact(backupDir, "documents");
  if (direct && statSync(direct).isDirectory()) {
    return direct;
  }
  const pattern = resolveLatestPatternMatch(backupDir, /^documents-backup-.*/);
  if (pattern && statSync(pattern).isDirectory()) {
    return pattern;
  }
  return null;
}

export function resolveCredentialKeyArtifact(
  backupDir: string,
  resolveUserPath: (value: string) => string
): string | null {
  const manifest = readBackupManifest(backupDir);
  const manifestCandidate = resolveManifestArtifactCandidate(
    backupDir,
    manifest,
    ["credential_key_artifact", "credentialKeyArtifact"],
    resolveUserPath
  );
  if (manifestCandidate) {
    return manifestCandidate;
  }
  return resolveBackupArtifact(backupDir, "credential_encryption_key.txt");
}

function resolveManifestArtifactCandidate(
  backupDir: string,
  manifest: Record<string, unknown> | null,
  keys: string[],
  resolveUserPath: (value: string) => string
): string | null {
  if (!manifest) {
    return null;
  }
  for (const key of keys) {
    const value = manifest[key];
    if (typeof value !== "string" || !value.trim()) {
      continue;
    }
    const direct = resolveUserPath(value.trim());
    if (existsSync(direct)) {
      return direct;
    }
    const moved = join(backupDir, basename(value.trim()));
    if (existsSync(moved)) {
      return moved;
    }
  }
  return null;
}

function resolveBackupArtifact(backupDir: string, fileName: string): string | null {
  const candidate = join(backupDir, fileName);
  return existsSync(candidate) ? candidate : null;
}

function resolveLatestPatternMatch(backupDir: string, pattern: RegExp): string | null {
  const matches = readdirSync(backupDir)
    .filter((entry) => pattern.test(entry))
    .sort()
    .reverse();
  for (const entry of matches) {
    const candidate = join(backupDir, entry);
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}
