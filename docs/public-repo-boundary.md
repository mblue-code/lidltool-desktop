# Public Repository Boundary

This repository is intended to be safe to publish as open-source code. Keep the product code, diagnostics behavior, and user-facing reporting workflow public; keep deployment secrets, private infrastructure configuration, and real user diagnostics private.

## Commit To The Public Repo

- Telemetry and diagnostics source code.
- Redaction logic and redaction tests.
- GitHub issue templates.
- Documentation explaining what diagnostics collect and do not collect.
- Example environment variable names with fake values.
- Build scripts that read release secrets from environment variables.
- Update and release scripts that read feed URLs, source-map upload settings, and signing placeholders from environment variables.
- Self-hosting instructions that do not include live credentials.

## Do Not Commit

- Real GlitchTip/Sentry DSNs for production, beta, or private testing.
- GlitchTip/Sentry auth tokens.
- Source-map upload tokens.
- Real update feed hostnames if they reveal private infrastructure.
- Real signing identities, certificate archives, certificate passwords, private keys, notarization credentials, or Authenticode credentials.
- VPS credentials, SSH keys, deployment `.env` files, database passwords, SMTP passwords, or object-storage credentials.
- Real diagnostics bundles from users or maintainers.
- Crash report exports, stack traces, logs, screenshots, databases, receipt exports, scraped retailer HTML, AI chat content, or other data that may contain personal information.
- Private support URLs if they expose non-public infrastructure.

## Release Configuration Rule

Inject production or beta reporting endpoints at release time through CI or local release environment variables:

```bash
LIDLTOOL_DESKTOP_GLITCHTIP_DSN=...
LIDLTOOL_DESKTOP_TELEMETRY=errors
LIDLTOOL_DESKTOP_RELEASE_CHANNEL=beta
LIDLTOOL_DESKTOP_UPDATE_BASE_URL=...
```

Do not hardcode live endpoints or tokens in source files. A GlitchTip/Sentry public DSN is not a credential in the same sense as an auth token, but hardcoding it in a public repo can invite noisy or spam event ingestion.

Run `npm run release:preflight` before release builds. It checks staged `.env` files, diagnostics zips, private key material, obvious secret patterns, invalid channel/version combinations, and new runtime/build `../../` references.

## Before Publishing

1. Run `git diff --staged` and check for live DSNs, tokens, private hostnames, and generated diagnostics zips.
2. Run `rg -n "GLITCHTIP|SENTRY|DSN|TOKEN|SECRET|PASSWORD|PRIVATE|BEGIN .*KEY" .`.
3. Confirm any `.env` or deployment files are examples only.
4. Confirm diagnostics docs still match the current implementation.
