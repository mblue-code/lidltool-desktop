import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(process.env.LIDLTOOL_DESKTOP_DIR?.trim() || resolve(__dirname, ".."));
const frontendSrcDir = resolve(desktopDir, "vendor", "frontend", "src");
const frontendOverridesSrcDir = resolve(desktopDir, "overrides", "frontend", "src");
const vendorManifestPath = resolve(desktopDir, "vendor", "vendor-manifest.json");

function loadVendorManifest() {
  if (!existsSync(vendorManifestPath)) {
    throw new Error(`Desktop vendor manifest not found: ${vendorManifestPath}`);
  }

  const manifest = JSON.parse(readFileSync(vendorManifestPath, "utf-8"));
  if (!manifest.frontend || typeof manifest.frontend !== "object") {
    throw new Error(`Desktop vendor manifest is missing the "frontend" section: ${vendorManifestPath}`);
  }

  return manifest.frontend;
}

function readFrontendFile(relativePath) {
  const fullPath = resolve(frontendSrcDir, relativePath);
  return readFileSync(fullPath, "utf-8");
}

function collectRelativeFiles(rootDir) {
  if (!existsSync(rootDir)) {
    return [];
  }

  const files = [];

  function visit(currentDir) {
    for (const entry of readdirSync(currentDir)) {
      const fullPath = resolve(currentDir, entry);
      const stats = statSync(fullPath);
      if (stats.isDirectory()) {
        visit(fullPath);
        continue;
      }
      files.push(relative(rootDir, fullPath));
    }
  }

  visit(rootDir);
  return files.sort();
}

function validateRequiredFiles(errors, requiredFiles) {
  for (const relativePath of requiredFiles) {
    const fullPath = resolve(frontendSrcDir, relativePath);
    if (!existsSync(fullPath)) {
      errors.push(`Missing required vendored frontend file: ${relativePath}`);
    }
  }
}

function validateDeclaredOverrides(errors, runtimeOverrideFiles, testOverrideFiles) {
  const declaredOverrides = new Set([...runtimeOverrideFiles, ...testOverrideFiles]);
  for (const relativePath of declaredOverrides) {
    const fullPath = resolve(frontendOverridesSrcDir, relativePath);
    if (!existsSync(fullPath)) {
      errors.push(`Missing declared desktop frontend override: ${relativePath}`);
    }
  }

  const actualOverrides = collectRelativeFiles(frontendOverridesSrcDir);
  for (const relativePath of actualOverrides) {
    if (!declaredOverrides.has(relativePath)) {
      errors.push(`Undeclared desktop frontend override file: ${relativePath}`);
    }
  }
}

function validateLoaderKeys(errors, requiredLoaderKeys) {
  const pageLoadersSource = readFrontendFile("app/page-loaders.ts");
  for (const key of requiredLoaderKeys) {
    const loaderPattern = new RegExp(`\\b${key}\\s*:\\s*\\(\\)\\s*=>\\s*import\\(`);
    if (!loaderPattern.test(pageLoadersSource)) {
      errors.push(`Missing required page loader "${key}" in src/app/page-loaders.ts`);
    }
  }
}

function validateMainRouteReferences(errors) {
  const mainSource = readFrontendFile("main.tsx");
  const pageLoadersSource = readFrontendFile("app/page-loaders.ts");
  const loaderMatches = [...mainSource.matchAll(/pageLoaders\.(\w+)\(\)/g)];

  for (const [, key] of loaderMatches) {
    const loaderPattern = new RegExp(`\\b${key}\\s*:\\s*\\(\\)\\s*=>\\s*import\\(`);
    if (!loaderPattern.test(pageLoadersSource)) {
      errors.push(`src/main.tsx references pageLoaders.${key}(), but that loader is missing in src/app/page-loaders.ts`);
    }
  }
}

function validateI18nKeys(errors, requiredTranslationKeys) {
  const messagesSource = readFrontendFile("i18n/messages.ts");
  for (const key of requiredTranslationKeys) {
    const keyPattern = new RegExp(`["']${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']`);
    if (!keyPattern.test(messagesSource)) {
      errors.push(`Missing required translation key "${key}" in src/i18n/messages.ts`);
    }
  }
}

function main() {
  const frontendManifest = loadVendorManifest();
  const errors = [];

  validateDeclaredOverrides(
    errors,
    frontendManifest.runtimeOverrideFiles ?? [],
    frontendManifest.testOverrideFiles ?? []
  );
  validateRequiredFiles(errors, frontendManifest.requiredFiles ?? []);

  if (errors.length === 0) {
    validateLoaderKeys(errors, frontendManifest.requiredLoaderKeys ?? []);
    validateMainRouteReferences(errors);
    validateI18nKeys(errors, frontendManifest.requiredTranslationKeys ?? []);
  }

  if (errors.length > 0) {
    console.error("Desktop vendored frontend validation failed:");
    for (const error of errors) {
      console.error(`- ${error}`);
    }
    process.exit(1);
  }

  console.log("Desktop vendored frontend validation passed.");
}

main();
