import assert from "node:assert/strict";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopDir = resolve(__dirname, "..");
const vendorManifestPath = join(desktopDir, "vendor", "vendor-manifest.json");

function withTempDesktopFixture(run: (fixtureDir: string) => void): void {
  const fixtureDir = mkdtempSync(join(tmpdir(), "lidltool-desktop-patcher-"));
  try {
    run(fixtureDir);
  } finally {
    rmSync(fixtureDir, { recursive: true, force: true });
  }
}

function runNodeScript(scriptPath: string, fixtureDir: string): void {
  const result = spawnSync(process.execPath, [scriptPath], {
    cwd: desktopDir,
    env: {
      ...process.env,
      LIDLTOOL_DESKTOP_DIR: fixtureDir
    },
    encoding: "utf-8"
  });

  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || `Script failed: ${scriptPath}`);
  }
}

function writeVendorManifestFixture(
  fixtureDir: string,
  overrides: {
    runtimeOverrideFiles?: string[];
    testOverrideFiles?: string[];
    requiredFiles?: string[];
    requiredLoaderKeys?: string[];
    requiredTranslationKeys?: string[];
  } = {}
): void {
  const baseManifest = JSON.parse(readFileSync(vendorManifestPath, "utf-8"));
  baseManifest.frontend = {
    ...baseManifest.frontend,
    ...overrides
  };
  mkdirSync(join(fixtureDir, "vendor"), { recursive: true });
  writeFileSync(
    join(fixtureDir, "vendor", "vendor-manifest.json"),
    JSON.stringify(baseManifest, null, 2),
    "utf-8"
  );
}

test("backend patcher stays green against the current vendored backend shape", () => {
  withTempDesktopFixture((fixtureDir) => {
    const backendFixtureDir = join(fixtureDir, "vendor", "backend");
    const backendSourceDir = join(desktopDir, "vendor", "backend");
    const backendFiles = [
      "src/lidltool/api/http_server.py",
      "src/lidltool/api/route_auth.py",
      "src/lidltool/ops/backup_restore.py",
      "src/lidltool/connectors/auth/browser_runtime.py",
      "src/lidltool/connectors/lifecycle.py",
      "src/lidltool/connectors/registry.py",
      "src/lidltool/connectors/runtime/execution.py",
      "src/lidltool/connectors/runtime/runner.py",
      "src/lidltool/ingest/jobs.py",
      "src/lidltool/ocr/providers/glm_ocr_local.py",
      "src/lidltool/cli.py"
    ];

    for (const relativePath of backendFiles) {
      const sourcePath = join(backendSourceDir, relativePath);
      const destinationPath = join(backendFixtureDir, relativePath);
      mkdirSync(dirname(destinationPath), { recursive: true });
      cpSync(sourcePath, destinationPath, { force: true });
    }

    runNodeScript(join(desktopDir, "scripts", "patch-vendored-backend.mjs"), fixtureDir);
    runNodeScript(join(desktopDir, "scripts", "patch-vendored-backend.mjs"), fixtureDir);

    const patchedHttpServer = readFileSync(
      join(backendFixtureDir, "src/lidltool/api/http_server.py"),
      "utf-8"
    );
    const patchedRuntimeExecution = readFileSync(
      join(backendFixtureDir, "src/lidltool/connectors/runtime/execution.py"),
      "utf-8"
    );
    const patchedIngestJobs = readFileSync(
      join(backendFixtureDir, "src/lidltool/ingest/jobs.py"),
      "utf-8"
    );
    const patchedGlmOcrLocal = readFileSync(
      join(backendFixtureDir, "src/lidltool/ocr/providers/glm_ocr_local.py"),
      "utf-8"
    );

    assert.match(patchedHttpServer, /scheduler: AutomationScheduler \| None = None/);
    assert.match(patchedHttpServer, /if scheduler is not None:\n\s+scheduler\.stop\(\)/);
    assert.match(patchedRuntimeExecution, /host_kind=_plugin_host_kind\(\)/);
    assert.match(patchedIngestJobs, /--idle-exit-after-s/);
    assert.match(patchedGlmOcrLocal, /glm_ocr_local_rapidocr_onnxruntime/);
  });
});

test("frontend patcher repairs the connector auth-status contract drift", () => {
  withTempDesktopFixture((fixtureDir) => {
    const frontendFixtureDir = join(fixtureDir, "vendor", "frontend");
    const overridesFixtureDir = join(fixtureDir, "overrides", "frontend", "src");
    const sharedDir = join(fixtureDir, "src", "shared");
    mkdirSync(join(frontendFixtureDir, "src", "api"), { recursive: true });
    mkdirSync(sharedDir, { recursive: true });
    mkdirSync(join(overridesFixtureDir, "api"), { recursive: true });
    writeVendorManifestFixture(fixtureDir, {
      runtimeOverrideFiles: ["api/dashboard.ts"],
      testOverrideFiles: []
    });

    writeFileSync(
      join(frontendFixtureDir, "vite.config.ts"),
      [
        "import { defineConfig } from \"vite\";",
        "",
        "export default defineConfig({",
        "  resolve: {",
        "    alias: {",
        "    }",
        "  }",
        "});",
        ""
      ].join("\n"),
      "utf-8"
    );
    writeFileSync(
      join(sharedDir, "desktop-route-policy.ts"),
      "export const DESKTOP_ROUTE_POLICY = [];\n",
      "utf-8"
    );
    writeFileSync(
      join(frontendFixtureDir, "src", "api", "connectors.ts"),
      [
        "import { z } from \"zod\";",
        "",
        "import { apiClient } from \"@/lib/api-client\";",
        "",
        "const ConnectorBootstrapStatusSchema = z.object({",
        "  source_id: z.string(),",
        "  status: z.string()",
        "});",
        "",
        "const ConnectorAuthStatusSchema = z.object({",
        "  source_id: z.string(),",
        "  state: z.string(),",
        "  detail: z.string().nullable(),",
        "  available_actions: z.array(z.string()).optional().default([])",
        "});",
        "",
        "const ConnectorBootstrapCancelSchema = z.object({",
        "  canceled: z.boolean()",
        "});",
        "",
        "export type ConnectorBootstrapStatus = z.infer<typeof ConnectorBootstrapStatusSchema>;",
        "export type ConnectorBootstrapCancelResult = z.infer<typeof ConnectorBootstrapCancelSchema>;",
        "",
        "export async function fetchConnectorBootstrapStatus(sourceId: string): Promise<ConnectorBootstrapStatus> {",
        "  return apiClient.get(`/api/v1/connectors/${sourceId}/bootstrap/status`, ConnectorBootstrapStatusSchema);",
        "}",
        "",
        "export async function cancelConnectorBootstrap(sourceId: string): Promise<ConnectorBootstrapCancelResult> {",
        "  return apiClient.post(`/api/v1/connectors/${sourceId}/bootstrap/cancel`, ConnectorBootstrapCancelSchema);",
        "}",
        "",
        "export async function fetchLegacyConnectorAuthStatus(sourceId: string) {",
        "  return apiClient.get(`/api/v1/connectors/${sourceId}/auth/status`, ConnectorAuthStatusSchema);",
        "}",
        ""
      ].join("\n"),
      "utf-8"
    );
    writeFileSync(join(overridesFixtureDir, "api", "dashboard.ts"), "export {};\n", "utf-8");

    runNodeScript(join(desktopDir, "scripts", "patch-vendored-frontend.mjs"), fixtureDir);
    runNodeScript(join(desktopDir, "scripts", "patch-vendored-frontend.mjs"), fixtureDir);

    const patchedConnectorsApi = readFileSync(
      join(frontendFixtureDir, "src", "api", "connectors.ts"),
      "utf-8"
    );

    assert.match(patchedConnectorsApi, /reauth_required: z\.boolean\(\)/);
    assert.match(
      patchedConnectorsApi,
      /export type ConnectorAuthStatus = z\.infer<typeof ConnectorAuthStatusSchema>;/
    );
    assert.match(
      patchedConnectorsApi,
      /export async function fetchConnectorAuthStatus\(sourceId: string\): Promise<ConnectorAuthStatus>/
    );
    assert.match(patchedConnectorsApi, /\/api\/v1\/sources\/\$\{sourceId\}\/auth/);
    assert.doesNotMatch(patchedConnectorsApi, /\/api\/v1\/connectors\/\$\{sourceId\}\/auth\/status/);
  });
});

test("frontend validator enforces the declared override surface from the vendor manifest", () => {
  withTempDesktopFixture((fixtureDir) => {
    const frontendSrcDir = join(fixtureDir, "vendor", "frontend", "src");
    const overridesSrcDir = join(fixtureDir, "overrides", "frontend", "src");
    mkdirSync(join(frontendSrcDir, "app"), { recursive: true });
    mkdirSync(join(frontendSrcDir, "i18n"), { recursive: true });
    mkdirSync(join(overridesSrcDir, "api"), { recursive: true });
    writeVendorManifestFixture(fixtureDir, {
      requiredFiles: ["app/page-loaders.ts", "i18n/messages.ts", "main.tsx"],
      runtimeOverrideFiles: ["api/dashboard.ts"],
      testOverrideFiles: [],
      requiredLoaderKeys: ["groceries"],
      requiredTranslationKeys: ["nav.item.dashboard"]
    });

    writeFileSync(
      join(frontendSrcDir, "app", "page-loaders.ts"),
      "export const pageLoaders = { groceries: () => import(\"../pages/GroceriesPage\") };\n",
      "utf-8"
    );
    writeFileSync(
      join(frontendSrcDir, "i18n", "messages.ts"),
      "export const messages = { \"nav.item.dashboard\": \"Dashboard\" };\n",
      "utf-8"
    );
    writeFileSync(
      join(frontendSrcDir, "main.tsx"),
      "pageLoaders.groceries();\n",
      "utf-8"
    );
    writeFileSync(join(overridesSrcDir, "api", "dashboard.ts"), "export {};\n", "utf-8");
    writeFileSync(join(overridesSrcDir, "api", "rogue.ts"), "export {};\n", "utf-8");

    const result = spawnSync(process.execPath, [join(desktopDir, "scripts", "validate-vendored-frontend.mjs")], {
      cwd: desktopDir,
      env: {
        ...process.env,
        LIDLTOOL_DESKTOP_DIR: fixtureDir
      },
      encoding: "utf-8"
    });

    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /Undeclared desktop frontend override file: api\/rogue\.ts/);
  });
});
