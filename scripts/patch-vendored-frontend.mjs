import { cpSync, existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const frontendDir = resolve(desktopDir, "vendor", "frontend");
const frontendOverridesDir = resolve(desktopDir, "overrides", "frontend");
const sharedDesktopRoutePolicyPath = resolve(desktopDir, "src", "shared", "desktop-route-policy.ts");
const frontendDesktopRoutePolicyPath = resolve(frontendDir, "src", "lib", "desktop-route-policy.ts");

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

function applyOverrides(sourceDir, destDir) {
  if (!existsSync(sourceDir)) {
    return [];
  }

  const copied = [];

  function visit(currentSourceDir) {
    for (const entry of readdirSync(currentSourceDir)) {
      const sourcePath = resolve(currentSourceDir, entry);
      const relativePath = relative(sourceDir, sourcePath);
      const destPath = resolve(destDir, relativePath);
      const stats = statSync(sourcePath);
      if (stats.isDirectory()) {
        visit(sourcePath);
        continue;
      }
      cpSync(sourcePath, destPath, { force: true });
      copied.push(relativePath);
    }
  }

  visit(sourceDir);
  return copied.sort();
}

function syncSharedDesktopRoutePolicy() {
  if (!existsSync(sharedDesktopRoutePolicyPath)) {
    throw new Error(`Shared desktop route policy not found at ${sharedDesktopRoutePolicyPath}.`);
  }

  cpSync(sharedDesktopRoutePolicyPath, frontendDesktopRoutePolicyPath, { force: true });
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

const overrideFiles = applyOverrides(frontendOverridesDir, frontendDir);
if (overrideFiles.length > 0) {
  console.log(`Applied desktop frontend overrides (${overrideFiles.length}):`);
  for (const file of overrideFiles) {
    console.log(`  - ${file}`);
  }
}
