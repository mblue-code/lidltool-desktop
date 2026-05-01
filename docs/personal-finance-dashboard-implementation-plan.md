# Personal Finance Dashboard And Transaction Intelligence Plan

Status: implementation plan
Audience: desktop app implementation agents
Repo: desktop side repo
Last updated: 2026-05-01

## 1. Executive Summary

The desktop app is no longer only a receipt overview or a grocery-focused
Haushaltsbuch. The current product direction is a local-first personal finance
intelligence platform:

- It can still work very well when the user only has grocery receipts.
- It must become substantially more useful when the user imports bank-account
  history, statement rows, manual cash-flow entries, bills, recurring expenses,
  and retailer receipts.
- The transaction page must become the central user-facing history surface.
- The dashboard must become a personal finance overview, not only a shopping
  receipt summary.
- Grocery receipt intelligence must remain strong and must not be diluted by
  bank-account categories.
- The app must support English and German without hard-coded user-facing text.

The key architectural change is to separate two related but different category
systems:

1. Transaction-level finance categories.
   These describe the purpose of the whole transaction, such as groceries,
   housing, insurance, credit, car, mobility, investment, subscriptions, health,
   income, fees, tax, and other.

2. Item-level grocery/product categories.
   These describe individual receipt items, such as beverages, dairy, meat,
   bakery, pantry, produce, fish, household supplies, and deposit.

The overall dashboard pie chart must use transaction-level finance categories.
The existing grocery pie chart must remain grocery-only and must use item-level
grocery categories.

Because the product is not published yet and has no external users, this plan
does not require a compatibility migration flow for existing production data.
Implementation may reshape schema, seed data, demo fixtures, and tests directly
as long as local developer data handling is explicit and the desktop repo
remains standalone.

## 2. Non-Negotiable Constraints

### 2.1 Desktop side-repo isolation

Follow the repository rules in AGENTS.md:

- Do not add runtime or build-time dependencies on paths outside this repo.
- Do not import or execute main-repo code at runtime.
- Any shared logic needed by desktop must live inside this repo.
- Packaging config must reference only files inside this repo.
- Dedicated sync/vendor scripts may read from the main repo only to copy files
  into this repo.
- If speed conflicts with side-repo isolation, choose isolation.

### 2.2 Multilingual implementation

The app currently supports English and German. All user-facing text added by
this plan must be localized.

Rules:

- No new hard-coded user-facing English or German strings inside React views.
- Put strings in the existing i18n system.
- Add both English and German messages in the same change.
- Labels for categories, filters, insights, empty states, charts, and buttons
  must resolve through a shared localization path.
- Tests must assert the intended labels without depending on implementation-only
  raw keys.
- Do not duplicate category label maps in multiple pages.

### 2.3 No production migration requirement

There are no published users. Therefore:

- Do not spend implementation effort on backwards-compatible production
  migrations.
- It is acceptable to reshape tables and seed taxonomy directly.
- It is acceptable to adjust demo fixtures, test fixtures, generated contracts,
  and local seed data.
- Still keep local developer ergonomics in mind: document reset/reseed behavior
  where needed.
- Do not remove useful tests; update them to reflect the new canonical product
  direction.

### 2.4 Scope boundary for investments

Investment tracking is deliberately narrow:

- Track money flowing out toward investments.
- Do not track compounding, holdings, gains, losses, broker balances, asset
  allocation, or portfolio performance.
- The dashboard can show investment outflow as a spending/allocation category.
- Investment outflow should not be presented as a loss or ordinary consumption
  in copy. Use language like allocation, transfer, or investment outflow.

## 3. Current Codebase Baseline

The current desktop app already has several pieces that make this plan feasible.

### 3.1 Routes and navigation

Current observations:

- The canonical route already exists at /transactions.
- /receipts redirects to /transactions.
- The main navigation already includes Transactions.
- Some user-facing links and labels still say Receipts or Belege.
- The transaction page header currently uses the receipts nav label, which is
  why German UI still shows Belege in the screenshot.

Important files:

- vendor/frontend/src/main.tsx
- vendor/frontend/src/components/shared/AppShell.tsx
- vendor/frontend/src/pages/TransactionsPage.tsx
- vendor/frontend/src/pages/TransactionDetailPage.tsx
- vendor/frontend/src/pages/ManualImportPage.tsx
- vendor/frontend/src/i18n/messages.ts
- vendor/frontend/src/i18n/literals.en.json
- vendor/frontend/src/i18n/literals.de.json

### 3.2 Transaction list and filters

The current transaction page supports:

- text query
- source id
- source kind
- weekday
- hour
- timezone offset
- merchant name
- year
- month
- purchased from/to
- min/max total
- sorting
- pagination

Current gaps:

- No first-class direction filter.
- No transaction-level finance category filter.
- No parent-category filter.
- No tag filter.
- No merchant facet list with counts.
- No fast inflow/outflow switching.
- Advanced filters are a large form rather than a polished finance filter bar.
- Total range currently assumes positive totals and does not clearly model
  inflow/outflow semantics.

Important files:

- vendor/frontend/src/pages/TransactionsPage.tsx
- vendor/frontend/src/api/transactions.ts
- vendor/frontend/src/app/queries.ts
- vendor/backend/src/lidltool/api/http_server.py
- vendor/backend/src/lidltool/analytics/queries.py

### 3.3 Data model

Current transaction fields include:

- source_id
- user_id
- shared_group_id
- source_account_id
- source_transaction_id
- purchased_at
- merchant_name
- total_gross_cents
- currency
- discount_total_cents
- confidence
- fingerprint
- raw_payload

Current transaction item fields include:

- transaction_id
- source_item_id
- line_no
- name
- qty
- unit
- unit_price_cents
- line_total_cents
- category
- category_id
- category_method
- category_confidence
- category_source_value
- category_version
- product_id
- is_deposit
- confidence
- raw_payload

Current gap:

- A receipt item can be categorized, but a bank transaction cannot be classified
  cleanly as credit, insurance, housing, investment, car, or income at the
  transaction level.

Important files:

- vendor/backend/src/lidltool/db/models.py
- vendor/backend/src/lidltool/db/migrations/versions/
- vendor/backend/src/lidltool/ingest/
- vendor/backend/src/lidltool/ingestion_agent/

### 3.4 Category taxonomy

The backend already has a categories table and item categorization migration.
The frontend already has a CategoryPresentation component with English and
German labels for many category ids.

Current gap:

- The taxonomy is not unified around personal finance.
- The backend seeded taxonomy is smaller than the frontend category label list.
- Dashboard category labels are locally duplicated in DashboardPage.
- Finance categories like credit, insurance, housing, car, mobility, investment,
  income, tax, and subscriptions are not first-class.

Important files:

- vendor/backend/src/lidltool/db/migrations/versions/0017_transaction_item_categorization.py
- vendor/backend/src/lidltool/db/migrations/versions/0023_add_fish_category.py
- vendor/frontend/src/components/shared/CategoryPresentation.tsx
- vendor/backend/src/lidltool/analytics/categorization.py
- vendor/backend/src/lidltool/analytics/item_categorizer.py
- vendor/backend/src/lidltool/analytics/normalization.py

### 3.5 Dashboard

The dashboard already has:

- KPI cards
- cash inflow
- cash outflow
- spending overview ring chart
- cash flow bars
- recent grocery transactions
- recent activity
- merchants
- goals and budget panels

Current gap:

- The spending ring chart currently uses item-level categories.
- There is no separate overall finance category pie.
- The grocery breakdown and overall spending breakdown are conflated.

Important files:

- vendor/frontend/src/pages/DashboardPage.tsx
- vendor/frontend/src/api/dashboard.ts
- vendor/backend/src/lidltool/api/http_server.py
- vendor/backend/src/lidltool/analytics/queries.py
- tests/backend/test_dashboard_window_summaries.py
- vendor/frontend/src/pages/__tests__/DashboardPage.test.tsx

## 4. Product Model

### 4.1 Mental model

The app should present one coherent model:

- Transactions are the canonical financial history.
- Receipts are a type of transaction source.
- Grocery receipt items provide extra detail inside grocery transactions.
- Bank imports add broad personal finance coverage.
- Manual entries fill gaps.
- Reports and insights turn the history into understanding.

### 4.2 Navigation model

Primary navigation should remain:

- Dashboard
- Transactions
- Ingestion
- Groceries
- Budget
- Bills
- Cash Flow
- Reports
- Goals
- Merchants
- Settings

Rules:

- Do not add a separate Receipts primary page.
- Keep /receipts as a redirect alias for compatibility during development.
- Use Transactions as the visible label in both English and German.
- Use receipts/Belege only for receipt-specific actions, documents, OCR uploads,
  or individual source records.

### 4.3 Dashboard model

The dashboard must answer:

- How much money moved in and out?
- Where did my outflow go?
- How much did I spend on groceries specifically?
- Which categories changed?
- Which merchants dominate my history?
- What bills or recurring patterns matter soon?
- What should I look at next?

It must support two data states:

1. Receipt-only state.
   The app behaves like an excellent Haushaltsbuch. Grocery pie, merchant
   summaries, receipt history, product/category detail, and manual workflows are
   still useful.

2. Full finance state.
   The app behaves like a local personal finance dashboard. Overall finance
   categories, inflow/outflow filters, investment outflow, credit, insurance,
   housing, mobility, car, recurring bills, and reports become visible.

## 5. Category Architecture

### 5.1 Category layers

Implement explicit category scopes:

1. finance_transaction
   Category is attached to the whole transaction.

2. grocery_item
   Category is attached to a transaction item.

3. optional tag
   Cross-cutting labels used for secondary views without double-counting.

The main dashboard pie uses finance_transaction.
The grocery dashboard pie uses grocery_item.
Car-total queries can use finance_transaction plus tags.

### 5.2 Recommended data fields

Add transaction-level categorization fields:

- direction
  - allowed values: inflow, outflow, transfer, neutral
  - inflow means money enters the user's finances
  - outflow means money leaves the user's finances
  - transfer means money moves between the user's own accounts or allocations
  - neutral is reserved for records that should not affect spending totals

- finance_category_id
  - references categories.category_id
  - examples: groceries, housing, insurance, credit, car, mobility, investment

- finance_category_method
  - allowed values: source, rule, ai, manual, fallback

- finance_category_confidence
  - decimal confidence where available

- finance_category_source_value
  - merchant, payee, rule id, model output, or source-provided category

- finance_category_version
  - taxonomy or categorizer version

- finance_tags_json
  - JSON list of string tags for now
  - examples: car, tax_relevant, household, shared, reimbursable
  - because there are no published users, this can later be normalized without
    compatibility work if needed

Alternative:

- A normalized transaction_tags table may be used immediately if implementation
  prefers query performance and clean filtering.

### 5.3 Category taxonomy

Seed categories with parent relationships.

Top-level finance categories:

- groceries
- dining
- housing
- insurance
- credit
- mobility
- car
- investment
- health
- personal_care
- subscriptions
- communication
- shopping
- entertainment
- travel
- education
- fees
- tax
- income
- transfer
- other
- uncategorized

Grocery subcategories:

- groceries:bakery
- groceries:baking
- groceries:beverages
- groceries:dairy
- groceries:fish
- groceries:frozen
- groceries:meat
- groceries:pantry
- groceries:produce
- groceries:snacks
- groceries:household
- groceries:deposit
- groceries:other

Housing subcategories:

- housing:rent
- housing:electricity
- housing:heating
- housing:water
- housing:utilities
- housing:internet
- housing:repairs
- housing:tradespeople
- housing:furniture
- housing:appliances
- housing:other

Insurance subcategories:

- insurance:health
- insurance:liability
- insurance:household
- insurance:legal
- insurance:car
- insurance:travel
- insurance:life
- insurance:other

Credit subcategories:

- credit:repayment
- credit:interest
- credit:fees
- credit:other

Mobility subcategories:

- mobility:public_transit
- mobility:train
- mobility:taxi_rideshare
- mobility:bike
- mobility:parking_tolls
- mobility:other

Car subcategories:

- car:fuel
- car:charging
- car:maintenance
- car:repairs
- car:parking
- car:tax
- car:wash
- car:other

Investment subcategories:

- investment:broker_transfer
- investment:savings_transfer
- investment:pension
- investment:crypto
- investment:other

Income subcategories:

- income:salary
- income:refund
- income:reimbursement
- income:interest
- income:gift
- income:other

Subscription subcategories:

- subscriptions:software
- subscriptions:streaming
- subscriptions:fitness
- subscriptions:news
- subscriptions:cloud
- subscriptions:other

Fees and tax:

- fees:bank
- fees:service
- fees:shipping
- fees:late_payment
- tax:income_tax
- tax:vehicle_tax
- tax:property_tax
- tax:other

### 5.4 Category labels

Create a single shared frontend category label source.

Requirements:

- English and German labels for every seeded category.
- Parent/child rendering support.
- Short labels for chips.
- Longer labels for select menus if needed.
- No page-local copies of category label maps.
- Dashboard, Transactions, Budget, Reports, and Detail pages use the same helper.

Suggested frontend module:

- vendor/frontend/src/lib/categories.ts

Suggested exports:

- CATEGORY_DEFINITIONS
- FINANCE_CATEGORY_OPTIONS
- GROCERY_CATEGORY_OPTIONS
- resolveCategoryLabel(categoryId, locale)
- formatCategoryPath(categoryId, locale)
- getCategoryParent(categoryId)
- isGroceryCategory(categoryId)
- isFinanceCategory(categoryId)

Backend should also have a canonical taxonomy list or seed helper.

Suggested backend module:

- vendor/backend/src/lidltool/analytics/taxonomy.py

Suggested exports:

- FINANCE_CATEGORY_TAXONOMY
- GROCERY_CATEGORY_TAXONOMY
- CATEGORY_LABEL_KEYS if backend needs stable ids
- category_parent(category_id)
- top_level_category(category_id)
- is_grocery_category(category_id)

## 6. Transaction Direction Semantics

### 6.1 Direction rules

Outflow:

- grocery purchases
- rent
- electricity
- insurance
- credit repayment
- car expenses
- train tickets
- investment transfers
- subscriptions
- fees

Inflow:

- salary
- refunds
- reimbursements
- interest income
- gifts
- manual income entries

Transfer:

- movement between own accounts
- internal savings transfer where the target is still user-owned
- investment transfer can be either investment outflow or transfer depending on
  source semantics; for this product, use investment outflow when the user wants
  to see how much money left daily cash flow toward investments

Neutral:

- ignored duplicates
- non-financial records
- pending review records that should not affect totals

### 6.2 Amount conventions

Pick one canonical convention and use it everywhere:

- Store signed_amount_cents or direction plus absolute amount.
- For existing total_gross_cents, keep positive absolute amount if that is the
  current convention.
- Add direction for meaning.
- Dashboard outflow totals sum absolute outflow amounts.
- Dashboard inflow totals sum absolute inflow amounts.
- Net cash flow = inflow - outflow.

If implementation introduces signed_amount_cents, document it clearly and update
all APIs consistently.

## 7. Categorization Rules

### 7.1 Rule pipeline

Every transaction should receive a finance category through this order:

1. Manual override
2. Source-provided normalized category
3. User/global merchant rule
4. Deterministic built-in rule
5. AI categorization where enabled
6. Fallback based on source kind
7. uncategorized or other

Manual overrides must win.

### 7.2 Built-in merchant/payee examples

Initial deterministic examples:

- Kredit -> credit:repayment
- Getsafe Digital GmbH -> insurance:other
- Lidl, Penny, Rewe, Edeka, Netto, Aldi -> groceries
- Deutsche Bahn, DB Vertrieb -> mobility:train
- local transport providers -> mobility:public_transit
- gas stations -> car:fuel
- charging providers -> car:charging
- utility/electricity providers -> housing:electricity
- heating providers -> housing:heating
- landlords and rent aliases -> housing:rent
- telecom providers -> communication:internet_mobile
- Spotify, Netflix, Apple, Google storage, iCloud -> subscriptions
- broker names -> investment:broker_transfer
- salary/payroll aliases -> income:salary

### 7.3 Tags

Use tags for cross-cutting questions:

- car
- tax_relevant
- reimbursable
- household
- shared
- recurring
- travel
- health

Example:

- Car insurance:
  - finance_category_id = insurance:car
  - tags = [car]

- Train ticket:
  - finance_category_id = mobility:train
  - tags = []

- Electricity for car charging:
  - finance_category_id = car:charging
  - tags = [car]

This allows:

- Overall pie counts car insurance under insurance.
- Car report includes insurance:car and tag car.
- No double-counting in top-level spending charts.

## 8. Transaction Page UX

### 8.1 Page name

Visible page title:

- English: Transactions
- German: Transaktionen

Do not use:

- Receipts
- Belege

Except in receipt-specific workflows.

### 8.2 Page goal

The page must let users answer quickly:

- What came in?
- What went out?
- Where did it go?
- Which merchant/payee was it?
- What category was it?
- Which account/source did it come from?
- What changed this month?
- Which transactions need better categorization?

### 8.3 Recommended layout

Use a polished but dense finance-workflow layout:

1. Header row
   - Title
   - Date range summary
   - Add/import action
   - Optional saved view action later

2. KPI/filter summary strip
   - Total inflow
   - Total outflow
   - Net
   - Transaction count
   - Uncategorized count

3. Primary filter bar
   - Search input
   - Direction segmented control
   - Date range segmented control
   - Category combobox
   - Merchant combobox
   - More filters button

4. Active chips row
   - Category chip
   - Merchant chip
   - Direction chip
   - Date chip
   - Source chip
   - Clear all

5. Results table/cards
   - Desktop table
   - Mobile compact cards

### 8.4 Primary filters

Search:

- Search merchant/payee, item names, source transaction id, description where
  available.

Direction:

- All
- Inflow
- Outflow
- Transfers

Date range:

- This month
- Last month
- Last 30 days
- This year
- Custom

Category:

- hierarchical finance categories
- top-level selection includes children
- child selection filters exact subcategory

Merchant:

- searchable combobox
- populated from transaction facets
- show count and amount where available

Source/account:

- source id/display name
- account where available

More filters:

- amount min/max
- source kind
- uncategorized only
- tagged with
- confidence below threshold
- weekday/hour for pattern use cases

### 8.5 Quick filters

Suggested quick filters:

- This month
- Outflows
- Inflows
- Groceries
- Housing
- Insurance
- Credit
- Car
- Investments
- Uncategorized
- High value

Each quick filter must be URL-backed so links are shareable inside the app.

### 8.6 Table columns

Desktop:

- Date
- Merchant/payee
- Category
- Direction
- Amount
- Source/account
- Confidence/status
- Open

Mobile:

- merchant/payee
- date
- category chip
- source
- amount with direction styling

### 8.7 Visual rules

- Do not make the page card-heavy.
- Use one main surface for filters and one main surface for the table.
- Keep rows scannable.
- Use icons for direction and filtering where helpful.
- Use tooltips for compact icon-only controls.
- Use restrained positive styling for inflow and restrained negative/outflow
  styling for outflow.
- Avoid one-note color palettes.

## 9. Transaction API Plan

### 9.1 Extend GET /api/v1/transactions

Add query params:

- direction
- finance_category_id
- finance_category_parent
- finance_tag
- merchant
- source_account_id
- uncategorized
- min_abs_amount_cents
- max_abs_amount_cents
- category_confidence_below

Keep existing params:

- query
- year
- month
- source_id
- source_kind
- weekday
- hour
- tz_offset_minutes
- merchant_name
- min_total_cents
- max_total_cents
- purchased_from
- purchased_to
- sort_by
- sort_dir
- limit
- offset

Add sort fields:

- finance_category
- direction
- abs_amount_cents

Response item additions:

- direction
- finance_category_id
- finance_category_method
- finance_category_confidence
- finance_tags
- source_account_id
- display_amount_cents or signed_amount_cents if introduced
- merchant_display_name if different from raw merchant_name

### 9.2 Add GET /api/v1/transactions/facets

Purpose:

- Power merchant/category/source dropdowns and counts for the current filter
  context.

Inputs:

- same base filters as transaction search
- exclude the facet's own filter when computing that facet if useful

Response:

- merchants:
  - merchant_name
  - display_name
  - transaction_count
  - outflow_cents
  - inflow_cents
  - last_seen_at
- categories:
  - category_id
  - parent_category_id
  - transaction_count
  - outflow_cents
  - inflow_cents
- directions:
  - direction
  - transaction_count
  - amount_cents
- sources:
  - source_id
  - display_name
  - source_kind
  - transaction_count
- tags:
  - tag
  - transaction_count
  - amount_cents
- amount_bounds:
  - min_abs_amount_cents
  - max_abs_amount_cents
- date_bounds:
  - first_purchased_at
  - last_purchased_at

### 9.3 Add category recategorization endpoint or job

Because there are no production users, this does not need a compatibility
migration flow. Still provide a developer/admin way to recompute local data:

- POST /api/v1/transactions/recategorize

Inputs:

- scope
- dry_run
- limit
- source_id optional
- overwrite_manual false by default

Behavior:

- Recompute direction/category/tags for matching transactions.
- Never overwrite manual categories unless explicitly requested.
- Return counts by category and method.

## 10. Dashboard Plan

### 10.1 Dashboard payload shape

Extend /api/v1/dashboard/overview with:

- overall_spending
  - total_outflow_cents
  - categories
    - category_id
    - parent_category_id
    - amount_cents
    - share
    - transaction_count

- grocery_spending
  - total_cents
  - categories
    - category_id
    - amount_cents
    - share
    - item_count
    - transaction_count

- cash_flow_summary
  - existing fields preserved
  - ensure inflow/outflow semantics match transaction direction

- uncategorized_summary
  - transaction_count
  - amount_cents
  - href to filtered transactions

- investment_outflow
  - amount_cents
  - transaction_count
  - href to filtered transactions

### 10.2 Dashboard UI

Add two separate ring/pie chart panels:

1. Overall categories
   - Title: Overall spending
   - German: Gesamtausgaben
   - Uses transaction-level finance categories.
   - Excludes inflow.
   - Includes investment outflow as investment/allocation category.
   - Links each slice to /transactions with category filter.

2. Grocery breakdown
   - Title: Grocery breakdown
   - German: Lebensmittel-Aufteilung or Einkaufskategorien
   - Uses item-level grocery categories only.
   - Keeps the current beloved grocery pie behavior.
   - Links each slice to /transactions or /groceries with category filter.

### 10.3 Empty states

Receipt-only empty state:

- If there are receipts but no bank imports, show strong grocery/dashboard
  functionality.
- Do not tell the user the dashboard is incomplete.
- Show optional prompts to import bank statements.

No-data empty state:

- Show clear first actions:
  - Import transactions
  - Add manual transaction
  - Upload receipt
  - Connect source

### 10.4 Insight copy

All dashboard insight copy must be localized.

Examples:

- English: Your largest outflow category this period is Housing.
- German: Ihre groesste Ausgabenkategorie in diesem Zeitraum ist Wohnen.

Use i18n keys with variable interpolation. Do not build German grammar through
hard-coded string concatenation in components.

## 11. Reports: Pattern Recognition Page

### 11.1 Purpose

Add a Reports subpage for GitHub-like transaction pattern recognition.

The page should feel like a small, delightful analytical tool:

- When do I usually shop?
- On which weekdays do I spend most?
- At what time of day do transactions happen?
- Which merchants are weekend-heavy?
- How do two merchants compare?
- Are there routines or unusual patterns?

This is a product differentiator and a useful gimmick. It should be real,
fast, and visually polished.

### 11.2 Route

Recommended route:

- /reports/patterns

Alternative if ReportsPage already has internal tabs:

- Reports -> Patterns tab

Visible labels:

- English: Patterns
- German: Muster

### 11.3 Core visualizations

1. Contribution-style heatmap
   - GitHub-like calendar grid.
   - Shows daily transaction count or outflow amount.
   - Toggle value:
     - Count
     - Outflow
     - Inflow
     - Net
   - Tooltip shows date, amount, count, top merchant.

2. Weekday/time heatmap
   - Rows: weekday.
   - Columns: hour or time bucket.
   - Values: count or amount.
   - Answers when shopping happens.

3. Merchant comparison
   - Select one or two merchants.
   - Show side-by-side:
     - weekday distribution
     - hour distribution
     - monthly trend
     - average transaction amount
     - typical visit time

4. Pattern cards
   - Most common shopping weekday.
   - Most common shopping hour.
   - Merchant with strongest weekend pattern.
   - Biggest category by weekday.
   - Regular monthly outflows.

### 11.4 Filters

Pattern report filters:

- date range
- merchant multi-select, max two selected for direct comparison
- category
- direction
- source/account
- value mode
- include/exclude transfers

All filters must be URL-backed.

### 11.5 API support

Add or extend analytics endpoints:

- GET /api/v1/reports/patterns

Suggested response:

- period
- selected_filters
- daily_points
  - date
  - transaction_count
  - inflow_cents
  - outflow_cents
  - net_cents
  - top_merchant
- weekday_hour_matrix
  - weekday
  - hour
  - transaction_count
  - inflow_cents
  - outflow_cents
  - net_cents
- merchant_profiles
  - merchant_name
  - transaction_count
  - total_outflow_cents
  - average_transaction_cents
  - top_weekday
  - top_hour
  - weekday_distribution
  - hour_distribution
  - monthly_points
- insights
  - kind
  - title_key
  - body_key
  - params

Potential reuse:

- The backend already has timing analytics concepts such as weekday/hour
  aggregation. Reuse existing analytics helpers where possible.

### 11.6 UI design

The page should be analytical and dense, not a marketing page.

Layout:

- Header with title and date range.
- Compact filter row.
- Heatmap panel full width.
- Two-column section:
  - weekday/hour heatmap
  - merchant comparison
- Pattern cards row.

Visual details:

- Stable grid dimensions.
- Tooltips for heatmap cells.
- Keyboard accessible cells or summarized alternative table.
- Color scale must work in dark and light mode.
- Avoid relying on color alone; include tooltip/text summaries.

### 11.7 Multilingual reports

All report labels must be localized:

- Patterns
- Merchant comparison
- Weekday
- Hour
- Count
- Outflow
- Inflow
- Net
- Typical day
- Typical time
- No pattern yet
- Select up to two merchants

## 12. Frontend Implementation Details

### 12.1 Shared category module

Create:

- vendor/frontend/src/lib/categories.ts

Move or replace duplicated logic from:

- vendor/frontend/src/components/shared/CategoryPresentation.tsx
- vendor/frontend/src/pages/DashboardPage.tsx

Keep CategoryPresentation as a rendering component but make it depend on shared
helpers.

### 12.2 Transaction filters componentization

Split TransactionsPage into smaller components:

- TransactionsPage
- TransactionFilterBar
- TransactionFilterChips
- TransactionSummaryStrip
- TransactionTable
- TransactionMobileList
- TransactionFacetCombobox
- TransactionDirectionSegmentedControl
- TransactionCategorySelect

Keep the page readable and testable.

### 12.3 API client types

Update:

- vendor/frontend/src/api/transactions.ts
- vendor/frontend/src/api/dashboard.ts
- vendor/frontend/src/api/reports.ts if present or create it
- vendor/frontend/src/app/queries.ts

Use zod schemas for new response fields.

### 12.4 Routing

Update:

- vendor/frontend/src/main.tsx
- vendor/frontend/src/app/page-loaders.ts
- vendor/frontend/src/pages/ReportsPage.tsx

Add /reports/patterns if using nested route or deep link.

### 12.5 Tests

Frontend tests:

- TransactionsPage title is Transactions/Transaktionen.
- /receipts redirects to /transactions.
- Direction filter writes URL param and calls API param.
- Category filter writes URL param and calls API param.
- Merchant combobox renders facet values.
- Chips remove filters correctly.
- Dashboard renders overall pie and grocery pie separately.
- Pattern report renders heatmap from API data.
- German locale renders translated filter/chart labels.

## 13. Backend Implementation Details

### 13.1 Data model update

Update:

- vendor/backend/src/lidltool/db/models.py
- latest migration/seed files under vendor/backend/src/lidltool/db/migrations/versions/

Because there are no users:

- Prefer a clean schema shape over compatibility hacks.
- If needed, update baseline/test DB setup to include the final schema.
- Keep migration chain coherent enough for local dev/test database creation.

### 13.2 Taxonomy seed

Add canonical taxonomy seed helper:

- vendor/backend/src/lidltool/analytics/taxonomy.py

Ensure categories table contains finance and grocery categories.

### 13.3 Categorizer

Add transaction finance categorizer:

- vendor/backend/src/lidltool/analytics/transaction_categorizer.py

Responsibilities:

- Determine direction.
- Determine finance_category_id.
- Determine tags.
- Return method/confidence/source/version.
- Respect manual overrides.

### 13.4 Search and facets

Update:

- vendor/backend/src/lidltool/analytics/queries.py
- vendor/backend/src/lidltool/api/http_server.py

Add:

- direction filter
- finance category filter
- parent category filter
- tag filter
- source account filter
- uncategorized filter
- facets helper

### 13.5 Dashboard aggregations

Update:

- dashboard overview payload
- category spend summary helpers
- tests

Add separate helpers:

- dashboard_overall_finance_category_summary
- dashboard_grocery_item_category_summary

### 13.6 Reports patterns API

Add helper:

- reports_pattern_summary or analytics pattern helper

Reuse existing timing aggregation where possible.

Add endpoint:

- GET /api/v1/reports/patterns

Add route auth policy if route auth is explicit.

## 14. Demo And Fixture Requirements

Update demo fixtures so the product direction is visible without live data.

Demo data should include:

- grocery transactions from Lidl/Penny/Rewe
- Kredit transaction
- Getsafe Digital GmbH insurance transaction
- rent
- electricity
- train ticket
- car fuel or charging
- investment transfer
- salary inflow
- subscription

Dashboard demo should show:

- overall categories pie
- grocery breakdown pie
- inflow/outflow KPIs
- recent activity
- pattern report heatmap

German demo labels must render correctly.

## 15. Testing And Verification

Run from repo root:

- npm run typecheck
- npm run build

Also run targeted tests:

- backend transaction search/facet tests
- backend dashboard summary tests
- backend reports pattern tests
- frontend TransactionsPage tests
- frontend DashboardPage tests
- frontend ReportsPage or PatternsReport tests
- i18n route tests

Before finishing:

- Search for user-facing Belege/Receipts in transaction context.
- Keep Belege/Receipts only where the context is specifically receipt upload,
  OCR, receipt document, or receipt plugin.
- Search for new hard-coded English/German strings in touched React pages.
- Verify no new ../../ references were introduced.

Suggested checks:

- rg -n "Belege|Receipts|Receipt|receipt" vendor/frontend/src
- rg -n "\\.\\./\\.\\." .
- npm run typecheck
- npm run build

## 16. Acceptance Criteria

The implementation is complete when:

- The transaction page is visibly named Transactions/Transaktionen.
- The transaction page no longer looks like a simple receipt list.
- Users can quickly filter by merchant, direction, finance category, source,
  date range, and amount.
- The filter UI is polished, compact, URL-backed, and multilingual.
- Transactions have direction and transaction-level finance category semantics.
- Kredit-like transactions can appear under credit.
- Getsafe-like transactions can appear under insurance.
- Housing, car, mobility, insurance, credit, investment, income, and groceries
  are first-class categories.
- Grocery item breakdown remains available and is not polluted by non-grocery
  finance categories.
- Dashboard shows separate overall finance category and grocery category pies.
- Investment outflows are tracked only as outflow/allocation, not portfolio
  performance.
- Reports contains a GitHub-like pattern recognition page or tab.
- Pattern reports can compare up to two merchants.
- Pattern reports show shopping/spending by day and time.
- English and German labels are complete.
- Tests and build pass.
- No new dependency on files outside this repo is introduced.

## 17. Full Implementation Prompt

Use this prompt for a future implementation agent:

~~~text
You are working in /Users/maximilianblucher/.codex/worktrees/d4e4/lidltool-desktop.

Implement the complete personal finance dashboard and transaction intelligence
plan from docs/personal-finance-dashboard-implementation-plan.md.

Important constraints:
- Follow AGENTS.md exactly.
- Keep this desktop repo standalone.
- Do not add runtime or build-time dependencies on paths outside this repo.
- The app is not published yet and has no users, so do not waste effort on a
  production migration compatibility flow. Prefer the clean final schema and
  update local migrations, seeds, demo fixtures, tests, and contracts as needed.
- The app supports English and German. Do not hard-code user-facing strings in
  React pages or backend-generated insight text. Add i18n keys and both English
  and German values for every new label, empty state, button, filter, chart,
  insight, and report string.
- Preserve receipt/grocery strengths. Do not remove item-level grocery category
  intelligence.
- Add transaction-level finance categories and direction. The overall dashboard
  category pie must use transaction-level finance categories. The grocery pie
  must stay grocery-only and use item-level grocery categories.
- Investment support is intentionally narrow: track outflows/transfers toward
  investments only. Do not implement portfolio holdings, compounding, gains,
  losses, broker balances, or performance.

Implementation scope:

1. Rename and clean transaction surface
- Make /transactions visibly Transactions/Transaktionen everywhere.
- Keep /receipts redirecting to /transactions.
- Replace receipt/Belege wording in transaction-history context.
- Keep receipt/Belege wording only for receipt-specific upload/OCR/plugin flows.

2. Add transaction-level finance categorization
- Extend backend transaction model with direction, finance category, category
  method/confidence/source/version, and tags or a tag table.
- Seed canonical finance and grocery taxonomy.
- Add a backend taxonomy helper and a frontend shared category helper.
- Remove duplicated page-local category label maps.

3. Implement transaction categorizer
- Add deterministic merchant/payee/source rules for groceries, housing,
  insurance, credit, car, mobility, investment, subscriptions, income, fees,
  tax, and other.
- Ensure examples like Kredit -> credit and Getsafe Digital GmbH -> insurance.
- Respect manual overrides.
- Apply categorization during ingestion/manual transaction creation and provide
  a developer/admin recategorization endpoint or service.

4. Extend transaction search
- Add API filters for direction, finance category id, parent category, tag,
  source account, uncategorized, amount bounds, and category confidence.
- Add sort fields for direction/category/amount where useful.
- Update frontend API zod schemas and query types.

5. Add transaction facets
- Add GET /api/v1/transactions/facets.
- Return merchants, categories, directions, sources, tags, amount bounds, and
  date bounds for the current filter context.
- Use this endpoint to power the filter UI.

6. Redesign TransactionsPage
- Componentize into filter bar, summary strip, chips, table, mobile list, and
  facet controls.
- Add search, direction segmented control, date range, category selector,
  merchant combobox, source/account selector, amount filters, quick filters,
  and active chips.
- Make all filters URL-backed.
- Preserve pagination and sorting.
- Use localized labels only.
- Ensure dark/light mode looks polished and text does not overlap.

7. Split dashboard category charts
- Extend dashboard overview payload with overall_spending and grocery_spending.
- overall_spending uses transaction-level finance categories and excludes
  inflow.
- grocery_spending uses item-level grocery categories and only grocery
  transactions/items.
- Render two separate chart panels.
- Link chart rows/slices to filtered transaction/grocery views.
- Update dashboard tests and zod schemas.

8. Add Reports pattern recognition
- Add a Reports page section, tab, or /reports/patterns route for GitHub-like
  pattern recognition.
- Add API support for daily heatmap points, weekday/hour matrix, merchant
  profiles, two-merchant comparison, and localized insight descriptors.
- UI must support date range, merchant selection up to two merchants, category,
  direction, source/account, and value mode.
- Render a contribution-style heatmap, weekday/hour heatmap, merchant comparison,
  and pattern cards.
- Localize English and German labels.

9. Update demo fixtures and tests
- Add demo transactions for groceries, Kredit, Getsafe insurance, rent,
  electricity, train, car fuel/charging, investment transfer, salary, and
  subscriptions.
- Update backend tests for taxonomy, categorization, search filters, facets,
  dashboard overview, and reports patterns.
- Update frontend tests for TransactionsPage, DashboardPage, Reports patterns,
  i18n, and route compatibility.

10. Verify
- Run npm run typecheck from repo root.
- Run npm run build from repo root.
- Run targeted backend/frontend tests relevant to changed code.
- Search for accidental hard-coded or outdated transaction-context labels.
- Verify no new ../../ dependencies.

Do not stop at a partial implementation. Continue until the plan is implemented,
tests are updated, and the repo builds. If a blocker appears, inspect the
codebase and solve it inside the repo rather than reducing scope. Only leave
work unfinished if a hard external dependency is impossible to satisfy, and then
document the exact blocker and remaining files.
~~~

## 18. Suggested Delivery Order For The Implementation Agent

Use this order to reduce risk:

1. Category/taxonomy shared helpers.
2. Backend model fields and seed data.
3. Transaction categorizer.
4. Transaction search filters.
5. Transaction facets endpoint.
6. Frontend API schemas and query types.
7. TransactionsPage redesign.
8. Dashboard payload split.
9. Dashboard UI split.
10. Reports pattern API.
11. Reports pattern UI.
12. Demo fixtures.
13. Tests.
14. Final typecheck/build and label audits.

## 19. Open Design Decisions

These can be decided during implementation:

- Whether transaction tags start as JSON or a normalized table.
- Whether investment transfer is represented as direction=outflow or
  direction=transfer with category=investment. The product copy should still
  show it as investment allocation/outflow, not portfolio performance.
- Whether Reports patterns is a nested /reports/patterns route or an internal
  tab. Prefer the route if it keeps URL-backed filters clean.
- Whether merchant identity remains plain merchant_name initially or gets a
  canonical merchant table. Prefer not to introduce a merchant table unless the
  existing merchant summary code makes it cheap.

## 20. Principle

The core product move is this:

Transactions become the finance history. Receipts become one source of
transactions. Grocery intelligence stays detailed. The dashboard becomes a
personal finance overview when finance data exists and remains a strong
Haushaltsbuch when only receipt data exists.
