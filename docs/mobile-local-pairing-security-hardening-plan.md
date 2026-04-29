# Mobile Local Pairing Security Hardening Plan

This plan hardens local mobile pairing so the desktop can support real phone pairing without accidentally exposing the full desktop app or relying on router firewall behavior as the only protection.

## Goals

- Keep localhost-only desktop behavior as the default.
- Open network access only when the user explicitly activates mobile pairing or sync.
- Expose only a narrow mobile API surface, not the full desktop web app.
- Make the risk visible with an explicit desktop confirmation dialog before opening a LAN listener.
- Let Android and iOS scan the QR code directly instead of requiring JSON copy/paste.
- Preserve self-hosted friendliness without making public internet exposure easy by accident.

## Threat Model

Primary risks to defend against:

- A user enables mobile pairing while on an untrusted Wi-Fi network.
- A router, VPN, tunnel, firewall rule, or OS sharing setting makes the selected port reachable outside the home LAN.
- Another device on the LAN scans or reuses the pairing payload.
- A stale sync token keeps working after the user expects pairing to be temporary.
- The LAN listener accidentally exposes normal desktop routes, setup routes, user sessions, or static frontend assets.
- A malicious local process or webpage tries to trigger pairing without user awareness.

Out of scope for the first hardening pass:

- Cloud relay.
- Full remote access over the public internet.
- Bluetooth transport for bulk sync.
- Background always-on sync.

## Target Security Model

Use layered controls. Router firewall is only an outer layer, not the security boundary.

1. Desktop main backend remains bound to `127.0.0.1` by default.
2. Mobile LAN access is a separate, temporary listener or bridge with its own route allowlist.
3. The mobile listener binds to one selected private interface address, not `0.0.0.0`, unless the user explicitly opts into an advanced mode.
4. Pairing sessions are short-lived and one-time-use.
5. Paired devices receive device-scoped sync tokens that are revocable from desktop settings.
6. Every mobile request requires either a valid pairing token during handshake or a valid device sync token after pairing.
7. Requests from non-private client IP ranges are rejected unless an explicit future remote mode is enabled.
8. The desktop UI clearly shows when local mobile access is open and provides a one-click stop action.

## Architecture Decision

Implement a dedicated mobile bridge instead of binding the full desktop app to the LAN.

The existing desktop backend can keep serving the full UI on localhost. When the user activates mobile pairing, desktop starts a bridge that only exposes these routes:

- `POST /api/mobile-pair/v1/handshake`
- `POST /api/mobile-captures/v1`
- `GET /api/mobile-sync/v1/changes`
- `POST /api/mobile-sync/v1/manual-transactions`
- `GET /api/mobile-local/v1/health`

The existing authenticated desktop route remains localhost-only:

- `POST /api/mobile-pair/v1/sessions`

The bridge can either be:

- a second backend instance with a route allowlist and shared local DB/config, or
- an Electron-owned HTTP proxy that forwards only allowed mobile routes to the localhost backend.

Recommended first implementation: Electron-owned bridge. It keeps LAN exposure logic in the desktop repo, can be started/stopped with the UI, and avoids changing the main backend exposure mode for normal users.

## Desktop UX Flow

### Activation Flow

1. User opens Settings -> Mobile pairing.
2. User clicks `Enable local phone pairing`.
3. Desktop shows a modal risk disclosure before opening the LAN listener.
4. User confirms.
5. Desktop selects a private LAN address and starts the temporary mobile bridge.
6. Desktop creates a short-lived pairing session.
7. Desktop shows a QR code and status panel.
8. Phone scans the QR code and pairs.
9. Desktop automatically closes the pairing listener after success or timeout unless the user chooses to keep a sync window open.

### Risk Modal Copy

Use direct wording, not a buried tooltip:

> Local phone pairing opens a temporary network port on this Mac so your phone can connect over the same Wi-Fi network. Other devices on this network may be able to reach that port while it is open. Only continue on a trusted home or private network.

Controls:

- Primary: `Open temporary pairing window`
- Secondary: `Cancel`
- Optional checkbox: `Remember this decision for this network`

Do not remember the decision globally. If remembering is implemented, scope it to the network fingerprint and selected interface.

### Status Panel

Show:

- selected interface name
- selected LAN URL
- listener state
- pairing expiry countdown
- paired device count
- last mobile request time
- `Stop sharing` button

Avoid saying the app is "online" or "public". Use "local network pairing window" consistently.

## Network Binding Rules

Implement a deterministic interface selection step.

Allowed by default:

- RFC1918 IPv4: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- IPv4 link-local: `169.254.0.0/16`, only with warning copy because routing can be odd
- ULA IPv6: `fc00::/7`, if IPv6 support is deliberately added

Rejected by default:

- public routable addresses
- loopback for LAN pairing
- `0.0.0.0`
- unspecified IPv6
- Docker, VM, and tunnel interfaces unless the user selects an advanced option

Recommended first pass:

- Use a selected concrete IPv4 address such as `192.168.1.146`.
- Bind the bridge to that address and randomize the mobile bridge port, or use the configured desktop port only when required.
- Include the actual bridge endpoint in the QR payload.

## Pairing Payload

Extend the QR payload to support direct scanning and multiple future transports:

```json
{
  "protocol_version": 1,
  "desktop_id": "desktop:...",
  "desktop_name": "Mac mini",
  "endpoint_url": "http://192.168.1.146:18766",
  "pairing_token": "...",
  "public_key_fingerprint": "...",
  "expires_at": "2026-04-27T20:32:08Z",
  "transport": "lan_http",
  "listener_expires_at": "2026-04-27T20:32:08Z"
}
```

Rules:

- `pairing_token` expires in 5-10 minutes.
- `pairing_token` is single-use.
- Store only a hash of the token server-side.
- Bind the session to the chosen bridge endpoint.
- Return the bridge endpoint in the handshake response so the phone persists the LAN mobile endpoint, not the localhost desktop URL.

## Mobile QR Scanner

### Android

Implement QR scanning in `vendor/mobile/android-harness`.

Recommended approach:

- Add CameraX for preview and lifecycle handling.
- Add ML Kit Barcode Scanning or ZXing for QR decode.
- Request camera permission at scan time.
- Parse QR values as:
  - raw JSON payload
  - `outlays-pair://<url-encoded-json>`
- Reuse the existing `HarnessViewModel.pairFromText()` parsing path after decode.

UI:

- Add `Scan QR` button beside paste/manual entry.
- Show camera permission rationale.
- Show a focused scanner screen with cancel action.
- On successful decode, vibrate lightly if available, close scanner, and run pairing.
- Keep manual paste as fallback.

Validation:

- Android build: `./gradlew :app:assembleDebug`
- Device smoke test with ADB logs for successful `POST /api/mobile-pair/v1/handshake`.

### iOS

Implement QR scanning in `vendor/mobile/ios-harness`.

Recommended approach:

- Use AVFoundation metadata capture for QR codes.
- Request camera permission at scan time.
- Parse the same raw JSON and `outlays-pair://` formats.
- Reuse the existing pairing store/client path.

UI:

- Add `Scan QR` action in the pairing screen.
- Present a native scanner view.
- Keep manual paste as fallback.

Validation:

- Simulator build with the existing `xcodebuild` command.
- Real-device scan test is required before release because camera scanning cannot be fully proven in simulator.

## Bridge Request Hardening

For every request handled by the mobile bridge:

- Reject paths not in the mobile allowlist.
- Reject methods not in the allowlist.
- Reject missing or invalid `Authorization` headers for post-pairing routes.
- Reject handshake requests with missing, expired, or already-used pairing tokens.
- Reject requests from non-private remote addresses.
- Add strict body size limits.
- Add upload size limits for capture artifacts.
- Rate-limit handshake attempts per session and source IP.
- Do not forward cookies from LAN requests to the localhost backend.
- Do not serve frontend HTML, static assets, setup routes, auth routes, or admin routes.
- Log security-relevant events without logging bearer tokens or full pairing payloads.

Recommended body limits:

- handshake: 32 KB
- sync changes: response pagination, no unbounded result sets
- manual transaction: 64 KB
- capture upload: configurable, start with 25 MB

## Token And Device Lifecycle

Add desktop UI controls for paired devices:

- device name
- platform
- first paired time
- last sync time
- token expiry or rotation state
- revoke button

Backend requirements:

- Store sync tokens hashed.
- Scope sync tokens to a single device id and user.
- Rotate token on re-pair.
- Revoke token immediately when the user removes a device.
- Return `401` for revoked tokens.
- Consider max token lifetime before broad beta, even if refresh is manual.

## Transport Encryption Roadmap

First secure LAN version can ship with HTTP on trusted LAN plus strong token controls, because this is local and temporary.

Before wider distribution, add one of:

- HTTPS with a generated local desktop certificate and QR-carried fingerprint.
- Pairing-derived request encryption at the application layer.

Recommended future direction:

- Generate a desktop keypair.
- Include public key fingerprint in QR payload.
- During handshake, derive a shared secret.
- Use that to authenticate mobile requests or pin the local HTTPS certificate.

## Implementation Phases

### Phase 1: Immediate Development Fix

- Keep `adb reverse tcp:18765 tcp:18765` documented for USB development.
- Add troubleshooting copy explaining that `127.0.0.1` in Android means the phone.
- No product behavior change.

### Phase 2: Temporary Mobile Bridge

- Add Electron-side bridge lifecycle:
  - start
  - stop
  - status
  - expiry timer
- Add private interface discovery.
- Add route allowlist.
- Add request body limits.
- Add request source validation.
- Generate QR payloads with bridge endpoint.
- Stop bridge automatically after pairing expiry.

### Phase 3: Desktop Pairing UI Hardening

- Add risk disclosure modal.
- Add status panel and `Stop sharing`.
- Add paired device management.
- Add clear error states:
  - no private network found
  - firewall blocked
  - listener start failed
  - pairing expired
  - phone reached desktop but token invalid

### Phase 4: Mobile QR Scanning

- Android QR scanner.
- iOS QR scanner.
- Keep manual paste fallback.
- Add scanner permission copy and denial state.
- Add scan-to-pair smoke tests where practical.

### Phase 5: Security Tests And Release Gate

- Unit test private interface selection.
- Unit test endpoint payload generation.
- Unit test bridge allowlist rejects unknown routes.
- Unit test token expiry and one-time use.
- Integration test that LAN bridge does not serve `/`, `/setup`, `/api/v1/auth/me`, or frontend assets.
- Integration test successful pairing and sync through bridge endpoint.
- Add release checklist item: verify no new `0.0.0.0` or public bind default.

## Code Areas

Likely desktop files:

- `src/main/runtime.ts`
- `src/main/ipc.ts`
- `src/shared/contracts.ts`
- `vendor/frontend/src/pages/SettingsPage.tsx`
- `overrides/frontend/src/pages/SettingsPage.tsx`
- `vendor/backend/src/lidltool/api/http_server.py`
- `overrides/backend/src/lidltool/api/http_server.py`
- `vendor/backend/src/lidltool/mobile/pairing.py`
- `overrides/backend/src/lidltool/mobile/pairing.py`

Likely Android files:

- `vendor/mobile/android-harness/app/build.gradle.kts`
- `vendor/mobile/android-harness/app/src/main/AndroidManifest.xml`
- `vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/MainActivity.kt`
- `vendor/mobile/android-harness/app/src/main/java/com/lidltool/androidharness/HarnessViewModel.kt`

Likely iOS files:

- `vendor/mobile/ios-harness/Features/Auth/LoginView.swift`
- `vendor/mobile/ios-harness/Services/Auth/HarnessStore.swift`
- `vendor/mobile/ios-harness/Services/API/APIClient.swift`
- `vendor/mobile/ios-harness/LidlToolHarness.xcodeproj/project.pbxproj`

## Acceptance Criteria

Implementation status:
- The first hardening pass is implemented with an Electron-owned bridge in `src/main/mobile-bridge.ts`.
- The bridge starts only after the Settings risk modal, binds to one selected private IPv4 interface, forwards only the mobile allowlist, strips cookies by construction, enforces request body limits, and closes on timeout or explicit `Stop sharing`.
- Native Android and iOS pairing screens now support QR scanning plus the existing manual paste fallback.

- Fresh install starts localhost-only.
- LAN mobile listener is closed until the user explicitly enables pairing.
- Enabling pairing shows a risk modal before binding any LAN port.
- QR payload uses a LAN-reachable bridge URL, not `127.0.0.1`, for Wi-Fi pairing.
- Android can scan the QR code and pair without copy/paste.
- iOS can scan the QR code and pair without copy/paste.
- Unknown LAN routes receive `404` or `403`.
- Normal desktop UI/auth/setup routes are not reachable through the mobile bridge.
- Pairing token cannot be reused.
- Expired pairing token fails.
- Revoked mobile device cannot sync.
- `npm run typecheck` and `npm run build` pass from repo root after desktop changes.
- Android debug build passes after scanner changes.
- iOS simulator build passes after scanner changes.
