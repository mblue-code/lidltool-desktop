# Desktop Update Flow

LidlTool Desktop uses `electron-updater` with a generic HTTPS feed. The update base URL is configured at release time with `LIDLTOOL_DESKTOP_UPDATE_BASE_URL`; live infrastructure URLs must not be committed.

Channels:

- `beta` checks only the beta feed.
- `stable` checks only the stable feed.
- development builds do not check updates unless `LIDLTOOL_DESKTOP_ALLOW_DEV_UPDATES=1`.

The runtime appends the channel path to the configured base URL when needed, for example `https://updates.example.invalid/lidltool-desktop/beta`.

Manual flow:

1. Check for updates.
2. Download the available update.
3. Restart to install.

Auto-download is disabled for the first production hardening pass. Updates are disabled when no update base URL is configured.

Local testing:

```bash
npm run updates:serve-local -- ./dist_electron
LIDLTOOL_DESKTOP_UPDATE_BASE_URL=http://127.0.0.1:47821 LIDLTOOL_DESKTOP_ALLOW_DEV_UPDATES=1 npm run dev
```

Rollback policy:

- Do not replace a broken release with the same version.
- Publish a higher version.
- Pull or edit update metadata to stop rollout if needed.

Production blocker: macOS production auto-updates require signed and notarized apps. Final macOS Developer ID signing, notarization, and Windows Authenticode signing are intentionally deferred.
