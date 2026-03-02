import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const frontendDir = resolve(desktopDir, "vendor", "frontend");

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
