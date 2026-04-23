# Desktop QA Report

## Build tested

- Repo: `/Volumes/macminiExtern/lidl-receipts-cli`
- Desktop workspace: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`
- Branch: `main`
- Commit: `84463bb436ad31ae52fd36112d27537e3ab09c00`
- Date: `2026-04-22`
- Packaged app tested: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_electron/mac-arm64/LidlTool Desktop.app`
- Fresh artifact timestamps:
  - app: `Apr 22 16:26:14 2026`
  - dmg: `Apr 22 16:27:08 2026`
  - zip: `Apr 22 16:27:30 2026`
- Build/install commands run successfully:
  - `npm run vendor:sync`
  - `npm run frontend:install`
  - `npm run build`
  - `npm run dist:with-backend`
- Primary packaged launch log:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/logs/launch.log`

Build result: `PASS`

## Fresh-state prep performed

- Killed running `LidlTool Desktop` processes
- Deleted stale desktop state per runbook before the rerun:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.backend/venv`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/build/frontend-dist`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/build/backend-src`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/build/backend-venv`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_electron`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/out`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/output/playwright`
- Rebuilt the packaged app from scratch
- Rebuilt local receipt-pack ZIPs:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.dm_de-0.1.0-electron.zip`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.rewe_de-0.2.0-electron.zip`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.kaufland_de-0.1.0-electron.zip`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.netto_plus_de-0.1.0-electron.zip`
- Primary fresh profile used:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data`

Fresh-state result: `PASS`

## Credentials and assets used

- Temporary desktop-local admin created:
  - username: `qaadmin2`
  - password: not recorded here
- Merchant credentials from `detailed.md` used only where needed:
  - `dm DE`
  - `REWE DE`
- `Lidl Plus DE` and `Amazon DE` remained under the runbook's intentionally-limited handling when live login or human verification was required
- `Netto Plus DE` full sync remained blocked because no session bundle file was provided
- OCR files used:
  - primary: `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`
  - alternate: `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf`
- Chrome fallback used: `Yes`, but only for the REWE merchant-auth recovery step

## Desktop surfaces passed

### Passed

- Fresh packaged launch reached `/setup`
- First-user setup succeeded on a fresh profile
- Success-path redirect reached the finance shell instead of dropping into Control Center
- Finance shell sidebar rendered and routed for the visible finance workspace:
  - `/`
  - `/transactions`
  - `/groceries`
  - `/budget`
  - `/bills`
  - `/cash-flow`
  - `/reports`
  - `/goals`
  - `/merchants`
  - `/settings`
  - `/settings/ai`
  - `/connectors`
  - `/add`
  - `/imports/ocr`
  - `/review-queue`
  - `/chat`
- Manual entry flow from `/add` worked and created a real transaction
- `/transactions` showed the created manual row
- `/groceries` showed the new purchase in recent activity
- `/budget` month save worked
- `/budget` cashflow entry creation worked
- `/cash-flow` rendered the created ledger row
- `/goals` goal creation worked
- `/reports` rendered templates and exported JSON successfully to:
  - `/Volumes/macminiExtern/DevData/Downloads/monthly-overview.json`
- `/settings/ai` loaded correctly and a safe no-secret save round-trip succeeded with:
  - `Erfolgreich gespeichert`
  - `Chat model settings saved`
- `/chat` opened and handled the unconfigured state without crashing; created thread remained `inaktiv`
- `/settings/users` backup path now succeeds on the fresh profile

### Partial / limited

- `/bills` loaded and opened the recurring-bill modal, but this rerun only verified validation behavior; no successful recurring bill save was confirmed
- `/review-queue` loaded and stayed coherent, but remained empty because OCR never advanced beyond `queued`
- `/add` is the visible desktop entrypoint for OCR; `/documents/upload` was not surfaced separately in the packaged UI during this rerun

### Not directly exercised in the packaged UI

These routes are present in desktop route policy but are non-nav-visible in the current packaged IA, so they were not directly opened through a surfaced desktop path during this rerun:

- `/sources`
- `/explore`
- `/products`
- `/compare`
- `/quality`
- `/patterns`
- `/documents/upload`
- `/imports/manual`

Diagnostic note:

- `vendor/frontend/src/lib/desktop-route-policy.ts` marks these as `enabled` or `preview`, but `navVisible: false`
- The user-facing packaged UI surfaced `/imports/ocr` from `/add`, not a distinct `/documents/upload` entry

## Finance workspace regression coverage

Status: `PASS_WITH_FINDINGS`

### Success-path boot

- Healthy packaged launch landed in `/setup`
- First-user setup completed
- Redirect into the finance workspace succeeded
- Control Center was not the default landing screen on the healthy success path

### Finance shell navigation and current layout

- Sidebar rendered the current finance-first desktop destinations
- Visible shell routing was stable across repeated navigation
- Dashboard layout matched the intended finance workspace rather than the older Control Center-first shell

### Explicit route coverage

Verified in the real packaged finance shell:

- `/`
- `/transactions`
- `/groceries`
- `/budget`
- `/bills`
- `/cash-flow`
- `/reports`
- `/goals`
- `/merchants`
- `/settings`
- `/settings/ai`
- `/connectors`
- `/add`
- `/imports/ocr`
- `/review-queue`
- `/chat`
- `/settings/users`

Observed behavior instead of separate route entry:

- `/receipts` was not explicitly opened, but `/transactions` is the canonical history view in the current shell
- `/documents/upload` was not separately surfaced; the visible OCR path is `/add -> /imports/ocr`

### Current finance-shell findings

- Dashboard, groceries, cashflow, and merchants do not agree on aggregates after local data creation
- Route loading itself is stable, but several summary cards stay zero while downstream tables/lists update

## Connector matrix

Imported ZIPs:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.dm_de-0.1.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.rewe_de-0.2.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.kaufland_de-0.1.0-electron.zip`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/dist_plugin_packs/local.netto_plus_de-0.1.0-electron.zip`

| Connector | Result | Notes |
| --- | --- | --- |
| dm DE | `PARTIAL_PASS_WITH_FINDING` | Pack imported and activated. Merchant login still shows `Es ist ein Fehler aufgetreten, bitte versuche es später erneut.` on the first submit, but the identical second submit succeeds. After packaged-app relaunch the card becomes `Bereit` and a real cookie-backed session file exists. A persisted import is still not proven from the packaged UI in the retest profile. |
| REWE DE | `PASS_WITH_FINDING` | Pack imported and activated. Chrome recovery path was used exactly per runbook. Normal Chrome reached a real logged-in REWE purchase-history page, and the packaged app created persisted `source`, `source_account`, `receipt`, `transaction`, and `sync_state` rows in the fresh retest profile. The connector card can still look stale and fall back to `Einrichtung nötig` despite the completed import. |
| Kaufland DE | `PARTIAL_PASS_WITH_FINDING` | Pack imported and activated. Setup collects the connector-local field and now opens a real visible Chrome-for-Testing login window instead of the old invisible auth path. The login page reaches a real submit state, but no authenticated Kaufland state is persisted and no callback/import is proven. |
| Netto Plus DE | `BLOCKED_EXTERNAL` | Pack imported and setup UX rendered. Full sync remained blocked because the required Android session bundle JSON was not provided. Evidence: `08-netto-pre-activation-modal.png`. |
| Lidl Plus DE | `BLOCKED_EXTERNAL` | Setup card surfaced, but full autonomous completion remains intentionally out of scope because live verification can require human-only factors. |
| Amazon DE | `BLOCKED_EXTERNAL` | Setup card surfaced, but full autonomous completion remains intentionally out of scope because live verification can require human-only factors. |
| Amazon FR | `NOT_IN_SCOPE` | Optional per runbook. |
| Amazon GB | `NOT_IN_SCOPE` | Optional per runbook. |
| Rossmann DE | `PARTIAL` | Present as a surfaced merchant chip in the desktop shell, but no dedicated connector flow was exercised in this rerun. |

Connector summary:

- Chrome fallback was used only for REWE auth recovery
- No Chrome desktop-route validation was used
- The packaged connector rail is now usable enough to import/activate packs and start merchant flows
- Live connector completion remains inconsistent and preview-gated

### Connector rerun addendum (`2026-04-22`, fresh packaged profile)

Fresh profile reused for this focused rerun:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data-retest`

Focused connectors rerun:

- `dm DE`
- `REWE DE`
- `Kaufland DE`

Observed updates versus the earlier matrix:

- `dm DE`
  - The first login submit still fails at `signin.dm.de` with the exact merchant text:
    - `Es ist ein Fehler aufgetreten, bitte versuche es später erneut.`
  - Re-submitting the identical preserved form a second time succeeds and advances past the merchant error.
  - The packaged app does not finalize that state immediately. It remains stuck in `Anmeldung läuft` until the packaged app is restarted.
  - After relaunch, `dm` becomes `Bereit` and shows `Belege importieren`.
  - The retest profile contains a real authenticated session file at:
    - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data-retest/config/connector_plugin_runtime/dm_de/data/dm_storage_state.json`
  - That file contains real cookies and origins, so auth is saved.
  - A downstream persisted import is still not proven in this retest profile; no `dm_de` `source`, `source_account`, `receipt`, `transaction`, or `sync_state` row was created from the packaged UI path during this pass.

- `REWE DE`
  - Pack import and activation still succeed.
  - Normal Chrome recovery remains valid and reaches a real logged-in REWE account page with visible `Meine Einkäufe im Markt` eBon entries.
  - This rerun did complete a real packaged-app import. Fresh-profile SQLite evidence:
    - `sources = 1`
    - `source_accounts = 1`
    - `receipts = 1`
    - `transactions = 1`
    - `sync_state` contains:
      - `rewe_de|2026-04-22 19:31:29.938916|aab80488-47e2-3d9c-987d-551e3fe010c8`
  - The persisted REWE storage state file exists at:
    - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data-retest/config/connector_plugin_runtime/rewe_de/data/rewe_storage_state.json`
  - Remaining finding:
    - the connector card can still regress visually to `Einrichten` / `Einrichtung nötig` even after the real import completed, so the UI state is less reliable than the persisted data.

- `Kaufland DE`
  - Pack import and activation succeed.
  - Setup modal opens and accepts the connector-local country/store field.
  - After submit, the packaged app moves Kaufland into:
    - `Anmeldung läuft`
    - `Import läuft`
    - technical details text:
      - `Browser open: complete login in the shared auth session window.`
  - Unlike the earlier broken runs, this rerun did open a real visible Chrome-for-Testing login page for Kaufland.
  - The login page reaches a visible submit/disabled state, but it snaps back without redirecting or persisting authenticated state.
  - The persisted runtime file remains only a stub:
    - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data-retest/config/connector_plugin_runtime/kaufland_de/data/kaufland_state.json`
    - keys:
      - `import_source`
      - `schema_version`
      - `tracking_source_id`
  - No `sources`, `source_accounts`, `receipts`, `transactions`, or `sync_state` row was created for Kaufland in the fresh retest profile.
  - The desktop app also blocks other connector setups with `Eine andere Anmeldung läuft` while Kaufland remains in this pending state.

Fresh-profile SQLite evidence from the same rerun:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data-retest/lidltool.sqlite`
- `connector_lifecycle_state` contains installed local packs for:
  - `dm_de`
  - `rewe_de`
  - `kaufland_de`
- Persisted runtime data in the retest profile:
  - `sources = 1`
  - `source_accounts = 1`
  - `receipts = 1`
  - `transactions = 1`
  - `sync_state` contains only the successful `rewe_de` row

Rerun conclusion:

- `dm` has a reproducible two-submit auth quirk and only looks ready after app relaunch, but auth itself is real.
- `REWE` is now proven end-to-end in the packaged app with real persisted downstream data.
- `Kaufland` is no longer blocked on the invisible-browser regression, but its auth callback still does not persist authenticated state or produce a proven import.

## OCR regression result

Status: `FAIL_PRODUCT`

### `/imports/ocr`

- Present and reachable from `/add`
- Primary file upload succeeded:
  - document: `31d4cfc8-f693-4ba2-9f2f-887c5b26036b`
  - job: `07a122b6-b1bd-447e-af78-65c69fd5191c`
- Alternate file upload succeeded:
  - document: `1f5d5161-799a-44af-8433-23aa893ffbef`
  - job: `de6c0a7d-7c37-4395-9ffb-1dd8016dc192`
- Both uploads persisted in SQLite
- Both OCR jobs remained `queued`
- Neither upload advanced into review or downstream transaction creation

### `/documents/upload`

- Not separately surfaced in the packaged desktop UI during this rerun
- Current user-facing OCR path is `/add -> /imports/ocr`
- Route policy still lists `/documents/upload` as desktop `preview`, but hidden from nav

### `/review-queue`

- Reachable and stable
- Remained empty after both OCR uploads:
  - `Keine Dokumente entsprechen den ausgewählten Filtern.`

### OCR failing layer

The break is not file selection or upload. The break is after job creation:

- upload: `PASS`
- document persistence: `PASS`
- OCR job creation: `PASS`
- OCR worker/runtime pickup: `FAIL`
- timeline progression beyond `queued`: `FAIL`
- review handoff: `FAIL`
- approval to receipt/transaction: `BLOCKED`

Database evidence:

- `documents.file_name` values present for both PDFs
- `documents.ocr_status = queued`
- `ingestion_jobs.status = queued`

## Failures

### 1. Aggregation drift across finance surfaces

Severity: `P1`

Observed:

- Manual transaction appears in `/transactions`
- Same row appears in `/groceries` recent purchases
- Merchant row appears in `/merchants`
- Report export includes the transaction and merchant correctly
- But several summary cards stay zero or inconsistent

Examples:

- `/groceries` recent purchase table updates while summary cards remain zero
- `/cash-flow` ledger row updates while top cards remain `0,00 €`
- `/merchants` directory shows `QA Markt` and `12,34 €`, while top cards still show `0`
- Dashboard top cards partially update, but not consistently across all sections

Evidence:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/14-groceries-stale-summary.png`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/21-merchants-stale-summary.png`

### 2. OCR jobs never leave `queued`

Severity: `P1`

Observed:

- Both OCR uploads succeed
- Timeline renders upload and queued-start events
- No later state appears
- Review queue remains empty

Evidence:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/16-ocr-primary-stuck-queued.png`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/24-review-queue-still-empty-after-second-ocr.png`

### 3. Connector completion remains inconsistent after auth

Severity: `P1`

Observed:

- `dm` reaches real external auth but returns merchant-side failure text
- `REWE` can save auth after the allowed Chrome recovery path, but the connector still falls back to `Aktion nötig` before import
- `Lidl Plus` start warns that remote browser session is unavailable and falls back to local display because virtual-display dependencies are missing
- Active connector logins still serialize the rest of the connector rail and block other setup attempts

Evidence:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/10-dm-login-error.png`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/25-connectors-lidl-active-rewe-auth-saved.png`

## External blockers

- `Lidl Plus DE`: runbook credentials intentionally not provided for a full autonomous human-verification path
- `Amazon DE`: runbook credentials intentionally not provided for full autonomous human-verification handling
- `Netto Plus DE`: required Android session bundle JSON not provided

## Risks

- Finance-shell regressions are no longer launch-blocking, but data-confidence regressions remain inside the happy path
- OCR is currently not useful for real packaged desktop intake because jobs stall after creation
- Connector state is still preview-like and can mislead users into thinking auth is complete when import is not actually proven
- Hidden-but-enabled desktop routes still need direct packaged-app coverage if they are expected to ship as supported analysis surfaces

## Suggested fixes

1. Fix the shared finance aggregations so dashboard, groceries, merchants, and cashflow cards derive from the same committed transaction source as the tables and report exports.
2. Instrument the OCR worker path after ingestion job creation and verify why `ocr_upload` jobs remain permanently `queued` on a fresh packaged profile.
3. Stabilize connector state transitions:
   - clear or complete active-login state reliably
   - distinguish `auth saved` from `import proven`
   - stop showing preview-only success states as if the connector is fully ready
4. For Lidl browser fallback, either ship the required virtual-display dependencies or degrade more explicitly without trapping the rest of the connector rail.
5. Expose or explicitly alias the hidden desktop analysis routes that are meant to be supported, or downgrade their support claims in route policy until they are reachable through the packaged UI.

## Evidence

- Launch log:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/logs/launch.log`
- Screenshots:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/01-setup.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/02-dashboard.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/03-connectors.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/10-dm-login-error.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/12-manual-entry-saved.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/13-transactions-manual-row.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/14-groceries-stale-summary.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/16-ocr-primary-stuck-queued.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/17-review-queue-empty-after-ocr.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/18-budget-cashflow-entry.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/20-bills-validation-error.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/21-merchants-stale-summary.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/22-settings-ai-save-success.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/23-chat-inactive-thread.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/24-review-queue-still-empty-after-second-ocr.png`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/qa-rerun-20260422/screenshots/25-connectors-lidl-active-rewe-auth-saved.png`
