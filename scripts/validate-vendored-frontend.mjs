import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const desktopDir = resolve(__dirname, "..");
const frontendSrcDir = resolve(desktopDir, "vendor", "frontend", "src");
const frontendOverridesSrcDir = resolve(desktopDir, "overrides", "frontend", "src");

const REQUIRED_FILES = [
  "api/goals.ts",
  "api/groceries.ts",
  "api/merchants.ts",
  "api/notifications.ts",
  "api/reports.ts",
  "api/dashboard.ts",
  "api/documents.ts",
  "api/systemBackup.ts",
  "app/date-range-context.tsx",
  "app/page-loaders.ts",
  "components/shared/AppShell.tsx",
  "i18n/messages.ts",
  "main.tsx",
  "pages/CashFlowPage.tsx",
  "pages/GoalsPage.tsx",
  "pages/GroceriesPage.tsx",
  "pages/MerchantsPage.tsx",
  "pages/ReportsPage.tsx",
  "pages/SettingsPage.tsx"
];

const REQUIRED_OVERRIDE_FILES = [
  "api/goals.ts",
  "api/groceries.ts",
  "api/merchants.ts",
  "api/notifications.ts",
  "api/reports.ts",
  "api/dashboard.ts",
  "api/documents.ts",
  "api/systemBackup.ts",
  "app/date-range-context.tsx",
  "app/page-loaders.ts",
  "app/providers.tsx",
  "components/shared/AppShell.tsx",
  "i18n/literals.de.json",
  "i18n/messages.ts",
  "lib/api-client.ts",
  "lib/backend-messages.ts",
  "lib/desktop-api.ts",
  "lib/desktop-capabilities.tsx",
  "lib/desktop-shell.ts",
  "main.tsx",
  "pages/AISettingsPage.tsx",
  "pages/BillsPage.tsx",
  "pages/BudgetPage.tsx",
  "pages/CashFlowPage.tsx",
  "pages/DashboardPage.tsx",
  "pages/DocumentsUploadPage.tsx",
  "pages/GoalsPage.tsx",
  "pages/GroceriesPage.tsx",
  "pages/MerchantsPage.tsx",
  "pages/ReportsPage.tsx",
  "pages/SettingsPage.tsx",
  "pages/TransactionsPage.tsx"
];

const REQUIRED_LOADER_KEYS = ["groceries", "cashFlow", "reports", "goals", "merchants", "settings"];
const REQUIRED_TRANSLATION_KEYS = [
  "nav.group.workspace",
  "nav.group.shortcuts",
  "nav.item.dashboard",
  "nav.item.transactions",
  "nav.item.groceries",
  "nav.item.cashFlow",
  "nav.item.reports",
  "nav.item.goals",
  "nav.item.merchants",
  "nav.item.settings",
  "app.sidebar.connectedMerchants",
  "app.sidebar.connectedMerchantsHint",
  "app.sidebar.connectedMerchantsEmpty",
  "app.sidebar.localData",
  "app.sidebar.localDataHint",
  "app.header.desktopSubtitle",
  "app.header.notifications"
];

function readFrontendFile(relativePath) {
  const fullPath = resolve(frontendSrcDir, relativePath);
  return readFileSync(fullPath, "utf-8");
}

function validateRequiredFiles(errors) {
  for (const relativePath of REQUIRED_FILES) {
    const fullPath = resolve(frontendSrcDir, relativePath);
    if (!existsSync(fullPath)) {
      errors.push(`Missing required vendored frontend file: ${relativePath}`);
    }
  }
}

function validateRequiredOverrides(errors) {
  for (const relativePath of REQUIRED_OVERRIDE_FILES) {
    const fullPath = resolve(frontendOverridesSrcDir, relativePath);
    if (!existsSync(fullPath)) {
      errors.push(`Missing required desktop frontend override: ${relativePath}`);
    }
  }
}

function validateLoaderKeys(errors) {
  const pageLoadersSource = readFrontendFile("app/page-loaders.ts");
  for (const key of REQUIRED_LOADER_KEYS) {
    if (!pageLoadersSource.includes(`${key}: () => import(`)) {
      errors.push(`Missing required page loader "${key}" in src/app/page-loaders.ts`);
    }
  }
}

function validateMainRouteReferences(errors) {
  const mainSource = readFrontendFile("main.tsx");
  const pageLoadersSource = readFrontendFile("app/page-loaders.ts");
  const loaderMatches = [...mainSource.matchAll(/pageLoaders\.(\w+)\(\)/g)];

  for (const [, key] of loaderMatches) {
    if (!pageLoadersSource.includes(`${key}: () => import(`)) {
      errors.push(`src/main.tsx references pageLoaders.${key}(), but that loader is missing in src/app/page-loaders.ts`);
    }
  }
}

function validateI18nKeys(errors) {
  const messagesSource = readFrontendFile("i18n/messages.ts");
  for (const key of REQUIRED_TRANSLATION_KEYS) {
    if (!messagesSource.includes(`"${key}"`)) {
      errors.push(`Missing required translation key "${key}" in src/i18n/messages.ts`);
    }
  }
}

function main() {
  const errors = [];

  validateRequiredOverrides(errors);
  validateRequiredFiles(errors);

  if (errors.length === 0) {
    validateLoaderKeys(errors);
    validateMainRouteReferences(errors);
    validateI18nKeys(errors);
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
