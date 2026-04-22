import { expect, test } from "@playwright/test";

import {
  ensureAuthenticated,
  ensureVisibleWindowCount,
  launchDesktopApp
} from "./helpers/desktop-app";

test.describe("packaged desktop first run", () => {
  test.skip(!process.env.LIDLTOOL_DESKTOP_EXECUTABLE, "Set LIDLTOOL_DESKTOP_EXECUTABLE to the packaged app binary.");

  test("boots straight into the finance app flow, reaches fresh setup, creates admin, and keeps a visible window alive", async () => {
    test.setTimeout(180_000);

    const session = await launchDesktopApp();
    const { electronApp, page, close } = session;

    try {
      await expect
        .poll(() => new URL(page.url()).pathname, { timeout: 90_000 })
        .toMatch(/^\/(?:setup|login)?$/);
      await ensureVisibleWindowCount(electronApp, 1);

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
