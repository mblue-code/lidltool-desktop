import test from "node:test";
import assert from "node:assert/strict";
import {
  findDiagnosticsArchives,
  findPrivateKeyMaterial,
  findRuntimeBoundaryReferences,
  findStagedEnvFiles,
  validateReleaseChannelVersion
} from "../scripts/lib/release-preflight.mjs";

test("detects staged env files", () => {
  assert.deepEqual(findStagedEnvFiles([".env", "config/.env.production", "src/main/index.ts"]), [
    ".env",
    "config/.env.production"
  ]);
});

test("detects diagnostics archives", () => {
  assert.deepEqual(findDiagnosticsArchives(["safe.zip", "lidltool-diagnostics-2026.zip"]), [
    "lidltool-diagnostics-2026.zip"
  ]);
});

test("detects private key material", () => {
  const findings = findPrivateKeyMaterial([
    { path: "README.md", content: "safe" },
    { path: "key.pem", content: "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----" }
  ]);
  assert.equal(findings.length, 1);
  assert.equal(findings[0].path, "key.pem");
});

test("detects runtime ../../ references", () => {
  const findings = findRuntimeBoundaryReferences([
    { path: "src/main/index.ts", content: "const path = '../../main-repo';" },
    { path: "docs/note.md", content: "../../allowed-in-docs" }
  ]);
  assert.equal(findings.length, 1);
  assert.equal(findings[0].path, "src/main/index.ts");
});

test("validates beta and stable version/channel relationship", () => {
  assert.equal(validateReleaseChannelVersion("beta", "0.2.0-beta.1").ok, true);
  assert.equal(validateReleaseChannelVersion("beta", "0.2.0").ok, false);
  assert.equal(validateReleaseChannelVersion("stable", "1.0.0").ok, true);
  assert.equal(validateReleaseChannelVersion("stable", "1.0.0-beta.1").ok, false);
});
