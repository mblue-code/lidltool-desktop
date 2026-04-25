# iOS Native Companion

This is the native iPhone foundation for the LidlTool Desktop mobile companion.

The app is local-first and desktop-paired:
- pair with a desktop-generated QR/session payload
- store pairing metadata, sync cursor, capture queue, transactions, and budget summary locally
- keep the mobile sync token in Keychain
- import receipt images/PDFs into app-private storage
- upload queued captures to Desktop during explicit foreground sync
- pull desktop-owned OCR status, transactions, transaction items, and budget summary back to the phone

It is not a self-hosted backend client, does not sign in with a backend URL, and does not use APNs or a public cloud account flow.

## Protocol

Current desktop endpoints:
- `POST /api/mobile-pair/v1/handshake`
- `POST /api/mobile-captures/v1`
- `GET /api/mobile-sync/v1/changes?cursor=...`

The desktop app creates the QR/session payload with:
- `POST /api/mobile-pair/v1/sessions`

## Local Use

Build from the desktop repo root:

```bash
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

Install and launch on a booted simulator:

```bash
DEVELOPER_DIR=/Volumes/macminiExtern/Applications/Xcode.app/Contents/Developer \
xcrun simctl install booted vendor/mobile/ios-harness/build/Debug-iphonesimulator/LidlToolHarness.app

DEVELOPER_DIR=/Volumes/macminiExtern/Applications/Xcode.app/Contents/Developer \
xcrun simctl launch booted com.lidltool.iosharness
```

## Current Scope

Implemented foundation:
- pairing-first SwiftUI shell
- app-private JSON persistence for local mobile state
- Keychain-backed sync token/device identity
- import-based capture queue
- explicit sync action
- transaction read model and budget summary read model

Known follow-up work:
- polished desktop QR-pairing UI
- native camera capture
- SwiftData/Core Data migration for larger local datasets
- mobile write models beyond receipt capture, such as manual expenses and category edits
- simulator/device UI flow tests against a running desktop backend

## Current Xcode Caveat

This external-drive Xcode install builds most reliably with `-target` plus the simulator SDK rather than scheme-selected destination discovery.
Asset-catalog thinning also needs an explicit simulator device model and OS version on this machine.
