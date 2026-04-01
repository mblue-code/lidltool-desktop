import { expect, test } from "@playwright/test";
import { launchDesktopApp } from "./helpers/desktop-app";
import { startTrustedPackFixtureServer } from "./helpers/plugin-pack-fixtures";

test("installs, updates, toggles, and removes a trusted receipt pack through the control center", async () => {
  test.setTimeout(300_000);

  const fixtureServer = await startTrustedPackFixtureServer();
  const session = await launchDesktopApp({
    frontendDistMode: "missing",
    envOverrides: {
      LIDLTOOL_DESKTOP_TRUSTED_CATALOG_PATH: fixtureServer.trustedCatalogPath,
      LIDLTOOL_DESKTOP_TRUST_ROOTS_PATH: fixtureServer.trustRootsPath
    }
  });
  const { page, close } = session;

  const installedPacksCard = page.locator("article.card").filter({
    has: page.getByRole("heading", { name: "Installed packs on this desktop" })
  });
  const trustedCatalogCard = page.locator("article.card").filter({
    has: page.getByRole("heading", { name: "Edition-aware optional packs" })
  });

  try {
    await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
    await expect(trustedCatalogCard.locator(".status-chip").first()).toContainText("Trusted");
    await expect(installedPacksCard.getByText("No local receipt packs installed yet.")).toBeVisible();
    await expect(trustedCatalogCard.getByRole("heading", { name: "Fixture Receipt" })).toBeVisible();
    await expect(trustedCatalogCard.getByRole("button", { name: "Install trusted pack" })).toBeVisible();

    await trustedCatalogCard.getByRole("button", { name: "Install trusted pack" }).click({ force: true });
    await expect(installedPacksCard.getByRole("heading", { name: "Fixture Receipt" })).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByText("community.fixture_receipt_de · 1.0.0")).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("Installed trusted pack Fixture Receipt 1.0.0.")).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByText("1 installed / 0 enabled")).toBeVisible({ timeout: 90_000 });

    await installedPacksCard.getByRole("button", { name: "Enable pack" }).click({ force: true });
    await expect(installedPacksCard.getByText("1 installed / 1 enabled")).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByRole("button", { name: "Disable pack" })).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByText("No enabled external packs")).toHaveCount(0);

    fixtureServer.setCatalogVersion("1.1.0");
    await installedPacksCard.getByRole("button", { name: "Rescan pack state" }).click();
    await expect(installedPacksCard.getByText("Trusted update available: 1.1.0")).toBeVisible({ timeout: 90_000 });
    await expect(trustedCatalogCard.getByRole("button", { name: "Install trusted update" })).toBeVisible({
      timeout: 90_000
    });

    const installTrustedUpdateButton = trustedCatalogCard.getByRole("button", { name: "Install trusted update" });
    await expect(installTrustedUpdateButton).toBeEnabled({ timeout: 90_000 });
    await installTrustedUpdateButton.click();
    await expect(installedPacksCard.getByText("community.fixture_receipt_de · 1.1.0")).toBeVisible({ timeout: 90_000 });

    await installedPacksCard.getByRole("button", { name: "Disable pack" }).click({ force: true });
    await expect(installedPacksCard.getByText("1 installed / 0 enabled")).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByRole("button", { name: "Enable pack" })).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByText("No enabled external packs")).toBeVisible();

    await installedPacksCard.getByRole("button", { name: "Remove pack" }).click({ force: true });
    await expect(installedPacksCard.getByText("No local receipt packs installed yet.")).toBeVisible({ timeout: 90_000 });
  } finally {
    await close();
    await fixtureServer.close();
  }
});
