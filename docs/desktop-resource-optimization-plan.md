# Desktop Resource Optimization Plan

## Implementation Status (2026-04-16)

Implemented in `apps/desktop`:

- desktop now launches into the control center first instead of eagerly booting the full app
- Python backend stays off at idle until the user explicitly opens the main app or starts the local service
- desktop backend startup now runs in explicit desktop-minimal mode and skips the automation scheduler plus connector live-sync background thread
- control-center and startup E2E coverage was updated for the shell-first model
- a reusable macOS-focused profiling harness now lives at `apps/desktop/scripts/profile-desktop.mjs`
- renderer idle work was reduced by pausing AI OAuth polling when hidden and by backing off shell sync-status polling when nothing is running
- browser-based sync/auth flows replaced several fixed sleeps with event-based waits and tightened browser/context cleanup
- Python CLI startup/import cost was reduced by deferring heavyweight connector/runtime imports until the relevant commands are actually used

Measured highlights from this implementation pass:

- previous eager-full-app baseline from the pre-change desktop shell: about `514.5 MB` total RSS, `6` resident processes, and a resident Python backend at about `146.2 MB` RSS
- current idle control center via the new profiler: about `364.8 MB` total RSS, about `322.4 MB` total physical footprint, `5` resident processes, backend off, and idle CPU/power effectively `0`
- current idle full app via the new profiler after a longer settle window: about `594.6 MB` total RSS, about `423.6 MB` total physical footprint, `6` resident processes, and settled CPU about `0.1%`
- current CLI startup: `python -m lidltool.cli --help` improved from about `4.14s` wall time to about `1.96s`; `import lidltool.cli` cumulative import time dropped from about `2.79s` to about `1.28s`

Current caveat:

- the largest measured win is the empty-state/control-center-first path, which was the primary objective
- full-app idle CPU is near-idle after settling, but full-app RSS did not show a comparable memory win in this pass and remains a follow-up target

## Scope

This plan covers resource optimization for `apps/desktop`, with emphasis on:

- lower idle RAM usage
- lower idle and background CPU usage
- lower energy impact on customer laptops
- faster wake-up into meaningful work
- predictable peak usage during sync, export, backup, and restore

The desktop app is an occasional-use Electron product. The optimization target is not "always-on server behavior on a laptop." The target is a responsive local shell that stays cheap when idle and only pays heavy costs when the user explicitly enters a full app or sync workflow.

## Current Baseline

Measured on macOS in the empty-state idle condition:

- Total physical footprint: about `376.6 MB`
- Python sidecar: about `137.3 MB`
- Electron GPU helper: about `140.4 MB`
- Electron main process: about `46.8 MB`
- Electron renderer: about `39.1 MB`
- Electron network utility: about `13.0 MB`
- Idle CPU: effectively `0%`
- macOS `POWER` metric: effectively `0.0`

Interpretation:

- idle memory is the main problem
- idle CPU and energy are already acceptable in the empty state
- the current optimization priority is to remove unnecessary resident processes and startup work

## Product Goal

Optimize for three distinct desktop states instead of one blended average:

1. Idle control center
2. Idle full app
3. Active sync or import/export job

These states have different tradeoffs and should be measured and optimized separately.

## Success Criteria

Initial target budgets:

- Idle control center: under `220 MB` total physical footprint
- Idle full app: under `300 MB` total physical footprint
- Idle foreground CPU after settling: near `0%`
- Idle background CPU after settling: near `0%`
- No background pollers or schedulers active in desktop idle mode unless the user explicitly started work
- No sync job leaves browser, helper, or Python subprocesses behind after completion
- Cold launch to control center remains fast enough to feel instant for normal users

## Metrics To Track

For every optimization phase, track:

- total physical footprint
- per-process physical footprint
- RSS
- `%CPU`
- macOS `POWER`
- app launch time
- time to first interactive paint
- time to open full app
- time to start sync
- peak memory during sync
- peak CPU during sync
- whether background activity continues after the workflow ends

## Phase 0: Establish A Repeatable Measurement Harness

### Goal

Create a stable measurement workflow so every optimization attempt can be validated against the same scenarios.

### Work

- Add a desktop profiling script under `apps/desktop/scripts`.
- Record the full desktop process tree, not just one PID.
- Capture measurements every `1-2` seconds.
- Store raw results as JSON and summarize them in Markdown.
- Record both steady-state and peak values.

### Scenarios To Measure

- cold launch to control center
- cold launch to full app
- login or setup path
- `5` minutes idle in foreground
- `5` minutes idle in background
- one sync per connector family
- export
- backup
- restore
- quit

### Tools

- `ps`
- `top`
- `vmmap`
- Activity Monitor
- Instruments Time Profiler
- Instruments Energy Log
- Instruments Allocations

### Deliverables

- `apps/desktop/scripts/profile-desktop-resources.*`
- a documented measurement procedure in `apps/desktop/README.md`
- baseline JSON snapshots committed or stored in an agreed artifact path

## Phase 1: Stop Eagerly Booting The Full App

### Goal

Make the cheapest desktop surface the default launch target.

### Current Behavior

The current Electron main process eagerly enters the full app path:

- [`createWindow()`](/Users/max/projekte/lidltool/apps/desktop/src/main/index.ts:83)
- [`bootIntoFullApp()`](/Users/max/projekte/lidltool/apps/desktop/src/main/index.ts:32)
- [`runtime.startBackend()`](/Users/max/projekte/lidltool/apps/desktop/src/main/index.ts:43)

This means a user looking at an empty app still pays for a resident Python server and the full browser-backed app path.

### Change

- Launch into the control center first.
- Do not start the Python backend during initial app startup.
- Keep the "Open main app" action as the explicit transition into the full app.
- Keep "Start local service" as an explicit advanced action in the shell.

### Why It Is Safe

The architecture already supports lazy backend startup:

- [`desktop:backend:start`](/Users/max/projekte/lidltool/apps/desktop/src/main/ipc.ts:27)
- [`desktop:backend:stop`](/Users/max/projekte/lidltool/apps/desktop/src/main/ipc.ts:28)
- [`desktop:app:url`](/Users/max/projekte/lidltool/apps/desktop/src/main/ipc.ts:29)

The current control center also already presents backend state and actions:

- [`handleStartBackend()`](/Users/max/projekte/lidltool/apps/desktop/src/renderer/App.tsx:402)
- [`handleStopBackend()`](/Users/max/projekte/lidltool/apps/desktop/src/renderer/App.tsx:415)
- [`handleOpenFullApp()`](/Users/max/projekte/lidltool/apps/desktop/src/renderer/App.tsx:487)

### Expected Win

- remove the always-on Python sidecar from idle
- cut roughly `137 MB` from idle physical footprint immediately
- remove backend startup work from the default launch path

### Risks

- current desktop tests assume eager full-app boot
- product messaging must clearly explain that desktop starts in a lightweight shell

### Validation

- update E2E tests that assume direct full-app startup
- measure cold launch idle before and after
- confirm backup, export, sync, and plugin management still work from the control center

## Phase 2: Make The Control Center The Primary Desktop Mode

### Goal

Treat the control center as the intended low-power default desktop experience rather than as a fallback for failures.

### Work

- revise product copy to explain the shell-first desktop model
- keep quick actions for sync, export, backup, restore, and plugin packs in the control center
- keep the full app as an explicit user choice
- allow returning from the full app back to the control center without quitting the desktop app

### Backend Policy

- if the user is in the control center and no active backend-dependent work is running, the backend should remain off
- if the user exits the full app back to the control center, the backend can be stopped when no jobs are active
- do not use aggressive inactivity shutdown while the user is actively in the full app

### Expected Win

- most desktop sessions will never boot the Python server
- the low-cost mode becomes the normal path for occasional users

## Phase 3: Introduce A Minimal Desktop Backend Mode

### Goal

Reduce Python-side startup work and resident memory when the backend is needed for the desktop full app.

### Current Concern

The backend HTTP server starts subsystems in FastAPI lifespan that are not desirable for a battery-sensitive desktop mode:

- [`AutomationScheduler` startup](/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/api/http_server.py:3623)
- optional live-sync thread startup in the same lifespan block

This is not aligned with the desktop product posture, especially because desktop explicitly marks some server-style features unsupported.

### Change

- introduce a desktop-specific runtime flag, for example `OUTLAYS_DESKTOP_MODE=minimal`
- pass that flag from Electron in backend process env
- use it to skip nonessential background services in desktop mode

### Candidate Subsystems To Disable In Desktop Minimal Mode

- automation scheduler
- live sync threads
- operator-only monitoring helpers
- VNC or display helpers not required for the current flow
- any resident background pollers not required by the visible desktop route

### Possible Follow-Up

If a flag-based approach is still too broad or too fragile:

- add a separate `serve-desktop` entrypoint with a reduced route and startup surface

### Expected Win

- lower backend startup cost
- lower backend idle RAM
- lower risk of background energy use on laptops

## Phase 4: Keep One-Off Desktop Tasks Out Of The Resident Server

### Goal

Preserve the current good pattern where possible: short-lived subprocess jobs instead of an always-running HTTP backend.

### Current Strength

The desktop runtime already executes several tasks as one-off commands:

- [`runSyncJob()`](/Users/max/projekte/lidltool/apps/desktop/src/main/runtime.ts:243)
- [`runExportJob()`](/Users/max/projekte/lidltool/apps/desktop/src/main/runtime.ts:251)
- [`runBackupJob()`](/Users/max/projekte/lidltool/apps/desktop/src/main/runtime.ts:260)
- [`runImportJob()`](/Users/max/projekte/lidltool/apps/desktop/src/main/runtime.ts:342)
- shared helper [`runCommand()`](/Users/max/projekte/lidltool/apps/desktop/src/main/runtime.ts:767)

### Plan

- keep these workflows serverless where practical
- avoid routing one-off desktop jobs through the resident HTTP service unless the full app truly requires it
- if a feature can be implemented as a short-lived command instead of a long-running server dependency, prefer the command path

### Expected Win

- limits the amount of resident state needed for occasional-use workflows
- keeps idle cost low even as desktop adds more workflows

## Phase 5: Audit Electron Renderer Idle Work

### Goal

Reduce the cost of keeping the control center open and reduce unnecessary work in the full app when the user is inactive.

### Current State

The vendored frontend already uses route-level lazy loading:

- [`vendor/frontend/src/main.tsx`](/Users/max/projekte/lidltool/apps/desktop/vendor/frontend/src/main.tsx:1)
- [`vendor/frontend/src/app/page-loaders.ts`](/Users/max/projekte/lidltool/apps/desktop/vendor/frontend/src/app/page-loaders.ts:1)

That means route bundle loading is not the first optimization target.

### Work

- audit timers, polling, and intervals on desktop-visible routes
- ensure polling is disabled when routes are hidden, unsupported, backgrounded, or not active
- avoid mounting expensive content before it is visible
- avoid preloading heavy route data unless a route is likely to be used immediately

### Concrete Audit Targets

- intervals like the one in [`AISettingsPage.tsx`](/Users/max/projekte/lidltool/apps/desktop/vendor/frontend/src/pages/AISettingsPage.tsx:209)
- route-level polling on OCR, AI, or connector pages
- hidden components that keep subscriptions or timers alive after navigation

### Electron-Specific Checks

- compare default GPU acceleration with `app.disableHardwareAcceleration()` behind a feature flag
- only keep the setting if measured results improve overall resource use without causing higher CPU or degraded UX
- inspect whether background windows are still painting or doing work unnecessarily

### Expected Win

- lower renderer wakeups
- lower background CPU
- better battery behavior when the app is open but inactive

## Phase 6: Reduce Sync CPU Time And Energy

### Goal

Lower the resource cost of active scraping and syncing, especially on battery.

### Important Clarification

The retailer-scraping Playwright browser is already short-lived. It opens inside auth or sync flows and closes afterward. For example:

- [`RewePlaywrightClient.fetch_receipts()`](/Users/max/projekte/lidltool/apps/desktop/vendor/backend/src/lidltool/rewe/client_playwright.py:163)

This means the main opportunity is not to "sleep" that browser. The opportunity is to shorten the active work and avoid unnecessary waits.

### Work

- audit fixed delays such as `page.wait_for_timeout(...)`
- replace fixed waits with event-based waits where safe
- keep browser-based connectors headless by default unless interactive auth is required
- add a desktop "low power sync" mode for battery-sensitive runs
- cap concurrency for desktop to one heavy connector job at a time

### Audit Targets

- Amazon client waits
- auth bootstrap waits
- Kaufland waits
- Rossmann waits
- REWE waits
- offer runtime waits

### Expected Win

- shorter sync durations
- lower energy use during active jobs
- lower peak CPU and less needless wall-clock time spent with a browser open

## Phase 7: Trim Python Import And Startup Cost

### Goal

Shrink backend memory and startup time by reducing what loads at process start.

### Work

- trace Python imports during desktop backend startup
- identify heavy modules loaded even when the user only needs a small part of the app
- push expensive modules behind lazy imports where safe

### Candidate Areas

- OCR providers
- AI providers and mediation
- offer-related modules
- automation modules
- connector plugin validation paths
- analytics helpers not required on initial route load

### Additional Work

- confirm DB migration is only done when required
- avoid loading large rule bundles or normalization data until a workflow actually needs them

### Expected Win

- lower backend physical footprint
- faster backend start when the user opens the full app

## Phase 8: Desktop-Aware Power Modes

### Goal

Adapt behavior based on user intent and machine state instead of treating all sessions the same.

### Work

- add a desktop "battery saver" or "low power" setting
- reduce sync aggressiveness on battery
- reduce page depth and optional enrichment by default when unplugged
- disable nonessential background refresh work in low power mode
- expose the current mode clearly in the UI

### Optional Later Extension

- integrate with platform power state where available
- automatically suggest low power mode when on battery

### Expected Win

- better customer experience on laptops
- explicit control over the tradeoff between completeness and resource usage

## Phase 9: Add Regression Gates

### Goal

Prevent performance drift from returning after improvements land.

### Work

- add a release checklist for desktop resource checks
- run the profiler on a defined set of benchmark scenarios before release candidates
- compare results with the current saved baseline
- fail or flag if idle shell or full-app budgets regress beyond an agreed threshold

### Initial Suggested Gates

- idle control center physical footprint regression over `10%`
- idle full-app physical footprint regression over `10%`
- background CPU not settling to near idle within `60` seconds
- orphaned browser or Python child processes after job completion

## Execution Order

Recommended implementation order:

1. Phase 0: build the measurement harness
2. Phase 1: launch into control center instead of eager full-app boot
3. Phase 2: make the control center the primary desktop mode
4. Phase 3: add minimal desktop backend mode
5. Phase 4: keep one-off tasks out of the resident server
6. Phase 5: audit renderer idle work
7. Phase 6: reduce active sync energy cost
8. Phase 7: trim Python import and startup cost
9. Phase 8: add desktop-aware power modes
10. Phase 9: add regression gates

## First Milestone

The first milestone should be intentionally narrow:

- ship a profiling harness
- ship control-center-first startup
- keep backend off at idle
- remeasure idle shell memory and energy

If that milestone lands cleanly, it should produce the largest immediate resource win with the lowest architectural risk.

## Notes

- Do not optimize the main self-hosted architecture around desktop packaging needs.
- Prefer explicit desktop behavior over hidden background cleverness.
- For laptop users, "nothing is happening" should mean very close to zero ongoing cost.
