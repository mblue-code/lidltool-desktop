# Architecture

Outlays Desktop is a local-first packaged application built from one repo.

## Runtime Overview

The app is composed of five main parts:

- Electron main process in `src/main/`
- Electron preload bridge in `src/preload/`
- React renderer shell in `src/renderer/`
- vendored Python backend in `vendor/backend/`
- on-demand OCR worker launched from the prepared backend runtime

The Electron main process owns:

- application lifecycle
- menu and shell integrations
- backend startup and shutdown
- diagnostics bundle creation
- privacy preference persistence
- update checks
- local plugin pack management
- the temporary mobile pairing bridge

## Startup Model

On the healthy path:

1. Electron starts.
2. The local backend is launched.
3. The app opens the bundled frontend experience.
4. The OCR worker stays off until OCR work is requested.

On degraded paths:

- the control center remains available when the full frontend is missing
- the control center can also expose local recovery tools when backend startup fails

## Frontend And Backend Layout

- `src/renderer/` contains the desktop-owned shell UI
- `vendor/frontend/` contains the vendored main app frontend
- `vendor/backend/` contains the vendored Python backend source
- `.backend/venv/` contains the local prepared Python runtime for development and packaging

The repo keeps desktop-specific code local and vendors shared logic explicitly instead of importing from an external parent repo.

## Packaging Model

Before packaging, `npm run build` stages local artifacts into `build/`:

- `build/frontend-dist/`
- `build/backend-src/`
- `build/backend-venv/`

`electron-builder` then packages those staged assets as local resources. The release artifact should not depend on files outside this repository.

## Data And Storage

By default, desktop state is stored under the Electron `userData` directory.

That local profile contains:

- the SQLite database
- document storage
- diagnostics logs
- privacy preferences
- imported receipt connector packs

Desktop intentionally avoids reusing shared self-hosted paths when it can keep data isolated inside the app profile.

## Trust Boundaries

The important trust boundaries are:

- local user data should remain on disk unless the user explicitly exports, backs up, or shares it
- diagnostics are opt-in and must remain privacy-conservative
- release-time endpoints such as update feeds and Sentry-compatible DSNs are injected through environment variables
- connector packs are installed into user-writable storage, not into the packaged app bundle
- vendored source refresh is a copy step only, not a runtime dependency

## Related Docs

- [development.md](development.md)
- [diagnostics.md](diagnostics.md)
- [update-flow.md](update-flow.md)
- [public-repo-boundary.md](public-repo-boundary.md)
