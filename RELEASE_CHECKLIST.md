# Desktop Release Checklist

Run all commands from `apps/desktop`.

## 1. Build pipeline

- [ ] `npm install`
  - Expected: installs desktop dependencies successfully.
- [ ] `npm run vendor:sync`
  - Expected: logs `Vendored frontend -> .../apps/desktop/vendor/frontend` and `Vendored backend -> .../apps/desktop/vendor/backend`.
  - Expected: logs `Patched vendored frontend Vite config with browser shim alias for @mariozechner/pi-ai.`
- [ ] `npm run frontend:install`
  - Expected: completes successfully (warnings are acceptable).
- [ ] `npm run frontend:build`
  - Expected: `vite build` completes and writes `vendor/frontend/dist`.
- [ ] `npm run backend:prepare`
  - Expected: logs `Prepared desktop backend runtime at .../apps/desktop/.backend/venv`.
  - Expected: Chromium exists under `.backend/venv/lib/python*/site-packages/playwright/driver/package/.local-browsers/chromium-*`.
- [ ] `npm run typecheck`
  - Expected: `tsc --noEmit` exits 0.
- [ ] `npm run build`
  - Expected: `Synced frontend assets`, `Synced backend source`, `Synced backend runtime`.
- [ ] `npm run dist:full`
  - Expected: packaged outputs in `dist_electron/` (`.dmg/.zip` on macOS, `.exe/.zip` on Windows).

## 2. Packaged resource inclusion

- [ ] Verify packaged resource directories exist:
  - `frontend-dist`
  - `backend-src`
  - `backend-venv`
- [ ] Verify key files:
  - `frontend-dist/index.html`
  - `backend-src/pyproject.toml`
  - `backend-venv/bin/lidltool` (macOS/Linux) or `backend-venv/Scripts/lidltool.exe` (Windows)
- [ ] Verify Playwright browser payload in package:
  - `backend-venv/lib/python*/site-packages/playwright/driver/package/.local-browsers/chromium-*`

## 3. Boot-flow validation

- [ ] Success path: launch packaged app normally.
  - Expected: backend auto-starts and full app UI opens directly.
  - Fresh install restore path: on `/setup`, run **Restore backup and sign in**, then sign in with restored user.
  - Expected: restored DB/user data is usable immediately in full UI after restore.
  - Verify full app backup flow: navigate to `System -> Users`, run **Create backup bundle**, and confirm result payload includes output directory + manifest path.
  - Verify full app restore flow: navigate to `System -> Users`, run **Restore backup bundle**, and confirm result payload indicates restore success.
  - Verify unsupported desktop URLs redirect safely: open `/offers`, `/automations`, `/automation-inbox`, and `/reliability` directly.
  - Expected: each request lands on `/` with desktop handoff messaging instead of rendering the unsupported page.
- [ ] Failure fallback path: launch with bad executable override, e.g.:
  - macOS/Linux: `LIDLTOOL_EXECUTABLE=/does/not/exist <launch app>`
  - Windows (PowerShell): `$env:LIDLTOOL_EXECUTABLE='C:\\does\\not\\exist.exe'; <launch app>`
  - Expected: fallback control center appears and shows boot error.
- [ ] From fallback control center:
  - Start backend.
  - Open full app.
  - Run one one-time sync action (for example, Lidl or Amazon).
  - Run one backup bundle action.
  - Run one backup restore action.
  - Run one data export action (optional quick check).
  - Expected: command logs stream in UI and command result shows exit status/output.

## 4. Final release outputs

- [ ] Attach/ship only artifacts from `dist_electron/`.
- [ ] Note that code signing/notarization is not configured in this scaffold.
