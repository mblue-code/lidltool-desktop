import test from "node:test";
import assert from "node:assert/strict";
import {
  findDiagnosticsArchives,
  findForbiddenPublicProductReferences,
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
  assert.deepEqual(findDiagnosticsArchives(["safe.zip", "outlays-diagnostics-2026.zip"]), [
    "outlays-diagnostics-2026.zip"
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

test("detects forbidden legacy public product identity outside allowlisted paths", () => {
  const findings = findForbiddenPublicProductReferences([
    { path: "README.md", content: "LidlTool Desktop" },
    { path: "vendor/backend/src/lidltool/config.py", content: "LidlTool internal module note" },
    { path: "docs/product-rename-implementation-plan.md", content: "lidltool-desktop migration note" }
  ]);
  assert.deepEqual(findings.map((file) => file.path), ["README.md"]);
});
