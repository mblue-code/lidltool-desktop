# lidl-receipts-cli

Personal data ingestion CLI for Lidl Plus (Germany). Authenticates once via OAuth PKCE, syncs all digital receipts into a local SQLite database, differentiates three discount types, and exposes analytics and export commands.

## Security Posture

- This service is not intended to be exposed directly to the public internet.
- Supported deployment modes are `localhost-only`, `docker-local`, `private-network/VPN`, and `reverse proxy with TLS`.
- `LIDLTOOL_HTTP_EXPOSURE_MODE` now makes the supported deployment model explicit. Supported modes are `localhost` (default), `container_localhost`, `private_network`, and `reverse_proxy_tls`.
- `lidltool serve` binds to `127.0.0.1` by default, and the default Compose mapping stays `127.0.0.1:8000:8000`.
- Docker-local access is supported through loopback-only published ports. Remote access is supported only through a private-network/VPN boundary or a trusted reverse proxy with TLS.
- Any non-local exposure mode now requires `LIDLTOOL_OPENCLAW_API_KEY` and `openclaw_auth_mode = "enforce"`.
- `reverse_proxy_tls` mode requires `LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS`; trusted proxy CIDRs are rejected in other modes.
- `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY`, `LIDLTOOL_OPENCLAW_API_KEY`, and `LIDLTOOL_AUTH_BOOTSTRAP_TOKEN` reject empty/placeholder/short/repetitive values at startup.
- First-user bootstrap is localhost-only by default. `container_localhost` is also treated as local when the published host port stays loopback-only. Any non-local exposure mode now fails closed until you either finish setup on localhost first or configure `LIDLTOOL_AUTH_BOOTSTRAP_TOKEN` and present it during `/api/v1/auth/setup`.
- Session cookies use `SameSite=Lax` and are marked `Secure` only for direct HTTPS requests or for explicitly trusted proxy CIDRs that forward `proto=https`.
- `POST /api/v1/tools/exec` is disabled by default via `http_tools_exec_enabled = false`; if you explicitly enable it, admin authentication is required.

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
- **OCR ingestion API (Sprint 13)** — HTTP upload/process/status endpoints with local-first VLM OCR, scanned-PDF rasterization, and review queue integration
- **Built-in item categorization** — deterministic-first canonical item categorization with a bundled local Qwen 3.5 fallback for unresolved items
- **Shared local text runtime** — a reusable internal model-runtime subsystem for item categorization today and Pi-agent reuse later, shipped as a Docker sidecar instead of in-process

## Shared Model Runtime

The self-hosted stack ships a bundled local text model runtime as a Docker sidecar. Today it is used by item categorization; the same internal runtime contract is intended to be reused by the Pi agent and other text tasks later.

The current operator knobs remain the `LIDLTOOL_ITEM_CATEGORIZER_*` settings for compatibility. Treat them as shared runtime policy settings, not as feature-specific transport wiring. The categorizer still stays deterministic-first: deposit, source/native category normalization, explicit rules, and product category matches run before the model. If the runtime is unavailable, ingest still falls back cleanly.

Recommended defaults:

```env
LIDLTOOL_ITEM_CATEGORIZER_ENABLED=true
LIDLTOOL_ITEM_CATEGORIZER_BASE_URL=http://item-categorizer:8000/v1
LIDLTOOL_ITEM_CATEGORIZER_MODEL=qwen3.5:0.8b
LIDLTOOL_ITEM_CATEGORIZER_API_KEY=
LIDLTOOL_ITEM_CATEGORIZER_TIMEOUT_S=5.0
LIDLTOOL_ITEM_CATEGORIZER_MAX_RETRIES=0
LIDLTOOL_ITEM_CATEGORIZER_MAX_BATCH_SIZE=16
LIDLTOOL_ITEM_CATEGORIZER_CONFIDENCE_THRESHOLD=0.65
LIDLTOOL_ITEM_CATEGORIZER_OCR_CONFIDENCE_THRESHOLD=0.60
LIDLTOOL_ITEM_CATEGORIZER_ALLOW_REMOTE=false
```

The shipped Docker sidecar is an OpenAI-compatible Qwen service, not an Ollama dependency. The base stack serves `Qwen/Qwen3.5-0.8B` internally as `qwen3.5:0.8b` on `http://item-categorizer:8000/v1`, and the NVIDIA override swaps in a faster GPU-backed vLLM variant behind the same contract. If you prefer a different local endpoint such as SGLang or another host-native OpenAI-compatible service, override the base URL and model name.

On Apple Silicon / Mac Mini hosts, the proven deployment path is:

1. Run the app stack in Docker Compose.
2. Run the local OpenAI-compatible model server natively on macOS.
3. Point both categorization and chat/local-text traffic at that host runtime.

The included override for that path is:

```bash
docker compose -f docker-compose.yml -f docker-compose.item-categorizer-macos-host-mlx.yml up -d
```

It keeps Docker-first app deployment while routing the shared local-text contract to `http://host.docker.internal:18000/v1` for both ingestion categorization and chat/Pi-agent usage. A proven host-native MLX launch command is:

```bash
uvx --from mlx-openai-server mlx-openai-server launch \
  --model-path mlx-community/Qwen3-1.7B-4bit \
  --model-type lm \
  --context-length 4096 \
  --served-model-name mlx-community/Qwen3-1.7B-4bit \
  --host 127.0.0.1 \
  --port 18000 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3 \
  --reasoning-parser qwen3 \
  --prompt-cache-size 8 \
  --max-bytes 2147483648 \
  --max-tokens 1024 \
  --temperature 0.0
```

The older ARM64 Docker CPU override is still in the repo for experimentation:

```bash
docker compose -f docker-compose.yml -f docker-compose.item-categorizer-apple-silicon.yml up -d
```

Treat that override as experimental on Apple Silicon. In the March 30, 2026 live validation on a Mac Mini, the host-native MLX path worked; the ARM64 vLLM CPU Docker path did not reach a healthy `/v1/models`.

Remote OpenAI-compatible endpoints are an optional overlay, not the default dependency. Keep `LIDLTOOL_ITEM_CATEGORIZER_ALLOW_REMOTE=false` for self-hosted operation unless you intentionally point the runtime at a trusted remote provider.

## Requirements

- Python 3.11+
- macOS / Linux (Windows untested)
- A Lidl Plus account registered in Germany

## Desktop Side-App Scaffold

For a distributable one-click desktop path (macOS + Windows), there is now a dedicated Electron app at `apps/desktop`.

- Purpose: host the full self-hosted UI inside Electron while orchestrating local backend/scrapers.
- Scope: separate desktop packaging/runtime layer that can bundle frontend + backend runtime.
- Start here: `apps/desktop/README.md`

## Official Market Bundles

Sprint 9 makes official bundle/profile/release metadata explicit and data-driven.

- Canonical strategy doc: `docs/design/market-bundle-release-strategy.md`
- Canonical catalog: `src/lidltool/connectors/official_market_catalog.json`
- Self-hosted keeps one universal artifact and uses `connector_market_profile` / `LIDLTOOL_CONNECTOR_MARKET_PROFILE` for curated market defaults.
- Trust labeling remains explicit: `official`, `community_verified`, `community_unsigned`, `local_custom`.

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

Direct connector commands now use the generic connector platform entrypoint. Source-specific utility commands such as `lidltool amazon import` and `lidltool amazon cron-example` remain, but auth and sync go through `lidltool connectors ...` with repeatable `--option key=value` flags.

Bootstrap Amazon session once (headful browser):

```bash
lidltool connectors auth bootstrap --source-id amazon_de
```

This stores Playwright session state at:

```text
~/.config/lidltool/amazon_storage_state.json
```

Set `LIDLTOOL_CONFIG_DIR` to move this (and all other session/token files) under another directory, for example `/config` in Docker.

Run direct sync (fetches orders from Amazon pages, then imports to DB):

```bash
lidltool connectors sync --source-id amazon_de --full --option years=2 --option max_pages_per_year=8
```

If the session expires, re-run `lidltool connectors auth bootstrap --source-id amazon_de`.

Print cron line for daily Amazon sync:

```bash
lidltool amazon cron-example
```

### 9. Direct REWE connector (session auth + live sync)

Bootstrap REWE session once (headful browser):

```bash
lidltool connectors auth bootstrap --source-id rewe_de
```

This stores Playwright session state at:

```text
~/.config/lidltool/rewe_storage_state.json
```

Run direct sync (fetches REWE order-history pages and ingests canonically):

```bash
lidltool connectors sync --source-id rewe_de --full --option max_pages=10
```

If the session expires, re-run `lidltool connectors auth bootstrap --source-id rewe_de`.

### 10. Direct Kaufland connector (session auth + live sync)

Bootstrap Kaufland session once (headful browser):

```bash
lidltool connectors auth bootstrap --source-id kaufland_de
```

This stores Playwright session state at:

```text
~/.config/lidltool/kaufland_storage_state.json
```

Run direct sync (fetches Kaufland order-history pages and ingests canonically):

```bash
lidltool connectors sync --source-id kaufland_de --full --option max_pages=10
```

If the session expires, re-run `lidltool connectors auth bootstrap --source-id kaufland_de`.

### 11. dm receipt plugin (session auth + live sync)

The `dm_de` connector now ships as an external receipt plugin. In self-hosted mode,
enable repo-managed plugins from `./plugins`; in desktop mode, install the dm receipt
plugin pack before bootstrap/sync.

Bootstrap dm session once (headful browser):

```bash
lidltool connectors auth bootstrap --source-id dm_de
```

This stores Playwright session state at:

```text
~/.config/lidltool/dm_storage_state.json
```

Run direct sync (fetches dm order-history pages and ingests canonically):

```bash
lidltool connectors sync --source-id dm_de --full --option max_pages=10
```

If the session expires, re-run `lidltool connectors auth bootstrap --source-id dm_de`.

### 12. Direct Rossmann connector (session auth + live sync)

Bootstrap Rossmann session once (headful browser):

```bash
lidltool connectors auth bootstrap --source-id rossmann_de
```

This stores Playwright session state at:

```text
~/.config/lidltool/rossmann_storage_state.json
```

Run direct sync (fetches Rossmann order-history pages and ingests canonically):

```bash
lidltool connectors sync --source-id rossmann_de --full --option max_pages=10
```

If the session expires, re-run `lidltool connectors auth bootstrap --source-id rossmann_de`.

### 13. OCR document ingestion API (upload + process + status)

Start the OCR API server:

```bash
lidltool serve --port 8000
```

`lidltool-ocr-api` remains available as a legacy alias.

By default this binds only to `127.0.0.1` with `LIDLTOOL_HTTP_EXPOSURE_MODE=localhost`. Publishing a port is not an auth boundary. For direct private-network/VPN access, switch to `LIDLTOOL_HTTP_EXPOSURE_MODE=private_network`, bind intentionally (for example `lidltool serve --host 0.0.0.0`), and configure `LIDLTOOL_OPENCLAW_API_KEY`. For TLS reverse-proxy access, use `LIDLTOOL_HTTP_EXPOSURE_MODE=reverse_proxy_tls`, keep or change the bind as appropriate for your proxy topology, configure `LIDLTOOL_OPENCLAW_API_KEY`, and set `LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS` to the exact proxy source networks.

Start the durable OCR/sync worker (queue consumer):

```bash
lidltool-job-worker --once --db ~/.local/share/lidltool/db.sqlite
```

Protected HTTP routes require either an authenticated user session or an approved API-key transport. For non-browser examples below, assume `X-API-Key: <api_key>` is configured.

The HTTP server always uses its configured runtime database and config file. Request-level `db` / `config` overrides are no longer accepted.

Upload an image/PDF receipt:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/documents/upload" \
  -H "X-API-Key: <api_key>" \
  -F "file=@/path/to/receipt.png;type=image/png"
```

Trigger OCR processing:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/documents/<document_id>/process" \
  -H "X-API-Key: <api_key>"
```

Poll status:

```bash
curl -s "http://127.0.0.1:8000/api/v1/documents/<document_id>/status" \
  -H "X-API-Key: <api_key>"
```

HTTP auth:

```bash
curl -s "http://127.0.0.1:8000/api/v1/reliability/slo" \
  -H "X-API-Key: <api_key>"
```

`Authorization: Bearer <api_key>` is also accepted. Query/form `api_key` fields are rejected with `400`.

Docker-first local GLM-OCR deployment:

- `docker-compose.yml` now starts both the main app and the durable ingestion worker, and treats Docker as `container_localhost` mode so local loopback-only container startup works without `LIDLTOOL_OPENCLAW_API_KEY`.
- The base self-hosted stack no longer assumes a host-native Ollama OCR endpoint. Configure `LIDLTOOL_OCR_GLM_LOCAL_BASE_URL` explicitly for any local OCR runtime, or add the NVIDIA override below.
- For Linux + NVIDIA Docker, enable the bundled vLLM sidecar with:

```bash
docker compose -f docker-compose.yml -f docker-compose.ocr-nvidia.yml up -d
```

- The NVIDIA override serves `zai-org/GLM-OCR` as `glm-ocr` and rewires the app to `http://glm-ocr:8080/v1`.

Public HTTP routes are intentionally minimal:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/auth/setup-required`
- `POST /api/v1/auth/setup`
- `POST /api/v1/auth/login`

Bootstrap, cookie, and key model:

- `POST /api/v1/auth/setup` remains public only for first-user bootstrap. In `localhost` mode it works only from loopback unless you deliberately configure a bootstrap token. In `container_localhost` mode it works through the loopback-only published Docker port. In `private_network` and `reverse_proxy_tls` mode, startup fails closed until `LIDLTOOL_AUTH_BOOTSTRAP_TOKEN` is configured or setup has already completed.
- Session cookies stay usable for plain `http://localhost` development and are not marked `Secure` there. They are marked `Secure` on direct HTTPS requests and on trusted reverse-proxy requests with `Forwarded` or `X-Forwarded-Proto` set to `https`.
- `LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS` is the only way the server will trust forwarded proto headers. Proxy headers are ignored otherwise.
- `LIDLTOOL_OPENCLAW_API_KEY` is the service/OpenClaw key for service-level agent access. User-created keys from `/api/v1/auth/keys` are user-scoped agent keys. Session cookies or bearer session tokens are still required for `/api/v1/auth/*` session-management routes, `/api/v1/users*`, and browser VNC/noVNC flows.
- Rotating `LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY` invalidates existing browser sessions and can make previously encrypted stored credentials unreadable until they are re-authenticated or re-encrypted. Rotate it during maintenance, not casually.

OCR provider routing:

- Preferred provider is configured via `LIDLTOOL_OCR_DEFAULT_PROVIDER` (`glm_ocr_local`, `openai_compatible`, or `external_api`).
- `glm_ocr_local` is the self-hosted default and uses `LIDLTOOL_OCR_GLM_LOCAL_BASE_URL` plus `LIDLTOOL_OCR_GLM_LOCAL_MODEL`.
- There is no longer a host-Ollama default. Set `LIDLTOOL_OCR_GLM_LOCAL_BASE_URL` explicitly for any local OCR runtime.
- `LIDLTOOL_OCR_GLM_LOCAL_API_MODE=openai_chat_completion` is the default for self-hosted OpenAI-compatible OCR runtimes such as vLLM or SGLang.
- `LIDLTOOL_OCR_GLM_LOCAL_API_MODE=ollama_generate` remains available only as a compatibility adapter for operators who intentionally use Ollama.
- Scanned PDFs are now rasterized into page images before they are sent to a VLM provider; PDFs with an embedded text layer still use direct text extraction.
- `openai_compatible` uses `LIDLTOOL_OCR_OPENAI_BASE_URL`, `LIDLTOOL_OCR_OPENAI_MODEL`, and `LIDLTOOL_OCR_OPENAI_API_KEY`.
- If those OCR-specific settings are omitted, the provider reuses the app-wide AI settings from `LIDLTOOL_AI_BASE_URL`, `LIDLTOOL_AI_MODEL`, and `LIDLTOOL_AI_API_KEY`.
- External OCR API is configured via `LIDLTOOL_OCR_EXTERNAL_API_URL` and `LIDLTOOL_OCR_EXTERNAL_API_KEY`.
- If enabled (`LIDLTOOL_OCR_FALLBACK_ENABLED=true`), failures in the preferred provider fall back to `LIDLTOOL_OCR_FALLBACK_PROVIDER`.
- `tesseract` is no longer supported anywhere in the OCR upload pipeline.

### 14. OCR review queue API (Sprint 14)

Low-confidence OCR results are routed into a review queue (`review_status=needs_review`) when
transaction confidence is below `LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD` (default `0.80`).

List pending review items:

```bash
curl -s "http://127.0.0.1:8000/api/v1/review-queue"
```

Fetch detailed review payload (document + transaction + items + confidence metadata):

```bash
curl -s "http://127.0.0.1:8000/api/v1/review-queue/<document_id>"
```

Apply a transaction correction:

```bash
curl -s -X PATCH "http://127.0.0.1:8000/api/v1/review-queue/<document_id>/transaction" \
  -H "content-type: application/json" \
  -d '{"actor_id":"reviewer-1","reason":"ocr typo","corrections":{"merchant_name":"Corrected Store"}}'
```

Approve or reject a review item:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/review-queue/<document_id>/approve" \
  -H "content-type: application/json" \
  -d '{"actor_id":"reviewer-1","reason":"validated"}'
```

All correction/decision actions write audit events and persist `training_hints` for parser improvements.

### 15. Manual one-off transaction ingestion

For purchases from merchants where you do not want a full connector, you can insert a canonical
transaction directly:

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/transactions/manual" \
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
curl -s "http://127.0.0.1:8000/api/v1/dashboard/cards?year=2026&month=2"

# Trends (last N months ending at end_month)
curl -s "http://127.0.0.1:8000/api/v1/dashboard/trends?year=2026&months_back=6&end_month=2"

# Savings breakdown (native or normalized)
curl -s "http://127.0.0.1:8000/api/v1/dashboard/savings-breakdown?year=2026&month=2&view=normalized"

# Savings by retailer composition
curl -s "http://127.0.0.1:8000/api/v1/dashboard/retailer-composition?year=2026&month=2"
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
| HTTP exposure mode | `LIDLTOOL_HTTP_EXPOSURE_MODE` | `localhost` |
| Service/OpenClaw API key | `LIDLTOOL_OPENCLAW_API_KEY` | _(required for `private_network` and `reverse_proxy_tls` exposure)_ |
| First-user bootstrap token | `LIDLTOOL_AUTH_BOOTSTRAP_TOKEN` | _(required before first-user setup for `private_network` and `reverse_proxy_tls`)_ |
| Trusted reverse-proxy CIDRs | `LIDLTOOL_HTTP_TRUSTED_PROXY_CIDRS` | `[]` _(required only for `reverse_proxy_tls`)_ |
| OCR storage path | `LIDLTOOL_DOCUMENT_STORAGE_PATH` | `~/.local/share/lidltool/documents` |
| OCR max upload (MB) | `LIDLTOOL_MAX_UPLOAD_SIZE_MB` | `12` |
| OCR default provider | `LIDLTOOL_OCR_DEFAULT_PROVIDER` | `glm_ocr_local` |
| OCR fallback enabled | `LIDLTOOL_OCR_FALLBACK_ENABLED` | `false` |
| OCR review confidence threshold | `LIDLTOOL_OCR_REVIEW_CONFIDENCE_THRESHOLD` | `0.80` |
| OCR GLM local base URL | `LIDLTOOL_OCR_GLM_LOCAL_BASE_URL` | _(unset)_ |
| OCR GLM local API mode | `LIDLTOOL_OCR_GLM_LOCAL_API_MODE` | `openai_chat_completion` |
| OCR GLM local model | `LIDLTOOL_OCR_GLM_LOCAL_MODEL` | `glm-ocr` |
| OCR OpenAI-compatible base URL | `LIDLTOOL_OCR_OPENAI_BASE_URL` | _(unset)_ |
| OCR OpenAI-compatible model | `LIDLTOOL_OCR_OPENAI_MODEL` | _(unset)_ |
| OCR OpenAI-compatible API key | `LIDLTOOL_OCR_OPENAI_API_KEY` | _(unset)_ |
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
- Source routing includes `lidl_plus_de`, `amazon_de`, `rewe_de`, `kaufland_de`, `rossmann_de`, and installed receipt plugins such as `dm_de` in async job mode.

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
- `docs/connectors-dev-reset-bootstrap.md`
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
