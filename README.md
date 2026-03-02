# LidlTool Desktop (Electron)

Desktop host for the full self-hosted LidlTool experience, including connector/scraper flows.

## What this app does

- Starts local backend (`lidltool serve`) from Electron
- Opens the real full app UI (the same frontend used in self-host mode)
- Keeps fallback control center UI if backend boot fails
- Supports one-off sync command execution directly from fallback control center

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

After every sync/build, desktop applies a local vendored frontend compatibility patch:
- `scripts/patch-vendored-frontend.mjs`
- Injects a Vite alias for `@mariozechner/pi-ai` -> `src/shims/pi-ai.ts`
- Prevents browser Rollup failures caused by Node-only Smithy/stream imports

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
