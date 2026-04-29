# Production Hardening

This plan turns Outlays from a beta-capable Electron app into a production-ready desktop product. It intentionally excludes final code-signing and trust setup for now because the macOS Developer ID certificate is not available yet. Signing and notarization must be added before public production release, but the rest of the update, release, diagnostics, privacy, QA, and support infrastructure can be implemented now.

## Goals

- Ship beta and production desktop releases that can update themselves.
- Keep release artifacts reproducible from this side repo only.
- Keep telemetry and diagnostics transparent, opt-in/configurable, and privacy-conservative.
- Make production support practical with GitHub Issues, diagnostics bundles, GlitchTip-compatible error reporting, and clear release metadata.
- Add CI/release workflows that build, validate, and publish artifacts without committing secrets.
- Document the release, update, privacy, and security surfaces clearly enough for public open-source users.

## Non-Goals For This Pass

- Final macOS Developer ID signing.
- Final macOS notarization activation.
- Final Windows Authenticode signing.
- Store distribution.
- Auto-update enforcement for unsigned builds.
- Paid crash-reporting SaaS lock-in.

Code-signing placeholders, docs, and environment-variable names may be added, but real certificates, signing identities, notarization credentials, and release-trust decisions are deferred.

## Current Baseline

Already present:

- Electron/Vite desktop app.
- `electron-builder` packaging scripts.
- macOS notarization hook placeholder via `scripts/notarize.mjs`.
- `dist`, `dist:mac`, `dist:win`, and `dist:full` scripts.
- Local-first desktop docs and QA docs.
- Optional Sentry-compatible diagnostics wiring for self-hosted GlitchTip.
- GitHub issue templates.
- Redacted diagnostics bundle export.

Missing or incomplete:

- Auto-update dependency and runtime update manager.
- Update feed configuration.
- Beta/stable channel policy.
- Update UI and IPC.
- Release pipeline docs/scripts.
- Source map upload flow.
- Public `SECURITY.md`, `PRIVACY.md`, `CONTRIBUTING.md`.
- Production QA checklist for update/install/upgrade.
- Secret scanning/release preflight.
- In-app telemetry/privacy controls.
- Open logs folder action.

## Phase 1: Update Strategy

### Decision

Use `electron-updater` with `electron-builder`.

Initial provider should be configurable:

- `generic` HTTPS feed on your VPS for self-hostable control.
- GitHub Releases can be supported later or as an alternate provider.

Recommended first implementation:

- Add generic provider support.
- Configure update URLs via environment variables at build/release time.
- Keep update checks disabled by default in dev.
- Allow manual update checks in dev when explicitly configured.

### Channels

Use two channels:

- `beta`
- `stable`

Optional later:

- `internal`
- `nightly`

Channel behavior:

- Beta builds check beta feed only.
- Stable builds check stable feed only.
- Stable users should not receive beta updates.
- Beta users can later be migrated to stable manually or by publishing a stable build to the beta channel with a migration note.

### Update Feed Layout

For generic HTTPS hosting:

```text
https://updates.example.com/outlays-desktop/
  beta/
    latest-mac.yml
    latest.yml
    Outlays-0.2.0-beta.1-arm64.dmg
    Outlays Setup 0.2.0-beta.1.exe
  stable/
    latest-mac.yml
    latest.yml
    Outlays-1.0.0-arm64.dmg
    Outlays Setup 1.0.0.exe
```

Keep each channel isolated.

### Update Metadata

`electron-builder` generates:

- `latest.yml` for Windows.
- `latest-mac.yml` for macOS.

macOS auto-updates require signed apps for production. Until signing exists, implement and test update logic with local/generic feeds, but treat production macOS auto-update as blocked by signing.

## Phase 2: Dependencies And Build Config

### Add Dependency

```bash
npm install electron-updater
```

### Add Build Config

Update `package.json` `build` config:

```json
{
  "build": {
    "publish": [
      {
        "provider": "generic",
        "url": "${env.OUTLAYS_DESKTOP_UPDATE_BASE_URL}"
      }
    ],
    "generateUpdatesFilesForAllChannels": true
  }
}
```

Because JSON config in `package.json` may not interpolate env the way we want, prefer one of these:

1. Move electron-builder config to `electron-builder.config.cjs`.
2. Keep `package.json` config and pass `--config.publish.url=...`.
3. Generate a local ignored builder config during release.

Recommended: move to `electron-builder.config.cjs` so update configuration can be computed safely from env while keeping all paths local to this repo.

### Required Env Vars

```bash
OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta
OUTLAYS_DESKTOP_UPDATE_BASE_URL=https://updates.example.com/outlays-desktop/beta
```

Optional:

```bash
OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES=1
OUTLAYS_DESKTOP_UPDATE_AUTO_CHECK=1
```

Do not commit live update URLs if they expose private infrastructure.

## Phase 3: Runtime Update Manager

### Files

Add:

```text
src/main/updates/update-config.ts
src/main/updates/update-manager.ts
tests/update-config.test.ts
```

### Shared Contracts

Extend `src/shared/contracts.ts`:

```ts
export type DesktopUpdateChannel = "development" | "internal" | "beta" | "stable";
export type DesktopUpdateStatus =
  | "disabled"
  | "idle"
  | "checking"
  | "available"
  | "not_available"
  | "downloading"
  | "downloaded"
  | "error";

export interface DesktopUpdateState {
  enabled: boolean;
  channel: DesktopUpdateChannel;
  status: DesktopUpdateStatus;
  currentVersion: string;
  availableVersion: string | null;
  updateBaseUrl: string | null;
  downloaded: boolean;
  error: string | null;
  lastCheckedAt: string | null;
  downloadProgress: {
    percent: number;
    transferred: number;
    total: number;
    bytesPerSecond: number;
  } | null;
}
```

### Config Logic

Rules:

- Updates disabled in dev unless `OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES=1`.
- Updates disabled if no update base URL is configured.
- Production/stable builds use stable channel.
- Beta builds use beta channel.
- Never silently switch channels.

Pseudo:

```ts
enabled =
  Boolean(updateBaseUrl) &&
  (app.isPackaged || env.OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES === "1");
```

### Update Manager Responsibilities

`DesktopUpdateManager` should:

- Initialize `autoUpdater` when enabled.
- Set `autoDownload = false` initially.
- Expose current state.
- Handle manual check.
- Handle download.
- Handle install/restart.
- Broadcast update-state changes to renderer.
- Log lifecycle events to existing diagnostics log pattern.
- Capture update errors in optional GlitchTip telemetry with sanitized details.

### Main IPC

Add IPC handlers:

```text
desktop:updates:state
desktop:updates:check
desktop:updates:download
desktop:updates:install
```

Add renderer event:

```text
desktop:updates:state-changed
```

### Preload API

Expose:

```ts
getUpdateState(): Promise<DesktopUpdateState>
checkForUpdates(): Promise<DesktopUpdateState>
downloadUpdate(): Promise<DesktopUpdateState>
installUpdate(): Promise<void>
onUpdateStateChanged(handler): () => void
```

## Phase 4: Update UI

### Control Center

Add an `Updates` card to the control center.

Content:

- Current version.
- Channel.
- Update status.
- Last checked time.
- Available version if present.
- Progress when downloading.
- Error message if failed.

Actions:

- `Check for updates`
- `Download update`
- `Restart to update`

Button behavior:

- `Check for updates`: enabled when idle/not_available/error.
- `Download update`: enabled when available.
- `Restart to update`: enabled when downloaded.

Do not auto-download in the first implementation. Manual flow is easier to validate and safer for beta.

### Menu

Add:

```text
Help -> Check for Updates
Help -> Report a Problem
Help -> Create Diagnostics Bundle
Help -> Open Logs Folder
Help -> Documentation
```

Current menu has app-level actions; either add a Help menu or place these under Application temporarily. Prefer adding a proper Help menu.

### Notifications

For first implementation:

- No OS notifications.
- In-app status only.

Optional later:

- Show a dialog when update is downloaded.

## Phase 5: Open Logs Folder

Add diagnostics helper:

```text
desktop:diagnostics:open-logs-folder
```

Implementation:

- Open Electron `userData` directory or a dedicated logs directory.
- Use `shell.openPath`.
- Keep this action separate from diagnostics bundle export.

Renderer:

- Add button in Diagnostics card.

Menu:

- Add Help -> Open Logs Folder.

## Phase 6: Privacy And Telemetry Controls

### Persistent Preference

Add:

```text
src/main/diagnostics/privacy-preferences.ts
```

Stored in Electron `userData`:

```json
{
  "errorReportingEnabled": false,
  "diagnosticLogSharingEnabled": false
}
```

Policy:

- Default off unless beta release policy explicitly sets default on.
- If default-on beta is chosen, first launch must disclose it.
- Production should provide a visible toggle.

### IPC

```text
desktop:privacy:get
desktop:privacy:set
```

### UI

Add Diagnostics/Privacy controls:

- Error reporting enabled/disabled.
- “What is sent?” summary.
- Create diagnostics bundle.
- Open bug report.
- Open logs folder.

### Important Technical Constraint

Sentry/Electron initialization happens early. Runtime toggles should:

- Control whether future events are sent.
- Avoid sending anything before consent if production policy requires opt-in.

Simplest implementation:

- Keep SDK uninitialized unless env and preference allow it.
- For beta env-enabled builds, initialize only after reading stored preference if feasible.
- If early crash capture is needed, document that beta builds use config-level enablement.

## Phase 7: Source Maps

### Goal

Readable production stack traces in GlitchTip/Sentry-compatible tooling.

### Build Changes

Enable source map generation for:

- main
- preload
- renderer

Prefer hidden source maps where supported.

In `electron.vite.config.ts`:

```ts
build: {
  sourcemap: true
}
```

Do not ship source maps publicly unless explicitly intended.

### Upload Script

Add:

```text
scripts/upload-sourcemaps.mjs
```

Inputs:

```bash
GLITCHTIP_AUTH_TOKEN=...
GLITCHTIP_ORG=...
GLITCHTIP_PROJECT=...
OUTLAYS_DESKTOP_RELEASE=outlays-desktop@0.2.0-beta.1
```

Possible approaches:

- Use `sentry-cli` pointed at GlitchTip if compatible.
- Use GlitchTip CLI if project workflow supports it.

Script behavior:

- Fail if required env vars are missing.
- Upload `out/**/*.map`.
- Upload vendored frontend maps if generated.
- Associate maps with release.
- Never print tokens.

Add docs for manual and CI usage.

## Phase 8: Release Scripts

Add scripts:

```json
{
  "release:preflight": "node ./scripts/release-preflight.mjs",
  "release:beta": "npm run release:preflight && npm run dist:full",
  "release:stable": "npm run release:preflight && npm run dist:full",
  "updates:serve-local": "node ./scripts/serve-update-feed.mjs"
}
```

### `scripts/release-preflight.mjs`

Check:

- `npm run typecheck`.
- No `../../` runtime/build references introduced.
- Required env vars for selected release channel.
- Package version is valid.
- `OUTLAYS_DESKTOP_RELEASE_CHANNEL` matches version suffix.
- No `.env` files staged.
- No diagnostics zips staged.
- No private key material staged.
- Git working tree status is visible to operator.

Do not make this script destructive.

### Local Update Feed Test Script

Add:

```text
scripts/serve-update-feed.mjs
```

Behavior:

- Serve a local directory over HTTP.
- Print URL.
- Useful for manually testing update checks.

No external dependency needed; use Node HTTP server.

## Phase 9: GitHub Actions

Add workflows:

```text
.github/workflows/ci.yml
.github/workflows/release-draft.yml
```

### CI

Run on PR/push:

- `npm ci`
- `npm run typecheck`
- `npm run test:diagnostics`
- `npm run test:runtime-contracts`
- optional `npm run build`

### Draft Release

Manual dispatch:

Inputs:

- version
- channel
- upload_artifacts boolean

Jobs:

- validate repo boundary
- build artifacts
- upload artifacts as workflow artifacts
- optionally create draft GitHub release

Do not include signing yet. Leave signing steps as documented TODOs gated by secrets.

## Phase 10: Public Repo Docs

Add or update:

```text
SECURITY.md
PRIVACY.md
CONTRIBUTING.md
docs/update-flow.md
docs/release-process.md
docs/production-qa-checklist.md
docs/signing-and-notarization.md
```

### `SECURITY.md`

Include:

- Private vulnerability reporting path.
- What counts as sensitive: credentials, retailer session tokens, receipts, local DB, LAN pairing.
- Do not file public issues with secrets.

### `PRIVACY.md`

Include:

- Local-first data model.
- What stays local.
- What automatic diagnostics can send when enabled.
- What diagnostics bundles include/exclude.
- How to disable reporting.

### `CONTRIBUTING.md`

Include:

- setup
- checks
- side-repo isolation rule
- diagnostics boundary
- PR checklist

### `docs/update-flow.md`

Include:

- provider choice
- channel policy
- env vars
- local update testing
- production signing blocker
- rollback rules

Rollback rule:

- Do not replace a broken release with the same version.
- Publish a higher version.
- Pull or edit update metadata to stop rollout if needed.

### `docs/release-process.md`

Include:

- beta release steps
- stable release steps
- source map upload
- diagnostics smoke test
- update smoke test
- artifact retention

### `docs/production-qa-checklist.md`

Include:

- fresh install
- upgrade from previous version
- update available
- update download
- update install/restart
- update failure behavior
- diagnostics bundle
- report issue
- open logs
- backup/export/restore
- connector install/update
- Windows install/uninstall
- macOS app launch

### `docs/signing-and-notarization.md`

Include placeholders:

- macOS Developer ID requirements.
- Apple notary credentials.
- Windows certificate requirements.
- CI secret names.
- Current status: deferred.

## Phase 11: Tests

Add tests:

```text
tests/update-config.test.ts
tests/release-preflight.test.ts
```

Test update config:

- no URL disables updates
- dev disables updates unless override
- beta channel resolves beta
- production/stable resolves stable
- invalid channel falls back safely

Test preflight helpers:

- detects `.env` staged path
- detects diagnostics zip staged path
- detects private key pattern
- validates version/channel relationship

If testing staged files directly is awkward, keep pure helper functions in `scripts/lib/release-preflight.mjs` and test those.

## Phase 12: Implementation Order

1. Add `electron-updater`.
2. Extract electron-builder config if needed.
3. Add shared update contracts.
4. Add update config resolver and tests.
5. Add update manager.
6. Wire update manager into `src/main/index.ts`.
7. Add IPC and preload APIs.
8. Add renderer update state hook.
9. Add Updates card.
10. Add Help menu actions.
11. Add Open Logs Folder action.
12. Add privacy preference storage and UI.
13. Add source map generation and upload script.
14. Add release preflight script and tests.
15. Add CI workflow.
16. Add release workflow draft.
17. Add production docs.
18. Run verification.

## Verification Commands

Run:

```bash
npm run test:diagnostics
npm run test:runtime-contracts
npm run typecheck
npm run build
```

If update config/preflight tests are added:

```bash
npm run test:updates
npm run test:release-preflight
```

Manual QA:

1. Launch app without update URL and confirm update status is disabled.
2. Launch app with local update URL and `OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES=1`.
3. Click Check for Updates.
4. Confirm unavailable state against empty feed.
5. Serve a valid generated feed.
6. Confirm update available state.
7. Confirm diagnostics bundle still exports.
8. Confirm bug report still opens.
9. Confirm logs folder opens.

## Production Blockers Remaining After This Plan

- macOS Developer ID signing.
- macOS notarization with real credentials.
- Windows Authenticode certificate.
- Signed update smoke tests.
- Final public privacy/legal review.
- Real VPS update feed hardening and backups.

## Agent Orchestration Prompt

Use the following prompt for an implementation agent:

```text
You are working in /path/to/outlays-desktop.

Implement the full Production Hardening plan in docs/production-hardening.md, with one explicit exclusion: do not implement final macOS Developer ID signing, notarization secrets, Windows Authenticode signing, or any real certificate/trust credentials. You may add placeholder docs, env var names, and TODO-gated workflow steps for signing, but do not add real secrets or require signing to pass local verification.

Hard constraints:
- Preserve side-repo isolation. Do not add runtime/build-time dependencies on ../../ paths.
- Do not import or execute code from the main repo at runtime.
- Everything needed by desktop runtime must live inside this repo.
- Do not commit or hardcode real DSNs, auth tokens, VPS URLs, credentials, signing identities, source-map tokens, or generated diagnostics bundles.
- Keep telemetry/update endpoints configurable through env/release configuration.
- Do not make destructive git operations.
- Work with any existing dirty tree changes; do not revert unrelated user work.

Primary deliverables:
1. Add electron-updater-based update infrastructure.
2. Add update config resolution and tests.
3. Add main-process update manager.
4. Add IPC/preload contracts for update state/check/download/install.
5. Add renderer update card and state handling.
6. Add Help menu actions:
   - Check for Updates
   - Report a Problem
   - Create Diagnostics Bundle
   - Open Logs Folder
   - Documentation
7. Add Open Logs Folder diagnostics action.
8. Add privacy/telemetry preference storage and UI.
9. Add source map generation/upload script with env-token handling and no secret printing.
10. Add release preflight script and tests.
11. Add CI workflow and draft release workflow without real signing.
12. Add or update SECURITY.md, PRIVACY.md, CONTRIBUTING.md, docs/update-flow.md, docs/release-process.md, docs/production-qa-checklist.md, and docs/signing-and-notarization.md.
13. Keep README and docs/public-repo-boundary.md aligned with the new production hardening behavior.

Implementation guidance:
- Prefer existing repo patterns in src/main/ipc.ts, src/preload/index.ts, src/shared/contracts.ts, and the control-center state/action hooks.
- Keep update checks disabled in dev unless OUTLAYS_DESKTOP_ALLOW_DEV_UPDATES=1.
- Disable updates when no update base URL is configured.
- Use channels beta and stable.
- Manual update flow first: check, download, restart. Do not auto-download by default.
- Update manager should broadcast desktop:updates:state-changed.
- Update errors should be sanitized and captured by existing optional diagnostics telemetry when enabled.
- Diagnostics bundles must continue excluding personal data.
- Source map upload script must fail clearly when required env vars are missing and must never print tokens.
- Release preflight must catch staged .env files, diagnostics zips, private key material, obvious secret patterns, invalid release channel/version combinations, and new ../../ runtime/build references.

Verification:
- npm run test:diagnostics
- npm run test:runtime-contracts
- npm run typecheck
- npm run build
- Add and run npm scripts for update config and release preflight tests.
- Run git diff --check.

Final response:
- Summarize implemented files and behavior.
- List verification commands and results.
- Clearly state that final signing/notarization remains intentionally deferred.
```

