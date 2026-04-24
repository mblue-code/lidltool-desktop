# REWE Receipt Plugin

`plugins/rewe_de` is a repo-managed external receipt plugin for the REWE web account.

## Current web surfaces

Live account inspection confirmed these authenticated routes:

- `https://www.rewe.de/shop/mydata/meine-einkaeufe`
- `https://www.rewe.de/shop/mydata/meine-einkaeufe/onlineshop`
- `https://www.rewe.de/shop/mydata/meine-einkaeufe/im-markt`
- `https://www.rewe.de/shop/mydata/rewe-bonus`

The `Im Markt` view exposes receipt-specific downloads under:

- `https://www.rewe.de/api/receipts/{receipt_id}/pdf`
- `https://www.rewe.de/api/receipts/{receipt_id}/csv`

Public bundle inspection also exposed structured bonus endpoints under:

- `https://www.rewe.de/api/rewe/loyalty-accounts/me`
- `https://www.rewe.de/api/loyalty-balance/me`
- `https://www.rewe.de/api/loyalty-balance/me/transactions`

## Ingestion strategy

The plugin uses a mixed path on purpose:

- Discovery uses the authenticated web account pages for `Online` and `Im Markt`.
- Session establishment uses imported browser cookies plus REWE's normal web SSO continuation over HTTP instead of depending on a fresh automation-browser login.
- In-market receipt detail prefers the receipt-specific downloads:
  - CSV for structured row data
  - PDF text as a completeness backstop for lossy or missing CSV fields
- Bonus/Guthaben uses the structured loyalty transaction API when available.

This avoids flattening REWE into a generic scraper while still handling the reality that different REWE surfaces expose different levels of structure.

## Auth flow

The plugin implements the public external auth lifecycle itself:

- `start_auth`
- `cancel_auth`
- `confirm_auth`

The intended path is standard REWE web login:

1. email + password
2. email-delivered verification code
3. post-login account area

The captured browser storage state is stored locally in the plugin runtime directory and reused for syncs.

### Cloudflare-safe bootstrap path

REWE can put Cloudflare / Turnstile in front of fresh automation browsers. The plugin therefore supports safer import-first bootstrap options:

- `chrome_cookie_export=true`: export REWE cookies from the currently running logged-in Chrome profile, then complete the standard REWE web SSO continuation over HTTP and persist the refreshed session state
- `import_storage_state_file`: import an existing Playwright storage-state JSON file directly
- `chrome_profile_import=true`: copy a logged-in local Chrome profile, extract browser storage state, then verify/refresh it through the same HTTP continuation path
- `chrome_live_tab=true`: on macOS, use the already-authenticated normal Chrome REWE tab directly instead of replaying the session into a separate browser runtime

The preferred order is:

1. export the currently running normal Chrome REWE session
2. fall back to copied-profile import if that export is unavailable
3. optionally use the already-authenticated normal Chrome REWE tab directly on macOS
4. only then open the shared auth browser flow

That means the operator can log in once in their everyday browser, and the connector can reuse that authenticated session without trying to beat Cloudflare in a brand-new automated browser window.

In live testing, cookie import plus REWE's own SSO continuation was enough to reach `Meine Einkäufe im Markt` and download real `pdf`/`csv` receipt payloads.

### Live Chrome tab mode

`chrome_live_tab=true` is an optional macOS-only fallback/debug path because it keeps all navigation and downloads inside the exact Chrome tab/session that already passed Cloudflare.

Requirements:

- a logged-in REWE tab open in normal Google Chrome
- Chrome menu setting `Darstellung > Entwickler > JavaScript von Apple Events erlauben`

In this mode, the plugin:

- navigates the existing REWE Chrome tab between `Im Markt`, `Online`, and order-detail pages as needed
- runs the same extraction scripts against the live page
- downloads CSV/PDF receipt payloads through the live authenticated tab context

This mode does not depend on Playwright storage-state replay, so it avoids the specific failure where copied/imported cookies are accepted by the website but still challenged or redirected in a new automation browser.

## REWE discount and bonus modeling

The parser keeps REWE-specific semantics distinct:

- ordinary promotions and coupons stay ordinary discounts
- low-MHD / low-freshness reductions are tagged as `low_freshness_reduction`
- multi-buy promotions are tagged as `multibuy_discount`
- redeemed REWE Bonus / Guthaben is tagged as `bonus_credit_redeemed`
- earned REWE Bonus / Guthaben is stored separately under `record["bonus"]["earned"]`

Earned future credit is intentionally not emitted as an ordinary discount row, because it is not an immediate price reduction on the current receipt.

## Limitations

- REWE currently places Cloudflare bot checks in front of the login flow. The plugin now prefers exporting cookies from the already running normal Chrome session and then continuing the normal REWE SSO flow over HTTP. That path is more reliable than replaying the session into a fresh automation browser.
- `chrome_live_tab=true` remains available on macOS, but it requires Chrome to allow Apple Events JavaScript. Treat it as an optional fallback, not the primary operator flow.
- The plugin now detects the REWE challenge page explicitly and fails with a clear blocker instead of silently returning a zero-receipt sync.
- The running-Chrome export path currently depends on access to the local Chrome cookie store and the Chrome Safe Storage secret on the same machine. If that host access is unavailable, `import_storage_state_file` remains the strongest manual fallback.
- Online-order detail parsing is implemented defensively, but live validation in this repo was stronger for the in-market eBon surface than for order-detail downloads.

## Suggested self-hosted config

```toml
connector_plugin_search_paths = ["./plugins"]
connector_external_runtime_enabled = true
connector_external_receipt_plugins_enabled = true
connector_external_allowed_trust_classes = ["local_custom"]
```
