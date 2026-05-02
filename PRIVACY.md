# Privacy

Outlays Desktop is local-first.

Receipt data, local databases, backups, document storage, retailer sessions, and AI chat content stay on your computer unless you explicitly export, back up, upload, or attach them somewhere yourself.

This project is independent and is not affiliated with Lidl or any retailer.

## Automatic Error Reporting

Automatic error reporting is off by default.

It only sends events when all of the following are true:

- the build was configured with a Sentry-compatible DSN
- desktop telemetry is enabled for the release
- you enable error reporting in the app privacy controls

Diagnostic log sharing is a separate preference.

## What Error Reports Must Not Include

When enabled, error reports are intended to be sanitized and limited to runtime details that help debug the app. They must not include:

- receipt contents
- credentials or tokens
- scraped retailer HTML
- screenshots
- databases
- document storage
- AI chat content

## Diagnostics Bundles

Diagnostics bundles are created locally from the Control Center or Help menu. They are redacted and intentionally exclude personal data and credential-bearing files.

You decide whether to attach a generated bundle to a bug report.

## Release-Time Configuration

Release/update endpoints and telemetry endpoints are configured at release time through environment variables. Real DSNs, auth tokens, private infrastructure URLs, and source-map upload tokens must not be committed to this repository.
