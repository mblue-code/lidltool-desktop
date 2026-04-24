import { cpSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(process.env.LIDLTOOL_DESKTOP_DIR?.trim() || resolve(__dirname, ".."));
const frontendDir = resolve(desktopDir, "vendor", "frontend");
const frontendOverridesDir = resolve(desktopDir, "overrides", "frontend");
const vendorManifestPath = resolve(desktopDir, "vendor", "vendor-manifest.json");
const sharedDesktopRoutePolicyPath = resolve(desktopDir, "src", "shared", "desktop-route-policy.ts");
const frontendDesktopRoutePolicyPath = resolve(frontendDir, "src", "lib", "desktop-route-policy.ts");
const connectorsApiPath = resolve(frontendDir, "src", "api", "connectors.ts");

const aliasFragment = "\"@mariozechner/pi-ai\": resolve(process.cwd(), \"src/shims/pi-ai.ts\"),";

function applyPiAiAlias(viteConfigPath) {
  if (!existsSync(viteConfigPath)) {
    return { changed: false, skipped: true };
  }

  const current = readFileSync(viteConfigPath, "utf-8");
  if (current.includes("@mariozechner/pi-ai")) {
    return { changed: false, skipped: false };
  }

  const marker = "alias: {";
  const markerIndex = current.indexOf(marker);
  if (markerIndex === -1) {
    throw new Error(`Could not patch ${viteConfigPath}: no alias block found.`);
  }

  const insertAt = markerIndex + marker.length;
  const next = `${current.slice(0, insertAt)}\n      ${aliasFragment}${current.slice(insertAt)}`;
  writeFileSync(viteConfigPath, next, "utf-8");
  return { changed: true, skipped: false };
}

function loadFrontendOverrides() {
  if (!existsSync(vendorManifestPath)) {
    throw new Error(`Desktop vendor manifest not found at ${vendorManifestPath}`);
  }
  const manifest = JSON.parse(readFileSync(vendorManifestPath, "utf-8"));
  const frontend = manifest.frontend ?? {};
  return [
    ...(frontend.runtimeOverrideFiles ?? []),
    ...(frontend.testOverrideFiles ?? [])
  ];
}

function applyOverrides(sourceDir, destDir, relativePaths) {
  if (!existsSync(sourceDir)) {
    return [];
  }

  const copied = [];
  for (const relativePath of relativePaths) {
    const sourcePath = resolve(sourceDir, "src", relativePath);
    const destPath = resolve(destDir, "src", relativePath);
    if (!existsSync(sourcePath) || statSync(sourcePath).isDirectory()) {
      throw new Error(`Declared desktop override not found: ${sourcePath}`);
    }
    mkdirSync(dirname(destPath), { recursive: true });
    cpSync(sourcePath, destPath, { force: true });
    copied.push(relativePath);
  }
  return copied.sort();
}

function syncSharedDesktopRoutePolicy() {
  if (!existsSync(sharedDesktopRoutePolicyPath)) {
    throw new Error(`Shared desktop route policy not found at ${sharedDesktopRoutePolicyPath}.`);
  }

  cpSync(sharedDesktopRoutePolicyPath, frontendDesktopRoutePolicyPath, { force: true });
}

function patchConnectorAuthStatusContract() {
  if (!existsSync(connectorsApiPath)) {
    return { changed: false, skipped: true };
  }

  const expandedSchemaBlock = `const ConnectorAuthStatusSchema = z.object({
  source_id: z.string(),
  state: z.string(),
  detail: z.string().nullable(),
  reauth_required: z.boolean(),
  needs_connection: z.boolean(),
  available_actions: z.array(z.string()),
  implemented_actions: z.array(z.string()),
  metadata: z.record(z.string(), z.unknown()),
  diagnostics: z.record(z.string(), z.unknown()),
  bootstrap: z
    .object({
      source_id: z.string(),
      status: z.string(),
      started_at: z.string().nullable(),
      finished_at: z.string().nullable(),
      return_code: z.number().nullable(),
      can_cancel: z.boolean()
    })
    .nullable()
});
`;

  const current = readFileSync(connectorsApiPath, "utf-8");
  let next = current;

  if (!next.includes("reauth_required: z.boolean()")) {
    const authStatusSchemaPattern =
      /const ConnectorAuthStatusSchema = z\.object\(\{[\s\S]*?\n\}\);\n/;
    if (authStatusSchemaPattern.test(next)) {
      next = next.replace(authStatusSchemaPattern, expandedSchemaBlock);
    } else {
      const bootstrapStatusMarker = "const ConnectorBootstrapStartSchema = z.object({\n";
      const insertAt = next.indexOf(bootstrapStatusMarker);
      if (insertAt === -1) {
        throw new Error(`Could not patch ${connectorsApiPath}: no bootstrap schema insertion point found.`);
      }
      next = `${next.slice(0, insertAt)}${expandedSchemaBlock}\n${next.slice(insertAt)}`;
    }
  }

  next = next.replaceAll("/api/v1/connectors/${sourceId}/auth/status", "/api/v1/sources/${sourceId}/auth");

  if (!next.includes("export async function fetchConnectorAuthStatus(sourceId: string): Promise<ConnectorAuthStatus>")) {
    const cancelBootstrapMarker =
      "export async function cancelConnectorBootstrap(sourceId: string): Promise<ConnectorBootstrapCancelResult> {\n";
    const insertAt = next.indexOf(cancelBootstrapMarker);
    if (insertAt === -1) {
      throw new Error(`Could not patch ${connectorsApiPath}: no auth status insertion point found.`);
    }
    next =
      `${next.slice(0, insertAt)}` +
      "export async function fetchConnectorAuthStatus(sourceId: string): Promise<ConnectorAuthStatus> {\n" +
      "  return apiClient.get(`/api/v1/sources/${sourceId}/auth`, ConnectorAuthStatusSchema);\n" +
      "}\n\n" +
      `${next.slice(insertAt)}`;
  }

  if (!next.includes("export type ConnectorAuthStatus = z.infer<typeof ConnectorAuthStatusSchema>;")) {
    const exportMarkers = [
      "export type ConnectorSyncStatus = z.infer<typeof ConnectorSyncStatusSchema>;\n",
      "export async function fetchConnectorBootstrapStatus(sourceId: string): Promise<ConnectorBootstrapStatus> {\n"
    ];
    const exportMarker = exportMarkers.find((marker) => next.includes(marker));
    if (!exportMarker) {
      throw new Error(`Could not patch ${connectorsApiPath}: no ConnectorAuthStatus export insertion point found.`);
    }
    const insertAt = next.indexOf(exportMarker);
    next =
      `${next.slice(0, insertAt)}` +
      "export type ConnectorAuthStatus = z.infer<typeof ConnectorAuthStatusSchema>;\n" +
      `${next.slice(insertAt)}`;
  }

  if (next === current) {
    return { changed: false, skipped: false };
  }

  writeFileSync(connectorsApiPath, next, "utf-8");
  return { changed: true, skipped: false };
}

const viteTs = resolve(frontendDir, "vite.config.ts");
const viteJs = resolve(frontendDir, "vite.config.js");

const tsResult = applyPiAiAlias(viteTs);
const jsResult = applyPiAiAlias(viteJs);

if (tsResult.skipped && jsResult.skipped) {
  throw new Error(
    `Vendored frontend config files not found under ${frontendDir}. Run 'npm run vendor:sync' first.`
  );
}

if (tsResult.changed || jsResult.changed) {
  console.log("Patched vendored frontend Vite config with browser shim alias for @mariozechner/pi-ai.");
} else {
  console.log("Vendored frontend Vite config already contains browser shim alias.");
}

syncSharedDesktopRoutePolicy();
console.log("Synced shared desktop route policy into vendored frontend.");

const authStatusContractResult = patchConnectorAuthStatusContract();
if (!authStatusContractResult.skipped) {
  console.log(
    authStatusContractResult.changed
      ? "Patched vendored connectors API auth-status contract for desktop."
      : "Vendored connectors API auth-status contract already matches desktop expectations."
  );
}

const overrideFiles = applyOverrides(frontendOverridesDir, frontendDir, loadFrontendOverrides());
if (overrideFiles.length > 0) {
  console.log(`Applied desktop frontend overrides (${overrideFiles.length}):`);
  for (const file of overrideFiles) {
    console.log(`  - ${file}`);
  }
}
