# Desktop Localization Fix Report

## Summary of fixes

- Resolved the full 26-item backlog from `i18n-findings.json`.
- Removed the audited English leakage from German runtime surfaces across the desktop shell, finance pages, settings, workflow routes, and shared chat chrome.
- Kept English runtime surfaces English during the final packaged sweep.
- Fixed both pre-auth and post-auth Control Center locale handling so returning from the full app no longer reverts the shell to stale English copy.

## Root causes addressed

1. Split locale ownership between the Electron shell and the full web app.
   - Fixed by syncing the shell bridge and app i18n provider through `window.desktopApi.getLocale()`, `setLocale()`, and `onLocaleChanged()`.
   - Re-broadcasted the active locale whenever the Control Center reloads.
2. Raw desktop-shell literals bypassing translation.
   - Added desktop literal translation coverage for Control Center hero copy, helper copy, backup/export/restore text, quick-import text, and shell placeholders.
3. Hardcoded JSX copy in desktop page overrides and vendored pages.
   - Replaced or normalized localized page headers, descriptions, KPI labels, table labels, action labels, and empty-state/support copy.
4. Raw backend/status strings rendered directly in UI.
   - Added desktop-owned mapping for connector preview warnings and OCR/document status labels.
5. Stale localization tests.
   - Updated focused AI/settings/document-upload tests to match the new canonical labels and statuses.

## Terminology decisions applied

- `recurring bill` / `wiederkehrende Rechnung` is the canonical recurring-bill term.
- `transaction` remains the ledger/list concept; `receipt` remains the document/import artifact concept.
- `connector`, `merchant`, and `source` are now kept distinct across pages.
- Status labels now use one localized set for `pending`, `active`, `ready`, `blocked`, and OCR/review states instead of raw enum tokens.
- Control Center copy now consistently uses desktop-shell terminology instead of mixed web-app or backend phrasing.

## Files changed

### Shell, locale plumbing, and desktop literals

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/main/index.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/renderer/i18n.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/renderer/App.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/renderer/control-center-model.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/i18n/index.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/src/i18n/literals.de.json`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/i18n/index.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/lib/desktop-api.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/desktop-api.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/vite-env.d.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/vite-env.d.ts`

### Desktop override pages

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/DashboardPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/SettingsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/AISettingsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/BudgetPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/CashFlowPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/ReportsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/MerchantsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/GoalsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/GroceriesPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/DocumentsUploadPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/lib/backend-messages.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/i18n/messages.ts`

### Vendored frontend pages and shared UI

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/DataQualityPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ProductsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ComparisonsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ExplorePage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/PatternsPage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/pages/ReviewQueuePage.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/ChatPanel.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/lib/backend-messages.ts`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/i18n/messages.ts`

### Focused tests

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/i18n/__tests__/i18n.test.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend/src/components/__tests__/ChatPanel.history.test.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/__tests__/AISettingsPage.test.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/__tests__/SettingsPage.test.tsx`
- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend/src/pages/__tests__/DocumentsUploadPage.test.tsx`
- Synced vendored copies of the same override-backed tests through `npm run vendor:patch-frontend`.

## Commands run

### Passed

- `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run build`
- `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && npm run dist:with-backend`
- `cd /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop && CSC_IDENTITY_AUTO_DISCOVERY=false npx electron-builder`
- `npm --prefix /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/vendor/frontend run test -- src/i18n/__tests__/i18n.test.tsx src/components/__tests__/ChatPanel.history.test.tsx src/pages/__tests__/SettingsPage.test.tsx src/pages/__tests__/AISettingsPage.test.tsx src/pages/__tests__/ExplorePage.test.tsx src/pages/__tests__/ComparisonsPage.test.tsx src/pages/__tests__/PatternsPage.test.tsx src/pages/__tests__/DocumentsUploadPage.test.tsx src/pages/__tests__/ReviewQueuePage.test.tsx`
  - Result: `9` test files passed, `38` tests passed.

### Expected non-issue during validation

- `npm --prefix /Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/overrides/frontend run test ...`
  - This path has no standalone `package.json`; override-backed tests are executed through the vendored frontend after `npm run vendor:patch-frontend`.

## Runtime recheck results

- Re-ran the packaged audit harness against the final `.app` bundle:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/run-i18n-audit.mjs`
- Fresh final artifacts were written at approximately `2026-04-23 01:38`:
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/i18n-audit-artifacts`
  - `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/i18n-audit-screenshots`
- The final packaged sweep covered the full original route matrix in both German and English.
- Result: all 26 original findings are no longer reproduced.
- Control Center now stays German in German locale both before auth and after returning from the main app.
- `/documents/upload` and `/imports/ocr` no longer show raw `State:` / `pending` tokens in German.
- The final exact-string comparison against the original audit backlog returned no matches.

## Remaining unresolved issues

- No unresolved items remain from the original 26 audited findings.
- Residual risk is limited to future data-bearing states that surface third-party merchant content or new backend diagnostics; those are intentionally not translated when they are not desktop-owned UI chrome.

## Output files

- Main fix report: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/i18n-fix-report.md`
- Updated findings: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/i18n-findings.json`
- Runtime screenshots: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/i18n-audit-screenshots`
- Runtime text dumps: `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/i18n-audit-artifacts`
