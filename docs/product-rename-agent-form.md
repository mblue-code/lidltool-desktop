# Product Rename Agent Implementation Form

Use this form to drive implementation of the product rename from the private development name `LidlTool Desktop` to the approved public brand.

This repo must remain a standalone desktop side repo. Do not introduce runtime or build-time dependencies on `../../*` paths. Sync/vendor scripts may read from upstream only to copy files into this repo.

## 0. Inputs To Fill Before Starting

Fill these values before making code changes.

- Final product name: `________________`
- Product slug/package name: `________________`
  - Example: `outlays-desktop`
- Reverse-DNS app ID: `________________`
  - Example: `com.gluecherlab.outlays.desktop`
- German subtitle: `________________`
  - Candidate: `Dein Haushaltsbuch`
- English subtitle: `________________`
  - Candidate: `Your Personal Spending Ledger`
- Long English product line: `________________`
  - Candidate: `Private receipt and household finance analysis for your own computer.`
- Long German product line: `________________`
- New diagnostics prefix: `________________`
  - Example: `outlays-diagnostics`
- New database filename: `________________`
  - Example: `outlays.sqlite`
- New environment variable prefix: `________________`
  - Example: `OUTLAYS_DESKTOP_`
- Legacy env prefix to keep temporarily: `LIDLTOOL_`
- New update feed base/path: `________________`
- New GitHub issue URL: `________________`
- New public website URL: `________________`
- Old names allowed only in migration notes: `LidlTool Desktop`, `lidltool-desktop`, `com.lidltool.desktop`

Clearance status:

- [ ] EUIPO/TMview checked
- [ ] WIPO Global Brand Database checked
- [ ] USPTO checked if US distribution/promotion is planned
- [ ] Apple App Store checked
- [ ] Microsoft Store checked
- [ ] GitHub repo/org availability checked
- [ ] npm package name checked if public package publication is planned
- [ ] PyPI package name checked if public Python package publication is planned
- [ ] Domain/social handles checked
- [ ] Risk notes recorded in `docs/product-name-decision.md`

## 1. Global Rules

Replace product-level LidlTool naming everywhere user-facing or distribution-facing.

Do replace:

- `LidlTool Desktop` product strings
- `lidltool-desktop` package/repo/update/telemetry/diagnostics identifiers
- `com.lidltool.desktop` app IDs
- `LIDLTOOL_DESKTOP_*` public env vars, with compatibility aliases
- `lidltool.sqlite` default desktop database filename, with migration/fallback
- docs, website copy references, release docs, privacy/security docs

Do not blindly replace legitimate connector/data identifiers:

- `lidl_plus_de`
- `lidl_plus_gb`
- `lidl_plus_fr`
- `Lidl Plus` when it is the connector/retailer display name
- imported merchant/store names like `Lidl Berlin`
- receipt parser modules and backend package paths if the deep Python module rename is deferred
- test fixtures that intentionally model Lidl receipt data

Implementation posture:

- Keep changes scoped to rename and compatibility.
- Preserve old user data where practical.
- Keep old env vars as aliases for at least one release.
- Keep existing connector source IDs stable unless a separate schema migration is explicitly requested.
- Do not rename `vendor/backend/src/lidltool` in the first pass unless the task explicitly includes Sprint 7 from the plan.

## 2. Initial Repo Audit

Run from repo root:

```sh
git status --short
rg -n "LidlTool|lidltool-desktop|com\\.lidltool\\.desktop|LIDLTOOL_|lidltool_session|lidltool\\.sqlite|lidltool-diagnostics" .
rg -n "Lidl|lidl" src package.json README.md PRIVACY.md SECURITY.md RELEASE_CHECKLIST.md CONTRIBUTING.md docs scripts
```

Record notable buckets:

- [ ] User-visible UI strings
- [ ] Electron packaging identity
- [ ] Runtime/env/database identifiers
- [ ] Diagnostics/telemetry/update identifiers
- [ ] Vendored frontend identity
- [ ] Mobile harness identity
- [ ] Docs/release/public website references
- [ ] Connector-specific references to preserve
- [ ] Backend/package internals to defer

## 3. Sprint 1 - UI, I18n, and Copy

Files likely involved:

- `src/renderer/App.tsx`
- `src/renderer/index.html`
- `src/i18n/generated.ts`
- `src/i18n/literals.de.json`
- `scripts/sync-shell-i18n.mjs`
- `src/main/index.ts`
- `src/main/updates/*`
- `src/main/diagnostics/*`

Tasks:

- [ ] Replace app title/window title with final product name.
- [ ] Replace first-run/control-center product copy.
- [ ] Add/use English subtitle where appropriate.
- [ ] Add/use German subtitle where appropriate.
- [ ] Keep connector-specific `Lidl Plus` labels unchanged.
- [ ] Regenerate/sync shell i18n if the project script owns generated strings.
- [ ] Update tests that assert old UI product names.

Validation:

```sh
npm run i18n:sync-shell
npm run typecheck
rg -n "Outlays|Use Outlays|LidlTool auf" src/renderer src/i18n scripts/sync-shell-i18n.mjs
```

Acceptance:

- [ ] No visible shell/control-center copy uses old product name.
- [ ] German and English strings are aligned.
- [ ] Lidl appears in UI only for Lidl Plus connector/source contexts.

## 4. Sprint 2 - Electron Packaging Identity

Files likely involved:

- `package.json`
- `package-lock.json`
- `src/main/index.ts`
- `src/main/updates/update-config.ts`
- `src/main/updates/update-manager.ts`
- `scripts/generate-icons.mjs`
- `scripts/serve-update-feed.mjs`
- `scripts/upload-sourcemaps.mjs`
- `scripts/lib/release-preflight.mjs`
- tests under `tests/*release*`, `tests/update-config.test.ts`

Tasks:

- [ ] Rename package `name`.
- [ ] Rename `build.productName`.
- [ ] Rename `build.appId`.
- [ ] Rename `app.setAppUserModelId`.
- [ ] Rename update feed default/path.
- [ ] Rename protocol display name.
- [ ] Decide whether `com.lidlplus.app` stays as a connector callback scheme.
- [ ] Rename diagnostics archive prefix.
- [ ] Rename telemetry app tag and release string.
- [ ] Rename icon/temp build prefixes.
- [ ] Update lockfile package metadata.
- [ ] Update tests for package metadata and update config.

Validation:

```sh
npm run test:updates
npm run test:release-preflight
npm run typecheck
rg -n "outlays-desktop|com\\.lidltool\\.desktop|Outlays|outlays-diagnostics" package.json package-lock.json src scripts tests
```

Acceptance:

- [ ] Packaged app metadata uses new product identity.
- [ ] Update metadata uses new feed path.
- [ ] Old names remain only where explicitly allowlisted.

## 5. Sprint 3 - Runtime Compatibility, Env Vars, and Data Paths

Files likely involved:

- `src/main/runtime-paths.ts`
- `src/main/runtime.ts`
- `src/main/runtime-backup-artifacts.ts`
- `src/main/runtime-backend-env.ts`
- `src/main/diagnostics/*`
- `src/main/sqlite-artifacts.ts`
- `tests/runtime-paths.test.ts`
- `tests/runtime-backup-artifacts.test.ts`
- `tests/sqlite-artifacts.test.ts`

Tasks:

- [ ] Add helper for new env vars with legacy `LIDLTOOL_*` fallback.
- [ ] Prefer new env vars in all docs/runtime code.
- [ ] Keep old env vars as deprecated aliases.
- [ ] Rename default database file to new filename.
- [ ] Add fallback/import path from `lidltool.sqlite`.
- [ ] Update backup/restore to accept old and new database artifact names.
- [ ] Rename default diagnostics output prefix.
- [ ] Rename cookie/session name only if safe; otherwise document compatibility reason.
- [ ] Add tests for new env vars.
- [ ] Add tests for old env var fallback.
- [ ] Add tests for old DB filename fallback/restore.

Validation:

```sh
npm run test:runtime-contracts
npm run test:diagnostics
npm run typecheck
rg -n "LIDLTOOL_|lidltool_session|lidltool\\.sqlite|outlays-diagnostics" src tests
```

Acceptance:

- [ ] New installs use neutral names.
- [ ] Existing beta/local installs can still find old database/config where intended.
- [ ] Old env vars work as aliases.
- [ ] Tests describe compatibility behavior.

## 6. Sprint 4 - Vendored Frontend and Mobile Harnesses

Files likely involved:

- `vendor/frontend/package.json`
- `vendor/frontend/package-lock.json`
- `vendor/frontend/src/i18n/*`
- `vendor/frontend/src/components/shared/AppShell.tsx`
- `vendor/frontend/src/lib/request-scope.ts`
- `vendor/frontend/src/demo/fixtures.ts`
- `overrides/frontend/**/*`
- `scripts/patch-vendored-frontend.mjs`
- `scripts/validate-vendored-frontend.mjs`
- `vendor/mobile/ios-harness/**/*`
- `vendor/mobile/android-harness/**/*`

Tasks:

- [ ] Rename vendored frontend product/package identity.
- [ ] Rename product-level localStorage/sessionStorage keys.
- [ ] Add migration from old storage keys if user settings would otherwise reset.
- [ ] Update i18n and app shell product copy.
- [ ] Update demo product copy without changing fixture merchant/source IDs.
- [ ] Update frontend tests.
- [ ] Update mobile app display names.
- [ ] Update iOS scheme/display/localized strings if in scope.
- [ ] Update Android application label/package only if in scope; document if package ID remains for compatibility.
- [ ] Ensure patch scripts do not reintroduce old product branding after vendor sync.

Validation:

```sh
npm run frontend:install
npm run frontend:build
npm --prefix ./vendor/frontend run test -- --run
rg -n "LidlTool|outlays-desktop|com\\.lidltool\\.desktop" vendor/frontend overrides/frontend vendor/mobile scripts/patch-vendored-frontend.mjs scripts/validate-vendored-frontend.mjs
```

Acceptance:

- [ ] Vendored frontend builds.
- [ ] Product-level old names do not reappear after patching.
- [ ] Connector IDs and fixture merchant names remain stable.

## 7. Sprint 5 - Docs, Website, Public Surfaces

Files likely involved:

- `README.md`
- `PRIVACY.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `RELEASE_CHECKLIST.md`
- `docs/**/*.md`
- `docs/github-actions/ci.yml.example`
- website repo/page outside this repo, if available

Tasks:

- [ ] Rename product in README.
- [ ] Rename product in privacy/security docs.
- [ ] Update release process and update-flow docs.
- [ ] Update GitHub issue links.
- [ ] Update screenshots/download references.
- [ ] Add or update non-affiliation language:
  - `This project is independent and is not affiliated with Lidl or any retailer.`
- [ ] Update GlucherLab website product page:
  - product name
  - English subtitle
  - German subtitle if applicable
  - hero/meta title
  - description
  - screenshots
  - download links
  - issue/support links
  - SEO/social cards
- [ ] Record rename/migration notes for existing users.

Validation:

```sh
rg -n "LidlTool|outlays-desktop|com\\.lidltool\\.desktop|LIDLTOOL_DESKTOP" README.md PRIVACY.md SECURITY.md CONTRIBUTING.md RELEASE_CHECKLIST.md docs
```

Acceptance:

- [ ] Docs use new public brand.
- [ ] Old name only appears in migration/changelog/decision docs.
- [ ] Retailer names appear only as connector/merchant references.

## 8. Sprint 6 - Guardrails

Files likely involved:

- `scripts/lib/release-preflight.mjs`
- `scripts/release-preflight.mjs`
- `tests/release-preflight.test.mjs`
- possibly a new `scripts/lib/brand-guard.mjs`

Tasks:

- [ ] Add forbidden product-brand patterns:
  - `LidlTool`
  - `outlays-desktop`
  - `com.gluecherlab.outlays.desktop`
  - old update feed URL
  - old diagnostics prefix
- [ ] Add allowlist paths/patterns for:
  - `vendor/backend/src/lidltool`
  - `overrides/backend/src/lidltool`
  - `tests/backend` imports
  - `lidl_plus_*`
  - `Lidl Plus` connector labels
  - historical fixtures
  - migration docs
  - this rename plan/form
- [ ] Include the guard in release preflight.
- [ ] Add tests proving forbidden names fail outside allowlisted contexts.

Validation:

```sh
npm run test:release-preflight
npm run release:preflight
```

Acceptance:

- [ ] Release preflight catches accidental old product branding.
- [ ] Legitimate connector/backend references are not blocked.

## 9. Final Verification

Run from repo root:

```sh
npm run typecheck
npm run build
npm run test:runtime-contracts
npm run test:updates
npm run test:release-preflight
```

If packaging is in scope:

```sh
npm run dist:mac
npm run dist:win
```

Final search:

```sh
rg -n "LidlTool|outlays-desktop|com\\.lidltool\\.desktop|outlays-diagnostics" .
rg -n "LIDLTOOL_DESKTOP|OUTLAYS_DESKTOP_CONFIG_DIR|OUTLAYS_DESKTOP_DOCUMENT_STORAGE_PATH|OUTLAYS_DESKTOP_REPO_ROOT|OUTLAYS_DESKTOP_FRONTEND_DIST" .
```

Classify every remaining hit:

- [ ] approved legacy compatibility alias
- [ ] approved backend internal module/package name
- [ ] approved connector/source ID
- [ ] approved fixture/merchant data
- [ ] approved migration/decision documentation
- [ ] must fix before merge

## 10. Implementation Report Template

Use this structure in the final agent response or PR description.

```md
## Summary

- Renamed public product identity from `Outlays` to `...`.
- Updated Electron packaging/app metadata to `...`.
- Added compatibility for legacy env/data names where applicable.
- Preserved Lidl Plus connector/source identifiers.

## Compatibility

- Old env vars supported:
  - ...
- Old data paths supported:
  - ...
- Breaking changes:
  - ...

## Remaining Intentional Old-Name References

- `vendor/backend/src/lidltool`: internal Python package, deferred.
- `lidl_plus_*`: durable connector source IDs.
- `Lidl Plus`: factual connector display name.
- ...

## Validation

- `npm run typecheck`: pass/fail
- `npm run build`: pass/fail
- `npm run test:runtime-contracts`: pass/fail
- `npm run test:updates`: pass/fail
- `npm run test:release-preflight`: pass/fail
- packaging smoke: pass/fail/not run

## Notes

- ...
```
