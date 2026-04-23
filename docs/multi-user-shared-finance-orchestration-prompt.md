You are the lead orchestration agent for the repository at:
`/Volumes/macminiExtern/lidl-receipts-cli`

Your mission is to execute the entire desktop shared-finance program defined in:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/multi-user-shared-finance-implementation-plan.md`

You must treat that plan as the primary execution contract.

You must also use these supporting documents as mandatory context:

- `/Volumes/macminiExtern/lidl-receipts-cli/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/README.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/multi-user-household-finance-vision.md`

## Mission

Implement the complete desktop multi-user shared-finance vision.

The finished desktop product must support all of the following:

- a single person using the app alone
- multiple local users on one desktop installation
- one or more household/family-style shared groups
- one or more flat community/shared-flat/shared-household groups
- personal/private finance data per user
- directly owned shared finance data per shared group
- coherent workspace behavior across all active desktop finance surfaces

The work is not complete when:

- auth works but collaboration is still a visibility overlay
- transactions are shared but budgets remain personal-only
- planning data is partly migrated
- only dashboard summaries are shared
- there is still no real shared-group entity
- the UI still behaves like `family` is just a filter toggle

The work is complete only when the old family-overlay model has been replaced by a real personal + shared-group ownership model across the desktop product.

## Product Direction

The architecture must implement a generalized shared-group model.

That means:

- backend/domain primitives must support group types such as:
  - `household`
  - `community`
- user-facing workspace concepts must support:
  - `Personal`
  - named shared workspaces
- the implementation must not hardcode `family` as the only collaborative structure

The earlier vision doc still matters, but this program refines it:
- build for `shared groups`, not just `households`

## Non-Negotiable Repo Constraints

You must preserve all of the following:

1. `apps/desktop` behaves like a standalone side repo.
2. Do not add desktop runtime/build dependencies on `../../*`.
3. Anything needed at desktop runtime must live inside `apps/desktop`.
4. Desktop remains local-first.
5. Desktop does not become an always-on server product.
6. Control Center and packaged desktop startup behavior must remain intact.
7. Do not weaken packaging, backup/restore, or fresh-profile behavior to make implementation easier.
8. Update desktop docs as behavior changes.
9. If a feature is implemented upstream first, ensure the desktop runtime ends with vendored copies under `apps/desktop`.
10. Keep desktop-only patches narrow, explicit, and documented.

## Required First Step

Before planning edits or coding, read these files fully:

- `/Volumes/macminiExtern/lidl-receipts-cli/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/AGENTS.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/README.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/multi-user-household-finance-vision.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/multi-user-shared-finance-implementation-plan.md`

Then inspect the current desktop code paths that will form the execution baseline:

### Backend baseline

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/db/models.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/db/migrations/versions/`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/api/auth.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/auth/sessions.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/analytics/queries.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/budget/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/goals/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/reports/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/notifications/service.py`

### Frontend baseline

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/app/providers.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/app/scope-provider.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/request-scope.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/api-client.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/main.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/UsersSettingsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/SourcesPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/TransactionDetailPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`

## Core Product Rules

You must preserve and implement these principles everywhere:

### 1. Ownership, not visibility hacks

The final product must model:
- personal ownership by user
- shared ownership by shared group

Do not leave collaboration implemented primarily as:
- overlay visibility flags
- implicit shared-only toggles
- a global workspace filter without real ownership semantics

Those may exist temporarily during implementation, but they must stop being the main model.

### 2. Shared-group abstraction

The architecture must support:
- `household`
- `community`

without another schema rewrite later.

Recommended direction:
- neutral backend abstraction such as `shared_group` or `group`
- `group_type` field
- workspace resolver that binds each request to either personal or a concrete group

### 3. Single-user flow remains first-class

Do not make solo users feel like they are in an unfinished collaborative product.

If there are no shared groups:
- the app must still feel complete
- personal workspace must remain clean and simple

### 4. Workspace clarity

Users must always know:
- who they are signed in as
- which workspace they are in
- whether the data is personal or shared

The current silent scope-switch behavior must be replaced by a real workspace model.

## Program Execution Rule

Execute the plan sprint by sprint.

The defined sprints are:

- Sprint 0: Program Lock
- Sprint 1: Identity and Session UX
- Sprint 2: Shared Group Foundation
- Sprint 3: Roles and Management Surfaces
- Sprint 4: Workspace Context Kernel
- Sprint 5: Compatibility and Backfill
- Sprint 6: Shell and Workspace UX
- Sprint 7: Sources and Connector Ownership
- Sprint 8: Transactions and Allocations
- Sprint 9: Documents and Review Queue
- Sprint 10: Budget Months and Budget Rules
- Sprint 11: Cash Flow and Reconciliation
- Sprint 12: Recurring Bills and Obligations
- Sprint 13: Goals, Notifications, Reports
- Sprint 14: Dashboard, Groceries, Merchants
- Sprint 15: Chat, Query, Quality, Analytics
- Sprint 16: Backup, Restore, Export, Import
- Sprint 17: Hardening, Packaging, Release

You must execute all of them unless a real blocker forces a stop.

Do not stop after:
- schema foundation
- transactions
- budgets
- dashboard

The program is incomplete until all major desktop finance surfaces are migrated.

## Required Working Method

For every sprint, do the following:

1. Re-state the sprint objective in direct engineering terms.
2. Inspect all current code paths affected.
3. Identify:
   - schema changes
   - service/API changes
   - frontend surfaces
   - tests
   - docs
4. Build a short sprint checklist.
5. Implement the sprint completely.
6. Run relevant checks.
7. Fix regressions introduced by that sprint.
8. Update the plan file with:
   - status
   - decisions
   - files changed
   - blockers
   - deferred items
   - verification
9. Update desktop docs if behavior changed.
10. Commit only if explicitly requested by the user.

## Required Engineering Discipline

### Data migrations

- Prefer additive migrations first.
- Backfill safely.
- Keep compatibility paths until the new model is proven.
- Avoid destructive removal of legacy fields too early.

### Authorization

- Every mutation must be authorized against:
  - current user
  - active workspace
  - user role within that workspace
- No cross-group leakage is acceptable.

### Frontend behavior

- Every page that reads finance data must bind to the active workspace.
- The shell must expose a real workspace switcher.
- Each page should show current workspace identity clearly enough that the user is never guessing.

### Desktop packaging

- Keep packaged app behavior healthy.
- Re-check backup/restore and fresh-profile flows after major migrations.
- Do not assume self-hosted behavior or always-on schedulers.

## Required Feature Outcome By Domain

### Identity

Must support:
- multiple users
- clear sign-in/sign-out behavior
- session/device management UI
- account switching ergonomics

### Shared groups

Must support:
- create group
- group type `household` or `community`
- membership
- roles
- group management UI

### Sources/connectors

Must support:
- personal-owned sources
- shared-group-owned sources
- explicit destination during setup/import where relevant

### Transactions

Must support:
- personal-owned transactions
- shared-owned transactions
- allocation for mixed baskets/items
- transaction detail editing that reflects ownership/allocation clearly

### Planning domains

Must support personal and shared ownership for:
- budget months
- budget rules
- cashflow entries
- recurring bills
- goals
- notifications
- reports

### Summary surfaces

Must be workspace-correct for:
- dashboard
- groceries
- merchants
- reports

### Secondary surfaces

Must also be migrated or explicitly redesigned for workspace correctness:
- chat
- saved queries
- quality flows
- product analytics
- document/review queue flows

### Operational durability

Must preserve the collaboration model across:
- backup
- restore
- export
- import
- packaged builds
- fresh profiles

## Concrete File Hotspots

Expect repeated edits in these areas.

### Backend

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/db/models.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/db/migrations/versions/*`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/analytics/queries.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/budget/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/goals/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/reports/service.py`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src/lidltool/notifications/service.py`

### Frontend

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/app/providers.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/app/scope-provider.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/request-scope.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/api-client.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/UsersSettingsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/SourcesPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/TransactionDetailPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`

## Required Verification Pattern

At minimum, run relevant subsets of:

- `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run typecheck`
- `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run build`
- targeted frontend tests
- targeted backend tests if present
- packaged or fresh-profile smoke checks when a sprint affects:
  - auth/session
  - imports/review queue
  - backup/restore
  - desktop startup/runtime behavior

You must summarize actual verification performed after each sprint.

## Documentation Rule

Keep these docs current as execution proceeds:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/docs/multi-user-shared-finance-implementation-plan.md`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/README.md`

If the implementation changes user-facing behavior, routes, backup/restore semantics, or workspace behavior, update the docs in the same sprint.

## Decision Rule For Ambiguity

If you face a tradeoff:

- prefer real ownership over compatibility shortcuts
- prefer a generalized shared-group model over household-only hacks
- prefer desktop side-repo correctness over convenience
- prefer migration safety over aggressive cleanup
- prefer explicit workspace UX over hidden behavior

## Definition Of Done

You are finished only when all of the following are true:

- a user can operate only in personal mode cleanly
- multiple users can sign in locally with private data separation
- shared groups exist with roles and membership
- at least household and community group types work
- workspace switching is explicit and visible
- transactions, budgets, cashflow, bills, goals, notifications, reports, dashboards, and secondary analytics surfaces all behave consistently by workspace
- backup/restore/import/export preserve the model
- packaged desktop flows still work
- docs match the implemented behavior

Do not stop early.
