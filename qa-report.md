# LidlTool Desktop QA Rerun

Date: 2026-04-20

## Build Tested

- Repo path: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`
- Git revision: `fbb0105602922582e61b32c6251240d256a92d09`
- Desktop package version: `0.1.0`
- Packaged app tested: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_electron/mac-arm64/LidlTool Desktop.app`
- Fresh profile path: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data`
- Pack storage used: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data/plugins/receipt-packs`

## Fresh-State Prep Performed

This rerun was executed from a full local wipe and rebuild. No old build output, desktop profile, SQLite DB, plugin ZIP, Electron userData, or prior `qa-report.md` was reused.

Deleted before QA:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.backend`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/build`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_electron`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/out`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/output/playwright`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/node_modules`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/node_modules`
- Previous desktop report and stale evidence files
- `~/Library/Application Support/lidltool-desktop`
- `~/Library/Application Support/LidlTool Desktop`
- `~/Library/Caches/lidltool-desktop`
- `~/Library/Preferences/com.lidltool.desktop.plist`
- Related crash / diagnostic artifacts and stale Python cache dirs

Rebuilt from scratch:

- `npm ci`
- `npm run vendor:sync`
- `npm run frontend:install`
- `npm run dist:with-backend`
- Local receipt-pack ZIP rebuilds:
  - `local.dm_de-0.1.0-electron.zip`
  - `local.rewe_de-0.2.0-electron.zip`
  - `local.kaufland_de-0.1.0-electron.zip`
  - `local.netto_plus_de-0.1.0-electron.zip`

Launch used:

- `HOME=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-home-clean`
- `TMPDIR=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-tmp-clean`
- `LIDLTOOL_DESKTOP_USER_DATA_DIR=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data`
- App args included `--user-data-dir=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data`

Result:

- `PASS`: packaged desktop app rebuilt from newest local code and launched against the fresh profile override.
- `PASS`: fresh Control Center pack storage matched the fresh profile path.

## Credentials And Assets Used

- Credentials were read from `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/detailed.md` and used without reproducing secrets here.
- OCR assets used:
  - `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`
  - `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf` was not needed after the primary OCR defect reproduced.
- Temporary local QA users created during this rerun:
  - `qa-admin-desktop`
  - `qa-viewer-desktop`

## Receipt Packs Imported

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.dm_de-0.1.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.rewe_de-0.2.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.kaufland_de-0.1.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.netto_plus_de-0.1.0-electron.zip`

## Desktop Surfaces Passed

- `PASS`: fresh Control Center load and pack import on the fresh profile
- `PASS`: first-user setup on the fresh DB
- `PASS`: admin login and logout on the fresh DB
- `PASS`: main supported routes exercised in this rerun:
  - `/`
  - `/receipts`
  - `/add`
  - `/budget`
  - `/bills`
  - `/connectors`
  - `/imports/ocr`
  - `/quality`
  - `/sources`
  - `/chat`
  - `/settings/ai`
  - `/settings/users`
  - `/explore`
  - `/products`
  - `/compare`
  - `/patterns`
- `PASS`: manual import flow
  - Created `QA Grocery Manual` `23,45 €`
  - Created `QA Internet Provider` `44,99 €`
  - Created `QA Streaming` `10,99 €`
- `PASS`: recurring bills CRUD baseline
  - Created `QA Internet Provider`
  - Created `QA Streaming`
  - Created `QA Rent`
- `PASS`: budget month settings save
- `PASS`: budget cash-flow entry save
- `PASS`: budget rule save
- `PASS`: backup package creation from the packaged desktop UI
- `PASS`: non-admin main-app restriction baseline
  - Viewer nav removed the `SYSTEM` section and hid the `Benutzer` surface

## Connector Matrix

| Surface | Status | Notes |
|---|---|---|
| dm | `FAIL_PRODUCT` | Browser handoff did not open the actual auth page from desktop. After manual Chrome login to `Meine Einkäufe`, desktop never consumed the auth state. No `source_accounts` row was created for `dm_de`. |
| dm cancel path | `FAIL_PRODUCT` | Exact UI text reproduced: `Abbrechen fehlgeschlagen` and `Invalid API payload: [ { "code": "invalid_value", "values": [ "idle", "running", "succeeded", "failed" ], "path": [ "bootstrap", "status" ], "message": "Invalid input" } ]`. |
| REWE | `FAIL_PRODUCT` | UI reported a saved Chrome-based REWE login as ready, but DB state still showed no usable REWE account/session. `connector_config_state` remained `dm_de|local.dm_de|null` and `rewe_de|local.rewe_de|null`; no REWE `source_accounts` row existed. |
| Amazon (built-in) | `FAIL_PRODUCT` + `PASS_PARTIAL_EXTERNAL_BLOCKER` | Desktop emitted the same local-browser fallback warning without actually opening a login surface in Chrome. Credentials were intentionally not provided, so full sync remained externally blocked even after the handoff defect reproduced. |
| Lidl Plus (built-in) | `PASS_PARTIAL_EXTERNAL_BLOCKER` | Desktop surface present. Human-only verification / credentials were intentionally not provided, so full sync was not completed. |
| Netto Plus | `PASS_PARTIAL_EXTERNAL_BLOCKER` | Pack import and setup UX passed. Full sync was blocked exactly as expected because no Android session bundle was provided. |
| Kaufland pack presence | `PASS` | Pack installed and enabled in Control Center. No distinct failing setup path reproduced in this rerun. |

## Failures

### `FAIL_PRODUCT`

1. dm auth handoff from desktop to browser is broken.
   - Desktop warned that the remote browser was unavailable and claimed a local fallback.
   - Chrome stayed on a blank/new-tab state instead of opening the dm login surface.
   - Manual completion in Chrome did not cause desktop to finalize auth.

2. dm cancel flow returns an invalid bootstrap payload error.
   - Exact UI text:
     - `Abbrechen fehlgeschlagen`
     - `Invalid API payload: [ { "code": "invalid_value", "values": [ "idle", "running", "succeeded", "failed" ], "path": [ "bootstrap", "status" ], "message": "Invalid input" } ]`

3. REWE shows false-ready / contradictory setup state.
   - UI text included:
     - `Die gespeicherte, Chrome-basierte REWE-Anmeldung ist für den nächsten Import bereit.`
     - `Nächster Schritt nach der Anmeldung`
   - DB evidence still showed no usable REWE account/session state afterward.

4. OCR pipeline is stuck in `queued`.
   - UI after upload:
     - `Beleg hochgeladen. OCR startet automatisch.`
     - Job id `c29b314f-5e6b-40c5-966f-d66413b5ae1b`
     - Document id `fcaa0571-0b1e-46e9-910f-5aefe169f781`
   - DB evidence:
     - `ingestion_jobs`: `c29b314f-5e6b-40c5-966f-d66413b5ae1b|ocr_upload|OCR Uploads|queued|manual|2026-04-20 16:50:51.446052|`
     - `documents`: `fcaa0571-0b1e-46e9-910f-5aefe169f781|38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf|queued|||`

5. Bills summary cards are disconnected from persisted recurring bills.
   - After creating three active recurring bills, `/bills` still showed:
     - `MONATLICH GEBUNDEN` = `-`
     - `AKTIVE RECHNUNGEN` = `0`
     - `DIESE WOCHE FÄLLIG` = `0`
   - DB evidence still contained:
     - `QA Rent|120000|qa rent|1`
     - `QA Streaming|1099|qa streaming|1`
     - `QA Internet Provider|4499|qa internet provider|1`

6. Budget aggregates ignore persisted recurring bills and manual cash-flow state.
   - `/budget` accepted and saved month settings, a cash outflow, and a budget rule.
   - Despite that, top cards and recurring commitments remained zero / empty.
   - Example UI state after save:
     - `Saved budget for April 2026`
     - `RECURRING BILLS 0,00 €`
     - `No recurring items`

7. Desktop restore reports success but does not replace the live DB state.
   - Control Center restore result showed `ok: true`, `command: "desktop:import"`, `exitCode: 0`.
   - Backup DB users:
     - `_service|1`
     - `qa-admin-desktop|1`
   - Live DB after restore still contained:
     - `_service|1`
     - `qa-admin-desktop|1`
     - `qa-viewer-desktop|0`
   - This proves the live profile DB was not actually rewound to the backup snapshot.

### `PASS_PARTIAL_EXTERNAL_BLOCKER`

- Lidl Plus: credentials / human verification intentionally unavailable
- Amazon: credentials intentionally unavailable after browser-handoff defect reproduced
- Netto Plus: session bundle intentionally unavailable

### `NOT_PRESENT_IN_DESKTOP_BUILD`

- None newly observed beyond the known unsupported route family below.

## Coverage Gaps

- Unsupported desktop routes were not revalidated end-to-end in this rerun:
  - `/offers`
  - `/automations`
  - `/automation-inbox`
  - `/reliability`
- Reason:
  - The packaged desktop shell exposes no direct route-entry affordance in the webview, and these unsupported routes are not surfaced in the visible desktop navigation.
  - This rerun therefore covered the supported in-app surfaces and logged the unsupported-route family as an explicit gap rather than fabricating a result.
- Alternate OCR review-path PDF was not rerun because the primary OCR defect reproduced immediately and kept the OCR pipeline in `queued`.

## External Blockers

- `INTENTIONALLY_NOT_PROVIDED` credentials prevented full Lidl Plus and Amazon completion
- `OPTIONAL_NOT_PROVIDED` Netto Plus Android session bundle prevented full Netto sync
- Human-only verification paths remain outside agent completion scope when triggered

## Evidence

- Fresh Control Center: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/phase1-control-center-clean.png`
- Fresh logout / login state: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/logout-state-check.png`
- Imported packs: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/control-center-all-packs-imported-20260420.png`
- Manual imports: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/manual-import-three-transactions-20260420.png`
- dm stuck / auth evidence:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/connectors-dm-stuck-20260420.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/connectors-dm-auth-succeeded-browser-but-desktop-stuck-20260420.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/connectors-dm-cancel-api-error-20260420.png`
- Netto setup evidence: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/connectors-netto-plus-missing-bundle-setup-20260420.png`
- Amazon bootstrap evidence: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/connectors-amazon-bootstrap-20260420.png`
- Post-restore viewer still authenticated: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-evidence-rerun/post-restore-viewer-still-authenticated-20260420.png`
- Launch logs:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/logs/desktop-launch-clean-20260420-174609.log`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/logs/desktop-relaunch-after-logout-20260420-175024.log`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/logs/desktop-relaunch-control-center-20260420-175821.log`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/logs/desktop-launch-clean-rerun-20260420-180311.log`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/logs/open-launch-20260420-180344.log`

## Risks

- Connector setup appears able to claim ready state without creating usable local source-account state.
- Billing / budget analytics surfaces can silently present zeroed summaries even when their underlying records exist.
- Backup restore currently gives a false-success signal that could mislead users into believing their desktop profile was recovered when it was not.
- OCR queue stalling blocks both OCR ingest and review/quality validation downstream.

## Suggested Fixes

1. Fix desktop browser handoff so local fallback actually opens the intended auth URL in the user’s browser and completes state handoff back into desktop.
2. Validate dm cancel payload generation against the backend bootstrap schema before sending.
3. Gate REWE “ready” UI on durable state creation, not just transient setup completion.
4. Trace the packaged OCR worker path and queue consumer startup for the bundled backend build.
5. Reconcile `/bills` and `/budget` aggregation queries with the persisted `recurring_bills` and manual cash-flow tables.
6. Make desktop restore verify that the live DB hash / user count / manifest contents actually match the restored backup before reporting success.
7. Add an internal route test affordance or packaged QA mode for unsupported desktop route validation without requiring hidden navigation.

## Overall Result

- Fresh rebuild from newest local code: `PASS`
- Fresh profile launch with fresh `userData`: `PASS`
- Full desktop matrix attempted end to end: `PASS_WITH_RECORDED_GAPS`
- New report generated from this rerun only: `PASS`
- Product outcome: multiple reproducible packaged-desktop defects remain in connectors, OCR, bills/budget aggregation, and restore
