# Contributing

Thanks for helping improve Outlays Desktop.

## Development Setup

Run from the repo root:

```bash
npm ci
npm run frontend:install
npm run backend:prepare
npm run typecheck
npm run build
```

See [docs/development.md](docs/development.md) for the fuller workflow.

## Core Repo Rules

This repository is a standalone desktop side repo.

- Do not add runtime or build-time dependencies on `../../` paths.
- Do not import or execute code from the main repo at runtime.
- Everything required for desktop packaging must live inside this repo.
- If shared logic is needed, vendor or copy it into this repo and document the source and sync method.

If there is a tradeoff between convenience and side-repo isolation, choose isolation.

## Before Opening A PR

- run the relevant checks for your change
- run `git diff --check`
- update `README.md` or `docs/` when setup, packaging, diagnostics, privacy, release, or UX behavior changes
- keep generated diagnostics bundles, `.env` files, keys, tokens, DSNs, private URLs, and credentials out of git

Recommended checks:

```bash
npm run typecheck
npm run build
npm run test:diagnostics
npm run test:runtime-contracts
npm run test:updates
npm run test:release-preflight
```

## Vendored Code

`vendor/frontend/` and `vendor/backend/` are committed to this repo.

Only refresh them intentionally:

```bash
LIDLTOOL_UPSTREAM_REPO=/path/to/upstream-checkout npm run vendor:sync
```

After a vendor refresh:

- desktop must still build from local copied files only
- no new runtime dependency on the upstream repo is allowed
- documentation should explain any new vendored surface or sync rule

## Privacy Expectations

Diagnostics and telemetry changes must stay privacy-conservative. Personal receipt data, credentials, local databases, document storage, scraped retailer HTML, screenshots, and AI chat content must not be collected automatically.
