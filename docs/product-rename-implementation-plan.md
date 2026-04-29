# Product Rename Implementation Plan

Status: planning draft  
Current private/dev name: LidlTool Desktop  
Candidate public direction: Outlays, with an English subtitle  
Primary reason: remove Lidl-owned branding from the product name, package identity, docs, website, and release surfaces while preserving legitimate retailer connector labels where they describe a user-selected Lidl Plus integration.

This is an implementation plan, not legal advice. Before shipping the final public name, run a trademark clearance pass with EUIPO, WIPO Global Brand Database, USPTO if the product will be available in the US, app stores, package registries, domains, and GitHub/org availability.

## Naming Direction

### Recommended Shortlist

1. Outlays
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Your Personal Spending Ledger
   - Why: simple, finance-native, short, and broad enough for receipts, household budgets, merchant analysis, manual imports, AI workflows, and future multi-retailer support.
   - Risk: there is already an App Store listing named "outlays App" for expense/group spending tracking, so this name needs a real clearance decision before public launch.

2. Outlay
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Your Local Spending Ledger
   - Why: singular form feels more like a product brand than a category noun.
   - Risk: close enough to "Outlays" that it may not solve clearance if "Outlays" is blocked.

3. Spendwise
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Your Local Household Ledger
   - Why: clear consumer-finance meaning; easy to understand in English and German-speaking markets.
   - Risk: more generic and likely crowded.

4. BasketLedger
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Receipts, Budgets, and Household Spending
   - Why: connects groceries/receipts with finance without referencing one retailer.
   - Risk: narrower; may feel grocery-heavy if the product expands into bills, reports, goals, and AI analysis.

5. ReceiptLedger
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Local Receipt and Spending Analysis
   - Why: highly descriptive, clear for self-hosters and desktop users.
   - Risk: less brandable; may underplay household finance modules.

6. HomeLedger
   - German subtitle: Dein Haushaltsbuch
   - English subtitle: Private Household Spending, Locally Managed
   - Why: aligns with local-first household finance.
   - Risk: broader and likely crowded; "home ledger" may overlap existing finance products.

### Best Brand/Subtitles Combinations

Recommended public combination:

- Product: Outlays
- German: Outlays - Dein Haushaltsbuch
- English: Outlays - Your Personal Spending Ledger
- Longer website line: Private receipt and household finance analysis for your own computer.

More pragmatic/local-first combination:

- Product: Outlays
- German: Outlays - Dein lokales Haushaltsbuch
- English: Outlays - Your Local Household Ledger
- Longer website line: Sync receipts when you need them, analyze spending locally, and keep your data on your machine.

More receipt-specific combination:

- Product: Outlays
- German: Outlays - Dein Beleg- und Haushaltsbuch
- English: Outlays - Receipt-Led Household Finance
- Longer website line: Turn receipts, manual entries, and retailer exports into private household finance insights.

If clearance rejects Outlays:

- Fallback A: BasketLedger - Your Local Household Ledger
- Fallback B: ReceiptLedger - Local Receipt and Spending Analysis
- Fallback C: HomeLedger - Private Household Spending, Locally Managed

## Naming Rules

Use the new brand for the product:

- app name
- window title
- menu labels
- website
- README and docs
- diagnostics bundle names
- update feed paths
- GitHub repo/org references
- telemetry release names
- package names
- installer names
- desktop file/application names
- app icons and visual brand assets

Keep retailer names only where they are factual connector/source labels:

- "Lidl Plus" connector display name
- `lidl_plus_de`, `lidl_plus_gb`, `lidl_plus_fr` source IDs
- parser modules and test fixtures that process Lidl receipts
- imported historical merchant/store names
- docs that explicitly explain a connector integration

Do not keep retailer names in:

- product name
- org/package/repo name
- app ID
- telemetry app tag
- diagnostics file prefix
- generic descriptions of the product
- update server path
- issue templates unless the issue is connector-specific

## Current Repo Rename Inventory

The desktop repo currently contains several classes of name usage:

- User-visible product strings: `Outlays`, `Use Outlays on this computer`, first-run copy, shell title, README, privacy copy, release docs.
- Electron packaging identity: `package.json` `name`, `build.appId`, `build.productName`, protocol display name, update feed URL, icon generation temp names.
- Runtime and environment names: `LIDLTOOL_*` environment variables, `lidltool_session`, `lidltool.sqlite`, diagnostics filenames, telemetry tags, Sentry release names.
- Backend executable/module names: `lidltool`, `lidltool.exe`, `python -m lidltool.cli`, vendored `vendor/backend/src/lidltool`.
- Connector/source identifiers: `lidl_plus_*` source IDs and `Lidl Plus` connector labels.
- Vendored frontend identity: `vendor/frontend/package.json`, storage keys, generated messages, demo fixtures, tests, frontend app shell.
- Mobile harnesses: iOS/Android harness names, bundle/package IDs, assets, localized strings.
- Docs and scripts: sync scripts, patchers, release checklist, GitHub Actions examples, public repo boundary docs.
- External surfaces: GitHub issue URLs, update feed URLs, GlucherLab website page/product listing, future app store metadata.

## Sprint Plan

### Sprint 0 - Brand Decision and Clearance Gate

Goal: choose the public name and define what is allowed to stay retailer-specific.

Tasks:

- Select the primary name and two fallback names.
- Decide final English subtitle.
- Decide final German subtitle.
- Define the exact long-form website description.
- Check name availability across:
  - EUIPO / TMview for EU-facing launch.
  - WIPO Global Brand Database for broader international conflicts.
  - USPTO if the app, website, binaries, or GitHub releases are promoted in the US.
  - Apple App Store, Microsoft Store, GitHub, npm, PyPI, domain names, social handles.
- Specifically investigate "Outlays" because a public App Store listing named "outlays App" already exists for expense/group spending tracking.
- Decide whether to use "Outlays" unchanged, modify it, or fall back.
- Create a naming decision record under `docs/`.

Deliverables:

- `docs/product-name-decision.md`
- final product name
- final subtitle pair
- approved list of terms to rename
- approved list of factual retailer terms to keep

Acceptance criteria:

- No implementation work starts until the final name is approved.
- Legal/clearance risk is documented, even if the decision is to proceed.

### Sprint 1 - Product Copy and Design System Rename

Goal: remove retailer-branded product naming from user-visible desktop UI while keeping connector labels intact.

Tasks:

- Replace `Outlays` user-facing strings with the new public name.
- Update English/German i18n generated shell strings.
- Update `src/renderer/index.html` title.
- Update first-run/control-center copy in `src/renderer/App.tsx`.
- Update `src/i18n/literals.de.json` and shell i18n sync source in `scripts/sync-shell-i18n.mjs`.
- Update menu labels, update dialog copy, diagnostics copy, and bug-report copy.
- Update app logo mark if the existing asset implies the old name.
- Add a visible app subtitle in the appropriate first-run/about/control-center locations if product design wants it.
- Keep connector display names like "Lidl Plus" only in connector context.

Deliverables:

- UI string rename PR.
- Screenshots of first-run/control-center/full-app shell in English and German.

Acceptance criteria:

- `rg -n "LidlTool|lidltool" src/renderer src/i18n` returns only approved internal identifiers or connector-specific terms.
- The product can be opened in dev mode and no visible product surface says "LidlTool".
- Lidl-specific text appears only where the UI is explicitly about a Lidl Plus connector.

### Sprint 2 - Electron Packaging and Desktop Runtime Identity

Goal: make installed app identity match the new product name without breaking existing users abruptly.

Tasks:

- Rename `package.json` `name` from `outlays-desktop` to the selected package slug.
- Change `build.productName`.
- Change `build.appId` from `com.gluecherlab.outlays.desktop` to the new reverse-DNS identifier.
- Change `app.setAppUserModelId`.
- Update update feed path from `/outlays-desktop` to the new slug.
- Update protocol display name.
- Decide whether to keep `com.lidlplus.app` as a callback scheme only for the Lidl Plus login flow, or replace it if the connector can support a neutral callback.
- Rename diagnostics zip prefix.
- Rename telemetry app tag and release name.
- Rename icon generation temp prefixes.
- Update installer artifact names if configured by electron-builder defaults.
- Add migration notes for installed app data paths.

Compatibility decision:

- If existing beta users matter, keep a migration window where the new app checks the old user data directory and imports/moves:
  - `lidltool.sqlite`
  - `documents`
  - `config/config.toml`
  - `config/token.json`
  - plugin packs
  - privacy preferences
- If existing beta users do not matter, document the breaking app ID/data directory change in release notes.

Deliverables:

- Packaging identity PR.
- Data directory migration strategy.
- Updated release process docs.

Acceptance criteria:

- Packaged macOS and Windows builds install as the new product.
- Diagnostics, telemetry, update release metadata, and installer filenames use the new brand.
- Existing data migration behavior is tested or explicitly declared unsupported for pre-release builds.

### Sprint 3 - Backend Runtime, CLI, and Data File Compatibility

Goal: remove product-level `lidltool` naming from the runtime where feasible while avoiding a risky module rename unless intentionally scheduled.

Recommended approach:

- Do not rename the Python package/module from `lidltool` in the first public rename unless there is a strong reason. This repo vendors the backend and many tests/scripts import `lidltool.*`; a module rename is a high-risk mechanical change.
- Introduce neutral public aliases around internal names first.

Tasks:

- Rename public environment variables from `LIDLTOOL_*` to new-prefix equivalents, while keeping old names as deprecated aliases for one or two releases.
- Add a small runtime helper that resolves new env vars first and old env vars second.
- Rename default database file from `lidltool.sqlite` to the new slug, with automatic fallback/import from the old filename.
- Rename default app support/config/log paths where Electron controls them.
- Rename diagnostics archive names and backup defaults.
- Rename `Receipt Plugin Packs` file extension only if desired. The current `.lidltool-plugin` extension should probably remain supported indefinitely and can gain a new preferred extension.
- Update runtime tests for both new and legacy env/database names.
- Keep `python -m lidltool.cli` and `lidltool` executable internally for now if backend packaging depends on it.

Deliverables:

- Runtime compatibility PR.
- Legacy compatibility matrix in docs.

Acceptance criteria:

- New installs create neutral filenames and env naming.
- Old installs can still start and find existing data.
- Tests cover new and old env var fallback.
- No build/runtime script depends on `../../*` paths beyond allowed sync/vendor scripts.

### Sprint 4 - Vendored Frontend, Backend Metadata, and Mobile Harnesses

Goal: clean up product identity inside vendored UI and companion foundations while preserving source IDs and parser names.

Tasks:

- Update `vendor/frontend/package.json` and lockfile package name.
- Update frontend storage keys that are product-level, such as workspace UI storage keys, with migration from old keys.
- Update `vendor/frontend/src/i18n/*`, app shell labels, demo product copy, README, and test expectations.
- Update backend project metadata if it exposes product-level names to users.
- Keep backend package path `src/lidltool` unless a separate module-rename sprint is approved.
- Update mobile harness app names:
  - iOS scheme/display name/localized strings/assets.
  - Android package/display name/localized strings.
- Keep connector source IDs like `lidl_plus_de` because they are durable data identifiers and should not be renamed unless a schema migration is planned.
- Update vendored patch scripts so sync does not reintroduce old product names.

Deliverables:

- Vendored UI/mobile rename PR.
- Storage-key migration tests.
- Patch script assertions to prevent product-brand regressions.

Acceptance criteria:

- Full vendored frontend build passes.
- Mobile harnesses build with the new display name.
- Product-level old name does not reappear after `npm run vendor:sync`.

### Sprint 5 - Docs, Website, Repository, and Public Distribution Rename

Goal: align every public-facing non-code surface.

Tasks:

- Update `README.md`, `PRIVACY.md`, `SECURITY.md`, `CONTRIBUTING.md`, `RELEASE_CHECKLIST.md`, and all `docs/`.
- Update GitHub issue URL references.
- Rename GitHub repository if desired, and configure redirects.
- Update GlucherLab website:
  - product name
  - subtitle
  - screenshots
  - download links
  - update feed links
  - privacy/support copy
  - any SEO title/description/meta/social cards
- Update release assets, changelog, and signing/notarization docs.
- Update domain/subdomain paths if the product gets a standalone page.
- Add a public statement that the app is independent and not affiliated with Lidl or any retailer, if legal/product approves.
- Add connector-specific language: "Lidl Plus connector" instead of product-level Lidl naming.

Deliverables:

- Public docs and website PR.
- Redirect/update-feed plan.
- New screenshots.

Acceptance criteria:

- Searching the website and docs for the old product name returns only migration notes, changelog entries, or connector-specific factual references.
- Download/install instructions use only new package names.
- Website makes the brand and subtitle clear in the first viewport.

### Sprint 6 - Automated Guardrails and Release Validation

Goal: prevent regressions and prove the rename is shippable.

Tasks:

- Add a release preflight check that fails on forbidden product-level strings:
  - `LidlTool`
  - `outlays-desktop`
  - `com.gluecherlab.outlays.desktop`
  - old update feed URL
  - old diagnostics prefix
- Allowlist legitimate internal/backend/connector strings:
  - `vendor/backend/src/lidltool`
  - Python imports
  - `lidl_plus_*`
  - `Lidl Plus`
  - historical fixtures
  - migration docs
- Add tests for:
  - env var aliasing
  - old database filename migration
  - old localStorage key migration
  - diagnostics filename
  - update release metadata
  - app ID/product name in package metadata
- Run:
  - `npm run typecheck`
  - `npm run build`
  - `npm run test:runtime-contracts`
  - `npm run test:release-preflight`
  - packaged smoke on macOS
  - Windows packaging check before public release

Deliverables:

- Automated rename guard.
- Release validation report.

Acceptance criteria:

- Guardrail check is part of release preflight.
- All required desktop checks pass from repo root.
- Packaged artifacts use the new product identity.

### Sprint 7 - Optional Deep Module Rename

Goal: only if necessary, rename internal backend package/executable names from `lidltool` to the new slug.

Recommendation:

- Defer this until after the public product rename ships. The user-facing and packaging rename solves the brand problem; the Python module rename is mostly internal and high-blast-radius.

Tasks if approved:

- Rename `vendor/backend/src/lidltool` package.
- Update all Python imports in backend, tests, patchers, fixtures, generated scripts, and packaged invocation logic.
- Rename executable from `lidltool` to new CLI name.
- Keep a compatibility console script alias for at least one release.
- Update plugin SDK import guidance if plugins currently import `lidltool.connectors.sdk`.
- Update plugin compatibility checks that reference backend package version.
- Run full backend and desktop integration tests.

Acceptance criteria:

- Third-party/plugin compatibility story is clear.
- Old CLI alias works or breaking change is documented.
- No plugin SDK docs point to a removed import path.

## Suggested Work Order

1. Decide name and subtitle.
2. Clear the name.
3. Rename user-visible desktop strings.
4. Rename Electron packaging/app identity.
5. Add migration aliases for env vars, data paths, and storage keys.
6. Rename docs and website.
7. Add guardrails.
8. Defer deep Python package renaming unless there is a real distribution reason.

## Rename Search Queries

Use these during implementation:

```sh
rg -n "LidlTool|outlays-desktop|com\\.lidltool\\.desktop|LIDLTOOL_|lidltool_session|lidltool\\.sqlite|outlays-diagnostics" .
rg -n "Lidl|lidl" src package.json README.md PRIVACY.md SECURITY.md docs scripts
rg -n "Outlays|BasketLedger|ReceiptLedger|HomeLedger" .
```

Expected permanent allowlist:

- `lidl_plus_de`, `lidl_plus_gb`, `lidl_plus_fr`
- `Lidl Plus` connector display names
- backend parser/import package names if Sprint 7 is deferred
- fixture merchant names and receipt examples
- migration notes documenting old paths and names

## External Clearance References

- EUIPO/TMview or EUIPO search should be used for EU marks before a German/EU launch.
- WIPO Global Brand Database can search multiple international and national trademark collections.
- USPTO trademark search should be used if the product will be distributed or promoted in the United States.
- App store searches matter because "Outlays" appears to be in active use by an expense/group spending app listing.
