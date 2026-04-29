# Signing And Notarization

Current status: deferred.

This repository has placeholders for production signing, but no real certificate, signing identity, notary credential, Authenticode credential, private key, or trust secret is committed or required for local verification.

macOS production requirements:

- Apple Developer Program membership
- Developer ID Application certificate
- hardened runtime
- notarization credentials
- stapled notarization ticket

Windows production requirements:

- Authenticode code-signing certificate
- timestamp server configuration
- signed installer and executable artifacts

Planned CI secret names:

- `APPLE_ID`
- `APPLE_TEAM_ID`
- `APPLE_APP_SPECIFIC_PASSWORD`
- `CSC_LINK`
- `CSC_KEY_PASSWORD`
- `WINDOWS_CERTIFICATE`
- `WINDOWS_CERTIFICATE_PASSWORD`

These names are documentation placeholders. Do not add real values to the repository. Local build verification must continue to pass without signing credentials until final production signing is implemented.
