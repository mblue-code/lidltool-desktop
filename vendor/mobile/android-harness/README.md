# Android Native Companion

This is the native Android foundation for the LidlTool Desktop mobile companion.

The app is local-first and desktop-paired:
- pair with a desktop-generated QR payload
- store pairing, sync metadata, capture queue, transactions, and budget summary locally
- import receipt images/PDFs into app-private storage
- upload queued captures to Desktop during explicit foreground sync
- pull desktop-owned OCR status, transactions, transaction items, and budget summary back to the phone

It is not a self-hosted backend client and does not use Firebase push or a public cloud account flow.

## Protocol

Current desktop endpoints:
- `POST /api/mobile-pair/v1/handshake`
- `POST /api/mobile-captures/v1`
- `GET /api/mobile-sync/v1/changes?cursor=...`

The desktop app creates the QR/session payload with:
- `POST /api/mobile-pair/v1/sessions`

## Local Use

Build from this folder:

```bash
./gradlew :app:assembleDebug
```

On this machine the build was verified with Android Studio `2024.3` from
`/Volumes/macminiExtern/Applications/Android Studio.app` and the Android SDK at
`/Volumes/macminiExtern/DevData/Android/sdk`.

The manifest allows cleartext LAN HTTP for local desktop pairing. Do not expose the desktop service directly to the public internet.
