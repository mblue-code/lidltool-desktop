# PENNY Receipt Plugin

This repo-managed plugin is the external `penny_de` grocery receipt connector.

What it does now:

- runs through the public external receipt-plugin runtime
- keeps Penny-specific auth state and diagnostics inside the plugin
- uses the real `account.penny.de` PKCE login shape from the Android app
- tries to reuse a logged-in normal Chrome Penny session before falling back to the desktop-hosted external Chrome callback flow
- discovers live Penny eBons directly from `api.penny.de`
- fetches the eBon PDF and parses the text layer into receipt items, discounts, totals, and store metadata
- supports both `self_hosted` and `electron`
- supports fixture mode for offline contract validation

What is proven:

- the Android app package is `de.penny.app`
- login opens `account.penny.de` in a browser surface with client id `pennyandroid`
- the redirect target is `https://www.penny.de/app/login`
- the app bridges auth into `account-ui` through `https://account.penny.de/realms/penny/cookie-setter?redirect=account-ui`
- the OAuth access token contains the `rewe_id` claim required by the eBon backend
- the authenticated eBon list endpoint works at `https://api.penny.de/api/tenants/penny/customers/{rewe_id}/ebons`
- the authenticated eBon PDF endpoint works at `https://api.penny.de/api/tenants/penny/customers/{rewe_id}/ebons/{id}/pdf`
- live sync can run over direct host-side HTTP with stored plugin OAuth state, without emulator state or Android token extraction

Current connector options:

- `state_file`: optional persistent plugin state path
- `fixture_file`: optional offline JSON fixture for local testing only
- `merchant_label`: optional display-name override for normalized receipts
- `import_storage_state_file`: import an existing browser storage-state JSON directly
- `chrome_cookie_export`: try to reuse the currently logged-in normal Chrome Penny session, default `true`
- `chrome_user_data_dir`: override Chrome user-data directory detection
- `chrome_profile_name`: select the Chrome profile directory, default `Default`
- `auth_timeout_seconds`: optional browser-login timeout, default `900`
- `timeout_seconds`: optional OIDC metadata/token timeout, default `30`
- `force_reauth`: start a fresh Penny auth flow even if plugin-local state already exists

Self-hosted operator flow:

1. Enable/install the external `penny_de` plugin.
2. Open Penny in normal Chrome and log in there if you want the connector to try Chrome-session reuse first.
3. Run the normal connector auth/bootstrap action.
4. The plugin first tries to import the running Chrome session. If that fails, desktop starts a PKCE flow, shows the exact PENNY login URL, and waits for the callback URL. Open that URL in your normal browser profile, finish the Penny login there, then either let desktop capture the callback automatically from a supported Chromium browser or paste the final redirect URL back into the app.
5. Run discovery or sync. The plugin will refresh stored OAuth when needed, call the Penny eBon backend directly, and parse receipt PDFs locally.

Suggested self-hosted config:

```toml
connector_plugin_search_paths = ["./plugins"]
connector_external_runtime_enabled = true
connector_external_receipt_plugins_enabled = true
connector_external_allowed_trust_classes = ["local_custom"]
```

Desktop pack build from this repository root:

```bash
python3 fixtures/plugin-sources/penny_de/build_desktop_pack.py --output-dir build/plugin-packs
```

That produces a manual-import desktop ZIP with the Electron-compatible payload layout.
