# Signing And Notarization

Current status: not finished.

This repository already carries the structure needed for production signing, but the actual public release trust chain is still pending.

No real certificate, signing identity, notarization credential, Authenticode credential, private key, or trust secret should ever be committed to this repository.

## macOS Requirements

- Apple Developer Program membership
- Developer ID Application certificate
- hardened runtime
- notarization credentials
- stapled notarization ticket for shipped artifacts

## Windows Requirements

- Authenticode code-signing certificate
- timestamp server configuration
- signed installer and executable artifacts

## Planned CI Secret Names

- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_SPECIFIC_PASSWORD`
- `CSC_LINK`
- `CSC_KEY_PASSWORD`
- `WINDOWS_CERTIFICATE`
- `WINDOWS_CERTIFICATE_PASSWORD`

These are documentation placeholders only.

## Current Rule

Local verification must continue to work without signing credentials. Public production release is still blocked on finishing the real signing and notarization pipeline.
