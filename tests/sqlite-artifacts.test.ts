import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  copySqliteArtifact,
  describeSqliteSnapshotMismatch,
  snapshotSqliteArtifact,
} from "../src/main/sqlite-artifacts.ts";

function pythonExecutable(): string {
  return process.platform === "win32" ? "python" : "python3";
}

function seedSqlite(path: string, usernames: string[]): void {
  execFileSync(
    pythonExecutable(),
    [
      "-c",
      `
import sqlite3
import sys

path = sys.argv[1]
connection = sqlite3.connect(path)
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("CREATE TABLE users (username TEXT PRIMARY KEY, is_admin INTEGER NOT NULL)")
for index, username in enumerate(sys.argv[2:]):
    connection.execute(
        "INSERT INTO users (username, is_admin) VALUES (?, ?)",
        (username, 1 if index == 0 else 0),
    )
connection.commit()
connection.close()
      `,
      path,
      ...usernames
    ],
    { stdio: "pipe" }
  );
}

test("copies SQLite artifacts through the backup API without losing rows", async () => {
  const fixtureRoot = mkdtempSync(join(tmpdir(), "lidltool-desktop-sqlite-"));
  try {
    const sourcePath = join(fixtureRoot, "source.sqlite");
    const backupPath = join(fixtureRoot, "backup.sqlite");
    const restoredPath = join(fixtureRoot, "restored.sqlite");
    seedSqlite(sourcePath, ["admin", "viewer"]);

    const helper = { pythonExecutable: pythonExecutable(), env: process.env };
    const sourceSnapshot = await snapshotSqliteArtifact(sourcePath, helper);
    await copySqliteArtifact(sourcePath, backupPath, helper);
    const backupSnapshot = await snapshotSqliteArtifact(backupPath, helper);
    assert.deepEqual(describeSqliteSnapshotMismatch(sourceSnapshot, backupSnapshot), []);

    await copySqliteArtifact(backupPath, restoredPath, helper);
    const restoredSnapshot = await snapshotSqliteArtifact(restoredPath, helper);
    assert.deepEqual(describeSqliteSnapshotMismatch(backupSnapshot, restoredSnapshot), []);
    assert.deepEqual(
      restoredSnapshot.users.map((user) => user.username),
      ["admin", "viewer"]
    );
  } finally {
    rmSync(fixtureRoot, { recursive: true, force: true });
  }
});

test("reports when two SQLite snapshots diverge", () => {
  const mismatches = describeSqliteSnapshotMismatch(
    {
      path: "/tmp/source.sqlite",
      fileSha256: "source",
      fileSizeBytes: 1,
      tableCounts: { users: 1 },
      users: [{ username: "admin", isAdmin: true }],
      dataSha256: "source-data"
    },
    {
      path: "/tmp/target.sqlite",
      fileSha256: "target",
      fileSizeBytes: 2,
      tableCounts: { users: 2 },
      users: [
        { username: "admin", isAdmin: true },
        { username: "viewer", isAdmin: false }
      ],
      dataSha256: "target-data"
    }
  );

  assert.equal(mismatches.length, 3);
});
