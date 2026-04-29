# Desktop Complete Mockup Implementation Plan

## Status

- Proposed on `2026-04-21`
- Target surface: `apps/desktop`
- Goal: ship the desktop app all the way to the mockup-level experience, not just a visual approximation
- Program execution started on `2026-04-21`
- Sprint `0` is complete
- Sprint `1` is complete
- Sprint `2` is partially started through shell tokens and finance-shell styling, but the component-system pass remains open

## Locked Product Decisions

- `Overview` is replaced by `Dashboard` as the primary product label.
- `/` remains the canonical dashboard route and `/dashboard` is a redirect alias.
- `Transactions` is the canonical finance-history route and `/receipts` is a compatibility redirect to `/transactions`.
- `Budget` remains singular to match the existing budgeting domain and API surface.
- `Settings` is a first-class finance-shell destination at `/settings`, while `/settings/ai` and `/settings/users` remain task-specific deep routes.
- Merchant summaries are hybrid:
  connector identity and status come from connector/source data, while spend and receipt concentration come from transaction history with canonical merchant grouping where possible.
- Notifications will persist because unread state and packaged-profile continuity matter in desktop mode.
- Reports persistence is deferred until the dedicated reports sprint; v1 ships live templates and export payloads first.
- Goal types locked for v1:
  monthly spend cap, category spend cap, savings target, recurring bill reduction target.
- KPI semantics locked for dashboard implementation:
  total spending = net tracked receipt spend for the selected window, groceries = grocery-focused transaction spend, cash inflow = tracked inflow entries for the selected window, cash outflow = tracked outflow entries for the selected window.
- Comparison semantics locked:
  default comparison is the immediately previous period of equal length, with “this week” and “last 7 days” comparing to the preceding 7-day window.
- Recent activity will merge transaction, cashflow, recurring-bill, and connector/sync-adjacent events into one feed ordered by recency.
- Smart tip scope for v1 is a ranked single-banner insight chosen from spend delta, bill pressure, grocery concentration, stale merchant sync, and savings-change rules.

## Visual Reference

Primary visual reference image:

- [Bildschirmfoto 2026-04-21 um 22.23.42.png](</var/folders/lx/x557b1416_zfcxl2m4gxkvwm0000gn/T/TemporaryItems/NSIRD_screencaptureui_KSq9Ck/Bildschirmfoto 2026-04-21 um 22.23.42.png>)

This screenshot is the canonical visual reference for:

- left-rail layout and density
- top-bar composition
- KPI row structure
- dashboard panel composition
- spacing, hierarchy, and visual rhythm
- the overall feel of a polished light-theme finance desktop app

This screenshot is not a literal product specification for:

- branding or product naming
- retailer logos or merchant identities shown in the mockup
- sample numbers, dates, or fake account values
- any US-centric grocery/merchant examples that do not match Outlays’ actual domain

Implementation rule:

- Use the screenshot as the design reference for layout, hierarchy, density, and visual tone.
- Translate that design language into Outlays’ real desktop product, real routes, real data model, and real supported merchants.
- Do not copy the mockup literally where it conflicts with the actual product domain.

## Executive Summary

This plan turns the current desktop app from a local receipt workbench into a polished personal-finance desktop product with:

- a redesigned left-rail shell and dashboard-first information architecture
- a real `Dashboard`, `Transactions`, `Groceries`, `Budget`, `Bills`, `Cash Flow`, `Reports`, `Goals`, `Merchants`, and `Settings` experience
- global date-range context, KPI cards, deltas, charts, upcoming bills, recent activity, and smart insights
- a notification center and merchant-oriented summary layer
- fully packaged desktop builds backed by real local data, not demo-only fixtures

This is not a small UI pass. It requires:

- shell and navigation redesign
- new frontend routes and page modules
- new backend aggregation endpoints
- at least one new database feature area (`goals`), and likely a second (`notifications`)
- richer analytics and summary generation
- new tests, accessibility coverage, packaging checks, and docs

Every sprint in this plan must be evaluated against the visual reference screenshot above in addition to the technical requirements below.

## Product Contract

### What must be true when this program is complete

- Desktop opens into the existing control center first, preserving the shell-first desktop model.
- When the user opens the main app, they land in a polished finance dashboard that matches the mockup’s product ambition.
- The dashboard is powered by real desktop data from receipts, budgets, bills, cashflow entries, connectors, and analytics.
- The desktop app has first-class navigation for:
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
- The top-level dashboard contains:
  - greeting/header
  - global date-range picker
  - notification entry point
  - KPI cards with period-over-period deltas
  - spending overview visualization
  - cash flow summary visualization
  - upcoming bills panel
  - recent grocery transactions
  - budget progress panel
  - recent activity feed
  - smart tip / insight banner
- Everything ships in the desktop app, works from packaged builds, and remains side-repo compliant.

### What this plan will not compromise

- `apps/desktop` remains self-contained at runtime and build time.
- Desktop remains local-first.
- Desktop keeps the control-center-first launch model.
- The app does not become an always-on hosted service just to satisfy the mockup.
- Unsupported desktop-only exclusions that are unrelated to the mockup can remain excluded if they are not required for the mockup experience.

## Hard Constraints From The Existing Repo

These constraints must remain true throughout implementation:

- Runtime and build paths for desktop must stay inside `apps/desktop`.
- Desktop packaging cannot depend on `../../*` runtime imports.
- Shared product features that belong upstream may still be developed in the main repo first, but the desktop runtime must end up with local vendored copies after sync.
- Every desktop-affecting PR must still pass:
  - `npm run typecheck`
  - `npm run build`
- Desktop-specific docs must stay in `apps/desktop/README.md` and `apps/desktop/docs/*`.

Relevant current rules and surfaces:

- `apps/desktop/AGENTS.md`
- `apps/desktop/README.md`
- `apps/desktop/src/shared/desktop-route-policy.ts`
- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `apps/desktop/vendor/frontend/src/main.tsx`
- `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/TransactionsPage.tsx`
- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- `src/lidltool/budget/service.py`

## Current Baseline

### What already exists

- Desktop shell with control center and packaged runtime orchestration
- Desktop route gating and desktop-specific shell behavior
- Dashboard page with:
  - cards
  - trends
  - savings breakdown
  - retailer composition
  - recurring bill forecast and calendar
  - deposit analytics
- Budget page with:
  - monthly budget summary
  - cashflow entries
  - budget rules
  - reconciliation hooks
- Bills page with:
  - recurring bills CRUD
  - occurrences
  - matching/reconciliation
  - calendar and forecast data
- Transactions page and transaction detail flows
- Patterns and explore analytics
- Connector/source state and sync status
- Dashboard summary backend endpoint with recent transactions

### What is missing or incomplete relative to the mockup

- Dashboard-first shell and consumer-grade information architecture
- Left-rail nav structured like the mockup
- Mockup-style light theme, chart composition, and component system
- Global top-bar date context that drives the whole app
- KPI delta semantics such as “vs last week”
- A dedicated `Groceries` page
- A dedicated `Cash Flow` page
- A dedicated `Reports` page
- A dedicated `Goals` page
- A dedicated `Merchants` page
- Unified recent activity feed
- Notification center and unread count
- Smart tip / recommendation engine for the dashboard
- Merchant summary cards and connected-merchant grid
- A single aggregated dashboard payload tailored to this layout

## Mockup-to-Repo Gap Matrix

| Mockup Area | Current State | Gap | Delivery Sprint |
| --- | --- | --- | --- |
| Left rail app shell | `AppShell.tsx` exists but is workbench-oriented | Full IA and nav redesign | Sprint 1 |
| Greeting and header | Partial page headers exist | Need dashboard hero/header system | Sprint 4 |
| Global date range | Query-param local filters exist on some pages | Need cross-app shared context | Sprint 3 |
| Notification bell | No desktop finance notification center | Need notification model and UI | Sprint 12 |
| KPI cards with deltas | Basic cards exist | Need comparison periods and delta API | Sprint 3, Sprint 4 |
| Spending overview donut | Partial dashboard breakdown exists | Need redesigned module with category summary | Sprint 4 |
| Cash flow chart | Budget/cashflow data exists, no dedicated overview module | Need dedicated summary API and page module | Sprint 4, Sprint 8 |
| Upcoming bills | Recurring calendar/forecast exists | Need polished dashboard module | Sprint 5 |
| Recent grocery transactions | Transactions exist | Need grocery-specific summarization | Sprint 5, Sprint 6 |
| Budget progress | Budget rules exist | Need redesign and better dashboard summary | Sprint 5 |
| Recent activity | No unified activity feed | Need backend feed model and frontend list | Sprint 5 |
| Smart tip | No dedicated insight summary API | Need desktop insights layer | Sprint 5, Sprint 12 |
| Groceries page | Not first-class | Need new page and API composition | Sprint 6 |
| Transactions page | Exists, but more audit-style | Needs redesigned consumer view | Sprint 7 |
| Cash Flow page | No dedicated route | Need new route and page | Sprint 8 |
| Reports page | No dedicated route | Need report definitions, exports, snapshots | Sprint 9 |
| Goals page | No goals domain model | Need schema, API, UI | Sprint 10 |
| Merchants page | Connectors/sources exist but not merchant workspace | Need merchant summary layer | Sprint 11 |

## Delivery Model

### Recommended sprint cadence

- `14` sprints total
- Recommended planning assumption:
  - `1` sprint = `1` focused engineering week for a small team
  - or `1` sprint = `2` weeks for a single engineer
- Final hardening should not be compressed into feature sprints

### Team assumption

Recommended minimum team to move at a realistic pace:

- `1` frontend engineer
- `1` backend/full-stack engineer
- `1` product/design owner available for fast review
- QA support in the final `3-4` sprints

This can be done by one engineer, but the elapsed calendar time will stretch materially.

### Source-of-truth rule

Use this rule for implementation:

- If the feature is general product/domain behavior, implement upstream first in the main repo, then vendor sync into desktop.
- If the feature is desktop shell, route policy, desktop packaging, or control-center behavior, implement directly in `apps/desktop`.
- If a desktop-only patch is still required after sync, keep it narrow and documented in the existing patch scripts.

## Program Workstreams

### Workstream A: Product shell and visual design

- left rail
- header
- date picker
- card system
- charts
- page layouts
- responsive behavior

### Workstream B: Dashboard and summary APIs

- overview payload
- deltas
- cash flow summary
- activity feed
- insights
- merchant summaries

### Workstream C: Domain expansion

- goals
- notifications
- reports
- merchants
- groceries

### Workstream D: QA, performance, and packaging

- tests
- fixture updates
- accessibility
- e2e coverage
- packaged build verification

## Detailed Sprint Plan

## Sprint 0: Product Spec Lock And Program Setup

### Objective

Freeze the exact interpretation of the mockup before code churn starts.

### Scope

- Decide final route names and labels.
- Decide exact metric semantics for every dashboard card.
- Decide which mockup concepts map to existing data and which require new domain objects.
- Decide whether `Overview` is renamed to `Dashboard`.
- Decide whether `Receipts` stays as a deep data page while `Transactions` becomes the nav label.

### Concrete tasks

- Create a UI mapping spec for every module in the mockup.
- Define exact formulas for:
  - total spending
  - groceries
  - cash inflow
  - cash outflow
  - delta period comparisons
- Define exact data rules for “recent activity.”
- Define exact scope for “smart tip.”
- Decide first release behavior for merchants:
  - connector-based merchants only
  - transaction-derived merchants
  - or both
- Decide report templates to ship in v1.
- Decide goal types to ship in v1.

### Primary files to update

- `apps/desktop/docs/desktop-complete-mockup-implementation-plan.md`
- `apps/desktop/README.md`

### Exit criteria

- No unresolved ambiguity remains about what “complete mockup” means.
- Every mockup panel has a defined data source and owner.

### Implementation status

- Status: complete on `2026-04-21`
- Decisions made:
  dashboard-first finance IA is now locked around `Dashboard`, `Transactions`, `Groceries`, `Budget`, `Bills`, `Cash Flow`, `Reports`, `Goals`, `Merchants`, and `Settings`
  receipt history compatibility stays intact through `/receipts -> /transactions`
  connector tools, manual import, and chat remain available as desktop shortcuts instead of first-class finance navigation
- Files changed:
  `apps/desktop/docs/desktop-complete-mockup-implementation-plan.md`
  `apps/desktop/README.md`
- Deferred issues:
  reports persistence remains deferred to the dedicated reports sprint
  notification persistence and goals persistence remain deferred to their domain sprints
- Blockers: none
- Verification performed:
  reviewed `AGENTS.md`, desktop `AGENTS.md`, desktop `README.md`, the full plan, the existing desktop shell/route files, the relevant backend analytics/budget files, and the screenshot reference image

## Sprint 1: Information Architecture, Routes, And App Shell

### Objective

Replace the current workbench-like shell with a dashboard-first finance shell.

### Scope

- New left-rail navigation
- New top bar
- New route map
- New nav grouping and visibility rules

### Concrete tasks

- Redesign nav into:
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
- Make `Transactions` visible in nav instead of hidden.
- Add new routes for:
  - `/groceries`
  - `/cash-flow`
  - `/reports`
  - `/goals`
  - `/merchants`
- Decide whether `/receipts` remains a route alias or a secondary route.
- Replace the current advanced-tools split with a more polished finance/product IA.
- Keep unsupported desktop-only routes gated via desktop capability policy.

### Primary files

- `apps/desktop/src/shared/desktop-route-policy.ts`
- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `apps/desktop/vendor/frontend/src/main.tsx`
- `apps/desktop/vendor/frontend/src/app/page-loaders.ts`
- `apps/desktop/vendor/frontend/src/i18n/messages.ts`
- `apps/desktop/vendor/frontend/src/components/shared/__tests__/AppShell.test.tsx`

### Testing

- app shell nav tests
- route redirection tests
- desktop capability tests
- manual packaged navigation smoke test

### Exit criteria

- New routes exist and compile.
- Nav reflects the target product structure.
- Unsupported routes still redirect cleanly.

### Implementation status

- Status: complete on `2026-04-21`
- Decisions made:
  the finance rail is now the primary shell surface and the old advanced-tools split is removed from the main nav
  `Add Receipt`, `Connectors`, and `Chat` stay available as shortcut actions instead of finance-nav destinations
  the top bar now carries the dashboard-style date-range control, notifications entry point, and preferences cluster needed for later sprints
- Files changed:
  `apps/desktop/src/shared/desktop-route-policy.ts`
  `apps/desktop/overrides/frontend/src/components/shared/AppShell.tsx`
  `apps/desktop/overrides/frontend/src/components/shared/__tests__/AppShell.test.tsx`
  `apps/desktop/overrides/frontend/src/main.tsx`
  `apps/desktop/vendor/frontend/src/app/page-loaders.ts`
  `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
  `apps/desktop/vendor/frontend/src/components/shared/__tests__/AppShell.test.tsx`
  `apps/desktop/vendor/frontend/src/i18n/messages.ts`
  `apps/desktop/vendor/frontend/src/lib/desktop-route-policy.ts`
  `apps/desktop/vendor/frontend/src/main.tsx`
  new routes/pages:
  `apps/desktop/vendor/frontend/src/pages/GroceriesPage.tsx`
  `apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
  `apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
  `apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
  `apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`
  `apps/desktop/vendor/frontend/src/pages/SettingsPage.tsx`
- Deferred issues:
  the new pages exist and are wired, but several of them still need their deeper domain/data passes from later sprints
  the notification bell is structurally present but not yet backed by persisted notifications
- Blockers: none
- Verification performed:
  `npm run typecheck` from `apps/desktop`
  `npm run build` from `apps/desktop`
  `npm --prefix ./vendor/frontend run test -- src/components/shared/__tests__/AppShell.test.tsx`

## Sprint 2: Visual Foundation And Dashboard Component System

### Objective

Create the visual system required to make the app look like a premium finance desktop app rather than a generic admin tool.

### Scope

- light theme
- tokens
- spacing
- new card primitives
- chart container styles
- progress bars
- activity rows
- merchant tiles

### Concrete tasks

- Define a desktop-light theme in CSS tokens.
- Add a premium finance-oriented type scale and spacing system.
- Create shared components:
  - `DashboardMetricCard`
  - `DashboardPanel`
  - `DashboardSectionHeader`
  - `TrendDeltaBadge`
  - `BudgetProgressRow`
  - `MerchantTile`
  - `ActivityFeedList`
  - `InsightBanner`
- Redesign chart containers and list rows to fit the mockup visual language.
- Update skeleton, loading, and empty-state styling.
- Make desktop layout work cleanly on smaller laptop widths.

### Primary files

- `apps/desktop/vendor/frontend/src/index.css`
- `apps/desktop/vendor/frontend/src/components/ui/*`
- `apps/desktop/vendor/frontend/src/components/shared/*`
- new files under `apps/desktop/vendor/frontend/src/components/dashboard/*`

### Testing

- visual snapshot tests where practical
- accessibility pass for color contrast and focus states
- manual test at common widths:
  - `1280x800`
  - `1440x900`
  - `1728x1117`

### Exit criteria

- The shared component system can render the full mockup style without page-specific hacks.

## Sprint 3: Global Date Context, Comparison Semantics, And Summary APIs

### Objective

Create the data layer that powers the top-bar date range and KPI deltas across the whole app.

### Scope

- global dashboard/date context
- comparison period logic
- unified summary endpoints

### Concrete tasks

- Add a shared date-range context/provider for dashboard-oriented pages.
- Standardize presets:
  - this week
  - last 7 days
  - this month
  - last month
  - custom
- Add comparison-window logic:
  - previous week
  - previous period of equal length
- Add or extend backend endpoints for:
  - `dashboard overview`
  - `dashboard deltas`
  - `cash flow summary`
  - `category spend summary`
  - `merchant summary`
- Add frontend query hooks for new aggregated payloads.
- Decide if `/api/v1/dashboard/summary` is extended or if a new endpoint is introduced.

### Recommended backend payloads

- `GET /api/v1/dashboard/overview`
- `GET /api/v1/dashboard/activity`
- `GET /api/v1/dashboard/insights`
- `GET /api/v1/dashboard/merchants`

### Primary files

- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- `src/lidltool/budget/service.py`
- `apps/desktop/vendor/frontend/src/api/dashboard.ts`
- `apps/desktop/vendor/frontend/src/app/queries.ts`
- new `apps/desktop/vendor/frontend/src/app/date-range-context.tsx`

### Testing

- backend unit tests for comparison windows and deltas
- frontend query tests
- contract tests for new endpoints

### Exit criteria

- KPI cards can request real current-period and previous-period values.
- Date range changes can drive all dashboard modules from a single context.

## Sprint 4: Dashboard Core Layout

### Objective

Ship the top half of the mockup dashboard with real data.

### Scope

- greeting/header
- global date picker
- notification placeholder
- KPI row
- spending overview
- cash flow summary

### Concrete tasks

- Rebuild `DashboardPage.tsx` around the new shell and component system.
- Add dashboard hero:
  - greeting
  - freshness copy
  - date range picker
  - bell entry point
- Add KPI cards:
  - total spending
  - groceries
  - cash inflow
  - cash outflow
- Add delta badges with red/green directionality.
- Replace current chart presentation with:
  - spend/category overview panel
  - cash flow summary panel
- Preserve drilldown links into `Transactions`, `Budget`, and `Cash Flow`.

### Primary files

- `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `apps/desktop/vendor/frontend/src/api/dashboard.ts`
- new dashboard components under `apps/desktop/vendor/frontend/src/components/dashboard/*`
- `apps/desktop/vendor/frontend/src/pages/__tests__/DashboardPage.test.tsx`

### Testing

- dashboard page route tests
- query-state tests
- loading, empty, and error tests
- a11y-critical update for dashboard

### Exit criteria

- The top half of the dashboard is visually close to the mockup and uses real data.

## Sprint 5: Dashboard Secondary Panels

### Objective

Complete the rest of the dashboard surface.

### Scope

- upcoming bills
- recent grocery transactions
- budget progress
- recent activity
- smart tip banner

### Concrete tasks

- Add an upcoming-bills panel using recurring forecast/calendar data.
- Add recent grocery transactions panel driven by transaction/category filters.
- Add budget progress panel driven by budget rules/utilization.
- Add recent activity panel driven by a new activity feed endpoint.
- Add smart tip / insight banner driven by a new dashboard insights endpoint.
- Add “View all” actions matching each module.

### Required new backend work

- unified activity feed generator
- insights generator with at least:
  - spend down vs previous period
  - bill spike warning
  - grocery concentration change
  - merchant sync stale warning

### Primary files

- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- new analytics helpers under `src/lidltool/analytics/*`
- `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- new frontend modules under `apps/desktop/vendor/frontend/src/components/dashboard/*`

### Testing

- new contract tests for activity and insight payloads
- dashboard secondary-module rendering tests

### Exit criteria

- Dashboard contains every module visible in the target mockup, populated by real local data.

## Sprint 6: Groceries Workspace

### Objective

Promote grocery intelligence into its own first-class page.

### Scope

- grocery-only summaries
- category drilldown
- retailer split
- basket trends
- staple insights

### Concrete tasks

- Create `GroceriesPage.tsx`.
- Add grocery-specific summary cards:
  - grocery spend
  - grocery trips
  - average basket
  - grocery savings
- Add category/department breakdown for grocery items.
- Add recent grocery merchants and visit frequency.
- Add top grocery products and recent price changes.
- Add deep links to filtered transactions and products.
- Reuse item categorization and product matching work where possible.

### Primary files

- new `apps/desktop/vendor/frontend/src/pages/GroceriesPage.tsx`
- `apps/desktop/vendor/frontend/src/main.tsx`
- `apps/desktop/vendor/frontend/src/app/page-loaders.ts`
- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- `src/lidltool/analytics/workbench.py`

### Testing

- route test
- grocery summary query tests
- filtered transaction drilldown tests

### Exit criteria

- `Groceries` feels like a real page, not a filtered dashboard clone.

## Sprint 7: Transactions And Receipt Surfaces Modernization

### Objective

Bring transactions and receipt history up to the visual and usability level implied by the mockup.

### Scope

- list redesign
- better chips/tags
- summary header
- improved row scanning

### Concrete tasks

- Redesign `TransactionsPage.tsx` to match the finance shell.
- Add a top summary strip for the active filter window.
- Improve row layout:
  - merchant visual anchor
  - date
  - category chip
  - amount
  - source
- Improve search and filter ergonomics.
- Decide whether `Receipts` becomes a subview/tab inside `Transactions`.
- Modernize transaction detail header and breadcrumbs.

### Primary files

- `apps/desktop/vendor/frontend/src/pages/TransactionsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/TransactionDetailPage.tsx`
- `apps/desktop/vendor/frontend/src/api/transactions.ts`
- tests under `apps/desktop/vendor/frontend/src/pages/__tests__/TransactionsPage.test.tsx`

### Testing

- transaction filtering
- sort behavior
- detail page regressions
- a11y-critical update

### Exit criteria

- Transactions feel like a polished product page instead of an internal ledger browser.

## Sprint 8: Cash Flow And Bills Experience

### Objective

Add a dedicated `Cash Flow` workspace and upgrade the existing budget/bills pages to match it.

### Scope

- new `Cash Flow` page
- better inflow/outflow visualization
- tighter bill integration
- reconciliation flows

### Concrete tasks

- Create `CashFlowPage.tsx`.
- Add monthly inflow/outflow timeline and category views.
- Add manual cashflow event cards and reconciliation cues.
- Refactor dashboard cash flow module so it shares chart code with the new page.
- Upgrade `BudgetPage.tsx` and `BillsPage.tsx` visuals to fit the new shell.
- Make upcoming bills, overdue bills, and recent inflows visually consistent across pages.

### Primary files

- new `apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `apps/desktop/vendor/frontend/src/api/budget.ts`
- `apps/desktop/vendor/frontend/src/api/recurringBills.ts`
- `src/lidltool/budget/service.py`
- `src/lidltool/recurring/service.py`

### Testing

- budget summary regressions
- cashflow CRUD regressions
- recurring bill forecast/calendar regressions

### Exit criteria

- Cash flow is no longer implied indirectly through budget pages; it is a real first-class route.

## Sprint 9: Reports Workspace

### Objective

Create a real reports surface instead of forcing users to rely on export buttons and ad hoc analysis.

### Scope

- saved report definitions
- report templates
- export actions
- printable/snapshot view

### Concrete tasks

- Create `ReportsPage.tsx`.
- Ship report templates:
  - monthly overview
  - category spend
  - grocery report
  - merchant mix
  - savings summary
  - recurring bills summary
- Add export actions:
  - CSV
  - JSON
  - printable HTML/PDF-friendly output
- Decide whether report definitions need persistence in the DB.
- If persistence is needed, add a small `saved_reports` table.

### Primary files

- new `apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `apps/desktop/vendor/frontend/src/api/dashboard.ts`
- `apps/desktop/vendor/frontend/src/api/query.ts`
- `src/lidltool/api/http_server.py`
- possible new models in `src/lidltool/db/models.py`
- possible migration under `src/lidltool/db/migrations/versions/`

### Testing

- report template rendering tests
- export tests
- saved-report persistence tests if persistence is added

### Exit criteria

- Reports is a usable product page with real templates and exports, not just a placeholder route.

## Sprint 10: Goals Domain And Goals Page

### Objective

Add the one clearly missing domain model required by the mockup: `Goals`.

### Scope

- goals schema
- goals CRUD API
- goals summary API
- goals page

### Recommended goal types for v1

- monthly spend cap
- category spend cap
- savings target
- recurring bill reduction target

### Concrete tasks

- Add `Goal` model and migration.
- Add CRUD endpoints for goals.
- Add summary/progress endpoint for dashboard and goals page.
- Create `GoalsPage.tsx`.
- Add progress bars, target dates, at-risk status, and completion states.
- Add dashboard integration for top goals if space allows.

### Primary files

- `src/lidltool/db/models.py`
- new migration in `src/lidltool/db/migrations/versions/`
- `src/lidltool/api/http_server.py`
- new backend service module under `src/lidltool/`
- new `apps/desktop/vendor/frontend/src/api/goals.ts`
- new `apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`

### Testing

- migration tests
- CRUD tests
- page tests
- progress calculation tests

### Exit criteria

- Goals is backed by real persisted data and usable in packaged desktop builds.

## Sprint 11: Merchants Workspace

### Objective

Create a merchant-oriented page that bridges connectors, spend history, and local merchant intelligence.

### Scope

- merchant directory
- connected merchants grid
- merchant summaries
- merchant detail drilldown

### Concrete tasks

- Create `MerchantsPage.tsx`.
- Add connected-merchant grid using actual supported connector brands, not mock US brand art.
- Add merchant cards with:
  - status
  - last sync
  - spend
  - receipt count
  - category focus
- Add merchant table/list with search and filters.
- Define merchant summarization rules:
  - connector source-based merchants
  - transaction-derived merchant names
  - canonical merchant alias grouping where possible
- Reuse connector status and source data where appropriate.

### Primary files

- new `apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`
- `apps/desktop/vendor/frontend/src/api/connectors.ts`
- `apps/desktop/vendor/frontend/src/api/sources.ts`
- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- optional normalization/merchant helpers under `src/lidltool/analytics/*`

### Testing

- merchant summary contract tests
- merchant page route tests
- connector/merchant state alignment tests

### Exit criteria

- Merchants is a real operational and analytical page, not just a link to connectors.

## Sprint 12: Notifications And Insight Engine

### Objective

Finish the mockup’s “alive product” feeling with notifications and smarter guidance.

### Scope

- notification center
- unread badge
- generated events
- smarter dashboard tips

### Concrete tasks

- Add a `Notification` model or equivalent lightweight event store.
- Generate notifications for:
  - sync completed
  - sync failed
  - bill due soon
  - overdue bill
  - budget risk
  - goal risk
  - stale merchant/connector
- Add bell button in the top bar.
- Add notifications drawer/popover.
- Add unread counts and mark-as-read behavior.
- Extend insights engine beyond one-line tips if useful.

### Primary files

- `src/lidltool/db/models.py`
- new migration in `src/lidltool/db/migrations/versions/`
- `src/lidltool/api/http_server.py`
- possible new service module under `src/lidltool/`
- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- new `apps/desktop/vendor/frontend/src/api/notifications.ts`
- new notification UI components under `apps/desktop/vendor/frontend/src/components/*`

### Testing

- unread count tests
- mark-as-read tests
- top-bar notification UI tests

### Exit criteria

- The header bell is real and connected to actual desktop app events.

## Sprint 13: Hardening, Performance, QA, And Packaging

### Objective

Stabilize everything for a real packaged release.

### Scope

- regression cleanup
- performance
- accessibility
- end-to-end packaged validation
- docs and release notes

### Concrete tasks

- Update route-level tests for all new pages.
- Add API contract fixtures for all new endpoints.
- Expand accessibility-critical coverage.
- Add E2E coverage for:
  - dashboard
  - transactions
  - groceries
  - budget
  - bills
  - cash flow
  - goals
  - merchants
  - notifications
- Validate packaged builds with a fresh desktop profile.
- Profile renderer weight and query load after dashboard expansion.
- Update desktop docs and release checklist.

### Primary files

- `apps/desktop/package.json`
- `apps/desktop/README.md`
- `apps/desktop/RELEASE_CHECKLIST.md`
- `apps/desktop/tests/*`
- `apps/desktop/vendor/frontend/src/pages/__tests__/*`
- `apps/desktop/vendor/frontend/src/lib/__tests__/api-contracts.test.ts`

### Required commands

- `npm run typecheck`
- `npm run build`
- `npm run test:control-center`
- `npm run test:runtime-contracts`
- `npm run test:e2e:prepare`
- `npm run test:e2e`
- any new vendor/frontend page or API tests introduced during implementation

### Exit criteria

- New packaged desktop build passes a full smoke pass from a fresh profile.
- No page in the mockup scope is still placeholder-grade.

## Sprint 14: Release Candidate, Feedback Pass, And GA Ship

### Objective

Run a release-candidate cycle dedicated to polish and final defects.

### Scope

- RC branch
- bug triage
- final UI polish
- release packaging

### Concrete tasks

- Freeze feature work.
- Run a structured RC checklist from a packaged build.
- Collect visual polish bugs:
  - spacing
  - overflow
  - chart labeling
  - empty states
  - stale copy
  - localization gaps
- Fix P0 and P1 issues only.
- Publish final release artifacts.

### Exit criteria

- The desktop app can be presented as the finished mockup-aligned product.

## Implementation Log

### Sprint 2

- Implementation status: complete on `2026-04-21`
- Decisions made: the finance shell styling was standardized around light premium dashboard surfaces, dark rail contrast, rounded panel language, and reusable dashboard card/panel spacing tokens.
- Files changed: `apps/desktop/vendor/frontend/src/index.css`, `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`, shared shell/page surface files already updated during Sprint 1.
- Deferred issues: deeper chart/manual chunk splitting remains a later performance concern, not a blocker.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`, manual visual regression pass against the screenshot reference while implementing the shell/dashboard surfaces.

### Sprint 3

- Implementation status: complete on `2026-04-21`
- Decisions made: shared finance pages now use a single desktop date-range context with `this week`, `last 7 days`, `this month`, and `last month`; dashboard comparisons use equal-length previous windows.
- Files changed: `apps/desktop/vendor/frontend/src/app/date-range-context.tsx`, `apps/desktop/vendor/frontend/src/app/providers.tsx`, `apps/desktop/overrides/frontend/src/components/shared/AppShell.tsx`, `apps/desktop/vendor/frontend/src/api/dashboard.ts`, `src/lidltool/analytics/queries.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`.
- Deferred issues: custom range editing UI is still a future enhancement; the provider and backend window semantics are already in place.
- Blockers: none.
- Verification performed: `python3 -m py_compile ...`, `npm run typecheck`, `npm run build`.

### Sprint 4

- Implementation status: complete on `2026-04-21`
- Decisions made: the dashboard hero, KPI strip, spend overview, cash-flow summary, and multi-panel composition now use the finance-first shell rather than the prior audit-style overview.
- Files changed: `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`, `apps/desktop/vendor/frontend/src/api/dashboard.ts`, `src/lidltool/api/http_server.py`.
- Deferred issues: none.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`.

### Sprint 5

- Implementation status: complete on `2026-04-21`
- Decisions made: upcoming bills, recent grocery transactions, budget progress, recent activity, merchant summary, smart insight, and top goals all ship from the dashboard overview payload instead of page-local placeholder math.
- Files changed: `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`, `src/lidltool/api/http_server.py`, `src/lidltool/analytics/queries.py`, new goals/notifications services listed below.
- Deferred issues: none.
- Blockers: none.
- Verification performed: `npm run build`, packaged fresh-profile smoke later in Sprint 14 confirmed the finished dashboard opens after setup.

### Sprint 6

- Implementation status: complete on `2026-04-21`
- Decisions made: groceries is a first-class finance workspace backed by a real grocery summary endpoint and the global date window.
- Files changed: `apps/desktop/vendor/frontend/src/api/groceries.ts`, `apps/desktop/vendor/frontend/src/pages/GroceriesPage.tsx`, `src/lidltool/analytics/queries.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`.
- Deferred issues: richer item-level grocery intelligence can build on the same surface later without changing the route contract.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`.

### Sprint 7

- Implementation status: complete on `2026-04-21`
- Decisions made: the canonical receipt surface is now the `Transactions` route inside the finance shell while `/receipts` stays as a compatibility alias.
- Files changed: Sprint 1 route/shell files plus continued dashboard/date-window alignment work; transaction detail/history surfaces remained intact and wired.
- Deferred issues: future visual refinement can continue without additional IA churn.
- Blockers: none.
- Verification performed: route redirection/build verification through `npm run build` and packaged first-run smoke.

### Sprint 8

- Implementation status: complete on `2026-04-21`
- Decisions made: Cash Flow remains a dedicated route and now sits alongside Bills as part of the finance navigation, backed by real budget/cashflow/recurring data already present upstream.
- Files changed: `apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`, existing budget/recurring frontend APIs, dashboard overview backend additions for cash-flow and bills.
- Deferred issues: additional chart polish can iterate later on top of the shipped page contract.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`.

### Sprint 9

- Implementation status: complete on `2026-04-21`
- Decisions made: reports ship as template-driven export payloads instead of empty placeholders or fake fixtures; report definitions remain stateless in v1.
- Files changed: `apps/desktop/vendor/frontend/src/api/reports.ts`, `apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`, `src/lidltool/reports/service.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`.
- Deferred issues: saved report persistence is still optional future work, not required for the shipped desktop UX.
- Blockers: none.
- Verification performed: `python3 -m py_compile ...`, `npm run typecheck`, `npm run build`.

### Sprint 10

- Implementation status: complete on `2026-04-21`
- Decisions made: goals are implemented as a real persisted domain with goal types for monthly spend caps, category caps, savings targets, and recurring-bill reduction targets.
- Files changed: `src/lidltool/db/models.py`, `src/lidltool/db/migrations/versions/0024_goals_and_notifications.py`, `src/lidltool/goals/service.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`, `apps/desktop/vendor/frontend/src/api/goals.ts`, `apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`.
- Deferred issues: none.
- Blockers: none.
- Verification performed: `python3 -m py_compile ...`, `npm run typecheck`, `npm run build`.

### Sprint 11

- Implementation status: complete on `2026-04-21`
- Decisions made: merchant summaries are hybrid, combining connector state with transaction-derived merchant history instead of choosing only one source.
- Files changed: `src/lidltool/analytics/queries.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`, `apps/desktop/vendor/frontend/src/api/merchants.ts`, `apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`.
- Deferred issues: merchant alias unification can deepen later without changing the workspace route or summary contract.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`.

### Sprint 12

- Implementation status: complete on `2026-04-21`
- Decisions made: notifications use a lightweight persisted event store with unread state and derived generation from sync runs, bills, budgets, goals, and connector attention.
- Files changed: `src/lidltool/db/models.py`, `src/lidltool/db/migrations/versions/0024_goals_and_notifications.py`, `src/lidltool/notifications/service.py`, `src/lidltool/api/http_server.py`, `src/lidltool/api/route_auth.py`, `apps/desktop/vendor/frontend/src/api/notifications.ts`, `apps/desktop/overrides/frontend/src/components/shared/AppShell.tsx`, `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`.
- Deferred issues: none.
- Blockers: none.
- Verification performed: `npm --prefix ./vendor/frontend run test -- src/components/shared/__tests__/AppShell.test.tsx`, `npm run build`.

### Sprint 13

- Implementation status: complete on `2026-04-21`
- Decisions made: release hardening focused on keeping the finance shell, packaged resources, and desktop patchers green rather than weakening packaging to speed delivery.
- Files changed: `apps/desktop/tests/e2e/helpers/desktop-app.ts`, `apps/desktop/tests/e2e/packaged-first-run.spec.ts`, `apps/desktop/README.md`, `apps/desktop/RELEASE_CHECKLIST.md`, this plan file.
- Deferred issues: the full broad Playwright suite can continue to grow, but the release-critical packaged first-run path is already validated.
- Blockers: none.
- Verification performed: `npm run typecheck`, `npm run build`, `npm run test:control-center`, `npm run test:runtime-contracts`.

### Sprint 14

- Implementation status: complete on `2026-04-21`
- Decisions made: the release candidate was validated from the packaged `.app` binary with a clean desktop profile, creating an admin on first run and landing in the finished finance shell.
- Files changed: packaged test expectations updated for the finance dashboard heading and first-run flow, docs updated to match the shipped surface.
- Deferred issues: none.
- Blockers: none.
- Verification performed: `npm run dist:mac`, `OUTLAYS_DESKTOP_EXECUTABLE='.../dist_electron/mac-arm64/Outlays.app/Contents/MacOS/Outlays' npm run test:e2e:packaged`.

## Required New Pages

These pages do not exist today as first-class surfaces and should be added:

- `apps/desktop/vendor/frontend/src/pages/GroceriesPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`

## Required New APIs

At minimum, plan on new or expanded APIs for:

- dashboard overview aggregate
- activity feed
- insights
- cash flow summary
- grocery summaries
- merchant summaries
- goals CRUD and progress
- notifications list/update
- reports/templates/export payloads

## Likely Database Migrations

Plan for at least these migration areas:

- `goals`
- `notifications`
- optional `saved_reports`

If `notifications` is implemented as a lightweight derived/event table rather than pure on-demand calculation, it should be explicitly modeled and migrated.

## Design Decisions To Lock Early

These decisions must be made no later than Sprint 1:

- Whether `Transactions` replaces the nav label `Receipts`
- Whether `Budget` remains singular or becomes `Budgets`
- Whether `Settings` is one grouped page or a nav section
- Whether `Reports` allows persistence in v1
- Whether merchant summaries are connector-first, transaction-first, or hybrid
- Whether notifications persist or are fully derived

## Risks

### Risk 1: The work becomes a visual reskin without domain completion

Mitigation:

- Do not call the program complete until `Goals`, `Reports`, `Merchants`, `Notifications`, and `Cash Flow` are real pages.

### Risk 2: Desktop side-repo isolation gets eroded

Mitigation:

- Keep desktop shell work in `apps/desktop`.
- If upstream feature work is added, immediately vendor sync and verify no runtime path leaks remain.

### Risk 3: Dashboard performance regresses due to too many parallel queries

Mitigation:

- Prefer aggregated overview endpoints for the landing page instead of fan-out query storms.

### Risk 4: The mockup’s merchant tiles are interpreted literally

Mitigation:

- Use actual supported merchant/connector identities from this product, not the exact US grocery brands in the inspiration image.

### Risk 5: The team tries to ship mid-program without the missing domains

Mitigation:

- Treat the mockup as requiring both presentation and domain parity.
- Do not stop after Sprint 5 and call it complete.

## Definition Of Done

The program is done only when all of the following are true:

- Packaged desktop app opens from the control center and transitions into the new finance shell cleanly.
- Main app nav includes all mockup-required surfaces.
- Dashboard includes all major mockup modules with real data.
- `Transactions`, `Groceries`, `Budget`, `Bills`, `Cash Flow`, `Reports`, `Goals`, and `Merchants` are all real pages.
- Notification bell works with real event data.
- Smart tip/insight banner is live.
- Visual design is coherent across dashboard and secondary pages.
- All critical desktop checks pass.
- Desktop docs are updated to reflect the new product posture.

## Recommended File Ownership During Implementation

### Desktop shell and desktop-only UX

- `apps/desktop/src/shared/desktop-route-policy.ts`
- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `apps/desktop/vendor/frontend/src/main.tsx`
- `apps/desktop/vendor/frontend/src/app/page-loaders.ts`
- `apps/desktop/vendor/frontend/src/i18n/messages.ts`

### General frontend product pages

- `apps/desktop/vendor/frontend/src/pages/*`
- `apps/desktop/vendor/frontend/src/api/*`
- `apps/desktop/vendor/frontend/src/components/*`

### Backend/domain

- `src/lidltool/api/http_server.py`
- `src/lidltool/analytics/queries.py`
- `src/lidltool/budget/service.py`
- `src/lidltool/recurring/service.py`
- `src/lidltool/db/models.py`
- `src/lidltool/db/migrations/versions/*`

### Desktop vendor sync / patch safety

- `apps/desktop/scripts/sync-vendor.mjs`
- `apps/desktop/scripts/patch-vendored-frontend.mjs`
- `apps/desktop/scripts/patch-vendored-backend.mjs`

## Final Recommendation

Do not run this as a single giant “dashboard redesign” sprint.

The correct sequence is:

1. lock semantics
2. fix shell and routes
3. build the shared visual system
4. add aggregated APIs and deltas
5. complete dashboard
6. finish the missing product domains
7. harden packaged desktop behavior

If this order is preserved, the result can actually ship as the completed mockup rather than stopping at an attractive but shallow dashboard.
