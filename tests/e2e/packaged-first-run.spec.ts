import { expect, test } from "@playwright/test";

import {
  ensureAuthenticated,
  ensureVisibleWindowCount,
  launchDesktopApp,
  openMainApp
} from "./helpers/desktop-app";

test.describe("packaged desktop first run", () => {
  test.skip(!process.env.LIDLTOOL_DESKTOP_EXECUTABLE, "Set LIDLTOOL_DESKTOP_EXECUTABLE to the packaged app binary.");

  test("opens control center first, reaches fresh setup, creates admin, and keeps a visible window alive", async () => {
    test.setTimeout(180_000);

    const session = await launchDesktopApp();
    const { electronApp, page, close } = session;

    try {
      await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
      await ensureVisibleWindowCount(electronApp, 1);

      await openMainApp(page);
      await expect
        .poll(() => new URL(page.url()).pathname, { timeout: 90_000 })
        .toBe("/setup");

      await ensureAuthenticated(page, {
        username: "packaged-admin",
        password: "packaged-admin-pass"
      });

      await expect(page).toHaveURL(/:\/\/(?:127\.0\.0\.1|localhost):\d+\/?(?:[#?].*)?$/);
      await expect(page.locator("#main-content").getByRole("heading", { name: "Your finance overview" }).first()).toBeVisible();
      await ensureVisibleWindowCount(electronApp, 1);

      await page.waitForTimeout(3_000);
      await ensureVisibleWindowCount(electronApp, 1);
    } finally {
      await close();
    }
  });
});
