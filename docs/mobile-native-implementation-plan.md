# Mobile Native Implementation Plan

This document turns the mobile companion vision into a concrete implementation plan for:
- native Android in Kotlin
- native iOS in Swift/SwiftUI

This plan assumes:
- no Flutter
- no React Native
- no cloud dependency
- no public internet exposure of the desktop backend
- direct local pairing between phone and desktop

## Product Goal

Build a local-first phone companion that is useful every day and syncs privately with the desktop app when both are open.

Desktop remains the authority for:
- OCR ingestion
- connector-driven imports
- bulk repair
- deeper analytics
- backup and restore

Mobile becomes the authority for:
- fast capture
- daily budgeting glanceability
- manual entry on the go
- quick transaction review

## Design Language Direction

The mobile apps should remain close to the desktop app's design language.

Required design stance:
- preserve the same overall product identity
- keep primary finance domains and terminology aligned with desktop
- reuse desktop visual cues for status, risk, success, warnings, and sync state
- mirror the desktop app's tone: practical, local-first, finance-focused

Allowed adaptation:
- native mobile navigation patterns
- mobile-first layout density
- platform-appropriate controls and gestures
- simplified screen composition where desktop has denser information

Avoid:
- creating a separate mobile brand language
- introducing generic consumer-finance styling that no longer feels like LidlTool Desktop
- copying desktop screen layouts directly without adapting them for touch and smaller viewports

Implementation implication:
- mobile design work should begin from desktop tokens, naming, hierarchy, and states, then translate them into native Android and iOS patterns

## Existing Foundation

Current vendored mobile baselines:
- Android: `vendor/mobile/android-harness`
- iOS: `vendor/mobile/ios-harness`

Security hardening reference:
- [Mobile Local Pairing Security Hardening Plan](/Volumes/macminiExtern/projects/lidltool-desktop/docs/mobile-local-pairing-security-hardening-plan.md)

Current upstream-derived stack:
- Android: Kotlin + Jetpack Compose + OkHttp + Kotlin serialization
- iOS: Swift + SwiftUI + URLSession

These baselines are worth keeping for:
- native project setup
- navigation shell
- local session/device persistence patterns
- API client structure
- receipt/chat/dashboard style companion UI

They should be refit, not rewritten from zero.

## Local Development Environment

This section is specific to the current workstation and should be updated if the local toolchain paths move.

Current local environment:
- desktop repo root: `/Volumes/macminiExtern/projects/lidltool-desktop`
- upstream mobile skeleton source: `/Volumes/macminiExtern/lidl-receipts-cli`
- vendored mobile baselines:
  - `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness`
  - `/Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/ios-harness`

Android toolchain on this machine:
- Android Studio: `/Volumes/macminiExtern/Applications/Android Studio.app`
- Android SDK: `/Volumes/macminiExtern/DevData/Android/sdk`
- validated upstream mobile project path: `/Volumes/macminiExtern/lidl-receipts-cli/apps/android-harness`

iOS toolchain on this machine:
- Xcode: `/Volumes/macminiExtern/Applications/Xcode.app`
- validated upstream mobile project path: `/Volumes/macminiExtern/lidl-receipts-cli/apps/ios-harness`

Known local caveats:
- the iOS simulator build on this machine currently works most reliably via `xcodebuild -target ... -sdk iphonesimulator` rather than relying on scheme destination discovery
- the Android harness has already been validated with the external-drive Android Studio install above

Working rules for local development:
- keep mobile implementation native:
  - Android in Kotlin
  - iOS in Swift/SwiftUI
- do not introduce Flutter or React Native
- do not depend on code outside this repo at runtime
- use the upstream monorepo only as a source for vendoring or comparison

Suggested local validation commands:

Android:
```bash
cd /Volumes/macminiExtern/projects/lidltool-desktop/vendor/mobile/android-harness
./gradlew :app:assembleDebug
```

iOS:
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

## Target App Model

### Shared product behavior

Both native apps should support:
- local onboarding
- pairing to desktop via QR code
- explicit sync status
- local database for offline use
- capture queue for receipt photos
- browsing synced transactions and budget summaries
- manual local changes queued for next sync

Both native apps should not require:
- background sync guarantees
- cloud account creation
- a public server URL

### Desktop-paired flow

Recommended user flow:
1. User opens desktop and chooses `Pair mobile`.
2. Desktop shows QR code with pairing payload.
3. Phone app scans QR code.
4. Phone stores paired desktop identity and trust material.
5. Phone and desktop sync only when both apps are open and reachable.

## Architecture

### 1. Pairing model

Use QR-based pairing for v1.

Desktop should provide a pairing payload containing:
- desktop device ID
- local endpoint URL or candidate endpoints
- pairing token or short-lived enrollment secret
- desktop public key or trust fingerprint
- protocol version

Phone should:
- scan QR
- validate payload shape
- attempt a local handshake
- store paired desktop record
- require explicit user confirmation before first trust

### 2. Sync model

Use an offline-first sync model, not direct live editing.

Recommended v1 model:
- each side has a local database
- each side records local mutations as sync events
- sync exchanges new events since last cursor
- desktop resolves ingestion-heavy operations
- mobile applies normalized results from desktop

Recommended stance for v1:
- desktop is the authority for OCR-derived records
- mobile may create manual entries and capture artifacts
- most conflicts should be avoided by ownership boundaries, not fancy merge logic

### 3. Receipt capture queue

This should be a core v1 feature.

Flow:
1. User captures receipt photo on phone.
2. Phone stores image and metadata locally.
3. Capture enters mobile queue.
4. On sync, phone uploads capture artifact to desktop.
5. Desktop creates document/OCR job and processes it.
6. Desktop emits normalized document/transaction/item results.
7. Phone syncs those results back into its local database.

Recommended capture states:
- `local_only`
- `queued_for_upload`
- `uploaded`
- `processing_on_desktop`
- `needs_review`
- `completed`
- `failed`

Important rule:
- the phone capture is an artifact, not yet a finance record
- the finance record is created only after desktop ingestion

### 4. Local storage

Each app needs a real local persistence layer.

Android:
- use Room for structured app data
- use app-private file storage for captured receipt images

iOS:
- use SwiftData or Core Data for structured app data
- use app-private file storage for captured receipt images

Recommendation:
- prefer Room on Android
- prefer SwiftData on iOS unless compatibility requirements force Core Data

### 5. Sync transport

For v1, use simple local HTTP over LAN with explicit pairing trust.

Recommended properties:
- desktop runs a local mobile sync API only while the desktop app is open
- phone discovers desktop from pairing payload plus optional local network retry
- all sync requests are authenticated with pairing credentials
- payloads are versioned

Future enhancements can add:
- local discovery
- mDNS / Bonjour / NSD
- better reconnect behavior

But discovery should not block the first shipping version if QR payload already includes a usable endpoint.

## Platform Plan

### Android plan

Keep and evolve the Kotlin app.

Target direction:
- Jetpack Compose UI
- Room database
- WorkManager only for best-effort deferred local tasks, not guaranteed sync
- CameraX for receipt capture
- DataStore or encrypted preferences for pairing/session metadata

Recommended modules over time:
- `app`: app shell and navigation
- `core-model`
- `core-storage`
- `core-sync`
- `feature-home`
- `feature-transactions`
- `feature-budget`
- `feature-capture`
- `feature-settings`

Key Android implementation work:
- replace backend URL login with pairing flow
- add local database schema
- add receipt capture pipeline
- add sync engine and retry policy
- remove server-first push assumptions from the harness baseline
- introduce shopping/budget-first mobile home
- keep Compose UI styling visually aligned with desktop product language

### iOS plan

Keep and evolve the native SwiftUI app.

Target direction:
- SwiftUI app shell
- SwiftData-backed local persistence
- URLSession-based sync client
- AVFoundation / PhotosUI for receipt capture and import
- Keychain for pairing secrets and trust material

Recommended feature grouping:
- App shell
- Pairing and trust
- Local store
- Sync client
- Capture queue
- Home/budget
- Transactions
- Settings

Key iOS implementation work:
- replace backend URL sign-in with pairing flow
- add local persistence for synced finance data and capture queue
- add receipt capture/import UX
- surface sync state clearly without promising background behavior
- reduce the old APNs/server-oriented assumptions to optional later work
- keep SwiftUI presentation visually aligned with desktop product language

## Shared Data Domains

### Phase 1 domains

Implement first:
- paired desktop metadata
- sync session metadata and cursors
- receipt capture queue
- transaction list
- transaction detail
- budget summary snapshots
- manual mobile-created entries
- sync status and sync history

### Phase 2 domains

Add next:
- goals
- recurring bill reminders
- shopping list / shopping notes
- household workspace support
- item-level category edits

### Phase 3 domains

Later:
- richer analytics snippets
- more advanced conflict handling
- optional mobile notifications from synced local state
- better background refresh where platform-safe

## API and Protocol Work Needed On Desktop

The desktop repo will need a dedicated mobile-pair protocol, separate from the old self-hosted harness assumptions.

New desktop capabilities needed:
- pairing session generation
- pairing handshake endpoint
- local mobile sync API
- capture upload endpoint
- OCR queue status endpoint
- normalized result sync back to phone
- protocol version negotiation

Recommended endpoint groups:
- `/api/mobile-pair/*`
- `/api/mobile-sync/*`
- `/api/mobile-captures/*`

The exact paths can change, but the separation should stay clear.

## Proposed Screen Set

### v1 screens on both platforms

- Pairing
- Home
- Transactions
- Transaction detail
- Budget
- Capture
- Capture queue
- Settings

### Optional early additions

- Goals
- Shopping
- Household

## Milestones

### Milestone 1: Refit foundations

Goal:
- fork the vendored harnesses into product-owned mobile apps inside this repo structure

Deliverables:
- native app rename/rebrand from harness naming
- remove self-hosted wording
- replace backend URL entry screen with placeholder pairing screen
- keep current native shells buildable

### Milestone 2: Pairing and local persistence

Goal:
- make both apps pairable and offline-capable

Deliverables:
- QR pairing flow
- local paired desktop record
- local persistence layer
- sync status model
- empty-state home screen with local DB backing

### Milestone 3: Capture queue

Goal:
- phone becomes useful immediately even before full finance sync

Deliverables:
- camera/import flow
- local image storage
- capture queue UI
- upload to desktop
- desktop OCR queue status reflected back on phone

### Milestone 4: Finance read model

Goal:
- synced mobile finance browsing

Deliverables:
- transaction list/detail sync
- budget summary sync
- home screen populated from local store
- manual refresh / sync now

### Milestone 5: Mobile write model

Goal:
- useful daily actions on phone

Deliverables:
- manual expense entry
- category/note edits
- conflict-safe queued mutations

### Milestone 6: Shopping and household depth

Goal:
- differentiate the companion app

Deliverables:
- shopping-mode views
- household visibility
- shared notes or lightweight shopping flows

## Technical Risks

Primary risks:
- pairing security design
- local network reliability across home Wi-Fi setups
- image upload deduplication
- schema evolution across desktop and two native apps
- keeping sync simple enough to ship
- avoiding a hidden drift back into server-first design

## Recommended Decisions Now

These decisions are strong enough to lock in early:
- native Android in Kotlin
- native iOS in Swift/SwiftUI
- no Flutter
- desktop-only OCR processing
- mobile receipt capture queue in v1
- local database on phone
- sync only when both apps are open in v1
- desktop remains ingestion authority

## Implementation Status: 2026-04-25

The native companion foundation now has concrete code movement on both platforms and in the desktop backend.

Delivered:
- Android has a pairing-first Compose shell, local SQLite persistence foundation, import-based capture queue, explicit sync action, transaction read model storage, and budget summary storage.
- iOS has a pairing-first SwiftUI shell, app-private JSON persistence foundation, Keychain-backed sync token/device identity, import-based capture queue, explicit sync action, transaction read model storage, and budget summary storage.
- Desktop backend has versioned local mobile tables and endpoints for pairing, capture upload into desktop OCR, capture status sync, transaction read model sync, and budget summary sync.

Current protocol v1:
- QR/session payload contains `protocol_version`, `desktop_id`, `desktop_name`, `endpoint_url`, `pairing_token`, `public_key_fingerprint`, `expires_at`, `transport`, and `listener_expires_at`.
- Desktop creates a pairing payload with `POST /api/mobile-pair/v1/sessions`; Wi-Fi pairing passes the temporary LAN bridge URL as `bridge_endpoint_url`.
- Phone completes trust with `POST /api/mobile-pair/v1/handshake`.
- Phone uploads queued capture artifacts with `POST /api/mobile-captures/v1` using `Authorization: Bearer <sync_token>`.
- Phone pulls desktop-owned read models with `GET /api/mobile-sync/v1/changes?cursor=...` using the same sync token.

Desktop persistence added:
- `mobile_pairing_sessions`
- `mobile_paired_devices`
- `mobile_captures`

Important current limits:
- Capture is implemented as local file/document import first. Native camera capture remains the next platform-specific enhancement.
- Sync is explicit and foreground-oriented. There is still no always-on daemon or background sync promise.
- The desktop pairing endpoint exists, but a polished desktop QR UI still needs to be added to the desktop app surface.
- Mobile write-model work beyond receipt capture, such as manual expense creation and category edits, remains follow-on work.
