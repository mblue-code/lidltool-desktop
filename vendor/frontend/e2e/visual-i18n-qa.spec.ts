import fs from "node:fs/promises";
import path from "node:path";

import { type Page, test } from "@playwright/test";

type RouteTarget = {
  slug: string;
  path: string;
};

const BASE_ROUTES: RouteTarget[] = [
  { slug: "overview", path: "/" },
  { slug: "explore", path: "/explore" },
  { slug: "products", path: "/products" },
  { slug: "comparisons", path: "/compare" },
  { slug: "data-quality", path: "/quality" },
  { slug: "connectors", path: "/connectors" },
  { slug: "sources", path: "/sources" },
  { slug: "manual-import", path: "/imports/manual" },
  { slug: "ocr-import", path: "/imports/ocr" },
  { slug: "budget", path: "/budget" },
  { slug: "bills", path: "/bills" },
  { slug: "patterns", path: "/patterns" },
  { slug: "receipts", path: "/receipts" },
  { slug: "documents-upload", path: "/documents/upload" },
  { slug: "review-queue", path: "/review-queue" },
  { slug: "automations", path: "/automations" },
  { slug: "automation-inbox", path: "/automation-inbox" },
  { slug: "chat", path: "/chat" },
  { slug: "reliability", path: "/reliability" },
  { slug: "settings-ai", path: "/settings/ai" },
  { slug: "settings-users", path: "/settings/users" }
];

const PUBLIC_ROUTES: RouteTarget[] = [
  { slug: "login", path: "/login" },
  { slug: "setup", path: "/setup" }
];

type SupportedLocale = "en" | "de";

async function login(page: Page): Promise<void> {
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("admin123");
  await page.locator("button[type='submit']").click();
  await page.waitForURL("**/", { timeout: 20_000 });
}

async function seedData(page: Page): Promise<string | null> {
  const purchasedAt = new Date().toISOString();
  const receiptResponse = await page.request.post("/api/v1/transactions/manual", {
    data: {
      purchased_at: purchasedAt,
      merchant_name: "Lidl QA Store",
      total_gross_cents: 1299,
      discount_total_cents: 120,
      source_id: "manual_import",
      source_display_name: "Manual Import",
      source_transaction_id: `qa-${Date.now()}`,
      currency: "EUR",
      items: [
        {
          name: "Vollmilch 3.5%",
          line_total_cents: 179,
          qty: 1,
          unit: "pcs",
          category: "dairy"
        },
        {
          name: "Brot",
          line_total_cents: 249,
          qty: 1,
          unit: "pcs",
          category: "bakery"
        }
      ]
    }
  });

  await page.request.post("/api/v1/recurring-bills", {
    data: {
      name: "Internet",
      merchant_canonical: "ISP",
      category: "utilities",
      frequency: "monthly",
      interval_value: 1,
      amount_cents: 4999,
      currency: "EUR",
      amount_tolerance_pct: 0.1,
      anchor_date: "2026-02-01",
      active: true
    },
    failOnStatusCode: false
  });

  await page.request.post("/api/v1/automations", {
    data: {
      name: "Weekly Summary QA",
      rule_type: "weekly_summary",
      enabled: true,
      trigger_config: {
        schedule: {
          interval_seconds: 3600
        }
      },
      action_config: {
        months_back: 3,
        include_breakdown: true
      },
      actor_id: "visual-qa"
    },
    failOnStatusCode: false
  });

  if (!receiptResponse.ok()) {
    return null;
  }

  const payload = (await receiptResponse.json()) as {
    result?: {
      transaction_id?: string;
    };
  };
  return payload.result?.transaction_id ?? null;
}

async function captureRoutes(
  page: Page,
  locale: SupportedLocale,
  routes: RouteTarget[]
): Promise<void> {
  const outputDir = path.resolve(process.cwd(), ".qa-screenshots", locale);
  await fs.mkdir(outputDir, { recursive: true });

  for (const route of routes) {
    await page.goto(route.path, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => undefined);
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(outputDir, `${route.slug}.png`),
      fullPage: true
    });
  }
}

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

for (const locale of ["en", "de"] as const) {
  test(`visual i18n qa screenshots (${locale})`, async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 1512, height: 982 },
      locale: locale === "de" ? "de-DE" : "en-US"
    });
    await context.addInitScript((currentLocale: SupportedLocale) => {
      window.localStorage.setItem("app.locale", currentLocale);
    }, locale);

    const page = await context.newPage();
    await login(page);
    const transactionId = await seedData(page);
    const protectedRoutes = transactionId
      ? [...BASE_ROUTES, { slug: "transaction-detail", path: `/transactions/${transactionId}` }]
      : BASE_ROUTES;

    await captureRoutes(page, locale, PUBLIC_ROUTES);
    await captureRoutes(page, locale, protectedRoutes);

    await context.close();
  });
}
