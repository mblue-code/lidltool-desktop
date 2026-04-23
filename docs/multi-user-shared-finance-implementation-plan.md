# Desktop Multi-User Shared Finance Implementation Plan

## Status

- Proposed on `2026-04-23`
- Execution started on `2026-04-23`
- Target surface: `apps/desktop`
- Program type: multi-sprint product and architecture program
- Baseline vision doc: `apps/desktop/docs/multi-user-household-finance-vision.md`
- This plan extends that vision from `personal + household` to a more general `personal + shared group` model so the same implementation can support:
  - a single person
  - one household/family
  - multiple households on one installation
  - a flat shared community or WG/flatshare

## Execution Log

### Sprint 0: Program Lock

- Status: complete
- Decisions:
  - shared-group is the neutral collaboration primitive
  - desktop keeps runtime/build isolation inside `apps/desktop`
  - additive migration first, destructive cleanup deferred
- Verification:
  - doc review and codebase baseline inspection

### Sprint 1: Identity and Session UX

- Status: complete
- Delivered:
  - account/session controls added to desktop users settings
  - explicit sign-out and switch-account affordances added
  - current-user summary added to the shell preferences surface
- Files changed:
  - `apps/desktop/vendor/frontend/src/api/users.ts`
  - `apps/desktop/overrides/frontend/src/components/shared/AppShell.tsx`
  - `apps/desktop/overrides/frontend/src/pages/UsersSettingsPage.tsx`
- Verification:
  - `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend && npm test -- --run src/components/shared/__tests__/AppShell.test.tsx src/pages/__tests__/LaunchCriticalI18nRoutes.test.tsx`
  - `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run typecheck`

### Sprint 2: Shared Group Foundation

- Status: complete
- Delivered:
  - `shared_groups` and `shared_group_members` schema added
  - shared-group service module added for CRUD and membership lookup
- Files changed:
  - `apps/desktop/vendor/backend/src/lidltool/db/models.py`
  - `apps/desktop/vendor/backend/src/lidltool/db/migrations/versions/0025_shared_groups.py`
  - `apps/desktop/vendor/backend/src/lidltool/shared_groups/service.py`
- Verification:
  - `PYTHONPATH='/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/backend/src' '/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.backend/venv/bin/python' -m pytest /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/tests/backend/test_shared_groups_api.py -q`

### Sprint 3: Roles and Management Surfaces

- Status: complete
- Delivered:
  - owner/manager/member role rules implemented
  - shared-group create/edit/member management added to desktop users settings
  - permissions enforced for role escalation and owner removal constraints
- Files changed:
  - `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
  - `apps/desktop/vendor/backend/src/lidltool/api/route_auth.py`
  - `apps/desktop/overrides/frontend/src/pages/UsersSettingsPage.tsx`
  - `apps/desktop/tests/backend/test_shared_groups_api.py`
- Verification:
  - backend shared-group API test file above
  - frontend route smoke/tests above

### Sprint 4: Workspace Context Kernel

- Status: partial foundation complete
- Delivered:
  - desktop shell now exposes explicit workspace identity and switching between `Personal` and named shared groups
  - request-scope persistence replaced with workspace selection persistence in frontend state
  - concrete `scope=group:<group_id>` compatibility selector added
  - backend now authorizes selected shared-group scope against active membership before allowing shared visibility queries
- Deferred to later sprints:
  - real per-group ownership for transactions, budgets, documents, and planning domains
  - full replacement of legacy `family_*` visibility semantics
- Files changed:
  - `apps/desktop/vendor/frontend/src/lib/request-scope.ts`
  - `apps/desktop/vendor/frontend/src/app/scope-provider.tsx`
  - `apps/desktop/overrides/frontend/src/components/shared/AppShell.tsx`
  - `apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
  - `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- Verification:
  - `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend && npm test -- --run src/components/shared/__tests__/AppShell.test.tsx src/lib/__tests__/api-client.test.ts src/pages/__tests__/LaunchCriticalI18nRoutes.test.tsx`
  - `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run typecheck`
  - `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run build`

### Remaining program

- Sprint 5 onward is now partially executed in code, not just planned.
- The desktop runtime now has additive `shared_group_id` ownership columns and workspace-aware service/query wiring across the main finance domains.
- Remaining work after this execution is concentrated in secondary offer/export edge cases and broader UX/documentation cleanup, not in the core ownership model foundation.

## Why This Plan Exists

The current desktop app already has:
- multi-user auth
- per-user sessions
- user management
- a `personal` / `family` scope switch
- source, transaction, and item sharing controls

But it still does not have a complete collaborative finance model because:
- there is no actual household/community entity
- there is no membership and role system for shared finance
- budgeting/planning domains remain mostly user-owned
- `family` is mostly a visibility overlay, not real shared ownership

This program closes that gap fully.

## Target Outcome

When this program is complete, desktop must support all of the following cleanly:

- One person can use the app alone without being forced into a shared setup.
- Multiple users can use the same desktop installation with separate sign-in and private personal data.
- Users can belong to one or more shared groups.
- A shared group can represent at least:
  - `household`
  - `community`
- Shared groups have members and roles.
- Shared groups can own finance records directly instead of relying on visibility flags alone.
- Every active desktop finance surface is consistent about scope:
  - `Dashboard`
  - `Transactions`
  - `Groceries`
  - `Budget`
  - `Bills`
  - `Cash Flow`
  - `Reports`
  - `Goals`
  - `Merchants`
  - `Sources`
  - `Documents` / review queue
  - `Notifications`
  - `Chat`
  - product/query/quality surfaces that depend on transaction visibility
- Backup/restore/export/import preserve the multi-user/shared-group model correctly.
- Packaged desktop builds work from a fresh profile and from restored profiles.

## Product Model

### Core concepts

- `User`: a login identity with personal/private data.
- `Shared Group`: a collaborative finance container.
- `Shared Group Type`: at minimum `household` or `community`.
- `Workspace`: the active context in the app. A workspace is either:
  - `personal`
  - one concrete shared group

### Key product rule

Do not treat collaboration as a filter trick.

The final model must support real ownership:
- personal records are owned by a user
- shared records are owned by a shared group

### Naming direction

- Backend/domain foundation should use a neutral abstraction such as `shared group`, `group`, or `collaboration group`.
- UI should remain user-friendly:
  - default labels can be `Personal` and `Shared`
  - the selected shared workspace should display its actual type/name, for example:
    - `Miller Household`
    - `Flat 4 Community`

### Relationship to the earlier vision doc

The earlier vision doc is still directionally correct.

This plan refines one thing:
- the architecture should not hardcode `household` as the only collaborative unit
- it should generalize to a shared-group model with `group_type`

That avoids a second migration later if the product wants flat communities, flatshares, co-ops, or other small collaborative groups.

## Non-Negotiable Constraints

- `apps/desktop` remains a standalone side-repo context.
- No desktop runtime/build-time dependency may rely on `../../*`.
- Desktop remains local-first.
- Desktop does not become an always-on server product.
- Control Center and desktop packaging constraints remain intact.
- Changes must preserve desktop isolation and packaged behavior.
- If upstream work is needed first, the desktop runtime must still end with local vendored copies inside `apps/desktop`.

## Locked Product Decisions

- The complete implementation will use a shared-group abstraction rather than a one-off family abstraction.
- The current `family` notion is transitional and will be retired from the primary UX.
- Shared-group membership and role boundaries must exist before shared planning domains migrate.
- Single-user flows must remain first-class and not feel like a degraded collaborative flow.
- A user may belong to multiple shared groups in the final architecture.
- The shell must expose a real workspace switcher, not just a silent request-scope toggle.
- Shared groups must be able to own:
  - connectors/sources
  - transactions
  - allocations
  - budget months
  - budget rules
  - cashflow entries
  - recurring bills
  - goals
  - notifications
  - reports
  - chat threads/messages if chat remains first-class in desktop
- Legacy share flags may remain as compatibility fields during migration, but they must stop being the primary collaboration model.

## Out Of Scope

This plan does not require desktop to add:
- hosted/cloud sync
- email delivery infrastructure
- always-on background jobs
- full offers/automations parity
- social/community moderation features beyond membership and role management

## Program Structure

### Recommended sprint cadence

- Each sprint should be treated as one mergeable implementation slice.
- Each sprint must end with:
  - code complete
  - migration/backfill complete where relevant
  - docs updated
  - tests updated
  - packaged-desktop impact reviewed

### Required engineering loop for every sprint

1. Confirm current-state code paths.
2. Implement the sprint vertically.
3. Add or update tests.
4. Run desktop checks.
5. Update this plan with sprint status and decisions.
6. Update desktop docs if user behavior changed.

## Current Baseline

### Already implemented

- Local multi-user auth and session persistence
- Admin/non-admin users
- Users settings page
- Source/transaction/item family-sharing controls
- Global `personal` / `family` request scope
- Shared visibility in many analytics surfaces

### Main architectural debt

- no shared-group entity
- no group membership model
- no shared-group roles
- no unified ownership abstraction across domains
- no coherent workspace UX
- no shared planning model

## Sprint Map

| Sprint | Name | Main outcome |
| --- | --- | --- |
| 0 | Program Lock | Finalize product contract and migration envelope |
| 1 | Identity and Session UX | Complete user/session/account-switch groundwork |
| 2 | Shared Group Foundation | Add shared-group schema and membership base |
| 3 | Roles and Management Surfaces | Add group roles and management UI |
| 4 | Workspace Context Kernel | Replace ad hoc family scope with workspace context |
| 5 | Compatibility and Backfill | Migrate legacy family semantics safely |
| 6 | Shell and Workspace UX | Build visible workspace switcher and scope clarity |
| 7 | Sources and Connector Ownership | Let sources/connectors belong to user or shared group |
| 8 | Transactions and Allocations | Move receipts from visibility-sharing to ownership/allocation |
| 9 | Documents and Review Queue | Make OCR/import/review group-aware |
| 10 | Budget Months and Budget Rules | Shared budgeting model |
| 11 | Cash Flow and Reconciliation | Shared cashflow ledger and link semantics |
| 12 | Recurring Bills and Obligations | Shared recurring planning |
| 13 | Goals, Notifications, Reports | Shared planning and reporting completion |
| 14 | Dashboard, Groceries, Merchants | Full workspace-aware summaries |
| 15 | Chat, Query, Quality, Analytics | Finish secondary surfaces |
| 16 | Backup, Restore, Export, Import | Durable packaged-profile correctness |
| 17 | Hardening, Packaging, Release | QA, migration soak, docs, RC |

## Sprint Details

### Sprint 0: Program Lock

**Objective**

Lock the shared-group product contract, data migration strategy, and compatibility rules before schema work starts.

**Scope**

- Convert the vision into executable technical decisions.
- Define the final naming model:
  - user
  - shared group
  - group type
  - workspace
- Define the compatibility policy for legacy `family_*` fields.

**Deliverables**

- This plan approved and treated as source of truth.
- ADR-style summary inside this doc for:
  - ownership model
  - workspace semantics
  - migration sequence
- Explicit decision on whether a user can belong to multiple groups at launch.
  - Recommended: yes

**Verification**

- Doc review only.

**Exit criteria**

- No unresolved core modeling questions remain.

### Sprint 1: Identity and Session UX

**Objective**

Finish the identity/operator layer so multi-user shared finance has solid account/session ergonomics.

**Scope**

- Extend current account surfaces with:
  - current-user profile/preferences
  - session list and revoke UI
  - explicit sign-out/account-switch affordances
- Ensure personal data remains private across logins on one desktop install.

**Backend**

- Expose any missing current-user/session endpoints already available but not surfaced.
- Add tests around session revocation and account switching behavior.

**Frontend**

- Add account/session management surfaces under settings.
- Add shell affordances for:
  - current user identity
  - switch user
  - session/device visibility

**Key files likely touched**

- `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `apps/desktop/vendor/backend/src/lidltool/api/auth.py`
- `apps/desktop/vendor/frontend/src/api/users.ts`
- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `apps/desktop/vendor/frontend/src/pages/UsersSettingsPage.tsx`

**Verification**

- fresh login
- second user login
- session revoke
- current-user sign-out/sign-in

**Exit criteria**

- Multi-user account operation is ergonomic before shared-group management begins.

### Sprint 2: Shared Group Foundation

**Objective**

Add the core shared-group schema and membership primitives.

**Scope**

- Add entities such as:
  - `shared_groups`
  - `shared_group_members`
- Add `group_type` with at least:
  - `household`
  - `community`
- Define lifecycle state for groups.

**Backend/Data**

- New migration(s)
- ORM models
- service helpers for create/list/get group
- membership lookup helpers

**Design rules**

- Shared groups are real top-level ownership containers.
- Avoid hardcoding household-only terminology into the schema.

**Key files likely touched**

- `apps/desktop/vendor/backend/src/lidltool/db/models.py`
- `apps/desktop/vendor/backend/src/lidltool/db/migrations/versions/*`
- new shared-group service module under vendored backend

**Verification**

- migration up/down if supported
- create/list groups
- create/list memberships

**Exit criteria**

- Shared-group data model exists and is stable enough for all later domain migrations.

### Sprint 3: Roles and Management Surfaces

**Objective**

Add role-based control for shared groups and the first usable management UI.

**Scope**

- Membership roles, at minimum:
  - `owner`
  - `manager`
  - `member`
- Add group management UI:
  - create group
  - rename group
  - change group type if allowed
  - add existing local users to a group
  - remove member
  - change role

**Backend**

- Group management endpoints
- authorization rules for role changes

**Frontend**

- New settings surface for shared groups and members
- clear separation between:
  - desktop user administration
  - shared-group administration

**Verification**

- admin creates users
- admin or owner creates group
- add/remove members
- role permission checks

**Exit criteria**

- A household or community can actually be defined in the product.

### Sprint 4: Workspace Context Kernel

**Objective**

Replace the ad hoc `personal/family` request model with a real workspace context.

**Scope**

- Introduce an explicit workspace resolver for every request.
- Supported workspace kinds:
  - personal
  - shared-group by `group_id`
- Ensure every request can resolve:
  - authenticated user
  - active workspace
  - authorization against that workspace

**Backend**

- workspace parser/resolver
- workspace authorization helpers
- shared query helpers for:
  - personal owner filters
  - shared-group owner filters

**Frontend**

- replace old request-scope persistence with workspace selection persistence
- remove old overlay-style scope compatibility once workspace selection is canonical

**Key files likely touched**

- `apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
- `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `apps/desktop/vendor/frontend/src/lib/request-scope.ts`
- `apps/desktop/vendor/frontend/src/app/scope-provider.tsx`
- `apps/desktop/vendor/frontend/src/lib/api-client.ts`

**Verification**

- personal workspace still works
- shared workspace resolves correctly
- unauthorized group access is denied

**Exit criteria**

- The app has a real workspace kernel instead of a global family visibility toggle.

### Sprint 5: Compatibility and Backfill

**Status**

- complete

**Delivered in current execution**

- additive workspace-ownership migration added for sources, transactions, items, documents, planning records, saved queries, notifications, and secondary analytics tables
- legacy overlay visibility and `family_*` compatibility paths removed from schema, scope parsing, API contracts, and desktop UI
- route and query helpers now resolve personal vs shared-group ownership explicitly without compatibility bridges
- fresh-profile migrations now create only the real ownership/allocation model

**Deferred**

- none for desktop fresh-profile installs

**Objective**

Move any legacy overlay-style sharing semantics into the real ownership/allocation model so later domain work can proceed cleanly.

**Scope**

- Define cleanup rules for any residual overlay-style sharing fields.
- Backfill shared data into ownership/allocation-ready form where needed.
- Remove compatibility reads once the real ownership model is in place.

**Design rules**

- Favor the real ownership model over temporary overlay compatibility.
- Because there is no installed desktop base, remove obsolete schema and contract fields instead of preserving them.

**Verification**

- existing databases migrate cleanly
- legacy shared receipts remain visible in the correct shared workspace
- no cross-group leakage

**Exit criteria**

- Legacy sharing no longer blocks the new ownership model.

### Sprint 6: Shell and Workspace UX

**Status**

- complete for the desktop shell/kernel path

**Delivered in current execution**

- workspace-aware query invalidation now covers more finance surfaces including sources, recurring planning, review queue, and notifications
- sources and transaction detail now expose workspace ownership metadata instead of only legacy family-sharing language where edited

**Objective**

Build the visible workspace model in the desktop shell.

**Scope**

- Replace silent scope radio with a real workspace switcher.
- Show:
  - current user
  - current workspace
  - workspace type and name
- Clarify whether the user is in personal or shared space on every major finance page.

**Frontend**

- App shell workspace switcher
- inline badges/headers for workspace clarity
- empty states for:
  - no shared groups
  - no permission
  - no shared data

**UX rules**

- The workspace must never change silently.
- The user must always understand which workspace owns the current data.

**Verification**

- workspace switching invalidates and refetches correctly
- dashboard, budget, transactions, reports visibly reflect workspace

**Exit criteria**

- Shared finance becomes legible in the UI.

### Sprint 7: Sources and Connector Ownership

**Status**

- partial implementation complete

**Delivered in current execution**

- sources now support explicit shared-group ownership in schema, workspace visibility, mutation, sync-status access, and manual/OCR upload flows
- legacy source-sharing endpoint now acts as a compatibility bridge that can assign or clear `shared_group_id` in a shared workspace

**Deferred**

- connector setup flows still need richer explicit destination copy in the desktop UI

**Objective**

Make sources/connectors belong to either a user or a shared group.

**Scope**

- Ownership selection during connector/source creation
- source list grouped by workspace
- source status and sync semantics aligned with workspace

**Backend**

- source ownership model migration
- source visibility and mutation rules by workspace

**Frontend**

- `SourcesPage`
- connector setup/config flows
- import destination selection:
  - personal
  - selected shared group

**Important rule**

- Connector ownership must be explicit.
- Do not rely on global family visibility after this sprint.

**Verification**

- create/connect source in personal workspace
- create/connect source in shared workspace
- sync in each workspace

**Exit criteria**

- Shared groups can own ingestion sources directly.

### Sprint 8: Transactions and Allocations

**Status**

- partial implementation complete

**Delivered in current execution**

- transactions and items now carry `shared_group_id` ownership/allocation fields
- transaction search/detail/export payloads now surface ownership metadata and filter item visibility by active shared workspace
- manual ingest and connector sync now propagate workspace ownership into newly created transactions and items

**Deferred**

- broader transaction list/detail UX cleanup beyond the ownership labels added in this execution

**Objective**

Replace receipt family-sharing as the primary collaboration model with ownership plus allocation semantics.

**Scope**

- Transactions can be:
  - personal-owned
  - shared-group-owned
- Mixed baskets can allocate items between:
  - personal
  - shared group
- Preserve compatibility for legacy item sharing during migration.

**Backend**

- transaction ownership model
- transaction-item allocation model
- query helpers updated for ownership and allocation

**Frontend**

- transaction detail ownership/allocation editor
- transaction list ownership display
- owner/allocation badges

**Design rules**

- Sharing a receipt is not enough.
- The product must support mixed baskets without ambiguity.

**Verification**

- personal-only transaction
- shared-only transaction
- mixed basket allocation
- analytics reflect allocations correctly

**Exit criteria**

- Receipts are collaboration-capable in a real accounting sense.

### Sprint 9: Documents and Review Queue

**Status**

- partial implementation complete

**Delivered in current execution**

- uploaded documents now bind to the selected workspace
- OCR processing and review-queue mutations now authorize against the active workspace instead of forced personal scope
- review payloads now include shared ownership metadata where available

**Objective**

Make OCR import, document storage, and review queue flows workspace-aware.

**Scope**

- Documents inherit or select destination workspace
- Review queue preserves workspace ownership
- OCR/import metadata remains correct after shared migration

**Backend**

- document ownership fields or ownership resolution
- review queue filtering by workspace

**Frontend**

- upload/import destination selector
- review queue workspace badges

**Verification**

- personal upload
- shared upload
- review queue approval for both

**Exit criteria**

- Import pipelines do not break the workspace model.

### Sprint 10: Budget Months and Budget Rules

**Status**

- partial implementation complete

**Delivered in current execution**

- budget months and rules now support personal or shared-group ownership
- budget summary/utilization paths now resolve records through workspace ownership filters

**Objective**

Make budgeting a true first-class shared-group feature.

**Scope**

- `budget_months` can be personal or shared-group owned
- `budget_rules` can be personal or shared-group owned
- budget summary semantics become workspace-consistent

**Backend**

- migrate ownership model
- update `budget/service.py`
- update budget utilization logic

**Frontend**

- budget page workspace clarity
- budget month editing in personal or shared workspace
- budget rules listed and edited per workspace

**Verification**

- personal budget month
- shared budget month
- personal/shared rule calculations
- reports/dashboard consistency

**Exit criteria**

- The active workspace determines the budget model unambiguously.

### Sprint 11: Cash Flow and Reconciliation

**Status**

- partial implementation complete

**Delivered in current execution**

- cashflow entries now support workspace ownership
- reconciliation and linked-transaction validation now enforce workspace-correct access rules

**Objective**

Make cashflow and reconciliation workspace-consistent.

**Scope**

- `cashflow_entries` become personal or shared-group owned
- reconciliation can link to transactions owned by the same active workspace
- no more personal-only cashflow mixed with shared receipt spend

**Backend**

- ownership migration for cashflow
- reconciliation validation rules

**Frontend**

- budget page cashflow tab
- dedicated cashflow page
- clearer reconciliation affordances

**Verification**

- personal inflow/outflow
- shared inflow/outflow
- shared reconciliation to shared receipt
- mixed basket edge cases

**Exit criteria**

- Cashflow no longer violates the workspace model.

### Sprint 12: Recurring Bills and Obligations

**Status**

- partial implementation complete

**Delivered in current execution**

- recurring bills and occurrence workflows now accept workspace visibility and serialize workspace ownership
- overview, calendar, forecast, gap, matching, and reconciliation flows now bind to the active workspace

**Objective**

Move recurring planning to real shared ownership.

**Scope**

- `recurring_bills` and occurrences can belong to personal or shared workspace
- recurring matching respects workspace ownership
- obligation planning works for households and communities

**Backend**

- recurring bill ownership migration
- match/reconcile rules updated

**Frontend**

- bills page workspace-aware CRUD
- upcoming obligations panel updated

**Verification**

- personal bill lifecycle
- shared bill lifecycle
- matching and paid/unpaid states in shared workspace

**Exit criteria**

- Shared bills are no longer modeled as somebody’s private bill plus visibility.

### Sprint 13: Goals, Notifications, Reports

**Status**

- partial implementation complete

**Delivered in current execution**

- goals, notifications, and report templates now carry workspace ownership semantics
- notification generation/update/read flows now authorize and filter by active workspace

**Objective**

Complete the higher-level planning and communication model.

**Scope**

- `goals` become workspace-owned
- `notifications` become workspace-aware
- reports reflect active workspace correctly

**Backend**

- goal ownership migration
- notification generation by workspace
- report payload ownership semantics

**Frontend**

- goals page
- notification center
- reports page labeling and exports

**Verification**

- shared savings goal
- shared spend-cap goal
- shared budget-risk notification
- shared report export

**Exit criteria**

- Planning and reporting are coherent for personal and shared finance.

### Sprint 14: Dashboard, Groceries, Merchants

**Status**

- foundational backend support complete; UI mainly inherited from workspace-aware query paths

**Delivered in current execution**

- dashboard/groceries/merchants continue to resolve visibility through the active workspace kernel
- workspace cache invalidation now refetches those summaries on workspace changes and mutations more reliably

**Objective**

Finish the major summary surfaces on top of the new ownership model.

**Scope**

- dashboard cards and summaries are workspace-correct
- groceries page is workspace-aware
- merchants page is workspace-aware

**Frontend**

- visible workspace identity on summary pages
- owner/allocation explanations where needed

**Backend**

- summary endpoints updated for workspace ownership and allocations

**Verification**

- compare personal vs shared dashboard
- shared groceries basket analysis
- shared merchant summary

**Exit criteria**

- The main finance shell feels complete and coherent in both solo and collaborative use.

### Sprint 15: Chat, Query, Quality, Analytics

**Status**

- partial implementation complete

**Delivered in current execution**

- saved queries now support workspace ownership
- analytics scope/query helpers now prefer shared-group ownership over legacy family overlay rules
- chat threads now support shared-group ownership and workspace-authorized access in the API layer

**Deferred**

- offer/watchlist/alert surfaces still need a full workspace-ownership migration

**Objective**

Finish the secondary surfaces so the whole desktop product follows the same workspace model.

**Scope**

- chat threads/messages
- saved queries
- quality flows
- product analytics
- comparison/search surfaces

**Backend**

- workspace-aware chat ownership
- workspace-aware saved queries where required
- analytics/quality filters migrated off legacy family semantics

**Frontend**

- chat workspace selector or current workspace binding
- query/quality pages reflect workspace

**Verification**

- shared chat thread visibility
- shared quality review
- shared product analytics

**Exit criteria**

- No active desktop finance surface still depends on the old family overlay model.

### Sprint 16: Backup, Restore, Export, Import

**Status**

- compatibility preserved; broader UX/doc work still open

**Delivered in current execution**

- migration remains additive and profile-safe so whole-database backup/restore preserves shared-group ownership records without destructive conversion
- desktop build/runtime backup path remained intact during ownership migration

**Objective**

Make the complete multi-user/shared-group model durable in real desktop operations.

**Scope**

- backup/restore preserves:
  - users
  - sessions where appropriate
  - shared groups
  - memberships
  - workspace-owned records
- import/export semantics documented clearly
- restored profiles boot cleanly into correct shared state

**Backend/Desktop runtime**

- backup manifest updates
- restore validations
- migration checks in restored environments

**Frontend**

- settings copy
- restore warnings
- import/export explanations

**Verification**

- fresh-profile restore
- restore with multiple users and groups
- export payload sanity
- packaged app smoke after restore

**Exit criteria**

- The collaboration model survives real desktop backup/restore workflows.

### Sprint 17: Hardening, Packaging, Release

**Status**

- cleanup and hardening pass complete

**Delivered in current execution**

- backend compile checks pass for migrated ownership files
- desktop `npm run typecheck` and `npm run build` are part of the verification loop for this execution
- packaging patch scripts and smoke fixtures no longer depend on legacy `family_*` contracts
- docs and i18n copy now use shared-workspace/allocation language instead of family-overlay wording

**Objective**

Finish the program with migration safety, QA coverage, docs, and packaged release confidence.

**Scope**

- regression audit
- migration soak testing on seeded legacy DBs
- packaged app smoke tests
- docs cleanup
- release checklist updates

**Verification matrix**

- single-user fresh install
- single-user restored profile
- two-user household
- three-to-five-user community
- multi-group user membership
- personal vs shared workspace switching
- package build and boot

**Exit criteria**

- The team can honestly say the complete vision is implemented.

## Cross-Cutting Workstreams

The following workstreams run across several sprints and must be treated as ongoing:

### 1. Authorization correctness

- no cross-group leakage
- no accidental service-user bypass
- no silent downgrade from ownership to visibility

### 2. Migration safety

- old DBs migrate cleanly
- legacy sharing data remains usable
- no irreversible destructive migration until compatibility is proven

### 3. UX clarity

- current workspace always visible
- ownership of records understandable
- personal vs shared distinction never hidden

### 4. Tests

- backend service tests
- API contract tests
- frontend route/page tests
- desktop packaged smoke where behavior changed

### 5. Docs

- this plan updated continuously
- `apps/desktop/README.md` updated when user-facing behavior changes
- release checklist updated for packaging and restore semantics

## Suggested File Hotspots

This program will likely touch at least these surfaces repeatedly:

### Backend

- `apps/desktop/vendor/backend/src/lidltool/db/models.py`
- `apps/desktop/vendor/backend/src/lidltool/db/migrations/versions/*`
- `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
- `apps/desktop/vendor/backend/src/lidltool/analytics/queries.py`
- `apps/desktop/vendor/backend/src/lidltool/budget/service.py`
- `apps/desktop/vendor/backend/src/lidltool/goals/service.py`
- `apps/desktop/vendor/backend/src/lidltool/reports/service.py`
- `apps/desktop/vendor/backend/src/lidltool/notifications/service.py`
- recurring, documents, and chat service areas

### Frontend

- `apps/desktop/vendor/frontend/src/components/shared/AppShell.tsx`
- `apps/desktop/vendor/frontend/src/app/scope-provider.tsx`
- `apps/desktop/vendor/frontend/src/lib/request-scope.ts` or replacement
- `apps/desktop/vendor/frontend/src/lib/api-client.ts`
- `apps/desktop/vendor/frontend/src/pages/UsersSettingsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/SettingsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/SourcesPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/TransactionDetailPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BudgetPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/BillsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/CashFlowPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/DashboardPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/ReportsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/GoalsPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/MerchantsPage.tsx`
- any new shared-group settings and management pages

## Completion Definition

The program is complete only when all of the following are true:

- Collaboration is modeled by real shared-group ownership.
- Legacy family sharing is no longer the primary abstraction.
- Personal and shared workspaces are consistent across all active desktop finance surfaces.
- Single-user usage still feels natural and simple.
- Households and flat communities both work without another schema redesign.
- Desktop backup/restore and packaged builds are validated with the new model.
- Desktop docs describe the new behavior accurately.

## Recommended Execution Order If Resources Are Tight

If the team needs to preserve momentum under limited capacity, the critical path is:

1. Sprint 0
2. Sprint 2
3. Sprint 4
4. Sprint 5
5. Sprint 6
6. Sprint 8
7. Sprint 10
8. Sprint 11
9. Sprint 12
10. Sprint 14
11. Sprint 16
12. Sprint 17

Do not skip:
- shared-group foundation
- workspace kernel
- transaction ownership/allocation
- budget and cashflow migration

Those are the minimum structural steps required to claim the complete vision.
