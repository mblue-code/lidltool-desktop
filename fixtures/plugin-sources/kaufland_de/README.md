# Kaufland Receipt Plugin

This repo-managed plugin is the external `kaufland_de` grocery receipt connector.

What it does now:

- runs through the public external receipt-plugin runtime
- keeps Kaufland-specific auth, token refresh, sync, normalization, and diagnostics inside the plugin
- uses the Android-app backend shape instead of the misleading marketplace order-history scraper
- supports both `self_hosted` and `electron`

Backend model:

- browser auth through Kaufland's Cidaas PKCE flow
- user bootstrap through `https://app.kaufland.net/users-srv/userinfo`
- receipt sync through `https://p.crm-dynamics.schwarz/api/v2/customers/{sub}/transactions`
- headless refresh through the stored Cidaas refresh token

Current connector options:

- `state_file`: optional persistent plugin state path
- `country_code`: receipt country sent to the transaction API, default `DE`
- `preferred_store_id`: optional Kaufland home-store id forwarded during auth and refresh
- `store_name`: optional display-name override for normalized receipts
- `auth_timeout_seconds`: optional browser-login timeout, default `900`
- `timeout_seconds`: optional live HTTP timeout, default `30`
- `lookup_limit`: optional fallback scan size when fetching a known record not present in the current cache
- `fixture_file`: optional offline JSON fixture for local testing only
- `force_reauth`: ignore stored auth state and mint a fresh browser flow during `start_auth`

Notes:

- this plugin targets grocery receipts visible in the Kaufland mobile app, not `www.kaufland.de` marketplace orders
- `preferred_store_id` is separate from `country_code`; the Android app forwards both concepts differently
- the first cut assumes the receipt country is `DE` unless overridden

Self-hosted operator flow:

1. Enable/install the external `kaufland_de` plugin.
2. Run the normal connector auth/bootstrap action.
3. Complete Kaufland login in the shared browser session.
4. The plugin exchanges the callback code, stores the refresh token, resolves the Cidaas `sub`, and persists plugin-local state.
5. Later syncs use only host-side HTTP requests and best-effort headless refresh.

Suggested self-hosted config:

```toml
connector_plugin_search_paths = ["./plugins"] # or your installed addon directory
connector_external_runtime_enabled = true
connector_external_receipt_plugins_enabled = true
connector_external_allowed_trust_classes = ["local_custom"]
```

Desktop pack build:

```bash
python3 plugins/kaufland_de/build_desktop_pack.py --output-dir apps/desktop/dist_plugin_packs
```

That produces a manual-import desktop ZIP with the Electron-compatible payload layout.
