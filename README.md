# LidlTool Desktop (Electron)

Desktop host for the full self-hosted LidlTool experience, including connector/scraper flows.

## What this app does

- Starts local backend (`lidltool serve`) from Electron
- Opens the real full app UI (the same frontend used in self-host mode)
- Keeps fallback control center UI if backend boot fails
- Supports one-off sync command execution directly from fallback control center
- Supports one-off backup import/restore from fallback control center
- Supports one-off local backup bundle creation from full app settings and fallback control center
- Supports one-off backup import/restore from full app settings and setup page
- Supports one-off JSON data export execution directly from fallback control center

## Runtime model

- Preferred backend executable order:
  1. `LIDLTOOL_EXECUTABLE` env override
  2. bundled backend venv inside packaged app (`resources/backend-venv/...`)
  3. local managed backend venv (`apps/desktop/.backend/venv/...`)
  4. system PATH (`lidltool` / `lidltool.exe`)
- Frontend assets for packaged builds are copied to `resources/frontend-dist`.
- Vendored backend source is copied to `resources/backend-src`.
- Backend receives:
  - `LIDLTOOL_FRONTEND_DIST` (so FastAPI serves packaged frontend)
  - `LIDLTOOL_REPO_ROOT` (cwd hint for connector subprocess usage)
  - `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY` (desktop auto-provisions and persists one in app user data)
  - `PLAYWRIGHT_BROWSERS_PATH=0` for bundled/managed venv backends (ensures packaged Chromium is used)

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

## Exact release workflow

Run from `apps/desktop` on the target OS you are releasing for.

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
