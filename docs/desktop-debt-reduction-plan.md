# Desktop Debt Reduction Plan

## Scope

This plan covers technical debt inside `apps/desktop` only.

Goals:
- reduce desktop fork-maintenance cost without breaking side-repo isolation
- shrink large orchestration files into smaller modules
- remove repeated render-path derivation in the control center
- replace brittle patch validation with stronger desktop-owned contracts
- keep unsafe or local-only artifacts out of mainline commits by default

Non-goals:
- re-couple desktop runtime to the main repo
- remove intentional desktop-specific product deltas
- expand desktop scope toward self-hosted/live-session behavior

## Constraints

- Runtime/build logic must stay inside `apps/desktop`.
- No new runtime imports from `../../*`.
- Desktop fallback behavior must remain intact:
  - healthy full-app boot
  - control-center fallback
  - local backup/export/restore
  - explicit receipt-pack enablement

## Newly Added Findings

These findings were added after the initial cleanup review and are now treated as phase-zero blockers.

### P1: Runtime protocol stdout corruption risk

File:
- `apps/desktop/vendor/backend/src/lidltool/connectors/runtime/runner.py`

Problem:
- Plugin stdout must not share the same stream as the runtime response envelope.
- Removing stdout redirection makes connector execution intermittently unsafe because any `print()` inside `invoke_action()` can corrupt the JSON protocol stream.

Required action:
- keep stdout reserved for protocol output
- retain regression coverage that proves plugin stdout is redirected to stderr

### P1: Deposit-aware transaction total regression

File:
- `apps/desktop/vendor/backend/src/lidltool/ingest/validation.py`

Problem:
- Candidate-total matching must continue to account for deposit lines.
- Dropping `deposit_total_cents` from the candidate total set can incorrectly flag or quarantine valid normalized receipts where the gross total legitimately includes deposits.

Required action:
- retain deposit-aware candidate totals
- keep targeted deposit validation tests green

### P3: Local QA artifact should not land by default

File:
- `apps/desktop/i18n-audit-report.md`

Problem:
- This is a dated local audit artifact tied to a specific local packaged-app run.
- It is not durable product documentation by default.

Required action:
- do not include it in default cleanup commits
- only version similar artifacts when explicitly requested
- otherwise summarize durable findings into maintained docs

## Workstreams

### Workstream 1: Safety fixes and guardrails

Tasks:
- restore runtime stdout redirection in vendored runner
- restore deposit-aware total matching in ingest validation
- verify existing regression tests still protect both behaviors
- leave `i18n-audit-report.md` out of default cleanup commits

Exit criteria:
- connector runtime protocol stays JSON-safe
- deposit-inclusive receipts do not falsely trip total mismatch warnings
- local QA artifacts are treated as opt-in repo history

### Workstream 2: Main-process file decomposition

Primary target:
- `apps/desktop/src/main/runtime.ts`

Extraction targets:
- `src/main/runtime/sync-args.ts`
- `src/main/runtime/export-args.ts`
- `src/main/runtime/desktop-paths.ts`
- `src/main/runtime/backup-artifacts.ts`
- `src/main/runtime/command-runner.ts`
- `src/main/runtime/backend-env.ts`
- `src/main/runtime/backend-invocation.ts`
- `src/main/runtime/release-context-service.ts`

Exit criteria:
- `runtime.ts` becomes an orchestrator instead of the home of every desktop concern

### Workstream 3: Plugin-pack manager decomposition

Primary target:
- `apps/desktop/src/main/plugins/receipt-plugin-packs.ts`

Extraction targets:
- `state-store.ts`
- `install-prep.ts`
- `catalog-install-policy.ts`
- `integrity-check.ts`
- `pack-paths.ts`
- `archive-json.ts`

Exit criteria:
- pack manager file is substantially smaller
- trust, integrity, storage, and install concerns are separated

### Workstream 4: Renderer control-center cleanup

Primary target:
- `apps/desktop/src/renderer/App.tsx`

Initial extraction targets:
- source-option derivation
- pack/catalog indexing
- installed-pack rows
- trusted-pack rows
- bundle-label lookup

Later extraction targets:
- `useDesktopBoot.ts`
- `useBackendActions.ts`
- `useSyncActions.ts`
- `useReceiptPackActions.ts`
- section components for overview/sync/packs/backup/logs

Exit criteria:
- `App.tsx` stops doing repeated lookup work while rendering
- data derivation is centralized in desktop-owned renderer model code

### Workstream 5: Vendor sync and patch hardening

Primary targets:
- `scripts/sync-vendor.mjs`
- `scripts/patch-vendored-frontend.mjs`
- `scripts/patch-vendored-backend.mjs`
- `scripts/validate-vendored-frontend.mjs`

Tasks:
- add a desktop vendor manifest
- make validation more contract-based and less substring-based
- document which backend/frontend patches are permanent desktop deltas vs temporary upstream gaps

Exit criteria:
- upstream drift fails loudly for structural reasons, not fragile text matches

### Workstream 6: Docs and artifact retention

Tasks:
- keep durable product/architecture docs under `apps/desktop/docs`
- review root-level report artifacts such as:
  - `qa-report.md`
  - `i18n-audit-report.md`
  - `i18n-fix-report.md`
  - `detailed.md`
  - `agent_prompt.md`
- delete or summarize one-off artifacts after their conclusions are captured elsewhere

Exit criteria:
- desktop repo history carries maintained docs instead of accumulated local task exhaust

## Execution Order

1. Safety fixes and regression verification
2. Renderer lookup/index cleanup
3. Runtime decomposition
4. Plugin-pack decomposition
5. Vendor contract hardening
6. Docs/artifact retention cleanup

## Required Checks Per Slice

- `npm run typecheck`
- `npm run build`
- targeted Node tests for touched desktop TS files
- targeted Python tests for touched vendored backend files
- targeted Playwright coverage only when a change affects cross-surface behavior

