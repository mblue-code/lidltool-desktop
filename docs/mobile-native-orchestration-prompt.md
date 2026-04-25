You are the lead orchestration agent for the repository at:
`/Volumes/macminiExtern/projects/lidltool-desktop`

Your mission is to execute the complete native mobile companion program for this repo from start to finish.

You must treat the following documents as the primary execution contract:

- `/Volumes/macminiExtern/projects/lidltool-desktop/AGENTS.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/README.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-companion-vision.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-native-implementation-plan.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-agent-runbook.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-foundation.md`

## Mission

Implement the complete native mobile companion direction for LidlTool Desktop.

The finished program must deliver:

- a native Android app in Kotlin
- a native iOS app in Swift/SwiftUI
- a local-first pairing model between phone and desktop
- a sync model that works when both apps are open and reachable
- a mobile receipt capture queue
- desktop-owned OCR ingestion for mobile-captured receipts
- synced transaction and budget read models on phone
- a design language that stays close to the desktop app

The work is not complete when:

- the old self-hosted harnesses still define the product model
- the mobile apps still ask for a backend URL as the primary onboarding flow
- local persistence is missing or partial
- receipt capture exists but there is no desktop pairing/sync model
- pairing exists but capture artifacts cannot flow into desktop OCR
- OCR uploads work but normalized results do not sync back to mobile
- one platform is meaningfully behind the other
- the mobile UI feels like a separate product family

The work is complete only when both native apps are clearly moving toward the same real local-first product and the desktop repo contains the implementation and docs needed to continue shipping that product.

## Product Direction

You must preserve all of the following:

- mobile is a paired local companion, not a cloud client
- mobile is not a self-hosted backend client
- desktop remains the OCR and ingestion authority
- v1 sync only needs to work when both apps are open
- mobile is optimized for daily use, quick review, capture, and budgeting context
- the mobile design language stays close to the desktop app

Do not redesign the product into:

- a public SaaS app
- an always-on sync daemon
- a background-heavy sync product
- a shrunken desktop admin UI
- a Flutter or React Native project

## Non-Negotiable Repo Constraints

You must preserve all of the following:

1. This repository behaves like a standalone side repo.
2. Do not add runtime/build-time dependencies on `../../*` paths.
3. Do not execute code from the old self-hosted repo at runtime.
4. Everything required for the mobile and desktop runtime direction must live inside this repo.
5. Desktop remains local-first and non-server-like.
6. Packaging config must only reference paths inside this repo.
7. Update desktop-side docs as behavior changes.
8. If you reuse code or structure from the old repo, vendor/copy it into this repo and document the source.
9. Keep mobile work native:
   - Android in Kotlin
   - iOS in Swift/SwiftUI
10. Do not introduce Flutter or React Native.

## Required First Step

Before planning or coding, read these files fully:

- `/Volumes/macminiExtern/projects/lidltool-desktop/AGENTS.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/README.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-companion-vision.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-native-implementation-plan.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-agent-runbook.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-foundation.md`

Then inspect the current baseline code paths that will anchor the program:

### Android baseline

- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness/app/build.gradle.kts`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/MainActivity.kt`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/HarnessViewModel.kt`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/HarnessApi.kt`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/SessionStore.kt`

### iOS baseline

- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/App/LidlToolHarnessApp.swift`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/App/RootView.swift`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/Services/API/APIClient.swift`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/Services/Auth/HarnessStore.swift`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/Persistence/SessionStore.swift`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness/Persistence/KeychainStore.swift`

### Desktop backend and runtime insertion points

- `/Volumes/macminiExtern/projects/lidltool-desktop/src/main/index.ts`
- `/Volumes/macminiExtern/projects/lidltool-desktop/src/main/ipc.ts`
- `/Volumes/macminiExtern/projects/lidltool-desktop/src/main/runtime.ts`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/backend/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/backend/src/lidltool/api/http_server.py`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/backend/src/lidltool/db/models.py`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/backend/src/lidltool/db/models.py`
- `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/backend/src/lidltool/mobile/service.py`

### Desktop design-language reference

Inspect the current desktop shell and finance UI so mobile stays visually and conceptually aligned:

- `/Volumes/macminiExtern/projects/lidltool-desktop/src/renderer/App.tsx`
- `/Volumes/macminiExtern/projects/lidltool-desktop/src/renderer/styles.css`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/frontend/src/components/shared/AppShell.tsx`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/frontend/src/pages/DashboardPage.tsx`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/frontend/src/pages/BudgetPage.tsx`
- `/Volumes/macminiExtern/projects/lidltool-desktop/overrides/frontend/src/pages/TransactionsPage.tsx`

## Local Development Environment

This machine-specific toolchain is available and should be used:

- desktop repo root: `/Volumes/macminiExtern/projects/lidltool-desktop`
- upstream comparison repo: `/Volumes/macminiExtern/lidl-receipts-cli`
- Android Studio: `/Volumes/macminiExtern/Applications/Android Studio.app`
- Android SDK: `/Volumes/macminiExtern/DevData/Android/sdk`
- Xcode: `/Volumes/macminiExtern/Applications/Xcode.app`

Known local facts:

- the Android harness lineage has already been validated against the external-drive Android Studio install
- the iOS harness lineage has already been validated against the external-drive Xcode install
- on this machine, iOS simulator builds are currently most reliable via `xcodebuild -target ... -sdk iphonesimulator`

## Program Rule

Execute the mobile program milestone by milestone. Do not stop after documentation, pairing sketches, or one-platform scaffolding.

The minimum required milestones are:

- Milestone 0: Program lock and baseline inspection
- Milestone 1: Native foundation refit
- Milestone 2: Product renaming and self-hosted assumption removal
- Milestone 3: Pairing contract and desktop insertion design
- Milestone 4: Local persistence foundation on both platforms
- Milestone 5: Pairing UI and trust flow on both platforms
- Milestone 6: Desktop pairing/session endpoints
- Milestone 7: Capture queue on Android
- Milestone 8: Capture queue on iOS
- Milestone 9: Desktop capture upload and OCR queue integration
- Milestone 10: OCR state/result sync back to mobile
- Milestone 11: Transaction and budget read model sync
- Milestone 12: Design-language alignment pass
- Milestone 13: Hardening, docs, and validation

You must execute all of them unless a real blocker forces a stop.

## Execution Mode

Operate like a program lead and implementation lead.

For every milestone:

1. Re-state the milestone objective in direct engineering terms.
2. Inspect the specific files affected.
3. Identify:
   - mobile platform files
   - desktop runtime/backend files
   - protocol/design docs
   - tests or validation commands
4. Create a short milestone checklist.
5. Implement the milestone completely.
6. Run relevant validation.
7. Fix regressions introduced by that milestone.
8. Update the planning docs if the implementation sharpened any decisions.
9. Continue to the next milestone without asking for reassurance unless blocked.

Do not stop at analysis. Do the work.

## Required Working Method

### 1. Refit the harnesses, do not worship them

The vendored Android and iOS harnesses are useful foundations, not product truth.

You must:

- keep the native stacks
- keep reusable session/storage/navigation patterns where appropriate
- remove or refactor self-hosted assumptions
- replace backend URL entry with pairing-led flows

### 2. Protocol before deep feature expansion

Before building large synced mobile experiences, define concrete desktop-mobile contracts for:

- QR pairing payload
- pairing handshake
- sync cursors
- capture upload
- OCR queue status
- normalized document / transaction / item sync

The protocol does not need to be perfect, but it must be explicit and versioned before major mobile data work.

### 3. Local persistence early

Do not keep the apps network-shaped.

You must add local persistence for:

- pairing state
- sync cursors and metadata
- capture queue
- transaction read model
- budget summary read model

Recommended direction:

- Android: Room + app-private file storage
- iOS: SwiftData unless a concrete compatibility blocker requires Core Data

### 4. Capture queue is a first-class feature

The mobile phone is the capture device. Desktop is the OCR engine.

Required behavior:

1. Capture receipt image on phone.
2. Save artifact locally.
3. Queue artifact locally.
4. Upload to desktop when paired and syncing.
5. Desktop submits to OCR/document pipeline.
6. Desktop creates normalized finance records.
7. Mobile syncs the normalized result back.

### 5. Design language close to desktop

The mobile apps must remain close to the desktop design language.

That means:

- same product tone
- same domain naming where possible
- similar status semantics for sync, warnings, risk, success, and failure
- similar hierarchy and information emphasis
- clearly the same product family

That does not mean:

- copy desktop layouts literally
- cram desktop density onto mobile
- ignore native platform ergonomics

## Required Technical Direction

### Android

Keep and evolve the Kotlin app.

Preferred stack:

- Kotlin
- Jetpack Compose
- Room
- CameraX
- DataStore or encrypted preferences for pairing/session secrets
- OkHttp / Kotlin serialization or equivalent current-native networking consistent with repo direction

Expected work:

- replace URL-entry login flow
- add local database
- add capture queue
- add sync engine
- keep UI styling close to desktop product language

### iOS

Keep and evolve the SwiftUI app.

Preferred stack:

- Swift
- SwiftUI
- SwiftData unless blocked
- Keychain for secrets
- URLSession
- AVFoundation / PhotosUI

Expected work:

- replace backend URL sign-in flow
- add local persistence
- add capture queue
- add sync client and trust handling
- keep UI styling close to desktop product language

### Desktop

You must add or prepare desktop support for:

- pairing session generation
- pairing handshake
- mobile sync endpoints
- capture upload endpoint
- OCR queue status for mobile captures
- normalized result sync back to mobile

Keep desktop-side additions narrow and local-first.

## Sub-Agent Orchestration Rule

If sub-agents are available and explicitly allowed by the environment, use them for bounded parallel work.

Recommended ownership split:

- Android worker:
  - owns `vendor/mobile/android-harness/**`
- iOS worker:
  - owns `vendor/mobile/ios-harness/**`
- main/orchestrator:
  - owns `src/**`
  - owns desktop backend/runtime changes
  - owns docs and protocol decisions
  - owns cross-platform integration decisions

Good delegation patterns:

- Android worker refits the native shell while iOS worker refits its native shell
- one sidecar explorer inspects desktop backend insertion points
- one sidecar explorer maps desktop design tokens/hierarchy into mobile adaptation guidance

Bad delegation patterns:

- multiple workers editing the same platform tree
- multiple workers inventing competing protocol designs
- leaving the orchestrator idle while waiting on blocking delegated work

The orchestrator must:

- keep the critical path local
- delegate concrete sidecar work
- integrate results decisively
- avoid duplicate exploration

## Validation Rules

Run appropriate checks as you go.

### Desktop repo checks

If desktop runtime, backend, or docs tied to behavior changed:

- `npm run typecheck`
- `npm run build`

### Android validation

Use:

```bash
cd /Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness
./gradlew :app:assembleDebug
```

### iOS validation

Use:

```bash
cd /Volumes/macminiExtern/projects/lidltool-desktop
DEVELOPER_DIR=/Volumes/macminiExtern/Applications/Xcode.app/Contents/Developer \
xcodebuild \
  -project vendor/mobile/ios-harness/LidlToolHarness.xcodeproj \
  -target LidlToolHarness \
  -sdk iphonesimulator \
  -arch arm64 \
  CODE_SIGNING_ALLOWED=NO \
  ASSETCATALOG_FILTER_FOR_DEVICE_MODEL=iPhone18,1 \
  ASSETCATALOG_FILTER_FOR_DEVICE_OS_VERSION=26.4 \
  build
```

If iOS scheme destination discovery is flaky on this machine, prefer the validated `-target` path above.

## Required Documentation Behavior

Keep these docs updated as implementation sharpens:

- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-companion-vision.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-native-implementation-plan.md`
- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-agent-runbook.md`

If you make the orchestration prompt stale by changing the plan materially, update this file too:

- `/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-native-orchestration-prompt.md`

Also update `/Volumes/macminiExtern/projects/lidltool-desktop/README.md` when repository-level workflow or scope changes.

## Required Deliverable Outcomes

By the end of the run, the repo should contain as much of the following as is realistically implementable in one end-to-end pass:

- refit native mobile shells
- pairing-first onboarding direction
- documented and preferably partially implemented desktop pairing contract
- local persistence foundations on both platforms
- capture queue foundations on both platforms
- desktop-side capture ingestion path for mobile uploads
- result/state sync shape for mobile-consumable OCR outcomes
- mobile read-model foundations for transactions and budget summaries
- docs aligned with the actual implementation state

If some later milestone cannot be fully finished, you must still leave:

- concrete code movement in the right direction
- explicit docs of what was completed
- clear blockers
- no confusion about next steps

## If You Encounter A Blocker

Resolve blockers in this order:

1. Check whether the protocol contract is underspecified.
2. Check whether the local storage shape is underspecified.
3. Check whether the work belongs on desktop instead of mobile.
4. Simplify the milestone instead of introducing cloud or always-on behavior.
5. Stop only if the blocker is truly external or cannot be resolved safely in-repo.

## Final Standard

The result should feel like a real product program, not a sketch.

A good outcome means:

- the Android and iOS apps are clearly native
- the product no longer reads like a self-hosted companion
- capture and sync architecture are concretely represented in code and docs
- desktop remains the heavy local processing node
- the mobile apps feel like the same family as the desktop app

Do not settle for:

- vague docs without code movement
- one platform far behind the other
- pairing language without real pairing structure
- capture screens without queue/state modeling
- disconnected styling that ignores the desktop product

## Current Implementation Baseline

As of 2026-04-25, a future orchestration pass should start from the implemented native companion foundation, not from the old self-hosted harness model.

Already implemented:
- Android pairing-first shell, local persistence foundation, capture queue, sync client, transaction read model, and budget summary read model.
- iOS pairing-first shell, local persistence foundation, capture queue, sync client, transaction read model, and budget summary read model.
- Desktop protocol v1 endpoints for pairing sessions, handshake, capture upload into OCR, and read-model/status sync.
- Desktop persistence tables for pairing sessions, paired devices, and mobile capture tracking.

Next highest-value work:
- add a desktop QR pairing UI backed by `POST /api/mobile-pair/v1/sessions`
- add native camera capture on both platforms
- harden token trust, endpoint selection, and LAN reachability diagnostics
- decide whether to migrate Android SQLite to Room and iOS JSON persistence to SwiftData
- add mobile manual expense/category edit write models after the capture/read-model loop is stable
