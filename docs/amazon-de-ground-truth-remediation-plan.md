# Amazon DE Ground Truth Remediation Plan

## Purpose

This document is the handoff plan for bringing the desktop Amazon DE scraper to ground-truth parity.

It captures:

- the exact validation artifacts already produced
- the proven mismatch buckets
- the likely root causes
- the ordered implementation plan
- the regression test plan
- the clean rerun procedure

The goal is to let another agent continue without reconstructing the investigation.

## Current Ground Truth

Ground-truth DB:

- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/amazon_ground_truth_v2.sqlite`

Ground-truth year counts:

- `2026: 18`
- `2025: 76`
- `2024: 104`
- `2023: 65`
- `2022: 48`
- `2021: 41`
- `2020: 58`
- `2019: 62`
- `2018: 23`
- `2017: 24`

Ground-truth run metadata:

- `pages = 57`
- `details = 384`
- `invoice_anomaly = 0`

Ground-truth HTML corpus:

- history HTML:
  `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history`
- detail HTML:
  `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/details`

Ground-truth script:

- `/Users/max/projekte/lidltool/apps/desktop/scripts/amazon_ground_truth.py`

## Current Scraper Validation Snapshot

Finished full-history validation DB:

- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/scraper-validate-v5.sqlite`

Observed imported year counts:

- `2026: 59`
- `2025: 73`
- `2024: 96`
- `2023: 50`
- `2022: 39`
- `2021: 33`
- `2020: 49`
- `2019: 51`
- `2018: 23`
- `2017: 22`

Validation summary from the run:

- `Pages = 57`
- `Orders fetched = 519`
- `Records seen = 519`
- `New receipts = 495`
- `New items = 614`

Important conclusion:

- the crawl did complete
- the scraper did not stop at `2024`
- the remaining problem is correctness, not traversal coverage

## Proven Mismatch Buckets

### 1. Wrong-year imports

Count:

- `43`

Pattern:

- all are `D01-...` digital orders
- they were imported as `2026`
- they carry `parseWarnings = ["missing_order_date"]`

Meaning:

- these orders were not skipped
- they lost their historical date
- they fell back to a current-time-like timestamp during canonical ingest

Examples:

- `D01-4822828-9912600`
- `D01-5333019-1919014`
- `D01-4851184-7650217`
- `D01-8877183-3112603`
- `D01-9739650-9362230`

### 2. Expected skipped canceled/unbilled orders

Count:

- `4`

IDs:

- `302-2956157-7140343`
- `302-9685584-2475537`
- `302-1596802-7921905`
- `302-7922257-3075561`

Meaning:

- these are expected skips
- do not treat them as scraper failures

### 3. Quarantined records

Count:

- `7`

IDs:

- `028-6287898-0978762`
- `302-3666426-1500361`
- `302-6514628-8916318`
- `304-2494218-0673143`
- `306-4081414-2825120`
- `306-4811772-1441902`
- `D01-7420653-4274230`

Observed failure:

- all are `transaction_total_mismatch`

Patterns:

- some have `item_total_cents = 0`
- some have small positive deltas
- one digital order still fails reconciliation

### 4. Missing non-quarantine records

The latest side analysis indicates that the older “missing non-quarantine” set collapsed after the most recent rerun and the only rows missing outside quarantine are canceled-only entries. Treat this as something to re-check after each fix, not as a fixed assumption.

## Root Cause Summary

### Root Cause A: Missing date provenance for digital orders

This is the main remaining bug.

Observed behavior:

- many older `D01` rows exist in the crawl
- their exact historical year is known from the history page
- they lose `orderDate`
- canonical ingest accepts a plausible fallback timestamp
- they end up in `2026`

Likely code areas:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/client_playwright.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/ingest/sync.py`

### Root Cause B: Detail-link selection is still too permissive or incomplete

Observed historical behavior:

- invoice popovers / invoice PDF routes were sometimes opened instead of real detail pages
- software/download orders can use alternate detail routes such as `/your-orders/search?search=...`

Meaning:

- selectors need to reject invoice routes
- selectors also need to accept valid alternate detail routes for digital/software orders

Likely code areas:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/selectors.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/parsers.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/client_playwright.py`

### Root Cause C: Some reconciliation logic is still too strict or too lossy

Observed behavior:

- a bounded set of records still goes to quarantine with `transaction_total_mismatch`
- some of them are sparse orders where detail metadata is weak
- at least one digital order still mismatches despite being a real valid order

Likely code areas:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/order_money.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/ingest/validation.py`

## Ordered Implementation Plan

### Phase 1: Fix date provenance

Goal:

- no Amazon history record may silently fall back to “now” if the page year is already known

Changes:

1. Carry page-year provenance from list crawl into every emitted order record.
2. Add explicit date provenance fields, for example:
   - `pageYear`
   - `dateSource`
3. Date precedence:
   - explicit detail/list full date
   - page-year fallback
   - never current time for Amazon history rows
4. In canonical upsert, treat date quality as ordered:
   - explicit full date > inferred page year > missing
5. Never overwrite an existing higher-quality historical date with a weaker inferred date.

Primary files:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/client_playwright.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/ingest/sync.py`

### Phase 2: Fix detail-link routing

Goal:

- always open real order-detail pages
- never treat invoice/popover/pdf pages as detail pages
- still support digital/software alternate detail routes

Changes:

1. Reject:
   - `/your-orders/invoice/popover`
   - `/documents/download/.../invoice.pdf`
2. Accept:
   - normal `order-details`
   - valid alternate digital/software detail routes such as `/your-orders/search?search=...` when confirmed useful
3. Log chosen detail URL kind before fetch for later debugging.

Primary files:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/selectors.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/client_playwright.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/parsers.py`

### Phase 3: Fix the quarantine set

Goal:

- reduce the `7` quarantines to either valid imports or well-justified quarantines

Work order:

1. Handle sparse digital mismatch:
   - `D01-7420653-4274230`
2. Handle “item total is zero” older records:
   - `302-3666426-1500361`
   - `302-6514628-8916318`
   - `304-2494218-0673143`
   - `306-4811772-1441902`
3. Handle small-delta physical mismatch records:
   - `028-6287898-0978762`
   - `306-4081414-2825120`

Primary files:

- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/amazon/order_money.py`
- `/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/ingest/validation.py`

### Phase 4: Re-run full history and compare against ground truth

Goal:

- exact parity on real orders
- canceled/unbilled rows intentionally skipped

Success condition:

- imported counts match ground truth year-by-year except for canceled/unbilled orders
- no wrong-year digital orders
- quarantine set reduced to only truly unsupported/irreconcilable cases

## Regression Test Plan

### Tests to add or extend

#### `vendor/backend/tests/test_amazon_client_playwright.py`

- `test_iter_orders_preserves_page_year_for_d01_rows_without_list_date`
- `test_merge_detail_parse_result_does_not_overwrite_existing_list_order_date`
- `test_detail_link_selection_ignores_invoice_popover_and_invoice_pdf_urls`
- `test_digital_software_orders_can_use_valid_search_detail_route_when_present`

#### `vendor/backend/tests/test_amazon_canonical_ingest.py`

- `test_amazon_sync_uses_page_year_fallback_for_missing_order_dates`
- `test_amazon_sync_does_not_import_blank_date_as_current_time`
- `test_amazon_sync_does_not_regress_existing_purchased_at_on_reimport`
- `test_amazon_sync_does_not_merge_distinct_amazon_orders_by_fingerprint`

#### `vendor/backend/tests/test_amazon_parsers.py`

- `test_parse_order_list_html_keeps_d01_rows_even_when_order_date_text_is_blank`
- `test_parse_order_detail_html_keeps_list_date_when_detail_date_is_missing`
- `test_parse_order_detail_html_ignores_invoice_routes_as_detail_pages`
- regression fixtures for software/download detail-link routing

#### `vendor/backend/tests/test_connector_validation.py`

- add a case that rejects current-time fallback for Amazon history rows
- allow explicit weaker page-year fallback as a known degraded state, not as a silent “now”

## Minimal Fixture Corpus

Use these concrete artifacts as fixtures/debug inputs.

### Physical mismatch examples

- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2020-page-002.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/details/028-6287898-0978762.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/details/306-4081414-2825120.html`

### Digital mismatch / route examples

- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5/order_detail_D01-7420653-4274230.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5/order_detail_D01-1906591-4994257.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5/order_detail_D01-5051746-5819837.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5/order_detail_D01-6405519-8543066.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5/order_detail_D01-7629149-7679000.html`

### History pages with older digital rows

- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2017-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2019-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2020-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2021-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2022-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2023-page-000.html`
- `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/ground-truth/html-v2/history/year-2024-page-000.html`

## Validation Queries

### Wrong-year digital records

```sql
select
  o.order_id,
  hp.year as truth_year,
  substr(t.purchased_at,1,4) as imported_year,
  json_extract(t.raw_payload,'$.connector_normalized.raw_json.parseWarnings') as warnings
from order_ref o
join history_page hp on hp.page_id = o.page_id
join transactions t on t.source_transaction_id = 'amazon-' || o.order_id
where o.order_id like 'D01-%'
  and cast(substr(t.purchased_at,1,4) as int) <> hp.year
order by hp.year desc, o.order_id;
```

### Quarantine summary

```sql
select
  source_record_ref,
  json_extract(validation_errors,'$[0].code') as code,
  json_extract(validation_errors,'$[0].details.delta_cents') as delta_cents,
  json_extract(validation_errors,'$[0].details.total_gross_cents') as total_gross_cents,
  json_extract(validation_errors,'$[0].details.item_total_cents') as item_total_cents
from connector_payload_quarantine
where source_id = 'amazon_de'
order by created_at;
```

### Year-by-year final compare

```sql
select substr(purchased_at,1,4) as year, count(*) as imported
from transactions
where source_id='amazon_de'
group by 1
order by 1 desc;
```

## Clean Rerun Procedure

Run from:

- `/Users/max/projekte/lidltool/apps/desktop`

### 1. Build a fresh scratch DB

Example DB paths:

- `v4` two-year validation:
  `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/scraper-validate-v4.sqlite`
- `v5` full-history validation:
  `/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/scraper-validate-v5.sqlite`

Initialize schema and seed:

- one admin user row
- one `amazon_de` source row bound to that user

### 2. Use the desktop config/session state

Config dir:

- `/Users/max/Library/Application Support/outlays-desktop/config`

Expected auth state file:

- `/Users/max/Library/Application Support/outlays-desktop/config/amazon_storage_state.json`

### 3. Two-year validation first

Command:

```bash
OUTLAYS_DESKTOP_CONFIG_DIR="$HOME/Library/Application Support/outlays-desktop/config" \
./.backend/venv/bin/python -m lidltool.cli \
  --db /Users/max/projekte/lidltool/apps/desktop/.amazon-debug/scraper-validate-v4.sqlite \
  connectors sync \
  --source-id amazon_de \
  --full \
  --option years=2 \
  --option headless=false \
  --option dump_html=/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v4 \
  --option owner_user_id=1a6d175f-1b70-446a-b608-0bcf473a77d7
```

Expected result after the recent digital fixes:

- all real `2026+2025` orders imported
- only the `4` canceled/unbilled rows skipped
- `0` quarantine

### 4. Full-history validation after two-year slice is clean

Command:

```bash
OUTLAYS_DESKTOP_CONFIG_DIR="$HOME/Library/Application Support/outlays-desktop/config" \
./.backend/venv/bin/python -m lidltool.cli \
  --db /Users/max/projekte/lidltool/apps/desktop/.amazon-debug/scraper-validate-v5.sqlite \
  connectors sync \
  --source-id amazon_de \
  --full \
  --option years=10 \
  --option headless=false \
  --option dump_html=/Users/max/projekte/lidltool/apps/desktop/.amazon-debug/validate-run-v5 \
  --option owner_user_id=1a6d175f-1b70-446a-b608-0bcf473a77d7
```

### 5. Compare against ground truth

Acceptance target:

- exact year counts match ground truth
- except canceled/unbilled skips

Ground-truth year targets:

- `2026: 18`
- `2025: 76`
- `2024: 104`
- `2023: 65`
- `2022: 48`
- `2021: 41`
- `2020: 58`
- `2019: 62`
- `2018: 23`
- `2017: 24`

## Recommended Execution Order For Another Agent

1. Reproduce the current mismatch using `scraper-validate-v5.sqlite`.
2. Implement Phase 1 date provenance fixes.
3. Add the date regression tests.
4. Re-run the two-year validation.
5. Confirm `2026+2025` parity except canceled skips.
6. Implement Phase 2 detail-link routing improvements.
7. Implement Phase 3 quarantine fixes.
8. Re-run full history.
9. Compare to ground truth year-by-year and by exact `order_id`.

## Important Notes

- Do not treat canceled-only rows as failures.
- Do not broaden selectors in a way that reintroduces invoice/popover tabs.
- Do not rely on “current time” as a fallback purchase date for Amazon history rows.
- Keep the ground-truth DB and HTML corpus unchanged; they are the benchmark.

