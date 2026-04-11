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
- Deferred parity remains deferred on purpose: OCR runtime parity, offers parity, automations parity, reliability/ops
  parity, and self-hosted operator workflows.

## User journey

Typical desktop flow:
1. Open the app.
2. Confirm whether the main app is available or whether the local control center is active.
3. Review the installed edition and market profile.
4. Install, update, enable, disable, or remove receipt packs if needed.
5. Run a one-off sync.
6. Review results locally, then export or back up if you want a portable copy.

## Runtime model

- Preferred backend executable order:
  1. `LIDLTOOL_EXECUTABLE` env override
  2. bundled backend venv inside packaged app (`resources/backend-venv/...`)
  3. local managed backend venv (`apps/desktop/.backend/venv/...`)
  4. system PATH (`lidltool` / `lidltool.exe`)
- Frontend assets for packaged builds are copied to `resources/frontend-dist`.
- Vendored backend source is copied to `resources/backend-src`.
- Backend receives:
  - `LIDLTOOL_FRONTEND_DIST`
  - `LIDLTOOL_REPO_ROOT`
  - `LIDLTOOL_CONFIG_DIR` rooted inside the Electron `userData` profile
  - `LIDLTOOL_DOCUMENT_STORAGE_PATH` rooted inside the Electron `userData` profile
  - `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY`
  - desktop-managed connector plugin env vars for explicitly enabled receipt plugin packs
  - `PLAYWRIGHT_BROWSERS_PATH=0` for bundled or managed venv backends
- Desktop defaults `config.toml`/`token.json` and document storage to the app profile instead of shared
  `~/.config/lidltool` or `~/.local/share/lidltool` paths, so packaged runs stay isolated from self-hosted state.

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

Management surface:
- use the connectors page inside the desktop app for local pack import, trusted pack install, enable/disable, and removal
- the Electron control center still reflects the same pack state, but it is no longer required for basic pack management

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
2. Use `Import local pack` for a ZIP file, or choose `Install trusted pack` for a verified catalog entry.
3. Review the status, trust, support, and market-profile messaging.
4. Enable the pack explicitly if you want desktop to load it into the next backend run.
5. Use the same connectors page to install a trusted update, disable a pack, or remove it from local storage.

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
- Python 3.11+

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

Run the real desktop Electron E2E smoke suite:

```bash
cd apps/desktop
npm run test:e2e:prepare
npm run test:e2e
```

## Exact release workflow

Run from `apps/desktop` on the target OS you are releasing for.

```bash
npm install
npm run vendor:sync
npm run frontend:install
npm run frontend:build
npm run backend:prepare
npm run test:e2e
npm run test:plugin-packs
npm run test:release-metadata
npm run typecheck
npm run build
npm run dist:full
```

Expected high-level outcomes:
- `frontend:build` succeeds and writes `vendor/frontend/dist`
- `backend:prepare` succeeds and reports Chromium under `.../site-packages/playwright/.../.local-browsers/chromium-*`
- `build` syncs `build/frontend-dist`, `build/backend-src`, `build/backend-venv`
- `dist:full` produces packaged artifacts in `dist_electron/`

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

See `RELEASE_CHECKLIST.md` for concrete verification commands and expected outputs.

## Notes

- First packaged run still depends on OS-level browser/sandbox compatibility for Playwright.
- Code signing/notarization is not yet configured in this scaffold.

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
find "$APP/backend-venv/lib" -type d -path "*/site-packages/playwright/driver/package/.local-browsers/chromium-*"
```

Outcome:
- `frontend-dist`, `backend-src`, `backend-venv`: present
- `frontend-dist/index.html`: present
- `backend-src/pyproject.toml`: present
- `backend-venv/bin/lidltool`: present
- Playwright Chromium payload present under `.local-browsers/chromium-1208`

### Boot-flow validation (packaged app)

Success path command:

```bash
APP="$PWD/dist_electron/mac-arm64/LidlTool Desktop.app/Contents/MacOS/LidlTool Desktop"
"$APP" --remote-debugging-port=9333
```

Verified via DevTools target + health probe:
- page target URL auto-loaded to full UI on `http://127.0.0.1:18765/setup`
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

## Electron security hardening plan

This section defines the desktop security-hardening plan for AI-driven Python analysis in the Electron product.

### Problem statement

Desktop currently ships an agent tool surface that includes arbitrary Python execution for flexible analysis. That is
useful for open-ended analytics, but the current host-subprocess pattern is not an acceptable security boundary for a
packaged desktop app on macOS or Windows.

We need to preserve Python-based analysis while removing host-level arbitrary code execution from the normal desktop
runtime path.

### Non-goals

- Do not preserve compatibility with older desktop installs.
- Do not design a migration path for earlier sandbox or exec-tool formats.
- Do not support arbitrary shell or terminal access from the agent.
- Do not optimize this design around self-hosted Docker deployments; this section is for the Electron desktop product.

### Migration assumption

There is currently no production installation base for desktop, so we do not need migration shims, dual-write paths,
legacy schema compatibility, upgrade jobs, or compatibility with older analysis worker formats. We can ship the first
secure implementation as the only supported desktop execution path.

### Security goals

- Keep Python execution available for analytics.
- Remove arbitrary host Python execution from the main backend runtime.
- Prevent agent-driven access to secrets, user files, plugin payloads, and network by default.
- Restrict analysis runs to a job-local workspace plus a read-only data snapshot.
- Enforce timeout, memory, output-size, and concurrency limits outside the Python runtime.
- Keep the implementation fully inside the packaged Electron app for macOS and Windows.

### Recommended architecture

Desktop runtime layout:

1. Electron renderer creates agent requests and sends structured tool calls to the local backend.
2. The local backend acts as an analysis broker, not as the execution environment.
3. The broker prepares a job directory and a read-only database snapshot or reduced analysis dataset.
4. The broker launches a packaged sandbox worker as a separate helper process.
5. The worker executes Python inside a real sandbox boundary and writes structured results back to the job directory.
6. The broker validates results, stores audit metadata, returns sanitized output to the frontend, and cleans up.

### Isolation model

Primary boundary:

- Use a dedicated packaged analysis worker instead of host Python in the main backend.
- Run Python inside a WASI/WebAssembly sandbox or equivalent restricted runtime inside the helper.
- Mount only the per-job workspace into the worker.
- Do not provide network, subprocess spawning, shared user-data directories, config paths, document paths, or plugin
  paths to the worker.

Defense in depth:

- Validate submitted code before execution.
- Provide a narrow allowed module set.
- Strip dangerous builtins.
- Cap stdout, stderr, and artifact sizes.
- Restrict result formats to declared structured outputs.

### Data-access model

Allowed worker inputs:

- a read-only SQLite snapshot, or
- a broker-generated reduced dataset containing only approved tables/views.

Disallowed worker inputs:

- live primary database path
- `config.toml`
- `token.json`
- credential encryption key
- document storage
- plugin directories
- arbitrary filesystem access outside the job workspace

Recommended first implementation:

- Create a read-only SQLite snapshot per job because it minimizes application changes.
- Move to reduced approved datasets later if snapshot size or privacy scope becomes an issue.

### Runtime policy

Every analysis run must enforce:

- timeout
- memory limit
- single-job or low-concurrency execution
- max output bytes
- max returned rows
- max artifact count
- full cleanup on timeout or crash

Platform-specific enforcement:

- Windows: wrap the worker process in a Job Object and apply process/memory kill behavior there.
- macOS: launch the worker in its own process group and kill the entire group on timeout or failure.

### Packaging model

The desktop app bundle should contain:

- Electron shell
- bundled backend runtime
- bundled frontend assets
- bundled analysis worker helper
- worker runtime assets required for sandboxed Python execution

Packaging expectations:

- macOS app bundle contains a signed helper binary under desktop resources.
- Windows installer contains the helper executable under desktop resources.
- Helper resolution follows the same packaged-versus-dev lookup pattern as the existing backend runtime.

### API and tooling changes

Replace the current raw exec path with a dedicated analysis path.

Backend:

- Add `POST /api/v1/tools/analysis-python`.
- Remove desktop reliance on `POST /api/v1/tools/exec`.
- Keep the old raw exec path disabled for desktop builds.

Frontend agent tools:

- Remove `execute_python` from the desktop-exposed tool list.
- Add `run_analysis_python` with a description that explicitly states:
  - no network
  - read-only dataset access only
  - structured outputs preferred
  - host shell access unavailable

### Backend broker responsibilities

Create a new desktop analysis broker module responsible for:

- auth and policy checks
- request schema validation
- code hashing and audit metadata
- job directory creation
- snapshot generation
- worker launch
- timeout and resource enforcement
- result parsing
- cleanup
- error normalization

### Worker contract

The worker should accept a manifest containing:

- job id
- code
- timeout
- memory limit
- mounted input files
- declared output path
- allowed module profile

The worker should return structured JSON containing:

- `ok`
- `stdout`
- `stderr`
- `exit_code`
- `artifacts`
- `metrics`
- `truncated`
- `policy_version`

### Audit and observability

The desktop app should record for each analysis run:

- user id
- chat thread id if present
- code hash
- start/end timestamps
- duration
- timeout/memory policy
- worker exit status
- output size
- artifact count
- sandbox version

Do not store raw submitted code long-term unless product/privacy policy explicitly allows it. Prefer storing a code
hash and short execution summary.

### Phase plan

Phase 1: secure broker skeleton

- Add a new analysis broker module.
- Add the new `analysis-python` endpoint.
- Add a packaged helper that only validates manifests and echoes a static result.
- Add job-directory creation, cleanup, timeout plumbing, and audit logging.
- Remove desktop dependence on the old raw exec route from the agent tool list.

Phase 2: snapshot-based execution

- Generate per-job read-only SQLite snapshots.
- Pass only the snapshot and a manifest into the helper.
- Return structured stdout/stderr/results through the broker.
- Add output-size and concurrency controls.

Phase 3: real sandbox enforcement

- Replace any placeholder execution path with the real sandbox runtime.
- Enforce no-network, no-subprocess, no-host-filesystem guarantees in the worker boundary.
- Add AST validation and restricted builtins as defense in depth.

Phase 4: UX and diagnostics

- Show sandbox status in desktop diagnostics.
- Show clear user-facing errors for timeouts, policy violations, and unavailable worker runtime.
- Add test coverage for packaged macOS and Windows builds.

### Acceptance criteria

Desktop is considered hardened for agent-driven Python analysis when all of the following are true:

- The agent cannot trigger host-level arbitrary Python execution from the normal desktop tool path.
- Analysis code runs only in the packaged sandbox worker.
- The worker cannot read config, token, credential key, documents, or plugin payloads.
- The worker cannot open outbound network connections.
- The worker cannot spawn subprocesses.
- The worker can only access the provided analysis snapshot/workspace.
- The worker is terminated reliably on timeout or memory breach.
- Packaged builds for macOS and Windows both pass the same analysis-worker integration tests.

### Sprint 1 scope

Sprint 1 should establish the new architecture without yet delivering the final sandbox runtime.

Sprint 1 deliverables:

- new `analysis-python` endpoint and request/response schema
- new backend analysis broker module
- job workspace creation and cleanup
- packaged helper path resolution in desktop runtime/build flow
- placeholder helper that returns deterministic JSON without executing host Python
- desktop tool-list swap from raw `execute_python` to `run_analysis_python`
- audit logging for requests and worker results
- tests proving the desktop agent no longer depends on `/api/v1/tools/exec`

Sprint 1 explicit exclusions:

- final WASI runtime integration
- pandas/dataframe ergonomics
- reduced-dataset export format
- migration support for old desktop installs

### Sprint 1 implementation checklist

- Add a new analysis module tree under `apps/desktop/vendor/backend/src/lidltool/analysis/`.
- Add broker entry points for manifest building, job workspace allocation, helper launch, and cleanup.
- Add `POST /api/v1/tools/analysis-python` to the desktop backend.
- Keep `http_tools_exec_enabled` disabled by default and stop relying on it in desktop agent flows.
- Replace desktop agent `execute_python` usage with `run_analysis_python`.
- Add build-time packaging for an `analysis-worker` resource.
- Add runtime helper lookup for packaged and dev modes.
- Add integration tests for:
  - endpoint auth
  - deterministic helper execution
  - timeout handling
  - cleanup behavior
  - tool-list migration away from `/api/v1/tools/exec`
