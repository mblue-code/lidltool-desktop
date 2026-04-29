# Manual App Issue Tracker

Opened: 2026-04-27
Scope: Interactive manual testing of the desktop app from the current fresh-profile launch
Tracking mode: Append issues from this chat as they are reported

## Session Context

- App repo: `outlays-desktop`
- Test mode: normal app build
- Profile root: `/tmp/outlays-desktop-fresh-0c7FcH`
- Fresh database: `/tmp/outlays-desktop-fresh-0c7FcH/electron-user-data/lidltool.sqlite`

## Issue Template

For each issue, record:

- ID
- Title
- Status
- Severity
- Area
- Repro steps
- Expected result
- Actual result
- Screenshot
- Notes

## Issues

### ISSUE-006

- ID: `ISSUE-006`
- Title: Goal scoping is too limited for merchant-specific and multi-category spending caps
- Status: `open`
- Severity: `high`
- Area: `goals`, `scoping`, `categories`, `merchants`
- Repro steps:
  1. Open the `Ziele` page and create or review spending-related goals.
  2. Try to define a monthly spending target for a specific merchant such as `Amazon`.
  3. Try to define a category-based goal for one category such as `meat`.
  4. Try to define a goal that combines multiple categories under one shared cap, such as a broader `leisure` goal.
- Expected result:
  - Users should be able to create merchant-specific spend caps, for example: do not spend more than `150 EUR` at `Amazon` next month.
  - Users should be able to create category-based spend caps from a dropdown populated from categories already present in the database, instead of relying on raw free-text entry.
  - Users should be able to attach more than one category to a single goal so one cap can track a grouped concept such as leisure spending across multiple categories.
- Actual result:
  - The current goal model/form does not provide a clear, structured way to create merchant-specific monthly limits.
  - Category targeting is too limited for the desired use case and does not support selecting multiple categories for one goal.
  - This prevents users from expressing realistic budgeting goals such as merchant-specific caps or grouped-category limits.
- Screenshot:
  - [Bildschirmfoto 2026-04-27 um 16.13.17.png](</var/folders/lx/x557b1416_zfcxl2m4gxkvwm0000gn/T/TemporaryItems/NSIRD_screencaptureui_D1480m/Bildschirmfoto 2026-04-27 um 16.13.17.png>)
- Notes:
  - A good UX would likely use searchable dropdowns or multi-select controls instead of free-text fields.
  - Category choices should be sourced from existing normalized category data in the database.
  - This remains open after the 2026-04-28 remediation pass because it requires an end-to-end model/API/UI feature: merchant-scoped caps, structured category lookup, and multi-category goal membership. It was not implemented in this pass.
