# Release Process

This document describes the release flow for Outlays Desktop from this repo alone.

## Versioning And Channels

- beta releases use `OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta` and a prerelease semver such as `0.2.0-beta.1`
- stable releases use `OUTLAYS_DESKTOP_RELEASE_CHANNEL=stable` and a stable semver such as `1.0.0`

Stable builds must not use prerelease versions. Beta builds must use a `-beta.N` suffix.

## Release Inputs

Required environment variables:

```bash
OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta
OUTLAYS_DESKTOP_UPDATE_BASE_URL=https://updates.example.invalid/outlays-desktop
```

Optional release-time inputs include telemetry DSNs, source-map upload credentials, and signing credentials. Those values must not be committed to the repository.

## Preflight

Run preflight before building release artifacts:

```bash
OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta \
OUTLAYS_DESKTOP_UPDATE_BASE_URL=https://updates.example.invalid/outlays-desktop \
npm run release:preflight
```

`release:preflight` checks:

- release channel and semver compatibility
- obvious secret material in staged files
- staged `.env` files or diagnostics archives
- forbidden `../../` runtime/build references
- public product identity regressions
- `npm run typecheck`

## Local Release Build

Prepare release-style artifacts from the repo root:

```bash
npm ci
npm run frontend:install
npm run backend:prepare
npm run release:preflight
npm run dist:with-backend
```

For channel shortcuts:

```bash
npm run release:beta
npm run release:stable
```

Those flows are expected to produce artifacts under `dist_electron/`.

## Source Maps

If release telemetry is enabled, upload source maps separately:

```bash
GLITCHTIP_AUTH_TOKEN=... \
GLITCHTIP_ORG=... \
GLITCHTIP_PROJECT=... \
OUTLAYS_DESKTOP_RELEASE=outlays-desktop@0.2.0-beta.1 \
npm run sourcemaps:upload
```

The upload script should fail when required inputs are missing and must not print tokens.

## Release Smoke Checks

Minimum release validation:

- launch with a fresh profile
- confirm the main app opens on the healthy path
- create a diagnostics bundle and inspect it
- confirm Help menu bug-reporting and logs-folder actions
- confirm update checks are disabled without an update URL
- confirm update checks behave correctly against a local feed
- confirm artifact retention in CI or release storage

See [../RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md) and [production-qa-checklist.md](production-qa-checklist.md) for the fuller checklist.

## Rollback Rule

- do not replace a broken release with the same version
- publish a higher version
- remove or update feed metadata to stop rollout if needed

## Current Production Blockers

- macOS production auto-updates require signed and notarized artifacts
- Windows production distribution still needs final Authenticode signing
- the public launch still needs a final `LICENSE` decision
