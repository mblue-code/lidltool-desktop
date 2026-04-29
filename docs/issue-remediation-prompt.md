# Issue Remediation Prompt

Use this prompt for a focused remediation pass on the current manual QA findings in the desktop app.

---

You are working in the repo `/Volumes/macminiExtern/projects/lidltool-desktop`.

Your job is to fix the currently logged manual QA issues in the desktop app, verify each fix properly, and then remove only the tracker entries that are fully fixed and fully tested.

## Source of truth

The current issue tracker is:

- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/manual-app-issue-tracker.md`

Treat that file as the authoritative list of issues to address in this pass.

## High-level objective

Do a real remediation pass, not a paper pass.

That means:

1. Read the issue tracker carefully.
2. Reproduce each issue where practical.
3. Inspect the relevant frontend/backend/runtime code.
4. Implement real fixes.
5. Run the appropriate validation for each fix.
6. Manually verify the fix in the app where needed.
7. Only after a fix is confirmed working, remove that issue entry from the tracker.

If an issue is only partially fixed, not confidently verified, or blocked by a larger follow-up, do not delete it from the tracker. Instead, keep it and update it if needed.

## Non-negotiable rules

- Do not invent status.
- Do not delete any tracker issue unless it is fully fixed and tested.
- Do not mark something done because the code “looks right”.
- Prefer targeted, defensible fixes over broad speculative refactors.
- Preserve existing user changes in the worktree.
- Do not revert unrelated changes.
- Respect the repo’s side-repo isolation rules from `AGENTS.md`.

## Required workflow

### 1. Initial review

- Read:
  - `AGENTS.md`
  - `README.md`
  - `docs/manual-app-issue-tracker.md`
- Summarize the current issue list in your own words before changing code.
- Group issues by subsystem:
  - connectors / merchants
  - dashboard empty state and date range
  - reports export UX
  - goals / savings-target UX and logic
  - desktop shell branding

### 2. Reproduce and map each issue

For every open issue still in the tracker:

- identify the exact UI surface
- identify the likely frontend file(s)
- identify the likely backend/service file(s), if any
- decide whether the issue is:
  - pure UI
  - UI + state wiring
  - backend contract / logic
  - packaging/runtime
  - product-model mismatch

### 3. Fix implementation

Work issue-by-issue or by tightly related group.

When implementing:

- keep fixes scoped
- avoid unrelated cleanup
- preserve the existing design system unless the issue specifically requires visual redesign
- add or adjust tests where the repo already has coverage in that area

### 4. Validation requirements

For every issue you claim fixed, do all relevant validation that applies:

- `npm run typecheck`
- `npm run build`
- relevant targeted frontend/backend tests if they exist
- manual in-app verification using the current desktop app run

If an issue is visual or interaction-based, code-only validation is not enough. Manually verify it in the app.

### 5. Tracker cleanup rules

After a fix is implemented and validated:

- delete that issue entry from `docs/manual-app-issue-tracker.md`

If not fully fixed:

- keep the issue entry
- optionally tighten wording or split it if you discovered two distinct issues

Never delete issues in bulk without per-issue verification.

## Current issues to address

At the time of this prompt, the tracker contains these issues:

### ISSUE-001

Merchant surfaces show external and built-in connectors as connected on a fresh profile.

Fix goals:

- Rossmann must not appear by default if it is an external plugin-only connector.
- Built-in availability must not be shown as “connected” when the user has not actually connected/authenticated the merchant.
- Dashboard merchant card and merchants page must agree on the corrected state model.

Likely areas:

- connectors/merchant frontend pages
- connector status APIs / derived status mapping
- desktop/plugin pack integration logic

### ISSUE-002

The dashboard spending overview chart has a poor empty state on first launch.

Fix goals:

- remove the awkward empty donut state or replace it with a deliberate, polished empty-state presentation
- make first-run dashboard experience feel intentional

Likely areas:

- dashboard cards/components
- chart empty-state logic

### ISSUE-003

Dashboard date labels do not stay in sync with the selected date scope.

Fix goals:

- top-right date range label must update correctly when scope changes
- date shown inside the dashboard hero/box must also update correctly
- all dashboard date labels must derive from the same selected range state

Likely areas:

- date range context/provider
- dashboard page bindings
- any duplicated date-label calculation

### ISSUE-004

Reports page over-advertises JSON export and does not foreground user-friendly formats.

Fix goals:

- determine what export formats are already supported vs missing
- if CSV/Excel/PDF support already exists, surface them appropriately
- if only JSON exists today, redesign the UX/copy so JSON is not misleadingly presented as the primary end-user reporting format, or implement better user-facing export support if feasible in scope

Likely areas:

- reports page frontend
- report export API/backend
- export templates / payload generation

### ISSUE-005

Savings target goals are implemented, but the UI is misleading and the goal card styling is broken.

Known code facts already established:

- `savings_target` is a real backend goal type
- progress is currently computed as `max(total inflow - total outflow, 0)` over the selected window
- target date affects status timing
- some form fields shown in the UI are not actually used by savings-target progress logic
- goal board styling in dark mode is visually wrong

Fix goals:

- correct the washed-out goal card styling
- make the savings-target creation/editing experience reflect what the system really tracks
- hide or adapt irrelevant fields for savings-target goals if they are not used
- improve clarity around how savings progress is calculated

Likely areas:

- `vendor/frontend/src/pages/GoalsPage.tsx`
- goals API contracts
- `vendor/backend/src/lidltool/goals/service.py`

### ISSUE-006

Goal scoping is too limited for merchant-specific and multi-category spending caps.

Fix goals:

- support merchant-specific spending limits such as “no more than 150 EUR at Amazon next month”
- support category-driven goals using structured category selection from known categories
- support multiple categories attached to one goal
- ensure backend model and UI support the richer scoping cleanly

Important note:

This may be a larger feature than a bug fix. If it is too large for one pass, do not fake completion. Either implement fully and verify it, or leave it in the tracker with refined wording and an honest remaining scope.

### ISSUE-007

The running app shows the default Electron dock icon instead of the LidlTool Desktop icon.

Fix goals:

- ensure the actual running app shows the correct branded icon in the dock
- verify whether this is a dev-launch-only problem, a built-app problem, or both

Likely areas:

- Electron main process window/app icon setup
- build resources / runtime icon path
- packaged vs dev launch behavior

## Suggested execution order

Use this order unless code inspection reveals a better dependency chain:

1. ISSUE-007
2. ISSUE-003
3. ISSUE-002
4. ISSUE-001
5. ISSUE-005
6. ISSUE-004
7. ISSUE-006

Reasoning:

- branding and dashboard/date issues are relatively contained
- connectors status mismatch is high-impact and likely has shared state implications
- goals work may require both UI and domain decisions
- multi-category / richer goal scoping is likely the largest item

## Goal-specific guidance

### For dashboard and date-range issues

- centralize the selected date range if it is duplicated
- verify every visible dashboard label derives from the same state
- confirm “this week”, “last 7 days”, “this month”, and “last month” produce distinct labels

### For goals issues

- inspect both `vendor/frontend` and `overrides/frontend`
- verify what the backend truly supports before changing the UI contract
- if multi-category support requires schema/API changes, implement them cleanly end-to-end or explicitly leave the issue open
- do not leave the UI pretending a field matters if the backend ignores it

### For reports issues

- distinguish between “format exists but is hidden” and “format does not exist yet”
- if a format does not exist, do not merely rename JSON to something friendlier
- make the UX honest and useful

### For connectors issues

- separate these concepts clearly:
  - built-in connector exists
  - connector/plugin is installed
  - connector is enabled
  - connector is authenticated/connected
  - connector has synced data

The UI should not collapse those into one “connected” badge.

## Required final output

When done, provide:

1. a short summary of what was fixed
2. a list of which tracker issues were removed because they were fully fixed and verified
3. a list of which tracker issues remain and why
4. the exact validation performed
5. any follow-up risks or design decisions that still need product direction

## Definition of done

This task is done only when:

- code changes are implemented
- relevant checks pass
- manual verification is completed for each claimed fix
- fully fixed issues are removed from `docs/manual-app-issue-tracker.md`
- unresolved issues remain in the tracker

If you are uncertain about a fix, keep the issue in the tracker.

---

End of prompt.
