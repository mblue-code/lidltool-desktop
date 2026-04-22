You are the lead orchestration agent for the repository at `/Volumes/macminiExtern/lidl-receipts-cli`.

Your mission is to implement the entire program defined in:
`/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-complete-mockup-implementation-plan.md`

The goal is to ship the desktop app all the way to the complete mockup-level experience, not a partial dashboard redesign. You must execute every sprint in that plan unless a hard blocker forces a pause. Do not stop after the shell, dashboard, or visual pass. The work is only complete when the full mockup-aligned product is implemented and packaged cleanly.

## Primary Visual Reference

Use this image as the canonical visual reference for the program:

- [Bildschirmfoto 2026-04-21 um 22.23.42.png](</var/folders/lx/x557b1416_zfcxl2m4gxkvwm0000gn/T/TemporaryItems/NSIRD_screencaptureui_KSq9Ck/Bildschirmfoto 2026-04-21 um 22.23.42.png>)

You must use this screenshot as the primary reference for:

- layout
- hierarchy
- density
- spacing rhythm
- dashboard composition
- left-rail shell structure
- top-bar structure
- panel mix and visual balance
- the overall feel of a polished light-theme finance desktop app

You must not copy the screenshot literally where it contains:

- unrelated branding
- unrelated product names
- merchant logos or merchant examples that do not belong to LidlTool
- invented sample balances, dates, or account numbers
- any domain assumptions that do not map to LidlTool’s real data model

Implementation rule:

- Translate the visual language of the screenshot into LidlTool’s real desktop product.
- Preserve the layout ambition and polish of the reference image.
- Adapt merchant, connector, and product concepts to LidlTool’s actual supported retailers and local-first receipt domain.

## First Step

Before making changes, read these files completely and treat them as binding constraints:

- `/Volumes/macminiExtern/lidl-receipts-cli/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/README.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-complete-mockup-implementation-plan.md`

Also inspect the current desktop shell and route structure before planning edits:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/shared/desktop-route-policy.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/main.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/TransactionsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/analytics/queries.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/budget/service.py`

## Non-Negotiable Constraints

You must preserve all of the following:

1. `apps/desktop` behaves like a standalone side repo.
2. Do not add runtime or build-time dependencies on `../../*` paths inside desktop runtime code.
3. Anything needed at desktop runtime must live inside `apps/desktop` after vendoring/sync.
4. Desktop remains local-first and control-center-first.
5. Do not redesign desktop into an always-on server product.
6. Do not remove the control center or break shell-first startup.
7. Do not weaken packaged build behavior to speed up implementation.
8. Do not leave desktop docs stale.
9. If a feature belongs upstream, implement it upstream first if appropriate, then vendor/sync it into desktop cleanly.
10. If a desktop-only patch remains necessary, keep it narrow, explicit, and documented.

## Product Outcome You Must Deliver

The finished desktop product must include:

- a dashboard-first finance shell
- first-class navigation for:
  - `Dashboard`
  - `Transactions`
  - `Groceries`
  - `Budget`
  - `Bills`
  - `Cash Flow`
  - `Reports`
  - `Goals`
  - `Merchants`
  - `Settings`
- a mockup-level dashboard with:
  - greeting/header
  - global date-range picker
  - notification entry point
  - KPI cards with deltas
  - spending overview
  - cash flow summary
  - upcoming bills
  - recent grocery transactions
  - budget progress
  - recent activity
  - smart tip / insight banner
- real pages for:
  - `Groceries`
  - `Cash Flow`
  - `Reports`
  - `Goals`
  - `Merchants`
- notification center and unread state
- packaged desktop compatibility with fresh-profile validation

## Program Rule

The plan file is the source of truth. Execute it sprint by sprint.

The plan currently defines these sprints:

- Sprint 0: Product spec lock and setup
- Sprint 1: IA, routes, app shell
- Sprint 2: Visual foundation and component system
- Sprint 3: Global date context, comparison semantics, summary APIs
- Sprint 4: Dashboard core layout
- Sprint 5: Dashboard secondary panels
- Sprint 6: Groceries workspace
- Sprint 7: Transactions and receipt modernization
- Sprint 8: Cash Flow and Bills experience
- Sprint 9: Reports workspace
- Sprint 10: Goals domain and Goals page
- Sprint 11: Merchants workspace
- Sprint 12: Notifications and insight engine
- Sprint 13: Hardening, QA, packaging
- Sprint 14: Release candidate and final ship

You must execute all of them.

## Execution Mode

Operate like a real technical program lead plus implementation lead.

For each sprint:

1. Re-state the sprint objective in concrete engineering terms.
2. Inspect the current code paths affected.
3. Create a short implementation checklist for that sprint.
4. Implement the sprint completely.
5. Run relevant tests and build checks.
6. Fix the regressions introduced by that sprint.
7. Update docs and the plan file with implementation status.
8. Commit only if explicitly requested by the user.

Do not just discuss work. Do the work.

## Required Working Style

- Be autonomous.
- Prefer concrete implementation over planning chatter.
- Use the repo’s actual architecture, not imagined abstractions.
- Reuse existing data and services where possible.
- Introduce new schema/API surfaces only where the plan requires real domain expansion.
- Keep changes coherent and incremental.
- Never leave half-migrated route structures or duplicate temporary shells behind.
- When adding new pages, wire them into:
  - routes
  - shell nav
  - page loaders
  - i18n
  - tests
- When adding backend features, wire them into:
  - API layer
  - services/query logic
  - migrations if needed
  - frontend API client
  - page/module consumers
  - contract tests

## Required Documentation Behavior

You must keep this file up to date as implementation proceeds:
`/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/desktop-complete-mockup-implementation-plan.md`

For each sprint, append or update:

- implementation status
- decisions made
- files changed
- deferred issues
- blockers
- verification performed

Also update:
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/README.md`
when desktop behavior, routes, workflows, or packaging expectations change.

## Technical Direction To Follow

### Shell and Routes
You must reshape the desktop app shell into a finance-first product shell.
Primary files likely include:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/shared/desktop-route-policy.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/main.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/app/page-loaders.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/i18n/messages.ts`

### New Pages To Create
You are expected to add and fully implement these if they do not exist yet:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/GroceriesPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`

### New Backend Surfaces
You are expected to add or expand backend APIs for:

- dashboard overview aggregation
- KPI delta/comparison data
- activity feed
- insights/tips
- grocery summaries
- merchant summaries
- goals CRUD/progress
- notifications list/update
- reports/templates/export payloads

Primary backend files likely include:

- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/analytics/queries.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/budget/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/recurring/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/db/models.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/src/lidltool/db/migrations/versions/*`

### Required New Domain Work
You must treat these as real product work, not fake placeholders:

- `Goals`
- `Notifications`
- likely `Reports` persistence if needed for a clean UX

### Visual Standard
The product must feel like a polished finance desktop app, not a generic admin dashboard.
Favor:

- strong hierarchy
- restrained but premium styling
- clear chart/readability
- real dashboard composition
- responsive laptop-friendly layout
- coherent empty/loading/error states

Evaluate all visual work against the screenshot reference. If a UI decision weakens alignment with the screenshot’s layout quality, density, or visual coherence, redesign it instead of accepting a weaker approximation.

Do not settle for a shallow card grid or “close enough” UI.

## Testing And Verification Rules

After each sprint, run the most relevant checks. At minimum, maintain:

- `npm run typecheck` from `apps/desktop`
- `npm run build` from `apps/desktop`

Also run relevant targeted tests as changes require, including current and newly added suites.

You are expected to update and/or extend:

- page tests
- app shell tests
- contract tests
- accessibility-critical tests
- e2e coverage where needed

Before declaring the program complete, validate a packaged desktop run against a fresh profile.

## Fresh-Profile Packaging Requirement

Before final completion, verify the desktop product from a fresh desktop profile using the packaged app path, not only dev mode.

Preserve the desktop shell-first model and confirm the main app opens into the finished finance shell cleanly.

## Progress Reporting

At the start of work, produce a short implementation rollout showing:
- sprint currently in progress
- major files likely to change
- expected verification for that sprint

While working:
- keep updates concise
- report real progress, not intentions
- mention blockers immediately if they are genuine

At the end of each sprint:
- summarize what was completed
- list files changed
- list tests/builds run
- state whether the sprint is fully done or what remains

## Completion Standard

You are not done until all of the following are true:

- the shell/nav matches the planned finance IA
- dashboard includes all mockup-required modules
- `Transactions`, `Groceries`, `Budget`, `Bills`, `Cash Flow`, `Reports`, `Goals`, and `Merchants` are all real and wired
- notification bell and notification center are implemented
- smart tip / insight layer is implemented
- desktop docs are updated
- builds pass
- packaged desktop flow is verified from a fresh profile

## Failure Conditions

Do not do any of the following:

- stop after the dashboard and call it complete
- leave new routes untested
- add fake placeholder pages just to satisfy nav structure
- break desktop side-repo isolation
- rely on demo fixtures as final product behavior
- weaken packaging or startup constraints to move faster
- silently defer goals, merchants, notifications, or reports

## Start Now

Begin with Sprint 0 and Sprint 1.
Read the required files, inspect the current implementation, produce a concise execution checklist, then start making the code changes.
