import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  normalizeTrustClass,
  readPackState,
  writePackState
} from "../src/main/plugins/receipt-plugin-pack-state.ts";

function tempStateFile(): string {
  return join(mkdtempSync(join(tmpdir(), "receipt-pack-state-")), "state.json");
}

test("normalizes supported trust classes and rejects unknown values", () => {
  assert.equal(normalizeTrustClass("official"), "official");
  assert.equal(normalizeTrustClass("community_verified"), "community_verified");
  assert.throws(() => normalizeTrustClass("nope"), /Unsupported imported plugin trust class/);
});

test("returns an empty state when the file is missing or invalid", () => {
  assert.deepEqual(readPackState(tempStateFile()), { version: 2, packs: {} });

  const invalidPath = tempStateFile();
  writeFileSync(invalidPath, "{broken", "utf-8");
  assert.deepEqual(readPackState(invalidPath), { version: 2, packs: {} });
});

test("normalizes stored pack records from disk", () => {
  const stateFile = tempStateFile();
  writeFileSync(
    stateFile,
    JSON.stringify({
      version: 2,
      packs: {
        "community.fixture": {
          installPath: "/tmp/install",
          manifestPath: "/tmp/install/manifest.json",
          trustClass: "community_verified",
          signatureStatus: "verified",
          installedVia: "catalog_url",
          supportedHostKinds: ["electron", 123],
          enabled: true
        }
      }
    }),
    "utf-8"
  );

  const state = readPackState(stateFile);
  const record = state.packs["community.fixture"];

  assert.ok(record);
  assert.equal(record?.pluginId, "community.fixture");
  assert.equal(record?.displayName, "community.fixture");
  assert.equal(record?.trustClass, "community_verified");
  assert.equal(record?.signatureStatus, "verified");
  assert.deepEqual(record?.supportedHostKinds, ["electron"]);
  assert.equal(record?.installedVia, "catalog_url");
  assert.equal(record?.enabled, true);
});

test("writes normalized state JSON", () => {
  const stateFile = tempStateFile();
  writePackState(stateFile, {
    version: 2,
    packs: {}
  });

  assert.match(readPackState(stateFile).version.toString(), /^2$/);
});
