# LidlTool Desktop (Electron)

LidlTool Desktop is the standalone occasional-use desktop product. It is local-first, receipt-oriented, and
plugin-capable, but it is intentionally narrower than the self-hosted server deployment.

## Desktop product scope

Desktop is for:
- opening the app when you want a local sync
- reviewing receipts on the same machine
- exporting normalized receipt data
- creating or restoring local backups
- enabling a small number of receipt plugin packs

Desktop is not for:
- running as an always-on household server
- offer/watchlist/alert parity
- recurring background scraping
- hosted/backend service workflows
- on-device plugin authoring

## Sprint 16 summary

Sprint 16 focuses on product polish instead of new parity scope.

- first-run and control-center copy now frames desktop as a local occasional-use product
- the control center now explains whether you are in full-app-ready mode, reduced fallback mode, or control-center-only mode
- desktop now boots into the low-power control center first and starts the Python backend only when the user explicitly opens the main app or starts the local service
- receipt pack management is organized around installed packs, trusted optional packs, explicit enable/disable/remove actions, and clearer trust/support labels
- backup, export, and restore flows now explain what is included, what stays out of scope, and where misunderstandings are most likely
- regional edition and market profile context is surfaced more clearly from the existing release metadata
- partial-runtime states now stay actionable when full frontend assets are missing or release metadata falls back to a safe local shell profile

## Intentional desktop deltas after parity

These desktop-specific differences are still intentional after the parity program and are expected to remain until the
main app offers a clean upstream equivalent.

- Route capability policy is owned by Electron in `src/shared/desktop-route-policy.ts` and consumed by
  `overrides/frontend/src/lib/desktop-capabilities.tsx` plus `overrides/frontend/src/main.tsx`.
  Unsupported routes stay hidden in navigation and direct requests to `/offers`, `/automations`, `/automation-inbox`,
  and `/reliability` redirect back to `/` with desktop-specific handoff messaging.
- Bills euro-input flow stays on the vendored `vendor/frontend/src/pages/BillsPage.tsx` plus
  `vendor/frontend/src/utils/money-input.ts` parsing path.
  Desktop keeps this stricter euro-input handling because the packaged app still targets local manual entry with
  comma-or-dot decimal input rather than introducing a separate desktop-only amount widget.
- Connector lifecycle UI stays close to main, and desktop-owned pack install, trust, and update actions are surfaced
  directly on the desktop connectors page in `overrides/frontend/src/pages/ConnectorsPage.tsx`.
  The full app remains the place for one-off setup and sync, while desktop-specific pack management stays available on
  the same connectors surface.
  Desktop sync-status banners and connector actions now follow the backend connector discovery payload instead of a
  hardcoded retailer list, so newly imported pluginized merchants do not require Electron UI source edits just to show
  status or sync affordances.
- AI settings stay on a desktop-safe fork of the vendored page and tests.
  The current desktop page keeps chat-oriented provider controls while continuing to hide OCR-provider management and
  other self-hosted runtime assumptions.
- Setup and users settings remain intentional overrides in
  `overrides/frontend/src/pages/SetupPage.tsx` and `overrides/frontend/src/pages/UsersSettingsPage.tsx`.
  Those files keep packaged backup/restore flows and desktop runtime affordances that do not exist in the self-hosted
  product.
- Backend parity still requires two narrow patch-time desktop adjustments instead of broad file forks:
  `scripts/patch-vendored-backend.mjs` adds the authenticated system-backup endpoint used by the full UI and aligns
  desktop-managed `local_path` receipt packs with the connector lifecycle model.
- Frontend parity still requires one narrow build patch in `scripts/patch-vendored-frontend.mjs` for the
  `@mariozechner/pi-ai` browser shim and for syncing the Electron-owned route policy into the vendored frontend before
  build/test.

Residual debt after Sprint 6:

- The route capability contract is now single-sourced inside `apps/desktop`, but the vendored frontend still receives it
  via patch-time file sync rather than a shared package.
- Desktop AI settings remain a maintained fork until the upstream app exposes the same desktop-safe provider gating
  without reintroducing OCR/runtime assumptions.
- The authenticated system-backup endpoint still lands through a narrow backend patch because it is desktop packaging
  behavior, not self-hosted server behavior.
- Deferred parity remains deferred on purpose: offers parity, automations parity, reliability/ops parity, and
  self-hosted operator workflows.

Future backlog note:

- A future desktop PR may add broader non-EUR currency support such as `USD` and `GBP`, but this is not a small
  symbol-only change.
- Current desktop budgeting, dashboard, recurring, and analytics flows still contain EUR-centric parsing/formatting and
  often sum raw cents across records, which is only safe for effectively single-currency views.
- If mixed-currency overviews are ever supported, the product will need an explicit policy such as base-currency
  conversion with stored FX-rate snapshots, separate per-currency totals, or hard limits on combining currencies in the
  same overview.

## User journey

Typical desktop flow:
1. Open the app.
2. Land in the control center with the backend still off.
3. Review the installed edition and market profile.
4. Install, update, enable, disable, or remove receipt packs if needed.
5. Either keep the session shell-only for one-off export/backup/import work, or explicitly choose **Open main app** when you want the full UI.
6. Run a one-off sync from the main app or from the control center using the connector `source_id` entries that the current desktop build exposes.
7. Review results locally, then export or back up if you want a portable copy.

## Runtime model

- Desktop launches into the Electron control center first.
- The Python backend stays off at idle until the user explicitly chooses **Open main app** or **Start local service**.
- Full-app startup runs the backend in desktop-minimal mode, which disables server-style background work such as the automation scheduler and connector live-sync thread.
- OCR processing is handled by a second Python worker process, separate from the Electron main process and the HTTP server process.
- The OCR worker is started on demand when the user triggers document OCR, not during normal backend startup.
- The desktop OCR worker exits after an idle timeout so the bundled OCR runtime does not stay resident in RAM between imports.
- One-off control-center tasks such as export, backup, restore, and most shell-managed workflows remain short-lived subprocesses instead of depending on a resident backend.
- Preferred backend executable order:
  1. `LIDLTOOL_EXECUTABLE` env override
  2. bundled backend venv inside packaged app (`resources/backend-venv/...`)
  3. local managed backend venv (`apps/desktop/.backend/venv/...`)
  4. system PATH (`lidltool` / `lidltool.exe`)
- Frontend assets for packaged builds are copied to `resources/frontend-dist`.
- Vendored backend source is copied to `resources/backend-src`.
- Desktop shell brand assets and packaged app icons live entirely inside `apps/desktop` (`src/renderer/assets`, `vendor/frontend/src/assets`, and `build/icon.*`).
- Backend receives:
  - `LIDLTOOL_FRONTEND_DIST`
  - `LIDLTOOL_REPO_ROOT`
  - `LIDLTOOL_CONFIG_DIR` rooted inside the Electron `userData` profile
  - `LIDLTOOL_DOCUMENT_STORAGE_PATH` rooted inside the Electron `userData` profile
  - `LIDLTOOL_DESKTOP_MODE=true`
  - `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY`
  - desktop-managed connector plugin env vars for explicitly enabled receipt plugin packs
  - `PLAYWRIGHT_BROWSERS_PATH=<profile>/playwright-browsers` for bundled or managed venv backends
- Desktop defaults `config.toml`/`token.json` and document storage to the app profile instead of shared
  `~/.config/lidltool` or `~/.local/share/lidltool` paths, so packaged runs stay isolated from self-hosted state.
- Local mac packaging is intentionally unsigned by default even when a signing identity exists in the keychain.
- Signed mac release builds use `npm run dist:mac:signed` together with explicit `CSC_NAME`, `APPLE_ID`,
  `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID` environment variables.
- Playwright browser binaries are kept outside the signed app bundle so Electron Builder does not try to recursively sign
  a nested Chromium tree inside `Resources/backend-venv`.

## Desktop OCR

Desktop OCR now ships as a local packaged workflow instead of depending on an external OCR service.

- The bundled backend venv includes `rapidocr_onnxruntime` and its ONNX model assets on disk.
- Electron keeps OCR out of the main app process by spawning a dedicated Python worker when OCR work is actually queued.
- The HTTP backend only enqueues OCR jobs. The durable worker consumes the queue and updates document/job state.
- The bundled desktop OCR provider is `glm_ocr_local`.
- Image uploads and scanned PDFs are OCRed locally in the worker process. PDFs that already contain a text layer still use direct text extraction first.
- The renderer wakes the worker after `POST /api/v1/documents/{document_id}/process` so the user does not get stuck in `queued`.
- If the worker cannot be started, desktop reports that startup failure back to the backend so the document/job move to `failed` instead of remaining queued forever.

User-visible OCR states:

- `queued`
- `starting_engine`
- `processing`
- `completed`
- `failed`

Idle lifecycle:

- The OCR worker stays warm briefly after work completes, then exits automatically.
- Tune the idle timeout with `LIDLTOOL_DESKTOP_OCR_IDLE_TIMEOUT_S`.
- Default idle timeout is `600` seconds.

Control-center states:
- full-app-ready: bundled frontend pages are present and the main app can open normally
- reduced fallback mode: desktop keeps the control center open because the local runtime did not start cleanly
- control-center-only: desktop keeps the shell open because the bundled frontend pages are missing, while local sync/export/backup tasks still remain available

Release metadata fallback:
- if the vendored market metadata is missing or incomplete, desktop falls back to a safe local shell profile
- manual receipt pack import remains available with conservative trust labeling
- trusted catalog installs only appear when verified metadata is present

## Receipt plugin packs

Desktop supports user-installed receipt connector packs without mutating the signed app bundle.

Scope:
- receipt plugins only
- manual local file import remains supported
- trusted URL install/update is supported only for signed catalog entries
- offer/deal plugins remain out of desktop scope
- recurring offer scraping and alerts remain out of desktop scope
- `dm_de` is now one of these optional receipt plugins rather than a built-in desktop connector
- `rewe_de` is an imported receipt pack in desktop rather than a built-in connector, so the desktop auth flow can reuse a normal Chrome session instead of depending on packaged CAPTCHA automation

Management surface:
- use the connectors page inside the desktop app for local pack import, trusted pack install, enable/disable, and removal
- the Electron control center still reflects the same pack state, but it is no longer required for basic pack management
- built-in browser-session connectors such as Amazon now finish setup by validating the saved session automatically; the desktop flow no longer depends on pressing Enter in a terminal window

Activation model:
- imported packs install disabled by default
- enable/disable is explicit
- manual unsigned packs are never presented as official or project-supported
- trusted catalog downloads must verify before install
- revoked, invalid, or incompatible packs stay visible but blocked from activation
- enabling, disabling, updating, or removing a pack restarts the local backend when needed

Support and trust labels shown in the desktop pack UI:
- `official`: project-maintained desktop path
- `community_verified`: signed community pack allowed by trusted desktop distribution
- `community_unsigned`: manual import only, kept under conservative trust labeling
- `local_custom`: operator-supplied local pack with no upstream support promise

Desktop workflow:
1. Open the connectors page in the desktop app.
2. Use `Import .zip connector` for a ZIP file, or choose `Install trusted pack` for a verified catalog entry.
3. Review the status, trust, support, and market-profile messaging.
4. Enable the pack explicitly if you want desktop to load it into the next backend run.
5. For built-in browser connectors such as Amazon, use `Connector settings` to tune saved defaults like scan depth, headless mode, and optional HTML debug dumps before running a real-account test.
6. For imported REWE packs, log into the REWE website in normal Chrome first, then use the connector auth/setup flow so the pack can import that authenticated Chrome session into its own saved state.
7. Use the same connectors page to install a trusted update, disable a pack, or remove it from local storage.

### Amazon multicountry

Desktop now exposes separate built-in Amazon marketplace connectors:
- `amazon_de` for `amazon.de`
- `amazon_fr` for `amazon.fr`
- `amazon_gb` for `amazon.co.uk`

Operator controls shared by both marketplaces:
- `years`: how many recent order-history years to scan
- `max_pages_per_year`: page limit per year
- `headless`: run sync without showing the browser
- `dump_html`: optional directory for list/detail/auth debug HTML

Saved browser-session state remains the auth model:
- `amazon_de` keeps the legacy state file name `amazon_storage_state.json`
- `amazon_fr` uses `amazon_fr_storage_state.json`
- `amazon_gb` uses `amazon_gb_storage_state.json`
- each marketplace validates the saved session against its own order-history URL before sync

Manual smoke-test steps from `apps/desktop`:
1. Start the desktop app and choose either `Amazon (DE)` or `Amazon (FR)` in the sync source picker.
2. Open connector bootstrap/auth for that marketplace and complete sign-in in the browser window, including MFA or CAPTCHA if Amazon requires it.
3. Set `headless=false` if you want to watch the browser during sync, then optionally set `years=1`, `max_pages_per_year=1`, and `dump_html=/absolute/path/to/amazon-debug`.
4. Run a sync and confirm that at least one order imports without a reauth error.
5. Inspect the debug HTML folder if a sync returns `partial` or `unsupported` Amazon parse metadata.

Manual CLI smoke-test commands from `apps/desktop`:

```bash
./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors auth bootstrap --source-id amazon_de
./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors sync --source-id amazon_de --option headless=false --option years=1 --option max_pages_per_year=1 --option dump_html=$PWD/.amazon-debug/de

./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors auth bootstrap --source-id amazon_fr
./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors sync --source-id amazon_fr --option headless=false --option years=1 --option max_pages_per_year=1 --option dump_html=$PWD/.amazon-debug/fr

./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors auth bootstrap --source-id amazon_gb
./.backend/venv/bin/python -m lidltool.cli --db "$PWD/.desktop-smoke.sqlite" connectors sync --source-id amazon_gb --option headless=false --option years=1 --option max_pages_per_year=1 --option dump_html=$PWD/.amazon-debug/gb
```

CLI debug scrape commands:

```bash
./.backend/venv/bin/python -m lidltool.cli amazon scrape --source-id amazon_de --headless --years 1 --max-pages-per-year 1 --dump-html $PWD/.amazon-debug/de
./.backend/venv/bin/python -m lidltool.cli amazon scrape --source-id amazon_fr --domain amazon.fr --headless --years 1 --max-pages-per-year 1 --dump-html $PWD/.amazon-debug/fr
./.backend/venv/bin/python -m lidltool.cli amazon scrape --source-id amazon_gb --domain amazon.co.uk --headless --years 1 --max-pages-per-year 1 --dump-html $PWD/.amazon-debug/gb
```

Third-party authoring reference:
- the clean-break template lives in `examples/reference_receipt_plugin_template`
- build a manual-import ZIP with `python examples/reference_receipt_plugin_template/build_desktop_pack.py`
- use the checklist in that template README to verify import, enable, bootstrap, sync, and uninstall behavior

### Pack format

Desktop uses a ZIP-based receipt plugin pack with this layout:

```text
plugin-pack.json
manifest.json
integrity.json
signature.json          # optional for manual import, required for trusted URL install
payload/...
```

Desktop validates:
- ZIP structure and safe paths
- required files and runtime payload presence
- per-file SHA-256 hashes
- backend manifest compatibility for host kind `electron`
- imported trust-class policy
- detached Ed25519 signatures against the pack envelope + payload hash manifest for trusted installs
- trusted distribution revocations by key id, plugin id/version, or archive hash

Desktop also reads optional connector onboarding content from the plugin `manifest.json`.
Plugin authors can provide an `onboarding` block there with:
- `title`
- `summary`
- `expected_speed`
- `caution`
- `steps`: array of `{ "title", "description" }`

The desktop connectors page uses that manifest-owned onboarding to explain connector-specific behavior such as slower scraping or first-run expectations.

### Storage layout

Imported packs live under user-writable Electron app-data, never under packaged app resources.

- macOS:
  - `~/Library/Application Support/LidlTool Desktop/plugins/receipt-packs/`
- Windows:
  - `%APPDATA%/LidlTool Desktop/plugins/receipt-packs/`

Desktop-managed layout:

```text
plugins/receipt-packs/
  state.json
  installs/
    <plugin-id>/
      <plugin-version>/
        plugin-pack.json
        manifest.json
        integrity.json
        signature.json
        payload/...
  staging/
```

## Backup, export, and restore

Backup:
- creates a local backup directory for this desktop profile
- always includes the database
- can include document storage and a JSON export snapshot
- does not include receipt pack archives or any hosted service state
- requires an empty output directory

Export:
- writes normalized receipts to a single local JSON file
- does not include credentials, tokens, plugin packs, or document storage
- is the better choice when you want portable data without restoring a full desktop profile

Restore:
- restores the local database from a backup directory
- can restore credential key, token, and document storage when present
- does not reinstall receipt packs automatically
- can restart the local backend after restore

## Release variants and regional editions

Desktop source of truth:
- official bundle/profile catalog is vendored under `apps/desktop/vendor/backend/src/lidltool/connectors/official_market_catalog.json`
- Electron resolves release metadata from that vendored catalog at runtime/build time

Current desktop release variants:
- `desktop_universal_shell`
  - stable default
  - neutral/global shell
  - still supports optional imported receipt plugin packs
  - bundled Lidl Plus source entries currently include DE plus preview GB/FR
- `desktop_dach_edition`
  - stable regional preset
  - preselects the `dach_starter` profile
- `desktop_us_shell`
  - preview preset for future rollout
  - intentionally does not imply official US connector support yet

Set the active desktop release preset with:
- `LIDLTOOL_DESKTOP_RELEASE_VARIANT`

Notes:
- universal shell and regional editions share the same plugin/runtime model
- official bundle metadata is separate from imported community/local receipt packs
- desktop uses the market profile to explain why some connectors are preselected while others are optional
- desktop offer/deal parity remains intentionally out of scope

## Curated connector catalog

Desktop consumes a signed connector catalog envelope and can optionally fetch a newer signed remote catalog when
`LIDLTOOL_DESKTOP_CATALOG_URL` is set.

Desktop catalog source of truth:
- bundled signed envelope: `apps/desktop/src/main/trusted-distribution/bundled-connector-catalog.json`
- bundled trust roots: `apps/desktop/src/main/trusted-distribution/trust-roots.json`
- parsed desktop catalog logic: `apps/desktop/src/main/connector-catalog.ts`

Current behavior:
- invalid or unverifiable remote catalog metadata fails closed and is ignored
- the bundled signed catalog remains the trust anchor fallback
- catalog entries never auto-install or auto-enable anything
- trusted desktop-pack entries may expose explicit `Install trusted pack` and `Install trusted update` actions
- revoked catalog entries stay visible with block reasons and cannot be installed through the trusted flow
- local ZIP import remains the first-class path for community and local receipt packs
- official versus community trust labeling stays explicit in the control center

Current desktop deferrals still remain:
- no full hosted marketplace flow
- no multi-hop signature chain beyond bundled trust roots and detached signatures
- no offer/deal plugin-pack parity

## Vendor sync (required)

Desktop uses local vendored sources under `apps/desktop/vendor`.

```bash
cd apps/desktop
npm run vendor:sync
```

This is the only script that reads from the main repo to refresh local copies.

`vendor:sync` now does three explicit things for i18n:
- copies the canonical web frontend, including `frontend/src/i18n/*`, into `apps/desktop/vendor/frontend`
- reapplies documented desktop-only overlays from `apps/desktop/overrides/frontend`
- regenerates the Electron shell catalog under `apps/desktop/src/i18n/generated.ts` from the canonical web message source plus desktop-shell-only additions

After every sync/build, desktop applies a local vendored frontend compatibility patch:
- `scripts/patch-vendored-frontend.mjs`
- Injects a Vite alias for `@mariozechner/pi-ai` -> `src/shims/pi-ai.ts`
- Prevents browser Rollup failures caused by Node-only Smithy/stream imports
- Reapplies desktop-only renderer overrides such as packaged backup/restore flows
- `overrides/frontend` reapplies the intentional desktop-only frontend surface after each vendor sync so the vendored app stays current with main
- `scripts/patch-vendored-backend.mjs` reapplies the desktop-only system-backup endpoint after each vendor sync
- `npm run frontend:install` uses `npm ci` against `vendor/frontend/package-lock.json` so desktop keeps the same React/JSON-renderer dependency graph as the vendored app

## Prerequisites

- Node.js 20+
- npm
- Python 3.11 to 3.12 for desktop backend preparation and release builds

## Local development

Build frontend + start Electron:

```bash
cd apps/desktop
npm install
npm run vendor:sync
npm run frontend:install
npm run frontend:build
npm run dev
```

If you want the backend fully managed inside `apps/desktop` (recommended):

```bash
cd apps/desktop
npm run vendor:sync
npm run frontend:install
npm run backend:prepare
npm run frontend:build
npm run dev
```

`npm run backend:prepare` now builds a standalone desktop backend venv instead of an editable checkout-linked install.
That venv is what later gets copied into `build/backend-venv` for packaged desktop runs.

Desktop intentionally prefers Python `3.12`, then `3.11` for backend preparation because the bundled
desktop OCR runtime is only treated as production-ready on that range today.
If you intentionally need to bypass that guard, set `LIDLTOOL_DESKTOP_ALLOW_UNSUPPORTED_PYTHON=1`, but that is not
the recommended release path.

Run the real desktop Electron E2E smoke suite:

```bash
cd apps/desktop
npm run test:e2e:prepare
npm run test:e2e
```

## Desktop profiling

Use the built-in profiler to capture the full desktop process tree as JSON.

Idle control center:

```bash
cd apps/desktop
npm run profile:desktop -- --scenario idle-control-center
```

Idle full app:

```bash
cd apps/desktop
npm run profile:desktop -- --scenario idle-full-app
```

Custom active workflow profiling:

```bash
cd apps/desktop
npm run profile:desktop -- --scenario export --action-shell 'echo "drive the export flow here"'
```

Notes:
- Reports are written under `apps/desktop/output/desktop-profiles/.../profile.json`.
- The profiler launches Electron with an isolated desktop profile so measurements do not reuse your normal local state.
- `idle-full-app` has a built-in **Open main app** transition.
- `sync`, `export`, and `backup` are named profiling slots; drive the active step with `--action-shell` when you want a repeatable workflow-specific sample.

## Exact release workflow

Run from `apps/desktop` on the target OS you are releasing for.

```bash
npm install
npm run vendor:sync
npm run frontend:install
npm run frontend:build
npm run backend:prepare
npm run test:ocr-packaged
npm run test:e2e
npm run test:plugin-packs
npm run test:release-metadata
npm run typecheck
npm run build
npm run dist:full
```

Expected high-level outcomes:
- `frontend:build` succeeds and writes `vendor/frontend/dist`
- `backend:prepare` succeeds and installs Chromium outside the venv, by default under `.cache/playwright-browsers`
- `test:ocr-packaged` proves the built `build/backend-venv` + `build/backend-src` payload can upload a scanned PDF,
  start the separate OCR worker, reach `queued -> starting_engine -> processing -> completed`, create a receipt, and
  let the worker exit after idle timeout
- `build` syncs `build/frontend-dist`, `build/backend-src`, `build/backend-venv`
- `dist:full` produces packaged artifacts in `dist_electron/` without attempting automatic mac signing

For a Windows release, run the same workflow on Windows (or Windows CI runner).  
For a macOS release, run it on macOS.

## Packaging commands

Build app bundles (fallback control center always included; full UI bundle included only if `vendor/frontend/dist` exists):

```bash
cd apps/desktop
npm run vendor:sync
npm run dist:mac
npm run dist:win
```

Build with bundled backend runtime + scrapers:

```bash
cd apps/desktop
npm run dist:with-backend
```

Build fully bundled UI + backend runtime:

```bash
cd apps/desktop
npm run dist:full
```

Build an explicitly signed/notarized mac release:

```bash
cd apps/desktop
CSC_NAME="Developer ID Application: <name> (<team>)" \
APPLE_ID="..." \
APPLE_APP_SPECIFIC_PASSWORD="..." \
APPLE_TEAM_ID="..." \
npm run dist:mac:signed
```

See `RELEASE_CHECKLIST.md` for concrete verification commands and expected outputs.

## Notes

- First packaged run still depends on OS-level browser/sandbox compatibility for Playwright.
- Default mac packaging scripts are intentionally unsigned so Electron Builder does not auto-discover a local development identity.
- Signed/notarized mac releases go through the explicit `dist:mac:signed` lane.

## Manual Verification Results

Date: 2026-03-02  
Environment: macOS arm64, commands run from `apps/desktop`

### Checklist command execution

Executed these release-checklist build commands in order:

```bash
npm install
npm run vendor:sync
npm run frontend:install
npm run frontend:build
npm run backend:prepare
npm run typecheck
npm run build
npm run dist:full
```

Desktop isolation rule check (no new desktop runtime/build `../..` references):

```bash
rg -n "\\.\\./\\.\\." src scripts package.json electron.vite.config.ts RELEASE_CHECKLIST.md README.md AGENTS.md
```

Outcome:
- Only documentation mentions in `AGENTS.md`; no runtime/build script `../..` path dependencies introduced.

Outcome summary:
- `npm install`: pass
- `npm run vendor:sync`: pass (`Vendored frontend -> .../apps/desktop/vendor/frontend`, `Vendored backend -> .../apps/desktop/vendor/backend`, frontend patch log present)
- `npm run frontend:install`: pass (npm peer/deprecation warnings only)
- `npm run frontend:build`: pass (`vite build` wrote `vendor/frontend/dist`)
- `npm run backend:prepare`: pass (`Prepared desktop backend runtime at .../apps/desktop/.backend/venv`)
- `npm run typecheck`: pass (`tsc --noEmit` exit 0)
- `npm run build`: pass (`Synced frontend assets`, `Synced backend source`, `Synced backend runtime`)
- `npm run dist:full`: pass (`dist_electron/` contains `.dmg`, `.zip`, and blockmaps)

### Packaged resource inclusion checks

Executed:

```bash
APP="dist_electron/mac-arm64/LidlTool Desktop.app/Contents/Resources"
for d in frontend-dist backend-src backend-venv; do test -d "$APP/$d" && echo "OK dir: $d"; done
for f in frontend-dist/index.html backend-src/pyproject.toml backend-venv/bin/lidltool; do test -f "$APP/$f" && echo "OK file: $f"; done
find "$APP/backend-venv/lib" -type d -path "*/site-packages/playwright/driver/package/.local-browsers"
```

Outcome:
- `frontend-dist`, `backend-src`, `backend-venv`: present
- `frontend-dist/index.html`: present
- `backend-src/pyproject.toml`: present
- `backend-venv/bin/lidltool`: present
- No Playwright browser payload bundled under `.local-browsers`

### Boot-flow validation (packaged app)

Success path command:

```bash
APP="$PWD/dist_electron/mac-arm64/LidlTool Desktop.app/Contents/MacOS/LidlTool Desktop"
"$APP" --remote-debugging-port=9333
```

Verified via DevTools target + health probe:
- desktop launched into the control center first
- opening the main app transitioned to the full UI on `http://127.0.0.1:18765/setup`
- backend health endpoint `GET /api/v1/health` returned `200`

Failure fallback command:

```bash
APP="$PWD/dist_electron/mac-arm64/LidlTool Desktop.app/Contents/MacOS/LidlTool Desktop"
LIDLTOOL_EXECUTABLE=/does/not/exist "$APP" --remote-debugging-port=9334
```

Verified from fallback control center (automated UI interaction against packaged renderer):
- fallback page loaded (`file://.../out/renderer/index.html`)
- boot error text shown:
  - `Automatic full-app boot failed: Error: Failed to launch backend executable '/does/not/exist' ...`
- clicked **Start backend** from fallback: status became `running (pid ...)`
- clicked **Run one-time scrape** from fallback:
  - `Command Result` panel updated with JSON command result (`exitCode: 1` in this environment)
  - runtime log stream populated with sync stderr/stdout lines

Note on one-time sync result:
- The one-time sync action executed correctly through fallback controls.
- In this local environment, sync returned `exitCode: 1` with `CredentialCryptoError: unable to decrypt credential envelope` (existing local credential state), but log/result behavior matched release checklist expectations.

### Failures found during verification and fixes applied

1) Forced-failure fallback could not recover for manual actions  
- Symptom: with `LIDLTOOL_EXECUTABLE=/does/not/exist`, fallback loaded but manual sync/start used the same bad path (`spawn ... ENOENT`) and backend status could remain stale.
- Fix:
  - `src/main/runtime.ts`: recover stale process state on spawn error, fail fast on invalid spawn, use strict override only for auto-boot, and use executable fallback chain for manual fallback actions (`start backend`, `open full app`, one-time sync).
  - `src/main/index.ts`: auto-boot now calls `startBackend({ strictOverride: true })` so the forced failure path still triggers fallback.

2) Boot error text could be missed in fallback UI  
- Symptom: fallback sometimes showed without the boot error message due event timing.
- Fix:
  - Added boot-error getter IPC + preload API and consume it during renderer boot.
  - Updated files: `src/main/ipc.ts`, `src/preload/index.ts`, `src/renderer/env.d.ts`, `src/renderer/App.tsx`, `src/main/index.ts`.

After each fix, `npm run typecheck` and `npm run dist:full` were rerun, then the affected boot-flow checks were rerun against the new packaged app.

### Final release-output check

Verified release artifacts are produced under `dist_electron/` and only these packaged outputs are intended for shipping.

### 2026-03-02 Full-App Backup Verification (Desktop-Only)

Goal: ensure desktop-only users can trigger a backup from the fully functional app UI (not only fallback).

Commands executed (from `apps/desktop`):

```bash
./.backend/venv/bin/python -m py_compile vendor/backend/src/lidltool/api/http_server.py vendor/backend/src/lidltool/ops/backup_restore.py
npm run typecheck
npm run frontend:build
npm run build
```

Outcome:
- Python compile check: pass
- `npm run typecheck`: pass
- `npm run frontend:build`: pass
- `npm run build`: pass

Authenticated backup API smoke (new backend route used by full UI settings page):

```bash
set -euo pipefail
PORT=18895
DB=/tmp/lidltool-system-backup-login.sqlite
CFG=/tmp/lidltool-system-backup-login-config
OUT=/tmp/lidltool-system-backup-login-output
COOKIE=/tmp/lidltool-system-backup-login-cookie.txt
LOG=/tmp/lidltool-system-backup-login.log
rm -rf "$CFG" "$OUT" "$COOKIE" "$DB" "$LOG"
mkdir -p "$CFG"
LIDLTOOL_CONFIG_DIR="$CFG" LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY="smoke-smoke-smoke-smoke-smoke-smoke-smoke-smoke" \
  ./.backend/venv/bin/python - <<'PY'
from pathlib import Path
from lidltool.auth.users import create_local_user
from lidltool.config import build_config, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope

cfg = build_config(db_override=Path("/tmp/lidltool-system-backup-login.sqlite"))
db_url = database_url(cfg)
migrate_db(db_url)
engine = create_engine_for_url(db_url)
sessions = session_factory(engine)
with session_scope(sessions) as session:
    create_local_user(
        session,
        username="admin",
        password="admin1234",
        display_name="Admin",
        is_admin=True,
    )
PY
LIDLTOOL_CONFIG_DIR="$CFG" LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY="smoke-smoke-smoke-smoke-smoke-smoke-smoke-smoke" \
  ./.backend/venv/bin/lidltool --db "$DB" serve --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && break
  sleep 0.25
done
curl -fsS -c "$COOKIE" -b "$COOKIE" -H 'content-type: application/json' \
  -d '{"username":"admin","password":"admin1234"}' \
  "http://127.0.0.1:$PORT/api/v1/auth/login" > /tmp/lidltool-system-backup-login-auth.json
curl -fsS -c "$COOKIE" -b "$COOKIE" -H 'content-type: application/json' \
  -d '{"output_dir":"'"$OUT"'","include_documents":false,"include_export_json":true}' \
  "http://127.0.0.1:$PORT/api/v1/system/backup" > /tmp/lidltool-system-backup-login-response.json
ls -1 "$OUT"
```

Observed result:
- Endpoint response `ok: true`
- Output directory created and contained:
  - `backup-manifest.json`
  - `credential_encryption_key.txt`
  - `db-backup-<timestamp>.sqlite`
  - `receipts-export.json`
- `skipped` field correctly reported unavailable/disabled artifacts (`token file not found`, `documents excluded by request`)

Full UI verification (login + click through `System -> Users` backup card):

```bash
set -euo pipefail
PORT=18896
DB=/tmp/lidltool-ui-backup-login.sqlite
CFG=/tmp/lidltool-ui-backup-login-config
OUT=/tmp/lidltool-ui-backup-login-output
LOG=/tmp/lidltool-ui-backup-login.log
rm -rf "$CFG" "$OUT" "$DB" "$LOG"
mkdir -p "$CFG"
LIDLTOOL_CONFIG_DIR="$CFG" LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY="smoke-smoke-smoke-smoke-smoke-smoke-smoke-smoke" \
  ./.backend/venv/bin/python - <<'PY'
from pathlib import Path
from lidltool.auth.users import create_local_user
from lidltool.config import build_config, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope

cfg = build_config(db_override=Path("/tmp/lidltool-ui-backup-login.sqlite"))
db_url = database_url(cfg)
migrate_db(db_url)
engine = create_engine_for_url(db_url)
sessions = session_factory(engine)
with session_scope(sessions) as session:
    create_local_user(
        session,
        username="admin",
        password="admin1234",
        display_name="Admin",
        is_admin=True,
    )
PY
LIDLTOOL_CONFIG_DIR="$CFG" LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY="smoke-smoke-smoke-smoke-smoke-smoke-smoke-smoke" \
LIDLTOOL_FRONTEND_DIST="$PWD/vendor/frontend/dist" LIDLTOOL_REPO_ROOT="$PWD/vendor/backend" \
  ./.backend/venv/bin/lidltool --db "$DB" serve --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && break
  sleep 0.25
done
./.backend/venv/bin/python - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path("/tmp/lidltool-ui-backup-login-output")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://127.0.0.1:18896/login", wait_until="networkidle")
    page.fill("#username", "admin")
    page.fill("#password", "admin1234")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("http://127.0.0.1:18896/")
    page.goto("http://127.0.0.1:18896/settings/users", wait_until="networkidle")
    page.fill("#backup-output-dir", str(out))
    page.get_by_label("Include document storage").uncheck()
    page.get_by_role("button", name="Create backup bundle").click()
    page.get_by_text("Backup created at", exact=False).wait_for(timeout=20000)
    browser.close()
PY
ls -1 "$OUT"
```

Observed result:
- Backup card executed successfully from full UI.
- Output directory contained `backup-manifest.json`, `credential_encryption_key.txt`, `db-backup-<timestamp>.sqlite`, and `receipts-export.json`.

### 2026-03-02 Backup Import Verification (Fresh Desktop Environment)

Goal: verify desktop users can restore a backup bundle into a fresh local desktop runtime, then sign in with restored data.

Build/type checks rerun after restore feature implementation:

```bash
npm run typecheck
npm run frontend:build
npm run build
```

Outcome:
- `npm run typecheck`: pass
- `npm run frontend:build`: pass
- `npm run build`: pass

Fresh-environment restore smoke (Electron + setup-page restore flow):

```bash
set -euo pipefail
cd /Users/max/projekte/lidltool/apps/desktop
SOURCE_BACKUP=/tmp/lidltool-import-source-backup
SOURCE_DB=/tmp/lidltool-import-source.sqlite
SOURCE_CFG=/tmp/lidltool-import-source-config
RESTORE_KEY=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
rm -rf "$SOURCE_BACKUP" "$SOURCE_DB" "$SOURCE_CFG"
mkdir -p "$SOURCE_BACKUP" "$SOURCE_CFG"

LIDLTOOL_CONFIG_DIR="$SOURCE_CFG" LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY="$RESTORE_KEY" \
  ./.backend/venv/bin/python - <<'PY'
from pathlib import Path
from lidltool.auth.users import create_local_user
from lidltool.config import build_config, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope

db_path = Path("/tmp/lidltool-import-source.sqlite")
cfg = build_config(db_override=db_path)
db_url = database_url(cfg)
migrate_db(db_url)
engine = create_engine_for_url(db_url)
sessions = session_factory(engine)
with session_scope(sessions) as session:
    create_local_user(
        session,
        username="restoreadmin",
        password="restorepass123",
        display_name="Restore Admin",
        is_admin=True,
    )
PY

cp "$SOURCE_DB" "$SOURCE_BACKUP/lidltool.sqlite"
printf '%s\n' "$RESTORE_KEY" > "$SOURCE_BACKUP/credential_encryption_key.txt"
printf '{"refresh_token":"sample-token"}\n' > "$SOURCE_BACKUP/token.json"
mkdir -p "$SOURCE_BACKUP/documents"
printf 'restored doc\n' > "$SOURCE_BACKUP/documents/example.txt"

USER_DATA_DIR=/tmp/lidltool-import-fresh-userdata
CONFIG_DIR=/tmp/lidltool-import-fresh-config
DOCS_DIR=/tmp/lidltool-import-fresh-docs
E_LOG=/tmp/lidltool-import-electron-fresh.log
rm -rf "$USER_DATA_DIR" "$CONFIG_DIR" "$DOCS_DIR" "$E_LOG"
mkdir -p "$USER_DATA_DIR" "$CONFIG_DIR" "$DOCS_DIR"

LIDLTOOL_CONFIG_DIR="$CONFIG_DIR" LIDLTOOL_DOCUMENT_STORAGE_PATH="$DOCS_DIR" \
  ./node_modules/.bin/electron . --user-data-dir="$USER_DATA_DIR" --remote-debugging-port=9461 >"$E_LOG" 2>&1 &
EPID=$!
trap 'kill "$EPID" >/dev/null 2>&1 || true' EXIT
for i in $(seq 1 120); do
  curl -fsS "http://127.0.0.1:9461/json/version" >/dev/null && break
  sleep 0.25
done

BACKUP_DIR="$SOURCE_BACKUP" ./.backend/venv/bin/python - <<'PY'
import os
import time
from playwright.sync_api import sync_playwright

backup_dir = os.environ["BACKUP_DIR"]
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9461")
    page = None
    for _ in range(120):
        for ctx in browser.contexts:
            for candidate in ctx.pages:
                if candidate.url.startswith("http://127.0.0.1:18765"):
                    page = candidate
                    break
            if page:
                break
        if page:
            break
        time.sleep(0.25)
    if page is None:
        raise SystemExit("no app page found")
    for _ in range(120):
        if page.locator("#restore-dir").count() > 0:
            break
        time.sleep(0.25)
    page.fill("#restore-dir", backup_dir)
    page.get_by_role("button", name="Restore backup and sign in").click()
    page.wait_for_url("http://127.0.0.1:18765/login", timeout=30000)
    page.fill("#username", "restoreadmin")
    page.fill("#password", "restorepass123")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("http://127.0.0.1:18765/", timeout=30000)
    browser.close()
PY

python3 - <<'PY'
import sqlite3
db = "/tmp/lidltool-import-fresh-userdata/lidltool.sqlite"
conn = sqlite3.connect(db)
row = conn.execute("select username from users where username='restoreadmin'").fetchone()
print("db_has_restore_user", bool(row))
conn.close()
PY
```

Observed result:
- Setup page restore action executed successfully via **Restore backup and sign in**.
- Login with restored user succeeded.
- Restored artifacts existed in fresh runtime paths:
  - DB: `/tmp/lidltool-import-fresh-userdata/lidltool.sqlite`
  - token: `/tmp/lidltool-import-fresh-config/token.json`
  - documents: `/tmp/lidltool-import-fresh-docs/example.txt`
  - credential key: `/tmp/lidltool-import-fresh-userdata/credential_encryption_key.txt`
