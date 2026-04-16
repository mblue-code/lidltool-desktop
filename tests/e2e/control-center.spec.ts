import { expect, test } from "@playwright/test";
import { launchDesktopApp } from "./helpers/desktop-app";

test("falls back to the control center when the main frontend bundle is unavailable", async () => {
  const session = await launchDesktopApp({ frontendDistMode: "missing" });
  const { page, close } = session;
  const controlCenterCard = page.locator("article.card").filter({
    has: page.getByRole("heading", { name: "Use LidlTool on this computer" })
  });

  try {
    await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
    await expect(page.getByText("Control center only")).toBeVisible();
    await expect(controlCenterCard.locator(".status-chip").first()).toContainText(/Stopped|gestoppt/);
    await expect(page.getByRole("button", { name: "Open main app" }).first()).toBeDisabled();

    await page.getByRole("button", { name: "Start local service" }).first().click();
    await expect(controlCenterCard.locator(".status-chip").first()).toContainText(/Running|aktiv/);
    await expect(page.getByRole("link", { name: "Manage connectors", exact: true })).toBeVisible();
    await expect(page.locator('a[href="#safety"]').first()).toBeVisible();

    await page.getByRole("button", { name: "Stop local service" }).first().click();
    await expect(controlCenterCard.locator(".status-chip").first()).toContainText(/Stopped|gestoppt/);
  } finally {
    await close();
  }
});
