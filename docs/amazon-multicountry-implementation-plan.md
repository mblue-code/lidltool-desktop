# Amazon Multicountry Connector Plan

## Scope

This plan covers the desktop Amazon connector in `apps/desktop` and assumes the current `amazon.de` Playwright-based implementation remains the base. The goal is to evolve it into a multicountry-capable connector without regressing desktop-first auth, side-repo isolation, or the existing normalized ingest pipeline.

## Goals

- Preserve browser-session bootstrap as the auth model.
- Refactor `amazon.de` onto a profile-based foundation before adding other countries.
- Make country expansion additive through profiles, selectors, and localized parsing rules rather than `if/else` sprawl.
- Increase parser and auth coverage using reusable ideas from `alexdlaird/amazon-orders`.
- Keep the connector integrated with the existing desktop orchestration, connector manifest, and canonical ingest model.

## Non-Goals

- Do not rebase onto `amazon-orders`.
- Do not switch to username/password form automation as the primary auth flow.
- Do not build the main repo around desktop requirements.
- Do not add runtime dependencies outside `apps/desktop`.

## Current Baseline

- Browser-session bootstrap:
  - `vendor/backend/src/lidltool/amazon/bootstrap_playwright.py`
  - `vendor/backend/src/lidltool/connectors/auth/browser_session_bootstrap.py`
- Core scraper:
  - `vendor/backend/src/lidltool/amazon/client_playwright.py`
- Connector normalization:
  - `vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- Connector registration and config UI:
  - `vendor/backend/src/lidltool/connectors/registry.py`
  - `vendor/backend/src/lidltool/connectors/lifecycle.py`
- Existing tests:
  - `vendor/backend/tests/test_browser_session_bootstrap.py`
  - Main-repo reference coverage currently exists in:
    - `../tests/test_amazon_client_playwright.py`
    - `../tests/test_amazon_canonical_ingest.py`
  - As part of this plan, equivalent desktop-local coverage should be added under `apps/desktop`.

## Design Principles

1. Country behavior must be data-driven.
   URLs, locale labels, currencies, date parsing, auth-wall detection, selectors, status strings, and subtotal mappings should come from country profiles.

2. Auth remains browser-first.
   We can borrow auth classification ideas from `amazon-orders`, but not its `requests`-driven login model.

3. The normalized output stays stable.
   Multicountry support should change acquisition and parsing internals, not the connector contract consumed by canonical ingest.

4. Fixtures matter more than speculation.
   Each parsing/auth improvement should be backed by saved HTML fixtures from real pages.

5. Add only one new country after the profile architecture is stable.
   `amazon.de` becomes the reference implementation; the second country validates that the abstraction is real.

## Target Architecture

### Core types

- `AmazonCountryProfile`
  - `country_code`
  - `source_id`
  - `domain`
  - `currency`
  - `languages`
  - `default_order_history_url`
  - `default_sign_in_url`
  - `time_filter_strategy`
  - `auth_wall_rules`
  - `selector_bundle`
  - `date_patterns`
  - `amount_parser`
  - `status_patterns`
  - `subtotal_label_map`
  - `unsupported_order_rules`

- `AmazonSelectorBundle`
  - Order list selectors
  - Detail page selectors
  - Shipment/item selectors
  - Pagination selectors
  - Auth-form and auth-wall selectors

- `AmazonParseResult`
  - Parsed order data
  - Parse warnings
  - Parse status
  - Unsupported-order classification when applicable

- `AmazonAuthState`
  - `authenticated`
  - `login_required`
  - `mfa_required`
  - `captcha_required`
  - `claim_required`
  - `intent_required`
  - `bot_challenge`
  - `unknown_auth_block`

### File layout

- `vendor/backend/src/lidltool/amazon/profiles.py`
- `vendor/backend/src/lidltool/amazon/selectors.py`
- `vendor/backend/src/lidltool/amazon/parsers.py`
- `vendor/backend/src/lidltool/amazon/auth_state.py`
- `vendor/backend/src/lidltool/amazon/client_playwright.py`
- `vendor/backend/src/lidltool/amazon/bootstrap_playwright.py`
- `vendor/backend/src/lidltool/connectors/amazon_adapter.py`

## Sprint Plan

### Sprint 1: Profile Foundation

Objective:
Refactor the current connector so `amazon.de` is implemented through an explicit country profile without behavior change.

Implementation:
- Introduce `AmazonCountryProfile` and a `get_country_profile()` registry.
- Move hardcoded domain and locale assumptions out of `client_playwright.py`.
- Replace direct `amazon.de` URL literals with profile-resolved URLs.
- Move German date, amount, status, and label parsing into the Germany profile.
- Make `bootstrap_playwright.py` consume the profile for sign-in URL, validation URL, and auth-wall markers.
- Keep existing source id `amazon_de` working unchanged.

Acceptance criteria:
- Existing `amazon.de` behavior is unchanged.
- All current tests still pass.
- No direct `amazon.de` literals remain in runtime logic except country-profile definitions and tests.

Primary files:
- `vendor/backend/src/lidltool/amazon/client_playwright.py`
- `vendor/backend/src/lidltool/amazon/bootstrap_playwright.py`
- `vendor/backend/src/lidltool/amazon/session.py`
- new `vendor/backend/src/lidltool/amazon/profiles.py`

### Sprint 2: Auth State Classification

Objective:
Strengthen auth/session detection while keeping the browser-session model.

Implementation:
- Add structured auth-state detection for:
  - login redirect
  - generic sign-in wall
  - MFA wall
  - CAPTCHA wall
  - claim flow
  - intent confirmation
  - JS bot challenge
  - expired or invalid storage state
- Replace generic auth-wall detection with a typed detector that returns `AmazonAuthState`.
- Improve bootstrap and fetch errors so the UI can distinguish failure classes.
- Support fixture-based tests for known auth pages.
- Add optional debug HTML dumps for auth probes.

Acceptance criteria:
- Connector can classify auth failures deterministically from saved HTML fixtures.
- Bootstrap output and backend errors are more specific than "reauth required".
- Existing browser bootstrap still works for real sessions.

Primary files:
- new `vendor/backend/src/lidltool/amazon/auth_state.py`
- `vendor/backend/src/lidltool/amazon/bootstrap_playwright.py`
- `vendor/backend/src/lidltool/amazon/client_playwright.py`
- `vendor/backend/tests/test_browser_session_bootstrap.py`

### Sprint 3: Selector Bundles and Parser Decomposition

Objective:
Split the scraper into profile-driven selectors and reusable parsing functions so additional countries are practical.

Implementation:
- Extract selector bundles out of embedded JS/Python logic into a profile-driven layer.
- Split list-page scraping, detail-page scraping, subtotal parsing, and item merge logic into focused helpers.
- Preserve Playwright page evaluation where useful, but drive it with selector bundles instead of hardcoded arrays.
- Introduce subtotal categories:
  - shipping
  - free_shipping
  - gift_wrap
  - coupon
  - promotion
  - subscribe_and_save
  - multibuy_discount
  - amazon_discount
  - gift_card
  - reward_points
- Add structured parse warnings when fields are missing or inferred.

Acceptance criteria:
- Parser code is no longer a single monolith.
- Country-specific selectors are isolated from generic scraping logic.
- Existing `amazon.de` tests pass after the refactor.

Primary files:
- new `vendor/backend/src/lidltool/amazon/selectors.py`
- new `vendor/backend/src/lidltool/amazon/parsers.py`
- `vendor/backend/src/lidltool/amazon/client_playwright.py`

### Sprint 4: Unsupported Orders and Edge Cases

Objective:
Handle partial or unsupported order classes explicitly instead of silently degrading.

Implementation:
- Add unsupported-order rules per country profile for cases like:
  - grocery / pantry style orders
  - store purchases
  - fully digital orders
  - canceled-only orders
  - refunded or return-heavy variants
- Return parse metadata in raw payloads:
  - `parse_status`
  - `parse_warnings`
  - `unsupported_reason`
- Update normalization logic to tolerate partial records without losing provenance.
- Add cases for zero-order pages, empty details, missing totals, and malformed subtotal layouts.

Acceptance criteria:
- Unsupported flows are explicitly surfaced in payload metadata.
- Sync does not silently misclassify unsupported orders as complete.
- Canonical ingest remains stable.

Primary files:
- `vendor/backend/src/lidltool/amazon/parsers.py`
- `vendor/backend/src/lidltool/connectors/amazon_adapter.py`
- desktop-local canonical ingest tests under `apps/desktop`

### Sprint 5: Fixture Corpus and Regression Harness

Objective:
Create the test surface needed to maintain the connector across Amazon UI changes and multiple countries.

Implementation:
- Add fixture directories for:
  - list pages
  - detail pages
  - auth pages
  - special order types
  - empty/no-results pages
- Use `dump_html` captures from real sessions to seed the corpus.
- Copy or port the current main-repo Amazon test intent into desktop-local tests so `apps/desktop` can validate itself in isolation.
- Add parser tests per fixture with expected normalized outputs and parse metadata.
- Add auth classification tests for saved HTML samples.
- Add smoke tests validating each registered country profile is internally complete.

Acceptance criteria:
- Fixture-backed tests cover both success and failure modes.
- A parser regression can be reproduced with saved HTML.
- Country profiles fail fast when incomplete.

Primary files:
- desktop-local fixture directories under `apps/desktop`
- desktop-local parser tests under `apps/desktop`
- new desktop-local `test_amazon_profiles.py`
- new desktop-local `test_amazon_auth_state.py`

### Sprint 6: Second Country Validation

Objective:
Add one more Amazon marketplace to validate the abstraction.

Recommended target:
- `amazon.fr` or `amazon.it`

Selection criteria:
- Similar order history layout to Germany
- EUR currency reduces one variable early
- Can be tested with a real account sooner than a more divergent market

Implementation:
- Add the new country profile.
- Register a new source id such as `amazon_fr`.
- Add localized:
  - date parsing
  - subtotal labels
  - auth-wall markers
  - pagination strings
  - status patterns
- Add fixtures and tests for the second country.

Acceptance criteria:
- `amazon.de` and the second country run through the same core client.
- Adding the second country required profile additions, not invasive parser rewrites.
- Desktop config/registry can expose multiple Amazon connector variants cleanly.

Primary files:
- `vendor/backend/src/lidltool/amazon/profiles.py`
- `vendor/backend/src/lidltool/connectors/registry.py`
- `vendor/backend/src/lidltool/connectors/lifecycle.py`
- `tests/test_amazon_profiles.py`

### Sprint 7: Connector UX and Operator Controls

Objective:
Make multicountry support operable from the desktop UI and debugging flow.

Implementation:
- Expose country-aware connector entries and settings in registry/config schemas.
- Ensure setup/import UX clearly identifies the marketplace.
- Add optional operator-only controls for:
  - headless
  - years
  - max pages
  - dump HTML path
  - country override where appropriate
- Update desktop README with setup and debugging instructions per marketplace.

Acceptance criteria:
- Desktop users can see and configure distinct Amazon marketplace connectors.
- Debug workflows are documented and stable.

Primary files:
- `vendor/backend/src/lidltool/connectors/registry.py`
- `vendor/backend/src/lidltool/connectors/lifecycle.py`
- `README.md`

## Cross-Sprint Constraints

- Run from `apps/desktop` only.
- Keep side-repo isolation intact.
- Avoid destructive git operations.
- Preserve current `amazon.de` source ids and normalized output shape unless a migration is explicitly planned.
- Do not land multicountry by duplicating full connector implementations per country.

## Testing Matrix

Minimum checks after each sprint:

- `npm run typecheck`
- `npm run build`
- `./.backend/venv/bin/python -m pytest vendor/backend/tests/test_browser_session_bootstrap.py`
- `./.backend/venv/bin/python -m pytest` against desktop-local Amazon tests inside `apps/desktop`

Recommended expanded checks by the end:

- country profile completeness tests
- parser fixture matrix for `amazon.de`
- parser fixture matrix for the second country
- auth-state fixture matrix
- one real-account manual smoke test per enabled country

## Rollout Order

1. Land Sprint 1 without behavior change.
2. Land Sprint 2 and Sprint 3 together if the refactor scope overlaps heavily.
3. Land Sprint 4 and Sprint 5 before adding a second country.
4. Add only one second country in Sprint 6.
5. Polish desktop UX and docs in Sprint 7.

## Risks

- Amazon pages differ across accounts, AB tests, and marketplaces.
- Auth flows can vary based on CAPTCHA, MFA, device trust, and anti-bot posture.
- Overfitting to one account or one locale will break multicountry support quickly.
- Inline JS page evaluation can become brittle if selectors are not profile-driven.

## Mitigations

- Build a real fixture corpus from multiple page variants.
- Separate selector bundles from parsing logic.
- Emit parse metadata and warnings instead of forcing false completeness.
- Validate each added country through a real-account smoke test before treating it as supported.

## Definition of Done

The multicountry Amazon connector is "done" for the first release when:

- `amazon.de` runs on the new profile architecture.
- At least one additional country works through the same core client.
- Auth failures are classified with typed states.
- The parser is covered by fixture-based regression tests.
- The connector remains compatible with the desktop setup/import workflow.
- Desktop README and connector settings reflect the multicountry model.
