# Mobile Foundation Fork

The desktop repo now vendors the upstream mobile harnesses under `vendor/mobile/` as a fork baseline for a future phone companion product.

## Why this exists

We already had usable native skeletons in the old self-hosted repo. They are worth keeping because they provide:

- Android and iOS project setup
- native navigation and view structure
- session persistence patterns
- REST client layers
- receipt, chat, OCR, dashboard, and offers companion-app surfaces

They do **not** provide the core desktop-pairing architecture we now want.

## Current source and sync

Source checkout used for vendoring:
- `/Volumes/macminiExtern/lidl-receipts-cli`

Source paths:
- `apps/android-harness`
- `apps/ios-harness`

Sync command from this repo root:

```bash
npm run vendor:sync:mobile
```

Alternative source checkout:

```bash
npm run vendor:sync:mobile -- --source-repo /path/to/lidl-receipts-cli
```

The sync script only copies the mobile harness apps into this repo. Desktop runtime/build flows remain isolated from the upstream repo.

## Reusable foundation

Useful now:
- native shell structure on Android and iOS
- local token/session storage patterns
- HTTP client and envelope decoding logic
- existing receipt-oriented companion UI
- localization scaffolding

Needs refit before product use:
- replace self-hosted backend URL entry with desktop pairing
- add local mobile data storage for offline-first use
- add a sync protocol between phone and desktop
- define authority/merge rules for shared records
- remove or redesign push assumptions around a server-first topology

## Current decision

Treat the vendored mobile apps as product-owned native companion foundations. They are no longer only old self-hosted harnesses.

As of 2026-04-25:
- Android and iOS both start from pairing-led onboarding instead of backend URL sign-in.
- Both apps keep native UI stacks and local storage foundations.
- Both apps model queued mobile receipt captures as artifacts that upload to desktop OCR.
- Both apps sync desktop-owned transaction and budget read models back into local mobile storage.
- The old push/server-client assumptions are no longer the primary product path.

Remaining refit work:
- add a polished desktop QR pairing UI
- move Android persistence from the current SQLite foundation to Room if the project accepts the additional Gradle/KSP setup
- move iOS persistence from the current app-private JSON foundation to SwiftData if deployment targets and migration policy allow it
- add native camera capture in addition to import-based capture
- add mobile manual expense/category edit write models after the capture/read-model loop is stable
