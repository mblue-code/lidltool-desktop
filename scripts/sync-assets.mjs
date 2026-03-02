import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const buildDir = resolve(desktopDir, "build");

const frontendDistSrc = resolve(desktopDir, "vendor", "frontend", "dist");
const frontendDistDest = resolve(buildDir, "frontend-dist");

const backendSrc = resolve(desktopDir, "vendor", "backend");
const backendSrcDest = resolve(buildDir, "backend-src");

const backendVenvSrc = resolve(desktopDir, ".backend", "venv");
const backendVenvDest = resolve(buildDir, "backend-venv");

function resetDir(path) {
  rmSync(path, { recursive: true, force: true });
  mkdirSync(path, { recursive: true });
}

resetDir(frontendDistDest);
if (existsSync(frontendDistSrc)) {
  cpSync(frontendDistSrc, frontendDistDest, { recursive: true });
} else {
  writeFileSync(
    join(frontendDistDest, "README.txt"),
    "Vendored frontend dist was not found. Run `npm run frontend:build` from apps/desktop.\n",
    "utf-8"
  );
}

resetDir(backendSrcDest);
if (existsSync(backendSrc)) {
  cpSync(backendSrc, backendSrcDest, { recursive: true });
} else {
  writeFileSync(
    join(backendSrcDest, "README.txt"),
    "Vendored backend source was not found. Run `npm run vendor:sync` from apps/desktop.\n",
    "utf-8"
  );
}

resetDir(backendVenvDest);
if (existsSync(backendVenvSrc)) {
  cpSync(backendVenvSrc, backendVenvDest, { recursive: true });
} else {
  writeFileSync(
    join(backendVenvDest, "README.txt"),
    "No bundled backend venv found. Run `npm run backend:prepare` from apps/desktop to include one.\n",
    "utf-8"
  );
}

console.log(existsSync(frontendDistSrc) ? `Synced frontend assets to ${frontendDistDest}` : "Skipped frontend asset sync (vendored dist missing).");
console.log(existsSync(backendSrc) ? `Synced backend source to ${backendSrcDest}` : "Skipped backend source sync (vendored backend missing).");
console.log(existsSync(backendVenvSrc) ? `Synced backend runtime to ${backendVenvDest}` : "Skipped backend runtime sync (no .backend/venv found).");
