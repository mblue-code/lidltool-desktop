# Mobile Agent Runbook

This runbook is for an implementation agent working on the native mobile companion inside this repo.

It describes:
- how to work on the Android and iOS apps
- how to coordinate mobile work with the desktop-side pairing/sync protocol
- how to use sub-agents safely when parallel work is helpful

## Goal

Build two native companion apps:
- Android in Kotlin
- iOS in Swift/SwiftUI

The target product is:
- local-first
- desktop-paired
- non-cloud
- not self-hosted

## Repo Context

Repo root:
- `/Volumes/macminiExtern/projects/lidltool-desktop`

Vendored native baselines:
- Android: `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness`
- iOS: `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness`

Key planning docs:
- [docs/mobile-companion-vision.md](/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-companion-vision.md:1)
- [docs/mobile-native-implementation-plan.md](/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-native-implementation-plan.md:1)
- [docs/mobile-foundation.md](/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-foundation.md:1)

## Local Toolchain

Android on this machine:
- Android Studio: `/Volumes/macminiExtern/Applications/Android Studio.app`
- Android SDK: `/Volumes/macminiExtern/DevData/Android/sdk`

iOS on this machine:
- Xcode: `/Volumes/macminiExtern/Applications/Xcode.app`

Upstream comparison checkout on this machine:
- `/Volumes/macminiExtern/lidl-receipts-cli`

## Non-Negotiable Constraints

- keep both apps native
- do not introduce Flutter
- do not introduce React Native
- do not add runtime/build-time dependencies on `../../*` paths
- do not execute code from the old self-hosted repo at runtime
- do not turn the phone apps back into self-hosted backend clients
- do not design around cloud requirements

## Product Stance To Preserve

Always preserve these assumptions:
- pairing is local
- sync is intentional
- v1 sync only needs to work when both apps are open
- desktop remains OCR and ingestion authority
- mobile is optimized for daily use, capture, and quick review
- mobile should remain visually and conceptually close to the desktop app's design language

## Recommended Work Sequence

### 1. Refit the foundations

First changes should remove or isolate the old self-hosted assumptions:
- backend URL login screens
- self-hosted wording
- server-first push assumptions
- routes and tabs that only made sense for the old backend companion

Do not start with fancy sync logic before the shells are pointed in the right direction.

### 2. Define the protocol before deep UI work

Before building large mobile features, define:
- pairing payload
- pairing handshake
- sync cursors
- capture upload contract
- capture/OCR status contract
- normalized transaction sync contract

The desktop API contract should lead the deeper mobile data work.

### 3. Build local persistence early

Before relying on sync:
- add local database schema
- add capture queue persistence
- add sync metadata persistence
- make screens render from local state, not network-only assumptions

### 4. Prioritize the capture queue

The first genuinely useful mobile behavior should be:
- capture receipt on phone
- queue locally
- upload to desktop on sync
- show OCR processing state
- show resulting transaction after desktop ingestion

## Platform-Specific Guidance

### Android guidance

Preferred direction:
- Kotlin
- Jetpack Compose
- Room
- CameraX
- DataStore or encrypted preferences

Preferred early work:
- replace URL-entry login with pairing
- add local database
- add capture queue UI and storage
- add sync engine

Validation commands:
```bash
cd /Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness
./gradlew :app:assembleDebug
```

### iOS guidance

Preferred direction:
- Swift
- SwiftUI
- SwiftData or Core Data if needed
- Keychain for secrets
- AVFoundation / PhotosUI

Preferred early work:
- replace backend URL sign-in with pairing
- add local persistence
- add capture queue UI and storage
- add sync client and trust handling

Validation command on this machine:
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

## How To Use Sub-Agents

If agent delegation is available and explicitly allowed for the task, use sub-agents to split work by ownership, not by vague exploration.

Good parallel splits:
- one worker owns Android app refit
- one worker owns iOS app refit
- main agent owns desktop pairing/sync contract and integration decisions

Good sidecar explorer tasks:
- inspect existing Android harness code for reusable session/state layers
- inspect existing iOS harness code for reusable storage/navigation layers
- inspect desktop backend for the best insertion points for pairing/sync endpoints

Bad delegation patterns:
- two workers editing the same mobile platform files
- delegating the core protocol design to multiple overlapping agents
- having sub-agents redo the same exploration

Recommended ownership split when parallelizing:
- Android worker: `vendor/mobile/android-harness/**`
- iOS worker: `vendor/mobile/ios-harness/**`
- desktop/protocol owner: `src/**`, `vendor/backend/**`, `overrides/backend/**`, `docs/**`

## Checkpoints For Every Meaningful Slice

For each implementation slice:
- update docs if behavior or scope changed
- keep the product local-first
- verify no new `../..` runtime dependencies were introduced
- validate the relevant native app still builds
- validate desktop root checks if desktop code changed:
  - `npm run typecheck`
  - `npm run build`

## Early Milestones The Agent Should Target

### Milestone A

Native shells are still buildable, but:
- self-hosted copy is removed
- pairing placeholders exist
- old login/server assumptions are isolated

### Milestone B

Local persistence exists on both platforms for:
- pairing state
- sync metadata
- capture queue

### Milestone C

Capture queue works end-to-end with local artifact storage on both platforms.

### Milestone D

Desktop pairing and sync contract exists and the mobile apps can sync:
- capture artifacts up
- OCR state down
- normalized transaction results down

## Current Native Companion Contract

As of 2026-04-25, the repo contains the first implemented local mobile protocol.

Desktop endpoints:
- `POST /api/mobile-pair/v1/sessions`: authenticated desktop user creates a short-lived QR/session payload.
- `POST /api/mobile-pair/v1/handshake`: phone exchanges the QR pairing token for a local sync token.
- `POST /api/mobile-captures/v1`: paired phone uploads a receipt artifact; desktop stores it as a document and queues OCR.
- `GET /api/mobile-sync/v1/changes?cursor=...`: paired phone pulls capture status, recent transactions, transaction items, and current budget summary.

Validation commands:
- Android: `cd /Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness && ./gradlew :app:assembleDebug`
- iOS: use the `xcodebuild -target LidlToolHarness -sdk iphonesimulator` command above.
- Desktop backend syntax: `python3 -m py_compile vendor/backend/src/lidltool/api/http_server.py vendor/backend/src/lidltool/db/models.py vendor/backend/src/lidltool/mobile/pairing.py`

Implementation notes:
- Android currently uses an isolated `SQLiteOpenHelper` persistence foundation instead of Room to keep this pass buildable and local.
- iOS currently uses app-private JSON persistence instead of SwiftData to avoid project migration risk in this pass.
- Both choices are acceptable foundations, but a later hardening pass should decide whether to migrate to Room/SwiftData before broad beta distribution.

## Review Standard

When reviewing or self-checking implementation work, prioritize:
- wrong product direction
- accidental reintroduction of self-hosted assumptions
- missing local persistence
- weak sync state modeling
- cross-platform drift in the protocol
- mobile UI complexity that feels like shrunken desktop UI
- mobile styling drift that no longer feels like the desktop product family

## If Blocked

If a task is blocked, do not jump straight to broad new architecture.

Resolve in this order:
1. check whether the protocol contract is underspecified
2. check whether local storage shape is underspecified
3. check whether the task belongs on desktop rather than mobile
4. simplify scope instead of introducing cloud or always-on behavior
