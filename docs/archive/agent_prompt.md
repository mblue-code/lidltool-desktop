> Archived note: this file is kept as a historical snapshot.
> For current manual QA guidance, use `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-qa-agent-prompt.md`
> together with `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-qa-runbook.md`.
> The path references and execution details below are obsolete for current runs.

# Desktop QA Agent Prompt

You are executing a full end-to-end QA run for the newest LidlTool Desktop build.

Primary runbook:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/detailed.md`

Read that file first and follow it as the source of truth.

This prompt extends that runbook with the current regression focus from the latest desktop finance-first product update. Treat `detailed.md` as the source of truth for setup and execution mechanics, but use this prompt to update the route expectations, success-path behavior, and regression priorities to the current desktop financial outlook.

On the success path, the packaged desktop build should boot directly into the finance workspace. The Control Center should now be treated as a fallback or explicitly opened tools surface, not the default happy-path landing screen.

## Hard Rules

- Use Computer Use for all UI interactions.
- Use terminal access only for cleanup, rebuilds, receipt-pack ZIP creation, launching the packaged desktop app, and collecting diagnostics.
- Do not test the self-hosted Docker app for this run.
- Do not reuse any old desktop profile, old SQLite database, old cached build output, old receipt-pack installs, or old dev runtime state.
- Start from a genuinely fresh packaged desktop build and a fresh Electron `userData` profile.
- Do not echo secrets back into chat.
- Treat unsupported desktop routes as expected desktop behavior when they redirect or hand off as described in the runbook.
- Do not treat Control Center-first boot on a healthy packaged build as correct success-path behavior unless the runbook or current build evidence proves fallback mode was intentionally triggered.
- Use Chrome only when the runbook explicitly allows it for connector authentication recovery or challenge handling. Do not use Chrome to validate desktop routes, app shell behavior, or packaged-app UI flows.

## Fresh Start Requirements

You must:

1. Work in `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`.
2. Kill any running LidlTool Desktop processes.
3. Delete stale build/profile state exactly as described in `detailed.md`.
4. Rebuild the newest packaged desktop app from scratch.
5. Build the local receipt-pack ZIPs described in `detailed.md`.
6. Launch the packaged desktop app with:

```bash
LIDLTOOL_DESKTOP_USER_DATA_DIR=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data
```

7. Confirm the app is using that fresh profile and not any previous profile.

## Credentials And Omissions

Use the values already recorded in:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/detailed.md`

Interpret omissions exactly like this:

- `INTENTIONALLY_NOT_PROVIDED`:
  do not block the run trying to obtain these credentials; attempt only the level of validation the runbook allows and mark the area as intentionally unavailable or externally blocked.
- `OPTIONAL_NOT_PROVIDED`:
  do not treat this as a required blocker for the whole run; skip or partially validate as instructed in the runbook.
- `AGENT_MAY_CREATE_TEMPORARY_QA_ADMIN` / `AGENT_MAY_CREATE_TEMPORARY_QA_VIEWER`:
  create temporary desktop-local users during the first-user setup and users-settings phases if needed.

## OCR Assets

Use these files during the OCR phases:

- `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`
- `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf`

Treat the first PDF as the primary OCR case and the REWE eBon PDF as the alternate/review-path OCR case.

## Current Regression Focus

The latest desktop changes added or materially changed the finance-first shell and surrounding desktop analysis surfaces. This QA run must explicitly cover them, not just the older baseline flows:

- success-path finance-shell boot
- app shell navigation and the current desktop finance workspace layout
- `/` dashboard overview
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
- `/imports/manual`
- `/documents/upload` as the current OCR document-upload path
- `/review-queue`
- `/quality`
- `/sources`
- `/explore`
- `/products`
- `/compare`
- `/patterns`
- `/chat`

Treat these as required regression targets for this run. The goal is to confirm the newest packaged desktop build still works across the full user journey after the latest UI and settings changes.

## Connector Rules

- Attempt every connector the desktop build actually surfaces.
- Import and enable local receipt-pack ZIPs where required.
- For REWE, try the normal flow first. If challenged, use a normal Chrome session only for the merchant-auth recovery path described in the runbook, then return to the packaged desktop app for the actual QA flow.
- For Lidl or Amazon, if SMS, WhatsApp, or another human-only verification path blocks progress, capture evidence and mark it as an external blocker instead of stalling the whole run.
- For Netto Plus, if no session bundle is provided, validate the pack import and setup UX, then mark the full sync as blocked by the missing bundle.

## Desktop Scope Rules

The route sweep must reflect the current packaged desktop IA, not the older control-center-first model.

Treat these as current supported or testable desktop routes if they are present in the packaged build:

- `/`
- `/dashboard` redirecting to `/`
- `/transactions`
- `/receipts` redirecting to `/transactions`
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
- `/settings/users`
- `/documents/upload`
- `/review-queue`
- `/chat`

These routes are expected to be unsupported in desktop:

- `/offers`
- `/automations`
- `/automation-inbox`
- `/reliability`

If those redirect or show desktop-specific handoff messaging, record that as correct desktop behavior, not a defect.

## Required Regression Coverage

### Finance workspace regression sweep

After success-path launch, after first-user setup, and again after receipts exist, verify all of these in the real packaged desktop UI:

- healthy packaged launch lands in `/setup`, `/login`, or the finance app rather than stopping in the Control Center
- sidebar navigation renders the current finance workspace destinations and they route correctly
- dashboard shows finance overview cards and usable downstream sections
- transactions renders the canonical receipt or ledger history view and `/receipts` redirects correctly if exercised
- groceries shows category mix and recent purchase activity
- budget supports budget month editing, cashflow entry creation, and receipt reconciliation where possible
- bills supports creating or viewing recurring obligations without breaking the finance shell
- cash flow shows inflow, outflow, remaining, upcoming bills, and ledger rows
- reports exposes report templates and can export at least one JSON payload
- goals supports creating at least one goal and shows it in the list afterward
- merchants shows connected merchant cards, status labels, and searchable merchant directory data
- settings loads the desktop settings hub and keeps desktop-only controls reachable from the finance shell
- settings/ai loads the current ChatGPT/Codex, categorization, and OCR settings surfaces without breaking

Use real data created during this run whenever possible. If a surface is empty because upstream data never arrived, record that as a downstream consequence of the earlier failure, not as "untested".

### Supporting desktop workflows sweep

Explicitly verify that the current non-nav but still-supported desktop workflows remain reachable and coherent from the packaged finance app:

- connectors shows pack install, enable/disable, trust/support labeling, and surfaced merchant actions
- add and imports/manual still support manual entry without forcing the run back through the Control Center
- documents/upload and imports/ocr are both checked, with notes on whether they are distinct flows or the same desktop upload surface
- review-queue and quality remain reachable from OCR and review-heavy paths
- sources, explore, products, compare, and patterns still render as supporting analysis surfaces
- chat opens from the packaged desktop shell and handles missing AI configuration cleanly if not configured

### Control Center fallback coverage

The Control Center still needs regression coverage, but only as a fallback/manual surface.

Explicitly verify at least one of these:

- open it from setup, login, or signed-in preferences and confirm it loads
- trigger a known fallback condition if the runbook supports that and confirm the Control Center appears with diagnostics

Do not downgrade the run to the old control-center-first happy path unless the desktop build actually failed to boot the finance app.

### AI settings regression sweep

In `/settings/ai`, explicitly verify:

- the ChatGPT / Codex connection area loads
- chat model selection is separate from item categorization settings
- item categorization controls render and can be inspected without corrupting chat settings
- the OCR settings section renders current provider controls, including primary provider and fallback controls
- if saving settings is possible without introducing secrets or unsafe side effects, verify at least one safe save round-trip and record the exact result

If credentials or provider access are not available, still verify the page behavior, surfaced state, validation, and any disabled-state messaging.

### OCR regression sweep

Treat OCR as a first-class regression target.

You must test both:

- the current document-upload OCR flow at `/documents/upload`
- the older OCR import entrypoint at `/imports/ocr` if it is still surfaced in desktop

For `/documents/upload`, explicitly verify:

1. upload the primary PDF
2. confirm OCR starts automatically after upload or can be started from the packaged UI as rendered
3. capture the visible status/timeline states
4. if the UI exposes `Run OCR again`, use it once
5. follow the handoff into `/review-queue`
6. approve or correct the document if possible
7. verify a downstream receipt or transaction appears

For the alternate OCR asset, explicitly try to exercise a review-heavy path:

1. upload the REWE eBon PDF
2. observe whether it lands in review, approves cleanly, or fails
3. use `/review-queue` and `/quality` as needed
4. if a rejection path is possible, test it once and verify the rejected state is visible

If OCR is broken, do not stop at "OCR failed". Determine which layer appears broken:

- document upload
- OCR job start
- OCR worker/runtime wake-up
- status polling/timeline updates
- review queue handoff
- approval creating a downstream receipt/transaction

Record the precise failing step, exact UI text, and any relevant terminal output.

### Connector-to-analytics propagation

After successful connector syncs and after OCR/manual imports, re-check that the new finance surfaces reflect the fresh data where applicable:

- dashboard
- transactions
- groceries
- merchants
- goals
- cash flow
- bills
- budget reconciliation candidates
- reports templates or exports if they depend on current data

## Evidence Requirements

For each major phase:

- capture screenshots
- record pass/fail/blocker
- record exact UI error text when failures occur
- record the packaged app path tested
- record the fresh profile path used
- record the receipt-pack ZIPs imported
- capture relevant terminal/build/launch output for failures
- record whether the success-path boot landed directly in the finance app or fell back
- record which of the new finance workspace surfaces were explicitly re-tested after data import
- record whether `/documents/upload` OCR passed, failed, or was externally blocked
- record whether `/imports/ocr` is still present and what happened there
- record whether any Chrome fallback was used and confirm it was limited to connector auth rather than desktop UI testing

## Final Deliverable

Produce `qa-report.md` with:

- Build tested
- Fresh-state prep performed
- Credentials/assets used
- Desktop surfaces passed
- Finance workspace regression coverage
- Connector matrix
- OCR regression result
- Failures
- External blockers
- Risks
- Suggested fixes

## Execution Standard

- Be persistent.
- Do not stop at the first failure.
- Continue through the full matrix unless a hard global blocker prevents the desktop app from launching at all.
- When in doubt, prefer the real desktop UI path over shortcuts.
