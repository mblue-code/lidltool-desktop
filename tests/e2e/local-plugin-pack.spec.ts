import { expect, test } from "@playwright/test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ReceiptPluginPackManager,
  type ValidatedManifestSnapshot
} from "../../src/main/plugins/receipt-plugin-packs";
import { clickNavLink, ensureAuthenticated, launchDesktopApp, openMainApp } from "./helpers/desktop-app";

async function validateManifestFixture(manifestPath: string): Promise<ValidatedManifestSnapshot> {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf-8")) as Record<string, any>;
  const supportedHostKinds = Array.isArray(manifest.compatibility?.supported_host_kinds)
    ? manifest.compatibility.supported_host_kinds.map((item: unknown) => String(item))
    : [];
  return {
    pluginId: String(manifest.plugin_id),
    sourceId: String(manifest.source_id),
    displayName: String(manifest.display_name),
    pluginVersion: String(manifest.plugin_version),
    pluginFamily: "receipt",
    runtimeKind: String(manifest.runtime_kind),
    pluginOrigin: String(manifest.plugin_origin),
    trustClass: String(manifest.trust_class) as ValidatedManifestSnapshot["trustClass"],
    entrypoint: typeof manifest.entrypoint === "string" ? manifest.entrypoint : null,
    supportedHostKinds,
    minCoreVersion:
      typeof manifest.compatibility?.min_core_version === "string" ? manifest.compatibility.min_core_version : null,
    maxCoreVersion:
      typeof manifest.compatibility?.max_core_version === "string" ? manifest.compatibility.max_core_version : null,
    compatibilityStatus: supportedHostKinds.includes("electron") ? "compatible" : "incompatible",
    compatibilityReason: supportedHostKinds.includes("electron") ? null : "host_kind_not_supported",
    onboarding:
      manifest.onboarding && typeof manifest.onboarding === "object"
        ? {
            title: typeof manifest.onboarding.title === "string" ? manifest.onboarding.title : null,
            summary: typeof manifest.onboarding.summary === "string" ? manifest.onboarding.summary : null,
            expectedSpeed:
              typeof manifest.onboarding.expected_speed === "string"
                ? manifest.onboarding.expected_speed
                : null,
            caution: typeof manifest.onboarding.caution === "string" ? manifest.onboarding.caution : null,
            steps: Array.isArray(manifest.onboarding.steps)
              ? manifest.onboarding.steps.flatMap((step: unknown) => {
                  if (!step || typeof step !== "object") {
                    return [];
                  }
                  const candidate = step as Record<string, unknown>;
                  if (typeof candidate.title !== "string" || typeof candidate.description !== "string") {
                    return [];
                  }
                  return [{ title: candidate.title, description: candidate.description }];
                })
              : []
          }
        : null
  };
}

test("shows a locally built Kaufland receipt pack in a fresh desktop profile", async () => {
  test.setTimeout(300_000);

  const session = await launchDesktopApp({ frontendDistMode: "missing" });
  const { page, profileRoot, close } = session;
  const pluginStorageDir = join(profileRoot, "electron-user-data", "plugins", "receipt-packs");
  const packOutputDir = join(profileRoot, "kaufland-pack");
  const pluginDir = fileURLToPath(new URL("../../../../plugins/kaufland_de/", import.meta.url));
  const manager = new ReceiptPluginPackManager({
    rootDir: pluginStorageDir,
    validateManifest: validateManifestFixture
  });

  try {
    const build = spawnSync(
      "python3",
      [join(pluginDir, "build_desktop_pack.py"), "--output-dir", packOutputDir],
      { encoding: "utf-8" }
    );
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.pack.sourceId, "kaufland_de");

    const packsSection = page.locator("section.card").filter({
      has: page.getByRole("heading", { name: "Stores and packs on this desktop" })
    });
    const installedPacksCard = packsSection.locator("article.subpanel").filter({
      has: page.getByRole("heading", { name: "Installed on this computer" })
    });

    await expect(page.getByRole("heading", { name: "Local receipt sync, review, export, and backup." })).toBeVisible();
    await packsSection.getByRole("button", { name: "Refresh connector list" }).click();
    await expect(installedPacksCard.getByRole("heading", { name: "Kaufland" })).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByText("local.kaufland_de · 0.1.0")).toBeVisible({ timeout: 90_000 });
    await expect(packsSection.getByText("1 installed / 0 enabled")).toBeVisible({ timeout: 90_000 });

    await installedPacksCard.getByRole("button", { name: "Enable pack" }).click({ force: true });
    await expect(packsSection.getByText("1 installed / 1 enabled")).toBeVisible({ timeout: 90_000 });
    await expect(installedPacksCard.getByRole("button", { name: "Disable pack" })).toBeVisible({ timeout: 90_000 });

    await installedPacksCard.getByRole("button", { name: "Remove pack" }).click({ force: true });
    await expect(installedPacksCard.getByText("No local receipt packs installed yet.")).toBeVisible({
      timeout: 90_000
    });
  } finally {
    rmSync(packOutputDir, { recursive: true, force: true });
    await close();
  }
});

test("enables a freshly imported Kaufland pack in the full Connectors flow and keeps Rossmann hidden", async () => {
  test.setTimeout(300_000);

  const session = await launchDesktopApp();
  const { page, profileRoot, close } = session;
  const pluginStorageDir = join(profileRoot, "electron-user-data", "plugins", "receipt-packs");
  const packOutputDir = join(profileRoot, "kaufland-pack");
  const pluginDir = fileURLToPath(new URL("../../../../plugins/kaufland_de/", import.meta.url));
  const manager = new ReceiptPluginPackManager({
    rootDir: pluginStorageDir,
    validateManifest: validateManifestFixture
  });

  try {
    await openMainApp(page);
    await ensureAuthenticated(page);
    await clickNavLink(page, "Connectors", "/connectors", "Connectors");

    const build = spawnSync(
      "python3",
      [join(pluginDir, "build_desktop_pack.py"), "--output-dir", packOutputDir],
      { encoding: "utf-8" }
    );
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.pack.sourceId, "kaufland_de");
    assert.equal(install.pack.status, "disabled");

    await page.getByRole("button", { name: "Refresh list" }).click();

    await expect(page.getByRole("heading", { name: "Finish adding connectors" })).toBeVisible();
    await expect(page.getByText("Kaufland", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Enable connector" })).toBeVisible();
    await expect(page.getByText("Rossmann")).toHaveCount(0);

    await page.getByRole("button", { name: "Enable connector" }).click();

    await expect(page.getByRole("heading", { name: "Finish adding connectors" })).toHaveCount(0, {
      timeout: 90_000
    });
    const kauflandCard = page.locator("div").filter({
      has: page.getByText("Kaufland", { exact: true }),
      has: page.getByRole("button", { name: "Set up" })
    }).last();

    await expect(page.getByText("Kaufland", { exact: true }).last()).toBeVisible({ timeout: 90_000 });
    await expect(kauflandCard.getByRole("button", { name: "Set up" })).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText("Rossmann")).toHaveCount(0);
  } finally {
    rmSync(packOutputDir, { recursive: true, force: true });
    await close();
  }
});
