# Diagnostics And Bug Reporting

Outlays Desktop supports two reporting paths:

- GitHub Issues for user-visible bugs and feedback
- optional Sentry-compatible crash and error reporting for release builds

The intended self-hosted telemetry target is GlitchTip, but the integration is Sentry-compatible rather than vendor-locked.

## Default Behavior

Automatic error reporting is disabled by default.

It becomes active only when:

- a release is configured with `OUTLAYS_DESKTOP_GLITCHTIP_DSN` or `OUTLAYS_DESKTOP_SENTRY_DSN`
- `OUTLAYS_DESKTOP_TELEMETRY` is set to `errors` or `errors_with_logs`
- the user enables error reporting in the desktop privacy preferences

See [public-repo-boundary.md](public-repo-boundary.md) for which values must stay out of the public repo.

## Example Release-Time Configuration

```bash
OUTLAYS_DESKTOP_GLITCHTIP_DSN=https://public-key@example.com/1
OUTLAYS_DESKTOP_TELEMETRY=errors
OUTLAYS_DESKTOP_RELEASE_CHANNEL=beta
OUTLAYS_DESKTOP_ISSUES_URL=https://github.com/example/outlays-desktop/issues/new
```

## Telemetry Modes

- `off`: no automatic error reporting
- `errors`: capture sanitized main-process and renderer exceptions
- `errors_with_logs`: reserved for future log-forwarding behavior; diagnostics bundles remain user-created

## Diagnostics Bundles

Users can create a diagnostics bundle from the Diagnostics card or Help menu.

Current bundle contents:

- `diagnostics.json`
- redacted `window-lifecycle.log`, when present

The bundle must not include:

- receipt databases or exports
- document storage
- credentials or tokens
- scraped retailer HTML
- screenshots
- AI chat content

The user decides whether to attach the generated bundle to a GitHub issue or share it privately.

## Release Validation

Before publishing a release:

1. Confirm `OUTLAYS_DESKTOP_RELEASE_CHANNEL` is set correctly.
2. Confirm the telemetry DSN points to the intended project.
3. Run `npm run typecheck`.
4. Run `npm run build`.
5. Generate a test diagnostics bundle and inspect it manually.
