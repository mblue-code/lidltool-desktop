# Development

This repo is designed to build as a standalone desktop side repo.

## Prerequisites

- Node.js 22
- npm
- Python 3.11 or 3.12

Target release platforms are macOS and Windows. Linux can still be useful for CI and static checks, but it is not the primary packaged distribution target.

## First-Time Setup

Run from the repo root:

```bash
npm ci
npm run frontend:install
npm run backend:prepare
npm run typecheck
npm run build
```

Start the app:

```bash
npm run dev
```

## Common Workflows

### Build The Desktop App

```bash
npm run build
```

This builds the Electron sources and stages packaged assets into `build/`.

### Prepare Packaged Backend Assets

```bash
npm run backend:prepare
```

This creates `.backend/venv/` using a supported Python interpreter and installs the vendored backend plus the local OCR dependency stack.

### Run Key Checks

```bash
npm run typecheck
npm run test:diagnostics
npm run test:runtime-contracts
npm run test:updates
npm run test:release-preflight
```

### Package Local Artifacts

```bash
npm run dist:mac
npm run dist:win
npm run dist:with-backend
```

Use `dist:with-backend` when you want a release-style artifact that explicitly includes the prepared backend runtime.

## Vendored Source Policy

`vendor/frontend/` and `vendor/backend/` are committed to this repo so normal development does not depend on an external checkout.

Only refresh vendored code intentionally:

```bash
LIDLTOOL_UPSTREAM_REPO=/path/to/upstream-checkout npm run vendor:sync
```

After sync:

- desktop must still build using local vendored files only
- no runtime code may reference the upstream repo
- docs should be updated if the vendored surface or sync method changes

## Isolation Rules

When changing desktop code:

- do not add runtime or build-time `../../` references
- do not execute code from outside this repo at runtime
- keep packaging config scoped to files inside this repo
- prefer copying shared logic into `vendor/`, `scripts/`, or local desktop source when reuse is necessary

## Troubleshooting

If the frontend build fails because vendored dependencies are missing:

```bash
npm run frontend:install
```

If the packaged backend runtime is missing:

```bash
npm run backend:prepare
```

If you intentionally need to refresh vendored code first:

```bash
LIDLTOOL_UPSTREAM_REPO=/path/to/upstream-checkout npm run vendor:sync
```
