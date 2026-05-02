# Outlays Desktop

Outlays Desktop is a local-first Electron app for one-time receipt sync, review, export, backup, and light connector management on a single machine.

The project is being prepared for a public open-source release on GitHub and a separate commercial distribution model for paid prebuilt installers and convenience support. The source repository is intended to remain self-buildable and self-host friendly.

This project is independent and is not affiliated with Lidl, Amazon, or any other retailer.

## Status

Outlays Desktop is still pre-release software.

Current release blockers before a public production launch:

- choose and add a root `LICENSE`
- finish signed macOS and Windows release distribution
- complete clean-machine install, upgrade, and update validation on both target platforms

See [docs/publication-checklist.md](docs/publication-checklist.md) for the publication pass and [docs/signing-and-notarization.md](docs/signing-and-notarization.md) for code-signing status.

## What It Does

- Runs a bundled desktop shell with a local Python backend.
- Imports receipts from supported connectors and optional connector packs.
- Keeps receipt data, backups, and OCR processing on the local machine by default.
- Supports local export, restore, diagnostics bundle creation, and optional update checks.
- Packages frontend, backend source, and backend runtime from this repo only.

## Product Boundaries

Outlays Desktop is built for occasional local use:

- run a sync when you want it
- review and export data on the same computer
- create or restore local backups
- manage a small number of optional receipt connector packs

It is intentionally not the always-on server product:

- no long-running background sync service
- no hosted SaaS dependency
- no assumption of a separate self-hosted operator workflow
- no requirement to keep a browser automation session running continuously

## Repository Principles

This repo is intentionally isolated from the main application repo:

- no runtime or build-time `../../` dependencies
- no importing executable code from the main repo at runtime
- everything required for desktop packaging must live in this repo
- vendoring from an upstream repo is allowed only through explicit sync scripts that copy files into `vendor/`

That isolation rule matters because the same repo needs to work both as a public source release and as the basis for a paid packaged desktop product.

## Architecture

At a high level the desktop app consists of:

- Electron main process in `src/main/`
- React renderer shell in `src/renderer/`
- vendored frontend in `vendor/frontend/`
- vendored Python backend in `vendor/backend/`
- local managed backend virtualenv in `.backend/venv/`
- packaged assets staged into `build/` before `electron-builder`

For the fuller runtime overview, see [docs/architecture.md](docs/architecture.md).

## Quick Start

### Prerequisites

- Node.js 22
- npm
- Python 3.11 or 3.12
- macOS or Windows for the target packaged experience

### First-Time Setup

Run from the repo root:

```bash
npm ci
npm run frontend:install
npm run backend:prepare
npm run typecheck
npm run build
```

Start the desktop app in development mode:

```bash
npm run dev
```

Notes:

- `vendor/frontend/` and `vendor/backend/` are already committed to this repo. You do not need an external upstream checkout for normal builds.
- `npm run backend:prepare` creates the local desktop backend runtime under `.backend/venv/`.
- `npm run build` stages packaged frontend and backend assets into `build/` and compiles the Electron app into `out/`.

## Common Commands

```bash
npm run dev
npm run build
npm run dist:mac
npm run dist:win
npm run typecheck
npm run test:diagnostics
npm run test:runtime-contracts
npm run test:updates
npm run test:release-preflight
```

Additional release and QA flows are documented in [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), [docs/release-process.md](docs/release-process.md), and [docs/production-qa-checklist.md](docs/production-qa-checklist.md).

## Refreshing Vendored Code

Refreshing `vendor/frontend/` or `vendor/backend/` from the upstream app is optional and should only be done intentionally.

```bash
LIDLTOOL_UPSTREAM_REPO=/path/to/upstream-checkout npm run vendor:sync
```

That flow copies files into this repo. The desktop app must continue to build from the local vendored copies after sync.

## Packaging

Local packaging commands:

```bash
npm run dist:mac
npm run dist:win
npm run dist:with-backend
```

Release builds should also run:

```bash
OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta \
OUTLAYS_DESKTOP_UPDATE_BASE_URL=https://updates.example.invalid/outlays-desktop \
npm run release:preflight
```

Current packaging notes:

- unsigned local builds are supported
- signed production builds are not fully finalized yet
- update feeds are configured at release time, not committed into the repo

See [docs/release-process.md](docs/release-process.md), [docs/update-flow.md](docs/update-flow.md), and [docs/signing-and-notarization.md](docs/signing-and-notarization.md).

## Privacy And Diagnostics

Outlays Desktop is local-first:

- receipt data, exports, backups, documents, and retailer sessions stay on the local machine unless you explicitly move them elsewhere
- automatic error reporting is off by default
- diagnostics bundles are created locally and intentionally redacted

See [PRIVACY.md](PRIVACY.md), [docs/diagnostics.md](docs/diagnostics.md), and [docs/public-repo-boundary.md](docs/public-repo-boundary.md).

## Documentation Map

- [docs/README.md](docs/README.md): documentation index
- [docs/development.md](docs/development.md): local development and build workflows
- [docs/architecture.md](docs/architecture.md): runtime and packaging architecture
- [CONTRIBUTING.md](CONTRIBUTING.md): contribution rules
- [SECURITY.md](SECURITY.md): security reporting guidance
- [docs/publication-checklist.md](docs/publication-checklist.md): open-source publication and commercial release readiness checklist

## Contributing

Contributions should preserve desktop-side isolation and keep public-facing docs aligned with behavior. Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## License

A final open-source license has not been added yet. This must be resolved before the public GitHub launch.
