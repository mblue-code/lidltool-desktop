# Security Policy

Report vulnerabilities privately to the maintainers before opening a public issue.

Do not post any of the following in public issues:

- credentials or retailer session artifacts
- receipts, exports, local databases, or OCR source files
- diagnostics bundles or raw logs from real users
- LAN mobile pairing payloads or bridge details
- DSNs, auth tokens, source-map tokens, signing credentials, or infrastructure secrets

## What To Include In A Private Report

- affected version
- operating system
- impact
- sanitized reproduction steps
- whether the issue affects packaged builds, development builds, or both

## What Counts As Sensitive Data

- retailer login and session state
- receipt databases, backups, exports, and document storage
- diagnostics archives and crash material from real users
- temporary pairing secrets and local network bridge endpoints
- Sentry-compatible DSNs, upload tokens, signing material, and deployment credentials

Public issues are still appropriate for non-sensitive reproducible bugs after removing private data.
