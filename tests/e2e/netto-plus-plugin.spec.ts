import { expect, test } from "@playwright/test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
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

function writeNettoBundle(bundlePath: string): void {
  writeFileSync(
    bundlePath,
    JSON.stringify(
      {
        schema_version: "1",
        account: {
          email: "fixture.netto@example.com"
        },
        receipts: [
          {
            summary: {
              BonId: "8640333292129767634134",
              Filiale: {
                FilialNummer: "2459",
                Bezeichnung: "Calberlah-Windmühlenweg 2",
                Strasse: "Windmühlenweg 2",
                Plz: "38547",
                Ort: "Calberlah"
              },
              Bonsumme: 19.92,
              Einkaufsdatum: "2026-03-13T10:45:27.920+01:00",
              Url: "https://bon.netto-online.de/bon/v1/app/8640333292129767634134?key=fixture",
              PdfUrl: "https://bon.netto-online.de/bon/api/Bon/pdf?BonId=8640333292129767634134",
              Ersparnis: 5.99,
              Zahlungen: [{ Zahlmittel: "NettoApp", Betrag: 19.92 }]
            },
            pdf_text: [
              "*** eBon ***",
              "Netto",
              "Filiale 2459",
              "Windmühlenweg 2",
              "38547 Calberlah",
              "WWW.NETTO-ONLINE.DE",
              "EUR",
              "Favora Topa 4lg. 10x200BL 4,95 A",
              "GL Kochcreme sort. 250ml 0,89 B",
              "2 x 0,89",
              "GL Kochcreme sort. 250ml 1,78 B",
              "Clarkys Erdnussflips 200g 0,99 B",
              "GRATIS -0,99",
              "Speisemoehren 2kg VKE QS 1,00 B",
              "Zwiebel rot 1kg VKE 0,99 B",
              "Bio Champignon 250g 1,89 B",
              "Lauchzwiebel 0,79 B",
              "Haehnchen-Schenkel 1,1 kg 5,29 B",
              "Rabatt 30% -1,59",
              "0,329 kg 27,90 EUR/kg",
              "SB Entrecote ca.300g 9,18 B",
              "Einwegleergut 19% -0,25 A",
              "SUMME [11] 24,92",
              "5\u20ac Rabatt Warenkorb -5,00",
              "----------",
              "SUMME 19,92\u20ac",
              "Netto plus App EUR 19,92"
            ].join("\n")
          }
        ]
      },
      null,
      2
    ),
    "utf-8"
  );
}

function queryNettoSyncState(dbPath: string): string {
  const script = [
    "import json, sqlite3, sys",
    "db = sqlite3.connect(sys.argv[1])",
    "tx = db.execute(\"select source_id, source_transaction_id, total_gross_cents, discount_total_cents from transactions where source_id = 'netto_plus_de'\").fetchall()",
    "items = db.execute(\"select name, qty, unit, line_total_cents, category, is_deposit from transaction_items order by line_no asc\").fetchall()",
    "print(json.dumps({'tx': tx, 'items': items}))"
  ].join(";");
  const result = spawnSync("python3", ["-c", script, dbPath], { encoding: "utf-8" });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
}

test("imports, sets up, and syncs the Netto Plus desktop pack from a fresh profile", async () => {
  test.setTimeout(300_000);

  const session = await launchDesktopApp();
  const { page, profileRoot, close } = session;
  const pluginStorageDir = join(profileRoot, "electron-user-data", "plugins", "receipt-packs");
  const packOutputDir = join(profileRoot, "netto-pack");
  const bundlePath = join(profileRoot, "netto-session-bundle.json");
  const dbPath = join(profileRoot, "electron-user-data", "lidltool.sqlite");
  const pluginDir = fileURLToPath(new URL("../../../../plugins/netto_plus_de/", import.meta.url));
  const manager = new ReceiptPluginPackManager({
    rootDir: pluginStorageDir,
    validateManifest: validateManifestFixture
  });

  try {
    writeNettoBundle(bundlePath);

    const build = spawnSync(
      "python3",
      [join(pluginDir, "build_desktop_pack.py"), "--output-dir", packOutputDir],
      { encoding: "utf-8" }
    );
    assert.equal(build.status, 0, build.stderr || build.stdout);
    const packPath = build.stdout.trim().split(/\r?\n/).at(-1);
    assert.ok(packPath);

    const install = await manager.installFromFile(packPath);
    assert.equal(install.pack.sourceId, "netto_plus_de");
    assert.equal(install.pack.status, "disabled");

    await openMainApp(page);
    await ensureAuthenticated(page);
    await clickNavLink(page, "Connectors", "/connectors", "Connectors");
    await page.getByRole("button", { name: "Refresh list" }).click();

    await expect(page.getByRole("heading", { name: "Finish adding connectors" })).toBeVisible();
    await expect(page.getByText("Netto Plus", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Enable connector" }).click();

    const nettoCard = page
      .getByText("Netto Plus", { exact: true })
      .locator("xpath=ancestor::*[contains(@class,'rounded-xl')][1]");
    await expect(nettoCard.getByRole("button", { name: "Set up" })).toBeVisible({ timeout: 90_000 });
    await nettoCard.getByRole("button", { name: "Set up" }).click();

    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByLabel("Netto Plus session bundle").fill(bundlePath);
    await page.getByRole("button", { name: "Save and continue" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 90_000 });

    await expect(nettoCard.getByRole("button", { name: "Import receipts" })).toBeVisible({ timeout: 90_000 });
    await nettoCard.getByRole("button", { name: "Import receipts" }).click();

    await expect.poll(
      () => {
        const raw = queryNettoSyncState(dbPath);
        const payload = JSON.parse(raw) as {
          tx: Array<[string, string, number, number]>;
          items: Array<[string, number, string, number, string | null, number]>;
        };
        const entree = payload.items.find(([name]) => name === "SB Entrecote ca.300g");
        const deposit = payload.items.find(([name]) => name === "Einwegleergut 19%");
        return JSON.stringify({
          tx: payload.tx,
          entree,
          deposit,
          itemCount: payload.items.length
        });
      },
      { timeout: 90_000, intervals: [1_000, 2_000, 3_000] }
    ).toBe(
      JSON.stringify({
        tx: [["netto_plus_de", "8640333292129767634134", 1992, 599]],
        entree: ["SB Entrecote ca.300g", 0.329, "kg", 918, "other", 0],
        deposit: ["Einwegleergut 19%", 1, "pcs", -25, "deposit", 1],
        itemCount: 10
      })
    );

    await clickNavLink(page, "Receipts", "/receipts", "Receipts");
    const receiptRow = page
      .getByRole("row")
      .filter({ has: page.getByRole("cell", { name: "Netto Plus - Calberlah-Windmühlenweg 2" }) })
      .first();
    await expect(receiptRow).toBeVisible({ timeout: 90_000 });
    await expect(receiptRow.getByRole("cell", { name: "€19.92" })).toBeVisible({ timeout: 90_000 });
  } finally {
    await close();
  }
});
