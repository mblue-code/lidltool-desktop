import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const sourceRepoRoot = resolve(desktopDir, "..", "..");
const vendorDir = resolve(desktopDir, "vendor");
const frontendSource = resolve(sourceRepoRoot, "frontend");
const frontendDest = resolve(vendorDir, "frontend");
const backendDest = resolve(vendorDir, "backend");

function resetDir(path) {
  rmSync(path, { recursive: true, force: true });
  mkdirSync(path, { recursive: true });
}

function copyTreeFiltered(source, dest, excludedNames) {
  cpSync(source, dest, {
    recursive: true,
    filter: (src) => {
      const name = src.split(/[/\\]/).pop() || "";
      return !excludedNames.has(name);
    }
  });
}

if (!existsSync(frontendSource)) {
  throw new Error(`Main frontend source not found at ${frontendSource}`);
}

mkdirSync(vendorDir, { recursive: true });

resetDir(frontendDest);
copyTreeFiltered(frontendSource, frontendDest, new Set(["node_modules", "dist", ".vite", "playwright-report", "test-results"]));

resetDir(backendDest);
const backendEntries = ["pyproject.toml", "README.md", "alembic.ini", "src"];
for (const entry of backendEntries) {
  const from = resolve(sourceRepoRoot, entry);
  if (!existsSync(from)) {
    throw new Error(`Required backend entry not found: ${from}`);
  }
  const to = resolve(backendDest, entry);
  cpSync(from, to, { recursive: true });
}

const novncSource = resolve(sourceRepoRoot, "novnc");
if (existsSync(novncSource)) {
  cpSync(novncSource, resolve(backendDest, "novnc"), { recursive: true });
}

console.log(`Vendored frontend -> ${frontendDest}`);
console.log(`Vendored backend -> ${backendDest}`);
