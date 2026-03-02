# AGENTS.md (Desktop Side Repo Rules)

## Product Intent
- Keep the main app open-source and self-host friendly for homelab/self-hoster users.
- Build `apps/desktop` as a one-click installable product for macOS and Windows users.
- Desktop supports one-time retailer scrape/sync workflows (not long-running live sessions).
- Desktop must still provide strong local analysis of personal data, including manual workflows and AI-assisted workflows.
- Expect intentional code forking from main repo: desktop can diverge in UX/runtime/packaging as needed.

## Goal
`apps/desktop` must behave like a standalone side repo that can be built, packaged, and run without depending on files outside `apps/desktop`.

## Hard Constraints
- Do not add runtime/build-time dependencies on `../../*` paths.
- Do not import or execute code from the main repo at runtime.
- Everything needed by desktop app runtime must live inside `apps/desktop` (code, assets, scripts, config, bundled backend/frontend artifacts).
- Packaging config must only reference paths inside `apps/desktop`.

## Allowed Exception
- A dedicated sync/vendor script may read from the main repo **only to copy/update** files into `apps/desktop`.
- After sync, desktop builds must run from local copied files only.

## Required Practices
- Keep all desktop-specific docs in `apps/desktop/README.md`.
- When adding shared logic from main repo, copy/vendor it under `apps/desktop` and document source + sync method.
- Prefer explicit local directories such as:
  - `apps/desktop/vendor/frontend`
  - `apps/desktop/vendor/backend`
  - `apps/desktop/scripts`
  - `apps/desktop/build`

## Change Checklist (for every PR touching desktop)
1. Verify no new `../..` references in desktop runtime/build scripts.
2. Run desktop checks from `apps/desktop`:
   - `npm run typecheck`
   - `npm run build`
3. If full bundle is intended, ensure bundled frontend/backend artifacts are produced from local desktop paths.
4. Update `apps/desktop/README.md` for any workflow or packaging changes.

## Decision Rule
If there is a tradeoff between speed and side-repo isolation, choose isolation.
