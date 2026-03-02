# lidl-receipts-cli

Personal data ingestion CLI for Lidl Plus (Germany). Authenticates once via OAuth PKCE, syncs all digital receipts into a local SQLite database, differentiates three discount types, and exposes analytics and export commands.

## Features

- **One-shot auth** — headful browser PKCE flow with `LidlPlusNativeClient`, refresh token stored in encrypted `0600` JSON (`keyring` is optional)
- **Full + incremental sync** — 238+ receipts fetched from `www.lidl.de/mre/api/v1/tickets`, idempotent (deduped by receipt ID + fingerprint hash)
- **Discount differentiation** — three types parsed from HTML receipts:
  - `lidl_plus` — Lidl Plus member discount (`100001000-*` / `100001001-*` promotion IDs)
  - `promotion` — regular Aktionsrabatt (any other promotion ID)
  - `mhd` — 20% best-before date discount (`_DISCOUNT2` promotion ID)
- **Normalized SQLite schema** — SQLAlchemy models, Alembic migrations, Postgres-ready
- **Analytics** — monthly spend totals, top stores, category breakdowns
- **JSON export** — all receipts as a flat JSON array
- **OpenCLAW adapter** — stdin/stdout JSON interface for AI tool use
- **OCR ingestion API (Sprint 13)** — HTTP upload/process/status endpoints with pluggable OCR providers (external API + local Tesseract fallback)

## Requirements

- Python 3.11+
- macOS / Linux (Windows untested)
- A Lidl Plus account registered in Germany

## Desktop Side-App Scaffold

For a distributable one-click desktop path (macOS + Windows), there is now a dedicated Electron app at `apps/desktop`.

- Purpose: host the full self-hosted UI inside Electron while orchestrating local backend/scrapers.
- Scope: separate desktop packaging/runtime layer that can bundle frontend + backend runtime.
- Start here: `apps/desktop/README.md`

## Install

```bash
git clone https://github.com/mblue-code/lidl-receipts-cli.git
cd lidl-receipts-cli
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install chromium
```

Optional local keychain integration:

```bash
pip install -e .[dev,keyring]
```

## Quick Start

### 0. Initialize database schema

```bash
make db-upgrade
```

This applies Alembic migrations to `./lidltool.sqlite` (or set `DB_FILE=...`).

### 1. Bootstrap auth (first run only)

```bash
lidltool auth bootstrap
```

This opens a headful browser at the Lidl Plus OAuth login page (German locale). After you log in, the PKCE authorization code is intercepted automatically, exchanged for a refresh token, and stored securely. You should see:

```
Browser open: log in to Lidl Plus (complete CAPTCHA / MFA if shown).
The refresh token will be captured automatically after login.
Refresh token captured and exchanged automatically.
ok
```

No manual token copying needed. If automatic capture fails (rare), the CLI will prompt you to paste the token.

### 2. Full sync (first run)

```bash
lidltool sync --full
```

Fetches all available receipts (~238 for a 2.5-year history). Takes 2–4 minutes at the default rate of 2 req/s.

```
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric           ┃ Value ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━┩
│ Pages            │ 24    │
│ Receipts seen    │ 238   │
│ New receipts     │ 238   │
│ New items        │ 2222  │
└──────────────────┴───────┘
```

### 3. Incremental sync (daily / cron)

```bash
lidltool sync
```

Fetches only new receipts since the last sync. Stops automatically once it encounters already-ingested receipts.

### 4. Monthly stats

```bash
lidltool stats month --year 2025
lidltool stats month --year 2025 --month 6
```

### 5. Export to JSON

```bash
lidltool export --out receipts.json
```

### 6. Machine-readable output

Any command accepts `--json` for stdout JSON:

```bash
lidltool --json sync
lidltool --json stats month --year 2025
```

### 7. Import Amazon order history JSON

Use an Amazon order export JSON (for example from the browser extension
`order-history-exporter-for-amazon`) and import it into the same normalized database.

```bash
lidltool amazon import --in amazon-orders.json
```

Optional source metadata:

```bash
lidltool amazon import --in amazon-orders.json --source amazon_de --store-name Amazon
```

### 8. Direct Amazon connector (session auth + live sync)

Bootstrap Amazon session once (headful browser):

```bash
lidltool amazon auth bootstrap --domain amazon.de
```

This stores Playwright session state at:

```text
~/.config/lidltool/amazon_storage_state.json
```

Set `LIDLTOOL_CONFIG_DIR` to move this (and all other session/token files) under another directory, for example `/config` in Docker.

Run direct sync (fetches orders from Amazon pages, then imports to DB):

```bash
lidltool amazon sync --domain amazon.de --years 2 --max-pages-per-year 8
```

If the session expires, re-run `lidltool amazon auth bootstrap`.

Print cron line for daily Amazon sync:

```bash
lidltool amazon cron-example
```

### 9. Direct REWE connector (session auth + live sync)

Bootstrap REWE session once (headful browser):

```bash
lidltool rewe auth bootstrap --domain shop.rewe.de
```

This stores Playwright session state at:

```text
~/.config/lidltool/rewe_storage_state.json
```

Run direct sync (fetches REWE order-history pages and ingests canonically):

```bash
lidltool rewe sync --domain shop.rewe.de --max-pages 10
```

If the session expires, re-run `lidltool rewe auth bootstrap`.

### 10. Direct Kaufland connector (session auth + live sync)

Bootstrap Kaufland session once (headful browser):

```bash
lidltool kaufland auth bootstrap --domain www.kaufland.de
```

This stores Playwright session state at:

```text
~/.config/lidltool/kaufland_storage_state.json
```

Run direct sync (fetches Kaufland order-history pages and ingests canonically):

```bash
lidltool kaufland sync --domain www.kaufland.de --max-pages 10
```

If the session expires, re-run `lidltool kaufland auth bootstrap`.

### 11. Direct dm connector (session auth + live sync)

Bootstrap dm session once (headful browser):

```bash
lidltool dm auth bootstrap --domain www.dm.de
```

This stores Playwright session state at:

```text
~/.config/lidltool/dm_storage_state.json
```

Run direct sync (fetches dm order-history pages and ingests canonically):

```bash
lidltool dm sync --domain www.dm.de --max-pages 10
```

If the session expires, re-run `lidltool dm auth bootstrap`.

### 12. Direct Rossmann connector (session auth + live sync)

Bootstrap Rossmann session once (headful browser):

```bash
lidltool rossmann auth bootstrap --domain www.rossmann.de
```

This stores Playwright session state at:

```text
~/.config/lidltool/rossmann_storage_state.json
```

Run direct sync (fetches Rossmann order-history pages and ingests canonically):

```bash
lidltool rossmann sync --domain www.rossmann.de --max-pages 10
```

If the session expires, re-run `lidltool rossmann auth bootstrap`.

### 13. OCR document ingestion API (upload + process + status)

Start the OCR API server:

```bash
lidltool serve --host 127.0.0.1 --port 8000
```

`lidltool-ocr-api` remains available as a legacy alias.

Start the durable OCR/sync worker (queue consumer):

```bash
lidltool-job-worker --once --db ~/.local/share/lidltool/db.sqlite
```

Upload an image/PDF receipt:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -F "db=~/.local/share/lidltool/db.sqlite" \
  -F "file=@/path/to/receipt.png;type=image/png"
```

Trigger OCR processing:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/documents/<document_id>/process" \
  -F "db=~/.local/share/lidltool/db.sqlite"
```

Poll status:

```bash
curl -s "http://127.0.0.1:8000/api/v1/documents/<document_id>/status?db=~/.local/share/lidltool/db.sqlite"
```

HTTP auth (when `openclaw_auth_mode = "enforce"` and `openclaw_api_key` is configured):

```bash
curl -s "http://127.0.0.1:8000/api/v1/reliability/slo?db=~/.local/share/lidltool/db.sqlite" \
  -H "X-API-Key: <api_key>"
```

`Authorization: Bearer <api_key>` is also accepted. Query/form `api_key` fields are rejected with `400`.

OCR provider routing:

- Preferred provider is configured via `LIDLTOOL_OCR_DEFAULT_PROVIDER` (`external_api` or `tesseract`).
- External OCR API is configured via `LIDLTOOL_OCR_EXTERNAL_API_URL` and `LIDLTOOL_OCR_EXTERNAL_API_KEY`.
- If enabled (`LIDLTOOL_OCR_FALLBACK_ENABLED=true`), failures in the preferred provider fall back to the other provider.
- Local fallback requires `tesseract` available on `PATH`.

### 14. OCR review queue API (Sprint 14)

Low-confidence OCR results are routed into a review queue (`review_status=needs_review`) when
transaction confidence is below `LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD` (default `0.80`).

List pending review items:

```bash
curl -s "http://127.0.0.1:8000/api/v1/review-queue?db=~/.local/share/lidltool/db.sqlite"
```

Fetch detailed review payload (document + transaction + items + confidence metadata):

```bash
curl -s "http://127.0.0.1:8000/api/v1/review-queue/<document_id>?db=~/.local/share/lidltool/db.sqlite"
```

Apply a transaction correction:

```bash
curl -s -X PATCH "http://127.0.0.1:8000/api/v1/review-queue/<document_id>/transaction?db=~/.local/share/lidltool/db.sqlite" \
  -H "content-type: application/json" \
  -d '{"actor_id":"reviewer-1","reason":"ocr typo","corrections":{"merchant_name":"Corrected Store"}}'
```

Approve or reject a review item:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/review-queue/<document_id>/approve?db=~/.local/share/lidltool/db.sqlite" \
  -H "content-type: application/json" \
  -d '{"actor_id":"reviewer-1","reason":"validated"}'
```

All correction/decision actions write audit events and persist `training_hints` for parser improvements.

### 15. Manual one-off transaction ingestion

For purchases from merchants where you do not want a full connector, you can insert a canonical
transaction directly:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/transactions/manual?db=~/.local/share/lidltool/db.sqlite" \
  -H "content-type: application/json" \
  -d '{
    "purchased_at":"2026-02-20T10:15:00+00:00",
    "merchant_name":"MediaMarkt",
    "total_gross_cents":129900,
    "idempotency_key":"manual-laptop-2026-02-20",
    "items":[{"name":"Laptop","line_total_cents":129900,"qty":1}]
  }'
```

OpenClaw can ingest the same one-off purchase via action `manual_ingest`.

### 16. Dashboard Analytics API + UI (Sprint 15)

Dashboard HTTP endpoints (all return the standard envelope: `ok`, `result`, `warnings`, `error`):

```bash
# Cards (paid/saved totals + savings rate)
curl -s "http://127.0.0.1:8000/api/v1/dashboard/cards?db=~/.local/share/lidltool/db.sqlite&year=2026&month=2"

# Trends (last N months ending at end_month)
curl -s "http://127.0.0.1:8000/api/v1/dashboard/trends?db=~/.local/share/lidltool/db.sqlite&year=2026&months_back=6&end_month=2"

# Savings breakdown (native or normalized)
curl -s "http://127.0.0.1:8000/api/v1/dashboard/savings-breakdown?db=~/.local/share/lidltool/db.sqlite&year=2026&month=2&view=normalized"

# Savings by retailer composition
curl -s "http://127.0.0.1:8000/api/v1/dashboard/retailer-composition?db=~/.local/share/lidltool/db.sqlite&year=2026&month=2"
```

OpenClaw action parity is available with:

- `dashboard_cards`
- `dashboard_trends`
- `dashboard_savings_breakdown`
- `dashboard_retailer_composition`

Frontend dashboard (new `frontend/` app):

```bash
cd frontend
npm install
VITE_DASHBOARD_API_BASE=http://127.0.0.1:8000 \
VITE_DASHBOARD_DB=~/.local/share/lidltool/db.sqlite \
npm run dev
```

Then open `http://127.0.0.1:5173`.

## Discount Data

Each receipt item stores a `discounts` JSON array. Each entry has:

```json
{
  "type": "lidl_plus",
  "promotion_id": "100001000-DE-TEMPLATE-DEAS000284044-1",
  "amount_cents": -65,
  "label": "Lidl Plus Rabatt -0,65"
}
```

Example query — total savings by type:

```sql
SELECT json_extract(d.value,'$.type') AS type,
       COUNT(*) AS n,
       ROUND(SUM(json_extract(d.value,'$.amount_cents')) / -100.0, 2) AS saved_eur
FROM receipt_items ri, json_each(ri.discounts) d
WHERE json_array_length(ri.discounts) > 0
GROUP BY 1 ORDER BY saved_eur DESC;
```

## Configuration

All options can be set via CLI flags, a TOML config file (`~/.config/lidltool/config.toml` by default), or environment variables.

| Option | Env var | Default |
|--------|---------|---------|
| DB path | `LIDLTOOL_DB` | `~/.local/share/lidltool/db.sqlite` |
| Config directory | `LIDLTOOL_CONFIG_DIR` | `~/.config/lidltool` |
| Config file | `LIDLTOOL_CONFIG` | `~/.config/lidltool/config.toml` |
| Log level | `LIDLTOOL_LOG_LEVEL` | `INFO` |
| Credential encryption key | `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY` | _(required for `lidltool serve` unless encryption is explicitly disabled)_ |
| OCR storage path | `LIDLTOOL_DOCUMENT_STORAGE_PATH` | `~/.local/share/lidltool/documents` |
| OCR max upload (MB) | `LIDLTOOL_MAX_UPLOAD_SIZE_MB` | `12` |
| OCR default provider | `LIDLTOOL_OCR_DEFAULT_PROVIDER` | `external_api` |
| OCR fallback enabled | `LIDLTOOL_OCR_FALLBACK_ENABLED` | `true` |
| OCR review confidence threshold | `LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD` | `0.80` |
| OCR external API URL | `LIDLTOOL_OCR_EXTERNAL_API_URL` | _(unset)_ |
| OCR external API key | `LIDLTOOL_OCR_EXTERNAL_API_KEY` | _(unset)_ |

See `/Volumes/macminiExtern/lidl-receipts-cli/.env.example` for Docker-focused defaults.

## Cron

```bash
# Daily incremental sync at 06:00
0 6 * * * /path/to/.venv/bin/lidltool sync >> ~/.local/share/lidltool/cron.log 2>&1

# Weekly full sync on Sunday at 05:30 (catches anything missed)
30 5 * * 0 /path/to/.venv/bin/lidltool sync --full >> ~/.local/share/lidltool/cron.log 2>&1
```

See `scripts/cron_example.txt` for the full snippet.

## Development

```bash
make setup      # install + pre-commit hooks
make lint       # ruff + black check
make test       # pytest
```

Frontend:

```bash
cd frontend
npm run build
```

## OpenClaw Async Sync Jobs

OpenClaw `sync` now creates async ingestion jobs and returns `job_id`.
Poll progress via `sync_status` using that `job_id`.

Sprint 5 Source management contracts are available:

- `sources_list` for Sources page cards and global/per-source trigger hints.
- `source_status` for deterministic source status (`connected`, `expired_auth`, `healthy`, `failing`).
- `sync` supports optional source-scoped trigger via `params.source`.
- `sync_status` (`job_id` mode) exposes additive `progress`, `timeline`, and `warnings` fields.
- Source routing now includes `lidl_plus_de`, `amazon_de`, `rewe_de`, `kaufland_de`, `dm_de`, and `rossmann_de` in async job mode.

Sprint 6 recovery/auth contracts are additive:

- `source_auth_status`, `source_auth_reauth_start`, `source_auth_reauth_confirm`.
- `sources_list` and `source_status` include `auth`, `recovery`, and `sync_history` blocks.
- `sync_status` includes stable recovery fields: `failure_classification`, `recommended_recovery_action`, `capabilities`, `recovery_message`.
- User-triggered source actions write additive `audit_events` rows.

Sprint 9 reliability additions:

- Repeated retry failures are dead-lettered using `retry_dead_letter_threshold`.
- `sync_status` (`job_id` mode) includes additive `dead_letter` metadata when applicable.
- `connector_health_dashboard` provides per-source health metrics and alert signals.
- `stats_month` now returns additive `query_duration_ms` profiling data.

Sprint 12 wave-closure additions:

- `connector_cost_performance_review` provides connector-level performance and cost-proxy trend signals.
- Wave 1B closure artifacts document six-source operational readiness.
- `manual_ingest` provides OpenClaw safe-write ingestion for one-off transactions.

See:

- `docs/api/openclaw-v1-contract.md`
- `docs/api/openclaw-v1-runbook.md`
- `docs/connectors/sdk.md`
- `docs/ops/incident-triage-playbook-v1.md`
- `docs/ops/wave1a-operational-readiness-checklist.md`
- `docs/ops/wave1b-operational-readiness-checklist.md`
- `docs/ops/six-source-coverage-report.md`
- `docs/ops/connector-rollout-context-2026-02-20.md`
- `docs/security/threat-model.md`
- `docs/security/security-hardening-checklist.md`
- `docs/ops/security-runbook.md`
- `docs/reports/sprint19-security-audit.md`

## Notes

- The active receipt API is `www.lidl.de/mre/api/v1/tickets`. The older `tickets.lidlplus.com` endpoint is unreachable.
- Receipt HTML is parsed via Python's `html.parser` using `data-*` attributes — no browser required after auth.
- Tokens are never committed. The `.gitignore` excludes `*.sqlite`, `token.json`, and `.env`.

## License

MIT
