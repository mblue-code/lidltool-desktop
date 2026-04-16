import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { clickNavLink, ensureAuthenticated, launchDesktopApp, openAdvancedTools, openMainApp } from "./helpers/desktop-app";

test.describe("desktop full app smoke", () => {
  test("returns to the control center from auth and signed-in flows", async () => {
    const session = await launchDesktopApp();
    const { page, close } = session;

    try {
      await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
      await openMainApp(page);
      await page.getByRole("button", { name: "Open control center" }).click();
      await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();

      await openMainApp(page);
      await ensureAuthenticated(page);
      await page.getByRole("button", { name: "Preferences" }).click();
      await page.getByRole("menuitem", { name: "Open control center" }).click();
      await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
    } finally {
      await close();
    }
  });

  test("boots through setup, creates a manual transaction, and traverses supported routes", async () => {
    const session = await launchDesktopApp();
    const { page, close } = session;

    try {
      await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
      await openMainApp(page);
      await ensureAuthenticated(page);

      await clickNavLink(page, "Receipts", "/receipts", "Receipts");
      await clickNavLink(page, "Add Receipt", "/add", "Add Receipt");

      await page.getByRole("tab", { name: "Manual" }).click();
      await page.getByLabel("Merchant").fill("Desktop E2E Market");
      await page.getByLabel("Total amount (EUR)").fill("12.34");
      await page.getByLabel("Item (optional)").fill("Apples");
      await page.getByLabel("Item amount (EUR) (optional)").fill("3.99");
      await page.getByRole("button", { name: "Add one-off purchase" }).click();

      await expect(page.getByText("Transaction saved")).toBeVisible();
      await page.getByRole("link", { name: "View receipts" }).click();
      await expect(page).toHaveURL(/\/receipts(?:$|[?#])/);
      await page.getByRole("link", { name: "Details" }).first().click();
      await expect(page).toHaveURL(/\/transactions\/[^/?#]+(?:$|[?#])/);
      await expect(page.getByText(/Transaction Detail #/)).toBeVisible();
      await expect(page.getByText("Desktop E2E Market").first()).toBeVisible();

      await page.locator("#main-content").getByRole("link", { name: "Receipts" }).first().click();
      await expect(page).toHaveURL(/\/receipts(?:$|[?#])/);
      await expect(page.getByRole("cell", { name: "Desktop E2E Market" }).first()).toBeVisible();

      await clickNavLink(page, "Connectors", "/connectors", "Connectors");

      await clickNavLink(page, "Budget", "/budget", "Budget");
      await clickNavLink(page, "Bills", "/bills", "Recurring Bills");

      await openAdvancedTools(page);
      await clickNavLink(page, "Products", "/products", "Products");
      await clickNavLink(page, "Comparisons", "/compare", "Comparisons");
      await clickNavLink(page, "Patterns", "/patterns", "Patterns");
      await clickNavLink(page, "Explore", "/explore", "Explore");
      await clickNavLink(page, "Sources", "/sources", "Sources");
      await clickNavLink(page, "Chat", "/chat", "Chat");
      await clickNavLink(page, "AI Assistant", "/settings/ai", "AI Assistant");
      await clickNavLink(page, "Users", "/settings/users");
      await expect(page.getByText("Users & Agent Keys")).toBeVisible();

      await clickNavLink(page, "Add Receipt", "/add", "Add Receipt");
      await page.getByRole("link", { name: "Open upload flow" }).click();
      await expect(page).toHaveURL(/\/imports\/ocr(?:$|[?#])/);
      await expect(page.getByRole("heading", { name: "OCR Import" })).toBeVisible();

      await page.goto(new URL("/add", page.url()).toString());
      await page.getByRole("link", { name: "Open review queue" }).click();
      await expect(page).toHaveURL(/\/review-queue(?:$|[?#])/);
      await expect(page.getByRole("heading", { name: "Review Queue" })).toBeVisible();
    } finally {
      await close();
    }
  });

  test("redirects unsupported direct routes back to the desktop-safe overview shell", async () => {
    const session = await launchDesktopApp();
    const { page, close } = session;

    try {
      await openMainApp(page);
      await ensureAuthenticated(page);

      for (const blockedPath of ["/offers", "/automations", "/automation-inbox", "/reliability"]) {
        await page.goto(new URL(`${blockedPath}?source=e2e#blocked`, page.url()).toString());
        await expect(page).toHaveURL(/\/\?source=e2e#blocked$/);
        await expect(page.getByRole("heading", { name: "Not available in desktop" })).toBeVisible();
        await expect(
          page.getByText(/Use the local analysis, backup, or connector pages instead|persistent scheduler host|operator-facing routes/)
        ).toBeVisible();
        await page.getByRole("button", { name: "Dismiss notice" }).click();
        await expect(page.getByRole("heading", { name: "Not available in desktop" })).toHaveCount(0);
      }

      await page.goto(new URL("/transactions", page.url()).toString());
      await expect(page).toHaveURL(/\/receipts(?:$|[?#])/);
    } finally {
      await close();
    }
  });

  test("runs backup from the users settings flow", async () => {
    const session = await launchDesktopApp();
    const { page, profileRoot, close } = session;

    try {
      await openMainApp(page);
      await ensureAuthenticated(page);
      await openAdvancedTools(page);
      await clickNavLink(page, "Users", "/settings/users");

      const backupDir = join(profileRoot, "users-settings-backup");
      await page.getByLabel("Backup output directory").fill(backupDir);
      await page.getByRole("button", { name: "Create backup" }).click();
      await expect.poll(() => existsSync(join(backupDir, "backup-manifest.json"))).toBe(true);
      await page.getByLabel("Backup directory").fill(backupDir);
      await expect(page.getByRole("button", { name: "Restore backup" })).toBeVisible();
    } finally {
      await close();
    }
  });
});
