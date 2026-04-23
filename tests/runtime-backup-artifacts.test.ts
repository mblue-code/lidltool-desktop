import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  readBackupManifest,
  resolveCredentialKeyArtifact,
  resolveDbArtifact,
  resolveDocumentsArtifact,
  resolveTokenArtifact
} from "../src/main/runtime-backup-artifacts.ts";

function tempBackupDir(): string {
  return mkdtempSync(join(tmpdir(), "desktop-backup-artifacts-"));
}

test("reads a valid backup manifest and ignores invalid JSON", () => {
  const validDir = tempBackupDir();
  writeFileSync(join(validDir, "backup-manifest.json"), JSON.stringify({ db_artifact: "/tmp/db.sqlite" }), "utf-8");
  assert.deepEqual(readBackupManifest(validDir), { db_artifact: "/tmp/db.sqlite" });

  const invalidDir = tempBackupDir();
  writeFileSync(join(invalidDir, "backup-manifest.json"), "{broken", "utf-8");
  assert.equal(readBackupManifest(invalidDir), null);
});

test("resolves db and token artifacts from manifest or fallback files", () => {
  const backupDir = tempBackupDir();
  const dbPath = join(backupDir, "lidltool.sqlite");
  const tokenPath = join(backupDir, "token.json");
  writeFileSync(dbPath, "db", "utf-8");
  writeFileSync(tokenPath, "{}", "utf-8");

  assert.equal(resolveDbArtifact(backupDir, (value) => value), dbPath);
  assert.equal(resolveTokenArtifact(backupDir, (value) => value), tokenPath);
});

test("resolves moved manifest artifacts by basename inside the backup folder", () => {
  const backupDir = tempBackupDir();
  const movedDbPath = join(backupDir, "copied.sqlite");
  const movedTokenPath = join(backupDir, "copied-token.json");
  writeFileSync(movedDbPath, "db", "utf-8");
  writeFileSync(movedTokenPath, "{}", "utf-8");
  writeFileSync(
    join(backupDir, "backup-manifest.json"),
    JSON.stringify({
      db_artifact: "/original/location/copied.sqlite",
      token_artifact: "/original/location/copied-token.json"
    }),
    "utf-8"
  );

  assert.equal(resolveDbArtifact(backupDir, (value) => value), movedDbPath);
  assert.equal(resolveTokenArtifact(backupDir, (value) => value), movedTokenPath);
});

test("resolves documents and credential-key artifacts", () => {
  const backupDir = tempBackupDir();
  const documentsDir = join(backupDir, "documents");
  mkdirSync(documentsDir);
  const keyPath = join(backupDir, "credential_encryption_key.txt");
  writeFileSync(keyPath, "secret", "utf-8");

  assert.equal(resolveDocumentsArtifact(backupDir, (value) => value), documentsDir);
  assert.equal(resolveCredentialKeyArtifact(backupDir, (value) => value), keyPath);
});

test("prefers manifest-declared directories for documents when present", () => {
  const backupDir = tempBackupDir();
  const manifestDocumentsDir = join(backupDir, "restored-documents");
  mkdirSync(manifestDocumentsDir);
  writeFileSync(
    join(backupDir, "backup-manifest.json"),
    JSON.stringify({
      documents_artifact: "/original/location/restored-documents"
    }),
    "utf-8"
  );

  assert.equal(resolveDocumentsArtifact(backupDir, (value) => value), manifestDocumentsDir);
});
