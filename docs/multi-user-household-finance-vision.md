# Desktop Multi-User Household Finance Vision

This document is for `apps/desktop` only.

It describes:
- what is implemented today
- where the current personal/family model breaks down
- the target model for a future multi-user desktop app where people keep personal data and also collaborate on shared household data

## Goals

- Keep desktop local-first and occasional-use.
- Support multiple local app users in one desktop installation.
- Let each user keep private personal finance data.
- Let users collaborate on shared household finance data.
- Make scope behavior consistent across transactions, budgets, bills, cash flow, goals, reports, and notifications.

## Non-goals

- Turning desktop into an always-on server product.
- Designing self-hosted household sync semantics in this document.
- Solving cross-device collaboration first.

## Current State

### 1. Identity and session model already exists

Desktop already supports:
- multiple local users
- first-user setup and login
- persistent user sessions
- admin vs non-admin users
- user-scoped API keys
- a desktop users settings page for create/edit/delete

Relevant implementation:
- `apps/desktop/vendor/backend/src/lidltool/db/models.py`
- `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `apps/desktop/vendor/backend/src/lidltool/api/auth.py`
- `apps/desktop/vendor/backend/src/lidltool/auth/sessions.py`
- `apps/desktop/vendor/frontend/src/pages/UsersSettingsPage.tsx`
- `apps/desktop/overrides/frontend/src/pages/LoginPage.tsx`

### 2. The receipt domain already has a primitive shared-allocation layer

Today the receipt/transaction side has:
- `sources.user_id`
- `sources.shared_group_id`
- `transactions.user_id`
- `transactions.shared_group_id`
- `transaction_items.shared_group_id`

The UI already exposes:
- source workspace ownership on `SourcesPage`
- receipt-level and item-level shared allocation on `TransactionDetailPage`
- an explicit `personal` / `group:<id>` workspace switch in the app shell

Relevant implementation:
- `apps/desktop/vendor/backend/src/lidltool/analytics/scope.py`
- `apps/desktop/vendor/backend/src/lidltool/api/http_server.py`
- `apps/desktop/vendor/frontend/src/pages/SourcesPage.tsx`
- `apps/desktop/vendor/frontend/src/pages/TransactionDetailPage.tsx`
- `apps/desktop/vendor/frontend/src/app/scope-provider.tsx`

### 3. Shared workspace scope works mostly as an analytics visibility mode

The current explicit shared-workspace scope behavior is strongest on:
- transactions
- item analytics
- dashboards
- reports
- product and purchase analytics
- some quality/query surfaces

This means the current system can already answer a question like:
- "show me family-visible grocery spending"

But it does that by widening visibility to shared receipt data, not by switching into a true household finance workspace.

### 4. Budgeting and planning are still fundamentally user-owned

The following domains are still modeled as user-owned records:
- `budget_months`
- `cashflow_entries`
- `recurring_bills`
- `goals`
- `notifications`

`budget_rules` are also effectively user-scoped in current API usage.

Important consequence:
- the budget summary can combine family-visible receipt spend with personal-only planning records
- cash flow entries cannot cleanly link to another user's family-shared transaction
- recurring bills, goals, and notifications do not behave like shared household objects

Relevant implementation:
- `apps/desktop/vendor/backend/src/lidltool/budget/service.py`
- `apps/desktop/vendor/backend/src/lidltool/goals/service.py`
- `apps/desktop/vendor/backend/src/lidltool/reports/service.py`
- `apps/desktop/vendor/backend/src/lidltool/notifications/service.py`

## Main Gaps

### 1. There is no household entity

The app has users, but it does not have:
- households
- household membership
- household roles
- invitations
- explicit access boundaries between one family and another

Current `family` scope is global visibility logic, not household membership logic.

### 2. Family scope is not a true ownership model

The current model answers:
- "is this receipt visible in family mode?"

It does not answer:
- "who owns this household?"
- "which users belong to the same household?"
- "is this budget personal or household?"
- "is this recurring bill mine or shared?"

### 3. The finance model is inconsistent across domains

Current behavior is split:
- transaction analytics can be family-visible
- planning records remain personal

That makes the meaning of the scope switch inconsistent.

### 4. `family` is now the wrong abstraction

The current naming is too narrow and too technical.

What we actually need is:
- `Personal`
- `Household`

That maps better to budgeting, helping, and shared responsibilities.

## Vision

Desktop should evolve from:
- a personal finance app with a family visibility overlay

to:
- a local multi-user finance app with two first-class workspaces: personal and household

Each user should be able to:
- sign into the same desktop app
- see their own personal workspace
- switch to a shared household workspace
- contribute receipts, budgets, bills, goals, and plans at either level

## Target Product Model

### 1. First-class household model

Add explicit entities such as:
- `households`
- `household_members`
- `household_roles`

At minimum:
- each non-service user belongs to one household
- a household has one or more members
- one or more members can manage membership and shared finance settings

### 2. First-class ownership scope

Every finance record should have an ownership scope:
- `personal`
- `household`

For some records we may also need attribution fields:
- `owner_user_id`
- `household_id`
- `created_by_user_id`

This should replace the current pattern where some tables are personal, some are family-visible, and some are mixed.

### 3. Shared finance should be modeled, not inferred

Shared household data should exist as actual household-owned records, not just as personal records that become visible in family mode.

That applies to:
- budget months
- budget rules
- cash flow entries
- recurring bills
- goals
- notifications
- reports

### 4. Transaction sharing should become allocation-aware

Receipts are special because one basket can mix:
- personal items
- household items

The long-term target should support:
- receipt owned by person, with household allocations
- receipt owned by household
- item-level split between personal and household

The old overlay-style sharing flags were only ever transitional, not the final model.

## Recommended Target Data Shape

### Core ownership

Introduce a common scope pattern:
- `scope_kind`: `personal` or `household`
- `scope_user_id`: nullable
- `scope_household_id`: nullable

Rules:
- personal rows use `scope_kind=personal` and `scope_user_id`
- household rows use `scope_kind=household` and `scope_household_id`

### Household entities

Suggested new tables:
- `households`
- `household_members`
- `household_invites` or desktop-local pending member entries

### Finance domain migration targets

Move these domains to the same scope model:
- `sources`
- `transactions`
- `transaction_items`
- `budget_rules`
- `budget_months`
- `cashflow_entries`
- `recurring_bills`
- `goals`
- `notifications`

## Recommended UX Direction

### 1. Replace “family” with “household”

User-facing copy should move toward:
- `Personal`
- `Household`

Keep backend compatibility temporarily if needed, but shift UI language early.

### 2. Make scope visible and stable

The top-level workspace switch should mean the same thing everywhere:
- in personal workspace, all views use personal records only
- in household workspace, all views use household records only

We should avoid screens where:
- spend is household-visible
- budget is personal-only
- goals are personal-only

### 3. Separate user management from household management

Current `Users Settings` mixes desktop-local admin concerns with app users.

Future structure should separate:
- desktop user administration
- household membership and roles
- shared finance defaults

### 4. Make connector ownership explicit

For connectors and imported data, the user should be able to choose:
- import into personal workspace
- import into household workspace
- import personal receipt, then allocate selected items to household

## Migration Strategy

### Phase 1. Introduce household identity without changing all UX

- add `households` and `household_members`
- create one default household for existing desktop datasets
- attach existing users to that household
- gate current `family` scope by household membership instead of global visibility

Outcome:
- current family mode stops being globally unsafe

### Phase 2. Unify scope infrastructure

- add shared scope helpers used by all finance domains
- move from ad hoc `user_id` filters toward common personal/household ownership filters
- keep compatibility shims for old routes where needed

Outcome:
- one scope concept across backend queries

### Phase 3. Migrate planning domains

- make `budget_months` household-capable
- make `cashflow_entries` household-capable
- make `recurring_bills` household-capable
- make `goals` household-capable
- make `notifications` household-capable

Outcome:
- budgeting becomes coherent in both personal and household workspaces

### Phase 4. Upgrade transaction allocation flows

- preserve current source/receipt/item allocation controls as coherent workspace UI
- add clearer ownership/allocation UI
- support mixed baskets without overloading receipt ownership semantics

Outcome:
- better household accounting for real-world receipts

### Phase 5. Clean up language and legacy fields

- rename UI from `household`-specific assumptions to generalized shared-workspace language where needed
- remove legacy overlay flags once ownership/allocation is stable

## Suggested Rules For Future Development

- Never introduce a new finance feature that is only personal unless that is explicit product intent.
- Never add a new shared feature by using visibility flags alone when ownership matters.
- Keep the scope switch semantically consistent across all finance pages.
- Treat personal and household as first-class finance workspaces, not as filtering tricks.
- Keep desktop local-first: one local database, multiple app users, explicit shared household data.

## Immediate Next Steps

1. Add a lightweight household foundation design and migration spec.
2. Decide whether desktop supports exactly one household per installation in v1, or multiple households later.
3. Define the target ownership model for:
   - connectors
   - transactions
   - budget months
   - cash flow
   - recurring bills
   - goals
4. Rename the product language from `family` to `household` in planning docs.
5. Implement Phase 1 before expanding more budgeting logic.

## Summary

What exists today is a useful base:
- real multi-user auth
- user management
- session handling
- shared receipt visibility
- shared-workspace-aware analytics surfaces

What does not exist yet is the thing the product now needs:
- a true household finance model

The right direction for desktop is not to keep extending overlay sharing flags.

The right direction is:
- explicit household membership
- explicit personal vs household ownership
- consistent scope behavior across every finance domain
