# Desktop Full QA Runbook

This file is for an agent using Computer Use plus terminal access to test the newest desktop app build only.

Do not test the self-hosted Docker app for this run.

Do not use stale local dev builds, stale Electron profile data, an old SQLite database, previously installed receipt packs, or old browser/session/token state.

The target is `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`.

## Product Model To Respect

Desktop is intentionally different from self-hosted.

Important current desktop truths:

- Successful packaged launches should reach first-user setup, login, or the finance workspace directly.
- The finance-first shell is the primary product hierarchy.
- The Control Center remains available as a fallback surface and explicit local-tools surface.
- Desktop is for occasional local use, not always-on server behavior.
- Some self-hosted routes are intentionally unsupported in desktop.
- Receipt packs are locally installed ZIPs in the desktop profile, not self-hosted plugin directories.
- The desktop shell is workspace-aware. `Personal` and shared-group workspaces are part of the intended product, not just hidden state.
- Chrome is not a substitute desktop test surface. It is only an allowed fallback for specific connector-auth recovery steps called out below.

Do not file desktop bugs just because desktop lacks self-hosted-only surfaces.

## Desktop Route Scope

Treat these as current supported or testable desktop routes if they are present in the packaged build:

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
- the success-path boot lands in setup/login/full app rather than defaulting to fallback mode
- the finance-first shell and its supporting analysis surfaces are the primary packaged-app experience
- the shared-workspace model is real and visible, not just dormant backend state
- the Control Center still behaves correctly when explicitly opened or when fallback is triggered
- desktop auth/setup works on a fresh database
- desktop connector and receipt-pack workflows work
- receipt import, OCR, review queue, analysis surfaces, planning surfaces, backup/export/restore, and key admin surfaces work
- every connector that is actually usable in the desktop build is genuinely attempted

## Output And Evidence Layout

Use a timestamped evidence directory so this run does not clutter the repo root.

Recommended layout:

```bash
STAMP="$(date +%Y%m%d-%H%M%S)"
EVIDENCE_DIR="/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/output/manual-qa/$STAMP"
mkdir -p "$EVIDENCE_DIR/screenshots" "$EVIDENCE_DIR/logs"
```

Place the final report at:

- `$EVIDENCE_DIR/qa-report.md`

Capture screenshots, copied terminal output, and any exported JSON/report payloads under the same evidence directory.

Do not assume the report should be committed to git by default.

Use this report structure:

- Build tested
- Fresh-state prep performed
- Credentials and assets used
- Desktop surfaces passed
- Shared-workspace regression coverage
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
| dm DE | `mein-dm.earache627@passmail.com` | `78NKn$zec&E04PVcET8PjR%v1` | Desktop local pack |
| REWE DE | `mein-dm.earache627@passmail.com` | `9qv#d9V&%gm#ApFP7G#` | Desktop local pack; Chrome recovery may be needed |
| Kaufland DE | `kaufland.catcall625@passmail.com` | `KT4UMq1D#n0%Q8zZ%` | Desktop local pack if imported |
| Rossmann DE | `mein-dm.earache627@passmail.com` | `0GRFQThTXpfvVu*Tq10u` | Only if desktop build surfaces it |
| Netto Plus DE | `OPTIONAL_NOT_PROVIDED` | `OPTIONAL_NOT_PROVIDED` | Full autonomous test needs a session bundle file |

### OCR Assets

| Asset | Path | Purpose |
| --- | --- | --- |
| Primary OCR receipt PDF | `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf` | First OCR import candidate; use this first in the desktop OCR flow |
| Secondary OCR receipt PDF | `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf` | Second OCR import candidate; use as alternate or review-heavy case |
| Clean receipt image | `NOT_PROVIDED` | If a flow specifically needs an image file, note that only the two PDF assets were provided |

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

Do not launch the desktop app against your normal existing Electron profile.

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

Run all commands from `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`.

### 1. Kill old desktop processes

Make sure no previous LidlTool Desktop process is still running.

### 2. Remove stale desktop build artifacts and profile state

Use the current desktop cleanup path, not an ad hoc partial cleanup:

```bash
cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop
npm run clean
rm -rf .tmp/e2e-user-data
mkdir -p .tmp build/plugin-packs output/manual-qa
```

If you suspect stale vendored dependency state, record that and then remove `vendor/frontend/node_modules` before reinstalling. Do not do this silently.

### 3. Sync the latest desktop vendored code

```bash
npm run vendor:sync
```

### 4. Prepare the backend runtime

```bash
npm run backend:prepare
```

### 5. Build a fresh packaged desktop app

Preferred path:

```bash
npm run dist:with-backend
```

This is the preferred target for the run. The QA target is the newest packaged desktop app built during this run, not a stale dev app.

If full packaging is blocked for a real local environment reason, record that and fall back to:

```bash
npm run build
```

Only use that fallback if packaged build validation is genuinely blocked.

### 6. Build local receipt-pack ZIPs for pack-import-driven connectors

These ZIPs are QA artifacts, not runtime dependencies:

```bash
python3 ../../plugins/dm_de/build_desktop_pack.py --output-dir ./build/plugin-packs
python3 ../../plugins/rewe_de/build_desktop_pack.py --output-dir ./build/plugin-packs
python3 ../../plugins/kaufland_de/build_desktop_pack.py --output-dir ./build/plugin-packs
python3 ../../plugins/netto_plus_de/build_desktop_pack.py --output-dir ./build/plugin-packs
```

Record the actual ZIP filenames produced.

### 7. Verify the packaged app path you will use

On macOS:

```bash
find ./dist_electron -name "LidlTool Desktop.app" -print | sort
```

On Windows, use the newest unpacked executable or packaged output under `dist_electron`.

Launch the newest packaged app produced during this run.

## Launch Procedure

Launch the packaged desktop app with the fresh profile override.

macOS example:

```bash
LIDLTOOL_DESKTOP_USER_DATA_DIR="$PWD/.tmp/e2e-user-data" \
  "/absolute/path/to/LidlTool Desktop.app/Contents/MacOS/LidlTool Desktop"
```

Do not launch it against the normal user profile.

## Execution Order

1. Fresh rebuild and fresh-profile launch
2. Success-path startup and first-user setup
3. Empty-state route sweep
4. Shared-workspace and users/account-center setup
5. Receipt-pack import and connector inventory
6. Connector setup and sync matrix
7. Manual import
8. OCR, review queue, and quality
9. Finance workspace and supporting analysis retest after data import
10. Budget, bills, goals, cash flow, and reports
11. Backup, export, restore, and permission checks
12. Control Center reachability and fallback behavior
13. AI settings and chat
14. Final evidence capture

## Phase 1: Success-Path Startup And First-User Setup

On a healthy packaged build, desktop should boot into the full product flow, not stop in fallback mode.

Verify:

- the app launches without immediately crashing
- the packaged app auto-starts the backend on the success path
- the initial route lands on fresh first-user setup, login, or the finance app depending on the fresh profile state
- on a fresh database, the app reaches first-user setup without requiring a manual Control Center detour

For a fresh profile:

1. Confirm the app lands on fresh first-user setup.
2. Create the admin user.
3. Confirm redirect into the desktop finance app.
4. Log out once.
5. Log back in as admin.

If the app lands in the Control Center first, determine whether it is:

- explicit fallback because full-app boot failed
- control-center-only because frontend assets are missing
- an intentional manual launch surface that still allows a healthy transition into the main app

Do not accept fallback mode as normal success-path behavior without evidence.

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

## Phase 3: Shared Workspace, Users, And Account Center

Use `Settings -> Users` plus the shell preferences menu as the source of truth for the current collaboration model.

Verify:

- the shell preferences surface shows the signed-in user and active workspace together
- `Personal` is visible as a workspace option
- a shared-group workspace can be created if none exists
- the app can switch between personal and shared workspaces without silent behavior
- current account/session management is visible
- shared-group creation, edit, and member management are visible
- local user administration is visible
- agent keys are visible
- desktop backup and restore controls are visible

If the run starts with no shared group:

1. Create a temporary shared group.
2. Use `household` unless the current UI or test goal makes `community` more useful.
3. If safe and possible, create a temporary non-admin local user and add it to the shared group.

After the shared group exists:

1. Switch to it from the shell preferences menu.
2. Confirm the active workspace label changes.
3. Re-open at least one finance page and one settings page to prove the change is real.

If the UI exposes workspace destination or ownership metadata for sources, manual imports, documents, review items, or transactions, exercise it and record the observed behavior.

## Phase 4: Desktop Receipt Packs And Connector Inventory

Use the desktop Connectors page as the primary source of truth.

Import local ZIP receipt packs from `build/plugin-packs` for:

- `dm_de`
- `rewe_de`
- `kaufland_de`
- `netto_plus_de`

Enable imported packs explicitly if required.

Record:

- which ZIPs were imported
- which packs appeared as installed vs enabled
- any support/trust labeling shown by the packaged UI
- any update/install affordances exposed for trusted packs

## Phase 5: Connector Matrix

Use:

- `PASS_FULL`
- `PASS_PARTIAL_EXTERNAL_BLOCKER`
- `FAIL_PRODUCT`
- `NOT_PRESENT_IN_DESKTOP_BUILD`
- `NOT_IN_SCOPE`

### Built-ins surfaced by desktop

Attempt every connector the desktop build actually shows, including any Amazon marketplaces, Lidl Plus, or Rossmann if present.

### dm DE local pack

1. Import ZIP.
2. Enable it.
3. Run setup.
4. Complete browser login.
5. Run sync.
6. Run sync again once.
7. Verify downstream receipts or transactions.

### REWE DE local pack

1. Import ZIP.
2. Enable it.
3. Try normal setup first.
4. If challenged, log into REWE in normal Chrome only for the merchant-auth recovery step, leave the session available, rerun setup in desktop, and keep all actual route and UI validation inside the packaged desktop app.
5. Run sync.
6. Verify downstream receipts or transactions.

### Kaufland DE local pack

1. Import ZIP.
2. Enable it.
3. Complete auth.
4. Run sync.
5. Verify downstream receipts or transactions.

### Rossmann DE

If surfaced by desktop:

1. Use the surfaced desktop flow.
2. Complete setup.
3. Run sync.
4. Verify downstream receipts or transactions.

### Lidl Plus / Amazon

If surfaced by desktop:

1. Attempt setup.
2. If SMS, WhatsApp, CAPTCHA, or other human verification blocks progress, record the exact blocker and screenshot it.

### Netto Plus DE local pack

1. Import ZIP.
2. Enable it.
3. If no session bundle is provided, verify the pack imports and the setup flow clearly requests the bundle.

## Phase 6: Manual Import

Create at least three manual transactions in `/add`.

Recommended set:

- `QA Grocery Manual` total `23.45`
- `QA Internet Provider` total `44.99`
- `QA Streaming` total `10.99`

Verify they appear in `/transactions`.

If the current UI exposes workspace destination:

- create at least one record in `Personal`
- create at least one record in the shared workspace

Record the ownership behavior the UI actually shows.

## Phase 7: OCR, Review Queue, And Quality

Treat `/documents/upload` as the current OCR entrypoint and `/imports/ocr` as an older compatibility entrypoint that still needs explicit coverage if surfaced.

### OCR happy path on `/documents/upload`

1. Upload `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`.
2. Confirm OCR starts automatically or can be started from the packaged UI as rendered.
3. Capture visible status or timeline states.
4. If the UI exposes `Run OCR again`, use it once.
5. Follow the handoff into `/review-queue`.
6. Approve or correct the document if possible.
7. Verify a downstream receipt or transaction appears.

### OCR alternate or review-heavy path

1. Upload `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf`.
2. Use `/quality` and `/review-queue` as needed.
3. Edit, reject, or approve as appropriate.
4. Record whether it lands in review, approves cleanly, or fails.

### OCR rejection path

If a review item is suitable for rejection, test rejection once and verify the rejected state is visible.

### OCR compatibility entrypoint

If `/imports/ocr` is still surfaced:

1. Open it explicitly.
2. Verify whether it is a separate flow or an alias to the current document-upload surface.
3. Record what happened in the report.

### OCR failure triage

If OCR is broken, determine which layer appears broken instead of stopping at a generic failure:

- document upload
- OCR job start
- OCR worker wake-up
- status polling or timeline updates
- review queue handoff
- approval creating a downstream receipt or transaction

## Phase 8: Finance Workspace And Supporting Surfaces

Test these after data exists, not only in the empty state:

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

Also verify:

- `/receipts` still redirects to `/transactions`
- the app shell navigation remains coherent after imports and connector syncs
- the top-level workspace context is still understandable after data import

Repeat at least one meaningful finance page after switching workspaces so the run proves the workspace model affects real product surfaces.

## Phase 9: Budget, Bills, Goals, Cash Flow, And Reports

Create a synthetic monthly budget and several cash-flow entries.

Create recurring bills:

- `QA Internet Provider`
- `QA Streaming`
- `QA Rent`
- `QA Electricity`

Generate occurrences and reconcile at least one to a manual or imported transaction if possible.

Also verify:

- at least one goal can be created and remains visible afterward
- budget reconciliation candidates reflect available imported or manual data when present
- reports can export at least one JSON payload
- if the current workspace model is visible on these pages, the page behavior remains coherent after a workspace switch

## Phase 10: Backup, Export, Restore, And Permissions

Test desktop-native:

- backup
- export
- restore, if safe to do inside the fresh test profile

From `Settings -> Users`, create a non-admin user if you have not already done so.

Verify:

- admin sees admin-only controls
- non-admin does not see restricted details
- the account/session surfaces remain coherent after sign-out and sign-in

## Phase 11: Control Center Reachability And Fallback

The Control Center is no longer the default happy-path shell, but it still needs coverage as a fallback and local-tools surface.

Verify at least one of these:

- open the Control Center from setup, login, or signed-in preferences and confirm it loads
- launch once with a known-bad backend override and confirm fallback Control Center appears with diagnostic messaging

If the fallback Control Center appears, verify:

- desktop runtime diagnostics are visible if exposed
- the app explains whether it is in reduced fallback mode or control-center-only mode
- local tool actions that are still owned by the Control Center behave coherently

## Phase 12: AI Settings And Chat

In `/settings/ai`, explicitly verify:

- the ChatGPT / Codex connection area loads
- chat model selection is separate from item categorization settings
- item categorization controls render cleanly
- OCR settings or provider controls render as they exist in the current desktop build
- if a safe save round-trip is possible without introducing secrets or unsafe side effects, test one and record the result

For `/chat`, verify it opens from the packaged desktop shell and handles missing AI configuration cleanly when AI is not configured.

If the current desktop page intentionally hides some self-hosted-only AI/OCR controls, record that as correct desktop policy instead of a defect.

## Failure Logging Requirements

Whenever something fails:

1. capture a screenshot
2. capture exact UI text
3. note the route or connector id
4. note the packaged app path used
5. note the fresh profile path used
6. capture relevant terminal output
7. if Chrome fallback was used, record that it was limited to connector-auth recovery only

## Minimum Success Bar

At minimum, prove:

- fresh packaged desktop build
- fresh profile launch
- first-user setup on a fresh DB
- finance app or setup/login is the healthy success path
- finance workspace routes and supporting analysis surfaces load from the packaged app
- shared-workspace UX is visible and can be exercised
- Control Center remains reachable as a fallback/manual tool surface
- receipt-pack import works
- usable desktop connectors are genuinely attempted
- manual import works
- OCR and review queue work
- core analytics and planning pages work
- backup/export works
- admin vs non-admin behavior is checked
