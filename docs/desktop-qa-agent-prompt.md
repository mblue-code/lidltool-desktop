# Desktop QA Agent Prompt

You are executing a full end-to-end QA run for the newest LidlTool Desktop build.

Primary runbook:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-qa-runbook.md`

Read that file first and follow it as the source of truth.

This prompt extends the runbook with the current regression focus for the finance-first packaged desktop app, the shared-workspace model, and the current OCR/import flows. Do not fall back to older control-center-first assumptions unless the runbook or current build evidence shows that fallback mode was intentionally triggered.

## Product Truths For This Run

- A healthy packaged desktop build should reach `/setup`, `/login`, or the full finance shell.
- The Control Center is still required test surface coverage, but it is now a fallback or explicitly opened local-tools surface, not the default happy-path product shell.
- The current desktop shell is workspace-aware. Personal and shared-group workspaces are first-class product behavior and must be covered during QA.
- Older prompts, older screenshots, and older Playwright expectations may still assume a Control Center-first launch. Treat that as stale unless the current build proves otherwise.

## Hard Rules

- Use Computer Use for all UI interactions.
- Use terminal access only for cleanup, rebuilds, receipt-pack ZIP creation, launching the packaged desktop app, and collecting diagnostics.
- Do not test the self-hosted Docker app for this run.
- Do not reuse any old desktop profile, old SQLite database, old cached build output, old receipt-pack installs, or old dev runtime state.
- Start from a genuinely fresh packaged desktop build and a fresh Electron `userData` profile.
- Do not echo secrets back into chat.
- Treat intentionally unsupported desktop routes as correct behavior when they redirect or hand off as described in the runbook.
- Use Chrome only when the runbook explicitly allows it for connector-auth recovery or challenge handling. Do not use Chrome as a substitute for packaged desktop route, shell, or OCR validation.

## Fresh Start Requirements

You must:

1. Work in `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop`.
2. Kill any running LidlTool Desktop processes.
3. Run the fresh-state cleanup and rebuild procedure from the runbook exactly, including `npm run clean`.
4. Rebuild the newest packaged desktop app from scratch.
5. Build the local receipt-pack ZIPs described in the runbook into the current QA pack output directory.
6. Launch the packaged desktop app with:

```bash
LIDLTOOL_DESKTOP_USER_DATA_DIR=/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/e2e-user-data
```

7. Confirm the app is using that fresh profile and not any previous profile.

## Credentials And Omissions

Use the values already recorded in:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-qa-runbook.md`

Interpret omissions exactly like this:

- `INTENTIONALLY_NOT_PROVIDED`:
  do not block the run trying to obtain these credentials; attempt only the validation depth the runbook allows and mark the area as intentionally unavailable or externally blocked.
- `OPTIONAL_NOT_PROVIDED`:
  do not treat this as a blocker for the whole run; skip or partially validate as instructed in the runbook.
- `AGENT_MAY_CREATE_TEMPORARY_QA_ADMIN` / `AGENT_MAY_CREATE_TEMPORARY_QA_VIEWER`:
  create temporary desktop-local users during setup and users-settings phases if needed.

## OCR Assets

Use these files during the OCR phases:

- `/Volumes/macminiExtern/DevData/Downloads/38c2032c-3acb-4a74-ac58-7ae5b5af820c.pdf`
- `/Volumes/macminiExtern/DevData/Downloads/REWE eBon Apr 18 2026.pdf`

Treat the first PDF as the primary OCR case and the REWE eBon PDF as the alternate or review-heavy case.

## Current Regression Focus

This run must explicitly cover the current packaged desktop IA and the newer shared-workspace behavior:

- healthy success-path launch into `/setup`, `/login`, or the finance shell
- app shell navigation and the finance workspace layout
- explicit workspace identity and switching between `Personal` and shared-group workspaces
- `/`
- `/dashboard` redirecting to `/`
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
- `/settings/users`
- `/connectors`
- `/sources`
- `/add`
- `/imports/manual`
- `/documents/upload`
- `/imports/ocr` if still surfaced
- `/review-queue`
- `/quality`
- `/explore`
- `/products`
- `/compare`
- `/patterns`
- `/chat`

Treat these as required regression targets unless the packaged build itself proves a route is absent or intentionally unsupported.

## Shared-Workspace Regression Sweep

You must explicitly validate the newer collaboration model, not just the older single-user flow.

At minimum:

- verify the preferences surface shows the signed-in user and active workspace together
- verify the workspace switcher exposes `Personal` and any created shared groups
- create at least one shared group from `Settings -> Users` if the fresh run starts with none
- create a temporary non-admin desktop user if needed to exercise membership/admin UX
- verify shared-group management, membership, local user administration, session controls, agent keys, and backup/restore surfaces in `Settings -> Users`
- verify at least one finance surface after switching workspaces so the run proves the workspace change is not cosmetic
- if the UI exposes workspace destination or ownership controls for sources, manual imports, documents, or review items, exercise them and record the observed ownership behavior

Use `household` or `community` shared-group language as rendered by the app. Do not describe the feature as a legacy family-overlay if the current UI and behavior have moved beyond that model.

## Connector Rules

- Attempt every connector the packaged desktop build actually surfaces.
- Import and enable local receipt-pack ZIPs where required.
- For REWE, try the normal flow first. If challenged, use a normal Chrome session only for the merchant-auth recovery path described in the runbook, then return to the packaged desktop app for the actual QA flow.
- For Lidl or Amazon, if SMS, WhatsApp, or another human-only verification path blocks progress, capture evidence and mark it as an external blocker instead of stalling the run.
- For Netto Plus, if no session bundle is provided, validate the pack import and setup UX, then mark the full sync as blocked by the missing bundle.

## OCR Regression Sweep

Treat OCR as a first-class regression target.

You must test both:

- the current document-upload OCR flow at `/documents/upload`
- the older `/imports/ocr` entrypoint if it is still surfaced in desktop

When OCR fails, do not stop at a generic failure. Determine which layer appears broken:

- document upload
- OCR job start
- OCR worker/runtime wake-up
- status polling or timeline updates
- review queue handoff
- approval creating a downstream receipt or transaction

Record the precise failing step, exact UI text, and any relevant terminal output.

## Control Center Coverage

The Control Center still needs explicit coverage, but only as a fallback or explicitly opened local-tools surface.

You must verify at least one of these:

- open it from setup, login, or signed-in preferences and confirm it loads
- trigger a known fallback condition supported by the runbook and confirm the Control Center appears with diagnostics

Do not downgrade the entire QA run to the old Control Center-first happy path unless the packaged build actually failed to reach the finance app.

## Evidence Requirements

For each major phase:

- capture screenshots
- record pass/fail/blocker
- record exact UI error text when failures occur
- record the packaged app path tested
- record the fresh profile path used
- record the receipt-pack ZIPs imported
- capture relevant terminal/build/launch output for failures
- record whether success-path boot landed directly in setup/login/full app or fell back first
- record which finance-shell and shared-workspace surfaces were re-tested after data import
- record whether `/documents/upload` OCR passed, failed, or was externally blocked
- record whether `/imports/ocr` is still present and what happened there
- record whether any Chrome fallback was used and confirm it stayed limited to connector auth recovery

## Final Deliverable

Produce the report and evidence bundle in the output location defined by the runbook, including:

- Build tested
- Fresh-state prep performed
- Credentials and assets used
- Desktop surfaces passed
- Shared-workspace regression coverage
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
- Continue through the full matrix unless a hard global blocker prevents the packaged desktop app from launching at all.
- When in doubt, prefer the real packaged desktop UI path over shortcuts.
