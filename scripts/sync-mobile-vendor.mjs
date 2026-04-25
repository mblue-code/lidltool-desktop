import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const argv = process.argv.slice(2);
const vendorRoot = resolve(desktopDir, "vendor", "mobile");
const manifestPath = resolve(vendorRoot, "vendor-manifest.json");

function parseArg(flagName) {
  const index = argv.indexOf(flagName);
  if (index === -1) {
    return null;
  }
  return argv[index + 1] ?? null;
}

function resolveUpstreamRepoRoot() {
  const explicit = parseArg("--source-repo") ?? process.env.LIDLTOOL_UPSTREAM_REPO ?? null;
  if (explicit) {
    return resolve(explicit);
  }

  const siblingCandidates = [
    resolve(desktopDir, "..", "lidl-receipts-cli"),
    resolve(desktopDir, "..", "..", "lidl-receipts-cli"),
    resolve(desktopDir, "..", "lidltool-server"),
    resolve(desktopDir, "..", "..", "lidltool-server"),
    resolve(desktopDir, "..", "lidltool-main"),
    resolve(desktopDir, "..", "..", "lidltool-main")
  ];
  for (const candidate of siblingCandidates) {
    if (existsSync(resolve(candidate, "apps", "android-harness"))) {
      return candidate;
    }
  }

  throw new Error(
    [
      "Mobile vendor sync requires an upstream checkout.",
      "Pass --source-repo /path/to/lidl-receipts-cli or set LIDLTOOL_UPSTREAM_REPO.",
      "Expected upstream contents: apps/android-harness and apps/ios-harness."
    ].join(" ")
  );
}

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

function loadManifest() {
  if (!existsSync(manifestPath)) {
    throw new Error(`Mobile vendor manifest not found at ${manifestPath}`);
  }
  return JSON.parse(readFileSync(manifestPath, "utf-8"));
}

const sourceRepoRoot = resolveUpstreamRepoRoot();
const manifest = loadManifest();
const excludedNames = new Set(manifest.excludeNames ?? []);

mkdirSync(vendorRoot, { recursive: true });

for (const app of manifest.apps ?? []) {
  const source = resolve(sourceRepoRoot, app.source);
  const dest = resolve(vendorRoot, app.dest);
  if (!existsSync(source)) {
    throw new Error(`Required mobile source not found: ${source}`);
  }
  resetDir(dest);
  copyTreeFiltered(source, dest, excludedNames);
  console.log(`Vendored mobile app -> ${dest}`);
}

console.log(`Upstream source repo -> ${sourceRepoRoot}`);
