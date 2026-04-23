import { existsSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const desktopDir = resolve(__dirname, "..");

const generatedPaths = [
  "out",
  "output",
  "dist_electron",
  "playwright-report",
  "test-results",
  ".backend",
  "build/frontend-dist",
  "build/backend-src",
  "build/backend-venv",
  "build/plugin-packs",
  "vendor/frontend/dist"
].map((relativePath) => resolve(desktopDir, relativePath));

for (const fullPath of generatedPaths) {
  if (!existsSync(fullPath)) {
    continue;
  }
  rmSync(fullPath, { recursive: true, force: true });
  console.log(`Removed ${fullPath}`);
}
