import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  findCatalogDesktopPackEntry,
  inspectBackendCommand,
  resolveBackendInvocation,
  resolveConfigDirPath,
  resolveDocumentsPath,
  resolveFrontendDist,
  resolveOcrIdleTimeoutSeconds,
  resolveRepoRootHint,
  resolveUserPath,
  type RuntimePathContext
} from "../src/main/runtime-paths.ts";

function createContext(overrides: Partial<RuntimePathContext> = {}): RuntimePathContext {
  return {
    appPath: "/workspace/apps/desktop",
    resourcesPath: "/Applications/LidlTool.app/Contents/Resources",
    isPackaged: false,
    homeDir: "/Users/tester",
    platform: "darwin",
    ...overrides
  };
}

test("resolves user, config, and documents paths with desktop defaults and overrides", () => {
  assert.equal(resolveUserPath("~/Desktop", "/Users/tester"), "/Users/tester/Desktop");
  assert.equal(resolveConfigDirPath("/tmp/user", {}, "/Users/tester"), "/tmp/user/config");
  assert.equal(
    resolveConfigDirPath("/tmp/user", { LIDLTOOL_CONFIG_DIR: "~/cfg" }, "/Users/tester"),
    "/Users/tester/cfg"
  );
  assert.equal(resolveDocumentsPath("/tmp/user", {}, "/Users/tester"), "/tmp/user/documents");
  assert.equal(
    resolveDocumentsPath("/tmp/user", { LIDLTOOL_DOCUMENT_STORAGE_PATH: "~/docs" }, "/Users/tester"),
    "/Users/tester/docs"
  );
});

test("resolves repo and frontend paths for dev and packaged modes", () => {
  assert.equal(
    resolveRepoRootHint(createContext(), {}),
    "/workspace/apps/desktop/vendor/backend"
  );
  assert.equal(
    resolveFrontendDist(createContext(), {}),
    "/workspace/apps/desktop/vendor/frontend/dist"
  );
  assert.equal(
    resolveRepoRootHint(createContext({ isPackaged: true }), {}),
    "/Applications/LidlTool.app/Contents/Resources/backend-src"
  );
  assert.equal(
    resolveFrontendDist(createContext({ isPackaged: true }), {}),
    "/Applications/LidlTool.app/Contents/Resources/frontend-dist"
  );
});

test("resolves backend command selection using explicit and managed executables", () => {
  const tempRoot = mkdtempSync(join(tmpdir(), "desktop-runtime-paths-"));
  try {
    const appPath = join(tempRoot, "app");
    mkdirSync(join(appPath, ".backend", "venv", "bin"), { recursive: true });
    writeFileSync(join(appPath, ".backend", "venv", "bin", "python"), "");
    writeFileSync(join(appPath, ".backend", "venv", "bin", "lidltool"), "");
    const context = createContext({ appPath });

    assert.deepEqual(resolveBackendInvocation(context, {}, false), {
      command: join(appPath, ".backend", "venv", "bin", "lidltool"),
      argsPrefix: []
    });
    assert.equal(inspectBackendCommand(context, {}).source, "managed_dev");

    assert.deepEqual(resolveBackendInvocation(context, { LIDLTOOL_EXECUTABLE: "custom-tool" }, false), {
      command: "custom-tool",
      argsPrefix: []
    });
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("finds trusted desktop pack entries and rejects invalid catalog references", () => {
  const entry = {
    entry_id: "desktop-pack.fixture",
    entry_type: "desktop_pack",
    plugin_id: "fixture",
    source_id: "fixture",
    display_name: "Fixture",
    summary: "fixture",
    description: null,
    trust_class: "community_verified",
    maintainer: "fixture",
    source: "fixture",
    supported_products: ["desktop"],
    supported_markets: ["DE"],
    current_version: "1.0.0",
    compatibility: {
      min_core_version: "0.1.0",
      max_core_version: null,
      supported_host_kinds: ["electron"],
      notes: []
    },
    install_methods: ["download_url"],
    docs_url: null,
    homepage_url: null,
    download_url: "https://example.test/plugin.zip",
    release_notes_summary: null,
    support_policy: null,
    official_bundle_ids: [],
    market_profile_ids: [],
    release_variant_ids: [],
    availability: {
      catalog_listed: true,
      discovered_locally: false,
      local_status: null,
      enabled_locally: false,
      blocked_by_policy: false,
      block_reason: null,
      officially_bundled: false,
      manual_install_supported: true
    }
  } as const;

  assert.equal(findCatalogDesktopPackEntry([entry], "desktop-pack.fixture").entry_id, "desktop-pack.fixture");
  assert.throws(
    () => findCatalogDesktopPackEntry([{ ...entry, download_url: null }], "desktop-pack.fixture"),
    /does not support trusted URL install/
  );
});

test("normalizes invalid OCR idle timeout values back to the safe default", () => {
  assert.equal(resolveOcrIdleTimeoutSeconds({}), 600);
  assert.equal(resolveOcrIdleTimeoutSeconds({ LIDLTOOL_DESKTOP_OCR_IDLE_TIMEOUT_S: "45" }), 600);
  assert.equal(resolveOcrIdleTimeoutSeconds({ LIDLTOOL_DESKTOP_OCR_IDLE_TIMEOUT_S: "900" }), 900);
});
