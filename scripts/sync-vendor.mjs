import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const vendorDir = resolve(desktopDir, "vendor");
const overridesDir = resolve(desktopDir, "overrides");
const argv = process.argv.slice(2);
const frontendDest = resolve(vendorDir, "frontend");
const frontendOverrides = resolve(overridesDir, "frontend");
const backendDest = resolve(vendorDir, "backend");
const vendorManifestPath = resolve(vendorDir, "vendor-manifest.json");

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
    resolve(desktopDir, "..", "lidltool-server"),
    resolve(desktopDir, "..", "lidltool-main")
  ];
  for (const candidate of siblingCandidates) {
    if (existsSync(resolve(candidate, "frontend")) && existsSync(resolve(candidate, "src"))) {
      return candidate;
    }
  }

  throw new Error(
    [
      "Desktop vendor sync requires an upstream checkout.",
      "Pass --source-repo /path/to/lidl-receipts-cli or set LIDLTOOL_UPSTREAM_REPO.",
      "Expected upstream contents: frontend/, src/, pyproject.toml, alembic.ini."
    ].join(" ")
  );
}

const sourceRepoRoot = resolveUpstreamRepoRoot();
const frontendSource = resolve(sourceRepoRoot, "frontend");

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

function loadFrontendOverrides() {
  if (!existsSync(vendorManifestPath)) {
    throw new Error(`Desktop vendor manifest not found at ${vendorManifestPath}`);
  }
  const manifest = JSON.parse(readFileSync(vendorManifestPath, "utf-8"));
  const frontend = manifest.frontend ?? {};
  return {
    src: [
      ...(frontend.runtimeOverrideFiles ?? []),
      ...(frontend.testOverrideFiles ?? [])
    ],
    root: frontend.rootOverrideFiles ?? []
  };
}

function applyDeclaredOverrides(sourceRoot, destRoot, relativePaths, sourceSubdir = "src") {
  for (const relativePath of relativePaths) {
    const from = resolve(sourceRoot, sourceSubdir, relativePath);
    if (!existsSync(from)) {
      throw new Error(`Declared desktop override not found: ${from}`);
    }
    const to = resolve(destRoot, sourceSubdir, relativePath);
    mkdirSync(dirname(to), { recursive: true });
    cpSync(from, to, { force: true, recursive: true });
  }
}

if (!existsSync(frontendSource)) {
  throw new Error(`Main frontend source not found at ${frontendSource}`);
}

mkdirSync(vendorDir, { recursive: true });
const frontendOverridesToApply = loadFrontendOverrides();

resetDir(frontendDest);
copyTreeFiltered(
  frontendSource,
  frontendDest,
  new Set(["node_modules", "dist", ".vite", ".qa-screenshots", "playwright-report", "test-results"])
);
if (existsSync(frontendOverrides)) {
  applyDeclaredOverrides(frontendOverrides, frontendDest, frontendOverridesToApply.src);
  applyDeclaredOverrides(frontendOverrides, frontendDest, frontendOverridesToApply.root, ".");
}

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
if (existsSync(frontendOverrides)) {
  console.log(`Applied frontend overrides -> ${frontendOverrides}`);
}
console.log(`Vendored backend -> ${backendDest}`);
console.log(`Upstream source repo -> ${sourceRepoRoot}`);
