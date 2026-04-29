# Release Process

Beta releases use `LIDLTOOL_DESKTOP_RELEASE_CHANNEL=beta` and a semver prerelease such as `0.2.0-beta.1`. Stable releases use `LIDLTOOL_DESKTOP_RELEASE_CHANNEL=stable` and a non-prerelease semver such as `1.0.0`.

Preflight:

```bash
LIDLTOOL_DESKTOP_RELEASE_CHANNEL=beta \
LIDLTOOL_DESKTOP_UPDATE_BASE_URL=https://updates.example.invalid/lidltool-desktop \
npm run release:preflight
```

Build:

```bash
npm run release:beta
npm run release:stable
```

Source maps:

```bash
GLITCHTIP_AUTH_TOKEN=... \
GLITCHTIP_ORG=... \
GLITCHTIP_PROJECT=... \
LIDLTOOL_DESKTOP_RELEASE=lidltool-desktop@0.2.0-beta.1 \
npm run sourcemaps:upload
```

The upload script fails when required variables are missing and does not print tokens.

Release smoke checks:

- launch a fresh profile
- confirm diagnostics bundle creation
- confirm Help menu actions
- confirm update disabled without an update URL
- confirm update check behavior against a local feed
- verify artifact retention in CI or release storage

Signing is not active in this pass. The release workflow contains TODO-gated placeholders only.
