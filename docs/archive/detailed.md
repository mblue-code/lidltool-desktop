> Archived note: this file is kept as a historical snapshot.
> For the current manual QA runbook, use `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-qa-runbook.md`.
> The cleanup commands, output paths, and pack-build locations below are obsolete for current runs.

# Desktop End-to-End Test Playbook

This file is for an agent using Computer Use plus terminal access to test the newest desktop app build only.

Do not test the self-hosted Docker app for this run.

Do not use stale local dev builds, stale Electron profile data, or an old SQLite database.

The agent must start from:

- a freshly rebuilt desktop app
- a fresh Electron `userData` profile
- a fresh desktop SQLite database
- no previously installed receipt packs in the desktop profile
- no reused documents, tokens, browser state, or cached plugin state from earlier dev runs

The target is `apps/desktop`.

## Product Model To Respect

Desktop is intentionally different from self-hosted.

Important desktop truths:

- Successful packaged launches should open the finance workspace directly.
- The Control Center remains available as a fallback surface and explicit local-tools surface.
- Desktop is for occasional local use, not always-on server behavior.
- Some self-hosted routes are intentionally unsupported in desktop.
- Receipt packs are locally installed ZIPs in the desktop profile, not self-hosted plugin directories.
- The finance-first shell is the primary product hierarchy, but supporting analysis and import routes outside the main left-nav are still part of the desktop app and must be covered during QA.
- Chrome is not a substitute test surface for desktop QA. It is only an allowed fallback for specific connector-auth recovery steps called out below.

Do not file desktop bugs just because desktop lacks self-hosted-only surfaces.

## Desktop Route Scope

The current desktop route policy treats these as supported or testable:

- `/`
- `/dashboard` redirecting to `/`
- `/login`
- `/setup`
- `/transactions`
- `/receipts` redirecting to `/transactions`
- `/transactions/...`
- `/groceries`
- `/explore`
- `/products`
- `/compare`
- `/quality`
- `/connectors`
- `/sources`
- `/add`
- `/imports/manual`
- `/imports/ocr`
- `/budget`
- `/bills`
- `/cash-flow`
- `/reports`
- `/goals`
- `/merchants`
- `/settings`
- `/settings/ai`
- `/settings/users`
- `/patterns`
- `/documents/upload`
- `/review-queue`
- `/chat`

The current desktop route policy intentionally treats these as unsupported and redirecting:

- `/offers`
- `/automations`
- `/automation-inbox`
- `/reliability`

If those unsupported routes redirect back to `/` with desktop-specific messaging, that is expected behavior, not a failure.

## Test Goals

The run should prove:

- the newest desktop app can be rebuilt cleanly
- the packaged desktop app can launch from a truly fresh profile
- the success-path boot lands in the finance app
- the finance-first shell and its supporting financial outlook surfaces are the primary packaged-app experience
- the Control Center still behaves correctly when explicitly opened or when fallback is triggered
- desktop auth/setup works on a fresh database
- desktop connector and receipt-pack workflows work
- receipt import, OCR, review queue, analysis surfaces, budget, recurring bills, cash flow, goals, reports, merchants, backup/export/restore, and key admin surfaces work
- every connector that is actually usable in the desktop build is genuinely attempted

## Final Deliverables

Produce:

- `qa-report.md`
- screenshots for each major area
- a connector matrix with pass/fail/blocker
- exact desktop build tested
- exact app profile path used
- exact receipt-pack ZIPs imported
- exact error text and log excerpts for failures

Use this report structure:

- Build tested
- Fresh-state prep performed
- Credentials and assets used
- Desktop surfaces passed
- Finance workspace regression coverage
- Connector results
- OCR regression result
- Failures
- External blockers
- Risks
- Suggested fixes

## Credentials And Assets To Fill In

### Desktop App Accounts

| Item | Value |
| --- | --- |
| Admin username | `AGENT_MAY_CREATE_TEMPORARY_QA_ADMIN` |
| Admin password | `AGENT_MAY_CREATE_TEMPORARY_QA_ADMIN_PASSWORD` |
| Non-admin username | `AGENT_MAY_CREATE_TEMPORARY_QA_VIEWER` |
| Non-admin password | `AGENT_MAY_CREATE_TEMPORARY_QA_VIEWER_PASSWORD` |

### Merchant Accounts

| Connector | Username / Email | Password | Notes |
| --- | --- | --- | --- |
| Lidl Plus DE | `INTENTIONALLY_NOT_PROVIDED` | `INTENTIONALLY_NOT_PROVIDED` | Skip full autonomous test if SMS-gated |
| Amazon DE | `INTENTIONALLY_NOT_PROVIDED` | `INTENTIONALLY_NOT_PROVIDED` | Skip full autonomous test if human verification is required |
| Amazon FR | `OPTIONAL_NOT_PROVIDED` | `OPTIONAL_NOT_PROVIDED` | Optional if real account exists |
| Amazon GB | `OPTIONAL_NOT_PROVIDED` | `OPTIONAL_NOT_PROVIDED` | Optional if real account exists |
| dm DE | mein-dm.earache627@passmail.com | 78NKn$zec&E04PVcET8PjR%v1 | Desktop local pack |
| REWE DE | mein-dm.earache627@passmail.com | 9qv#d9V&%gm#ApFP7G# | Desktop local pack; normal Chrome may be needed |
| Kaufland DE | kaufland.catcall625@passmail.com | KT4UMq1D#n0%Q8zZ% | Desktop local pack if imported |
| Rossmann DE | mein-dm.earache627@passmail.com | 0GRFQThTXpfvVu*Tq10u | Only if desktop build surfaces it |
| Netto Plus DE | `OPTIONAL_NOT_PROVIDED` | `OPTIONAL_NOT_PROVIDED` | Real full test needs a session bundle file |

### OCR Assets

| Asset | Path | Purpose |
| --- | --- | --- |
| Primary OCR receipt PDF | `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf` | First OCR import candidate; use this first in the desktop OCR flow |
| Secondary OCR receipt PDF | `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf` | Second OCR import candidate; use as alternate or comparison case |
| Clean receipt image | `NOT_PROVIDED` | If the desktop flow specifically needs an image file, stop and note that only the two PDF receipt files were provided for this run |

### Netto Plus Bundle

| Item | Value |
| --- | --- |
| Netto Plus session bundle JSON | `OPTIONAL_NOT_PROVIDED` |

### Optional AI

| Item | Value |
| --- | --- |
| Chat/OAuth available | `OPTIONAL_NOT_PROVIDED` |
| API-compatible AI base URL | `OPTIONAL_NOT_PROVIDED` |
| API-compatible AI model | `OPTIONAL_NOT_PROVIDED` |
| API-compatible AI key | `OPTIONAL_NOT_PROVIDED` |

## Fresh-State Rules

The agent must not launch the desktop app against the normal existing Electron profile.

Use a dedicated throwaway desktop profile for the run:

```bash
/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data
```

Desktop honors the environment variable:

```bash
LIDLTOOL_DESKTOP_USER_DATA_DIR=/absolute/path/to/fresh/profile
```

That profile will contain, once the app runs:

- `lidltool.sqlite`
- `config/`
- `documents/`
- `plugins/receipt-packs/`
- `credential_encryption_key.txt`

Delete that whole profile before the run starts.

## Clean Rebuild Procedure

Run these from `apps/desktop`.

### 1. Kill old desktop processes

Make sure no previous Desktop app instance is still running.

### 2. Remove stale desktop build artifacts and profile state

Use a real cleanup, not just a rebuild on top:

```bash
cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop
rm -rf \
  .tmp/e2e-user-data \
  .backend/venv \
  build/frontend-dist \
  build/backend-src \
  build/backend-venv \
  dist_electron \
  dist_plugin_packs \
  out \
  output/playwright
mkdir -p .tmp
```

If you suspect stale frontend dependency state, also remove `vendor/frontend/node_modules` before reinstalling.

### 3. Sync the latest desktop vendored code

```bash
npm run vendor:sync
```

### 4. Install desktop frontend dependencies

```bash
npm run frontend:install
```

### 5. Build a fresh desktop runtime with backend included

Preferred path:

```bash
npm run dist:with-backend
```

If local packaging is blocked for an environmental reason, record that, then fall back to:

```bash
npm run backend:prepare
npm run build
```

But the preferred target for this test is the newest packaged desktop app produced during this run, not a stale dev app.

### 6. Build local receipt-pack ZIPs for the connectors that are pack-import driven

These ZIPs are test artifacts, not runtime dependencies:

```bash
python3 ../../plugins/dm_de/build_desktop_pack.py --output-dir ./dist_plugin_packs
python3 ../../plugins/rewe_de/build_desktop_pack.py --output-dir ./dist_plugin_packs
python3 ../../plugins/kaufland_de/build_desktop_pack.py --output-dir ./dist_plugin_packs
python3 ../../plugins/netto_plus_de/build_desktop_pack.py --output-dir ./dist_plugin_packs
```

### 7. Verify the packaged app path you will use

```bash
find ./dist_electron -name "LidlTool Desktop.app" -print
```

Launch the newest app produced during this run.

## Launch Procedure

Launch the packaged desktop app with the fresh profile override.

Example:

```bash
LIDLTOOL_DESKTOP_USER_DATA_DIR="$PWD/.tmp/e2e-user-data" \
  "/absolute/path/to/LidlTool Desktop.app/Contents/MacOS/LidlTool Desktop"
```

Do not launch it against the normal user profile.

## Execution Order

1. Fresh rebuild and fresh-profile launch
2. Success-path startup and first-user setup
3. Empty-state route sweep
4. Receipt-pack import and connector inventory
5. Connector setup and sync matrix
6. Manual import
7. OCR, review queue, and quality
8. Finance workspace and supporting analysis retest after data import
9. Budget, bills, goals, cash flow, and reports
10. Backup, export, and restore
11. Users settings and permission checks
12. Control Center reachability and fallback behavior
13. AI settings and chat
14. Final evidence capture

## Phase 1: Success-Path Startup And First-User Setup

On a healthy packaged build, desktop should boot into the full finance app, not the fallback shell.

Verify:

- the app launches without immediately crashing
- the packaged app auto-starts the backend on the success path
- the initial route lands on fresh first-user setup, login, or the finance app depending on the profile state
- on a fresh database, the app reaches first-user setup without needing a manual Control Center hop

For a fresh profile:

1. Confirm the app lands on fresh first-user setup.
2. Create the admin user.
3. Confirm redirect into the desktop finance app.
4. Log out once.
5. Log back in as admin.

## Phase 2: Empty-State Desktop Route Sweep

Visit:

- `/`
- `/dashboard`
- `/transactions`
- `/receipts`
- `/groceries`
- `/add`
- `/imports/manual`
- `/documents/upload`
- `/review-queue`
- `/budget`
- `/bills`
- `/cash-flow`
- `/reports`
- `/goals`
- `/merchants`
- `/connectors`
- `/imports/ocr`
- `/quality`
- `/sources`
- `/chat`
- `/settings`
- `/settings/ai`
- `/settings/users`
- `/explore`
- `/products`
- `/compare`
- `/patterns`

Expected unsupported-route behavior to verify, not fail:

- `/offers`
- `/automations`
- `/automation-inbox`
- `/reliability`

## Phase 3: Desktop Receipt-Packs And Connector Inventory

Use the desktop Connectors page as the source of truth.

Import local ZIP receipt packs from `dist_plugin_packs` for:

- `dm_de`
- `rewe_de`
- `kaufland_de`
- `netto_plus_de`

Enable imported packs explicitly if required.

## Phase 4: Connector Matrix

Use:

- `PASS_FULL`
- `PASS_PARTIAL_EXTERNAL_BLOCKER`
- `FAIL_PRODUCT`
- `NOT_PRESENT_IN_DESKTOP_BUILD`
- `NOT_IN_SCOPE`

### Built-ins surfaced by desktop

Attempt every connector the desktop build actually shows, including any Amazon marketplaces, Lidl Plus, or Rossmann if present.

### dm DE local pack

1. Import ZIP
2. Enable it
3. Run setup
4. Complete browser login
5. Run sync
6. Run sync again once
7. Verify downstream receipts

### REWE DE local pack

1. Import ZIP
2. Enable it
3. Try normal setup first
4. If challenged, log into REWE in normal Chrome only for the merchant-auth recovery step, leave the tab open, rerun setup in desktop, and keep all actual route and UI validation inside the packaged desktop app
5. Run sync
6. Verify downstream receipts

### Kaufland DE local pack

1. Import ZIP
2. Enable it
3. Complete auth
4. Run sync
5. Verify downstream receipts

### Rossmann DE

If surfaced by desktop:

1. Use the surfaced desktop flow
2. Complete setup
3. Run sync
4. Verify downstream receipts

### Lidl Plus / Amazon

If surfaced by desktop:

1. Attempt setup
2. If SMS or WhatsApp / human verification blocks progress, record exact blocker and screenshot

### Netto Plus DE local pack

1. Import ZIP
2. Enable it
3. If no session bundle is provided, verify the pack imports and the setup flow clearly requests the bundle

## Phase 5: Downstream Data Verification

After each successful connector sync, verify:

- `/transactions` shows rows from that source
- `/receipts` redirects to `/transactions` if exercised
- filtering works
- at least one detail page opens
- `/sources` reflects the source
- dashboard values update
- groceries, merchants, and reports reflect the new data where applicable

## Phase 6: Manual Import

Create at least three manual transactions in `/add`:

- `QA Grocery Manual` total `23.45`
- `QA Internet Provider` total `44.99`
- `QA Streaming` total `10.99`

Verify they appear in `/transactions`.

## Phase 7: OCR, Review Queue, And Quality

Treat `/documents/upload` as the current OCR entrypoint and `/imports/ocr` as the older compatibility entrypoint that still needs explicit coverage if surfaced.

### OCR happy path on `/documents/upload`

1. Upload `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`
2. Confirm OCR starts automatically or can be started from the packaged UI as rendered
3. Capture visible status or timeline states
4. If the UI exposes `Run OCR again`, use it once
5. Approve if acceptable
6. Verify the handoff into `/review-queue`
7. Verify a downstream transaction appears

### OCR alternate or review path

1. Upload `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf`
2. Use `/quality` and `/review-queue` as needed
3. Edit, reject, or approve as appropriate
4. Record whether it lands in review, approves cleanly, or fails

### OCR rejection path

If a review item is suitable for rejection, test rejection once and verify the rejected state is visible.

### OCR compatibility entrypoint

If `/imports/ocr` is still surfaced:

1. Open it explicitly
2. Verify whether it is a separate flow or an alias to the current document-upload surface
3. Record what happened in the report

### OCR failure triage

If OCR is broken, determine which layer appears broken instead of stopping at a generic failure:

- document upload
- OCR job start
- OCR worker wake-up
- status polling or timeline updates
- review queue handoff
- approval creating a downstream transaction

## Phase 8: Finance Workspace And Insight Pages

Test:

- dashboard
- transactions history
- groceries
- merchants
- reports
- goals
- cash flow
- products
- compare
- patterns
- explore
- sources
- quality

## Phase 9: Budget, Bills, Goals, And Cash Flow

Create a synthetic monthly budget and several cashflow entries.

Create recurring bills:

- `QA Internet Provider`
- `QA Streaming`
- `QA Rent`
- `QA Electricity`

Generate occurrences and reconcile at least one to a manual transaction.

Also verify:

- at least one goal can be created and remains visible afterward
- budget reconciliation candidates reflect available imported or manual data when present
- reports can export at least one JSON payload

## Phase 10: Backup, Export, And Restore

Test desktop-native:

- backup
- export
- restore, if safe to do in the fresh test profile

## Phase 11: Users And Permissions

Create a non-admin user from `/settings/users`.

Verify:

- admin sees admin controls
- non-admin does not see restricted details

## Phase 12: Control Center Reachability And Fallback

The Control Center is no longer the default success-path shell, but it still needs coverage as a fallback and local-tools surface.

Verify at least one of these:

- open the Control Center from setup, login, or in-app preferences and confirm it loads
- launch once with a known-bad backend override and confirm fallback Control Center appears with diagnostic messaging

If the fallback Control Center appears, verify:

- desktop runtime diagnostics are visible if exposed
- the app explains whether it is in reduced fallback mode or control-center-only mode
- local tool actions that are still owned by the Control Center behave coherently

## Phase 13: AI Settings And Chat

In `/settings/ai`, explicitly verify:

- the ChatGPT / Codex connection area loads
- chat model selection is separate from item categorization settings
- item categorization controls render cleanly
- OCR provider controls render, including primary provider and fallback controls
- if a safe save round-trip is possible without introducing secrets or unsafe side effects, test one and record the result

For `/chat`, verify it opens from the packaged desktop shell and handles missing AI configuration cleanly when AI is not configured.

## Failure Logging Requirements

Whenever something fails:

1. capture a screenshot
2. capture exact UI text
3. note the route or connector id
4. note the packaged app path used
5. note the fresh profile path used
6. capture relevant terminal output
7. if Chrome fallback was used, record that it was limited to connector auth recovery only

## Minimum Success Bar

At minimum, prove:

- fresh packaged desktop build
- fresh profile launch
- first-user setup on a fresh DB
- finance app boots directly on the success path
- finance workspace routes and supporting analysis surfaces load from the packaged app
- Control Center remains reachable as a fallback/manual tool surface
- receipt-pack import works
- usable desktop connectors are genuinely attempted
- manual import works
- OCR and review queue work
- core analytics pages work
- budget, bills, cash flow, goals, and reports work
- backup/export works
- admin vs non-admin behavior is checked
