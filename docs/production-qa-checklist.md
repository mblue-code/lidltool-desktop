# Production QA Checklist

- Fresh install launches on macOS and Windows.
- Upgrade from the previous version preserves local profile state.
- Update check shows disabled state when no update feed is configured.
- Update check finds no update against an empty local feed.
- Update check finds an available update against a valid local feed.
- Update download shows progress and reaches downloaded state.
- Restart to update installs the downloaded update in signed production builds.
- Update failure shows sanitized errors and does not expose tokens or private URLs.
- Create Diagnostics Bundle produces a redacted zip.
- Report a Problem opens the GitHub issue path.
- Open Logs Folder opens the Electron `userData` folder.
- Privacy toggles persist across app restart.
- Backup, export, and restore still work from local paths.
- Connector install, update, enable, disable, and remove flows still work.
- Windows installer installs and uninstalls cleanly.
- macOS app launches without quarantine/signing surprises in the tested distribution mode.

Before public production release, repeat the update install/restart checks with real signed and notarized macOS artifacts and signed Windows artifacts.
