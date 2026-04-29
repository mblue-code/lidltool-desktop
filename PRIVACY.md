# Privacy

LidlTool Desktop is local-first. Receipt data, local databases, backups, document storage, retailer sessions, and AI chat content stay on your computer unless you explicitly export, back up, upload, or attach them somewhere yourself.

Automatic error reporting is off by default. It only sends events when a release is configured with a Sentry-compatible DSN and you enable error reporting in the desktop privacy controls. Diagnostic log sharing is a separate toggle.

When enabled, error reports are sanitized and limited to app/runtime details useful for debugging. They must not include receipt contents, credentials, tokens, scraped retailer HTML, screenshots, databases, document storage, or AI chat content.

Diagnostics bundles are created locally from the Control Center or Help menu. They are redacted and intentionally exclude personal data and credential-bearing files. You decide whether to attach a generated bundle to a bug report.

Release/update endpoints and telemetry endpoints are configured at release time through environment variables. Real DSNs, auth tokens, VPS URLs, and source-map upload tokens must not be committed to this repository.
