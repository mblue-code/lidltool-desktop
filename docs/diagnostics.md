# Diagnostics and Bug Reporting

LidlTool Desktop uses two bug-reporting paths:

- GitHub Issues for user-visible bug reports and beta feedback.
- Optional Sentry-compatible error reporting for automatic crash/error diagnostics. The intended self-hosted target is GlitchTip.

Automatic error reporting is disabled unless a release is configured with `LIDLTOOL_DESKTOP_GLITCHTIP_DSN` or `LIDLTOOL_DESKTOP_SENTRY_DSN` and `LIDLTOOL_DESKTOP_TELEMETRY=errors` or `errors_with_logs`.

See `docs/public-repo-boundary.md` for what belongs in the public repository and what must stay in private release configuration.

## Environment

```bash
LIDLTOOL_DESKTOP_GLITCHTIP_DSN=https://public-key@example.com/1
LIDLTOOL_DESKTOP_TELEMETRY=errors
LIDLTOOL_DESKTOP_RELEASE_CHANNEL=beta
LIDLTOOL_DESKTOP_ISSUES_URL=https://github.com/mblue-code/lidltool-desktop/issues/new
```

Telemetry modes:

- `off`: no automatic error reporting.
- `errors`: capture sanitized main/renderer exceptions and crash-like renderer failures.
- `errors_with_logs`: reserved for later log forwarding; diagnostics bundles are still user-created.

## Diagnostics Bundle

Users can create a diagnostics zip from the Diagnostics card or Help menu. The bundle includes:

- `diagnostics.json`
- redacted `window-lifecycle.log`, when present

The bundle does not include receipt databases, receipt exports, document storage, credentials, tokens, scraped retailer HTML, screenshots, or AI chat content.

## Release Checklist

For beta and production releases:

1. Confirm `LIDLTOOL_DESKTOP_RELEASE_CHANNEL` is set correctly.
2. Confirm the GlitchTip DSN points to the right project.
3. Run `npm run typecheck`.
4. Run `npm run build`.
5. Create a test diagnostics bundle and inspect it before publishing.
