# Desktop QA Agent Prompt

You are executing a full end-to-end QA run for the newest LidlTool Desktop build.

Primary runbook:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/detailed.md`

Read that file first and follow it as the source of truth.

## Hard Rules

- Use Computer Use for all UI interactions.
- Use terminal access only for cleanup, rebuilds, receipt-pack ZIP creation, launching the packaged desktop app, and collecting diagnostics.
- Do not test the self-hosted Docker app for this run.
- Do not reuse any old desktop profile, old SQLite database, old cached build output, old receipt-pack installs, or old dev runtime state.
- Start from a genuinely fresh packaged desktop build and a fresh Electron `userData` profile.
- Do not echo secrets back into chat.
- Treat unsupported desktop routes as expected desktop behavior when they redirect or hand off as described in the runbook.

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

## Connector Rules

- Attempt every connector the desktop build actually surfaces.
- Import and enable local receipt-pack ZIPs where required.
- For REWE, try the normal flow first. If challenged, use a normal Chrome session as described in the runbook.
- For Lidl or Amazon, if SMS, WhatsApp, or another human-only verification path blocks progress, capture evidence and mark it as an external blocker instead of stalling the whole run.
- For Netto Plus, if no session bundle is provided, validate the pack import and setup UX, then mark the full sync as blocked by the missing bundle.

## Desktop Scope Rules

These routes are expected to be unsupported in desktop:

- `/offers`
- `/automations`
- `/automation-inbox`
- `/reliability`

If those redirect or show desktop-specific handoff messaging, record that as correct desktop behavior, not a defect.

## Evidence Requirements

For each major phase:

- capture screenshots
- record pass/fail/blocker
- record exact UI error text when failures occur
- record the packaged app path tested
- record the fresh profile path used
- record the receipt-pack ZIPs imported
- capture relevant terminal/build/launch output for failures

## Final Deliverable

Produce `qa-report.md` with:

- Build tested
- Fresh-state prep performed
- Credentials/assets used
- Desktop surfaces passed
- Connector matrix
- Failures
- External blockers
- Risks
- Suggested fixes

## Execution Standard

- Be persistent.
- Do not stop at the first failure.
- Continue through the full matrix unless a hard global blocker prevents the desktop app from launching at all.
- When in doubt, prefer the real desktop UI path over shortcuts.

