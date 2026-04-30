# Ingestion Agent Sprint 0 Notes

Sprint 0 is research and alignment only. It introduces no runtime behavior changes.

## Existing Primitives

- Transaction writes: `overrides/backend/src/lidltool/ingest/manual_ingest.py`
  - `ManualIngestService.ingest_transaction()` is the required commit path for transaction proposals.
  - Idempotency is already supported by deriving `source_transaction_id` from `idempotency_key`.
  - Audit is already written through `record_audit_event()`.
- Transaction APIs: `overrides/backend/src/lidltool/api/http_server.py`
  - Existing list/detail routes live at `/api/v1/transactions` and `/api/v1/transactions/{transaction_id}`.
  - Manual transaction creation lives at `/api/v1/transactions/manual`.
- Cashflow services: `overrides/backend/src/lidltool/budget/service.py`
  - `create_cashflow_entry()`, `update_cashflow_entry()`, and `delete_cashflow_entry()` should be reused for cashflow proposal commits.
- Recurring bill services: `overrides/backend/src/lidltool/recurring/service.py`
  - `RecurringBillsService.create_bill()` and occurrence reconciliation helpers should be reused after recurring proposals are approved.
- Chat and model runtime: `ChatThread`, `ChatMessage`, and `ChatRun` are defined in `overrides/backend/src/lidltool/db/models.py`.
  - The ingestion workspace should expose ingestion-specific sessions and proposals rather than overloading user chat threads as the product object.
  - Chat persistence can be referenced later for model run metadata if needed.
- OpenClaw tool adapter: `overrides/backend/src/lidltool/openclaw/tool_adapter.py`
  - Existing `manual_ingest` action validates parameters and uses `ManualIngestService`.
  - The ingestion agent should get dedicated proposal tools and no low-level DB mutation tools.
- Document storage and OCR: `overrides/backend/src/lidltool/ingest/ocr_ingest.py` and `overrides/backend/src/lidltool/storage/document_storage.py` in the vendored backend.
  - Sprint 5 should reuse document storage metadata and OCR extraction instead of creating a parallel document store.

## Database and Migration Decision

- Desktop uses Alembic migrations under `overrides/backend/src/lidltool/db/migrations/versions`.
- `migrate_db()` in `overrides/backend/src/lidltool/db/engine.py` runs/stamps the local SQLite database on startup or test setup.
- Sprint 1 should add real ingestion tables immediately:
  - `ingestion_sessions`
  - `ingestion_files`
  - `statement_rows`
  - `ingestion_proposals`
  - `ingestion_proposal_matches`
- Rationale: CSV and monthly reconciliation need queryable rows, statuses, idempotency keys, and auditable proposal state. JSON-only prototype blobs would be removed almost immediately in Sprint 3.

## Session Persistence Decision

- Use ingestion-specific tables as the product source of truth.
- Do not store ingestion sessions as `chat_threads`.
- Store model metadata on proposals and add chat/thread linkage later only if a live conversational transcript becomes necessary.

## Initial Prompt Draft

```text
You are the Outlays ingestion agent. You turn messy user input into structured ingestion proposals for deterministic backend validation.

Rules:
- The model proposes; backend code validates and commits.
- Never directly mutate transactions, cashflow entries, recurring bills, or links.
- Default to Review First. Only backend policy may auto-approve or auto-commit.
- Do not fabricate missing dates, totals, merchants, currencies, or source details.
- Distinguish extracted facts from guesses in the proposal explanation.
- When date and amount are known, search for existing transactions before proposing a new transaction.
- Prefer already_covered or link_existing_transaction when an existing connector transaction matches.
- Ambiguous matches or missing required fields must become needs_review.
- Recurring-looking inputs create recurring bill candidates unless the user explicitly approves creating an active recurring bill.
- Never delete, overwrite, or hide existing user data.
- Include compact evidence for user review, but do not log raw personal input in diagnostics.
```

## Route Decision

- Frontend route: `/ingestion`
- Navigation: add a primary workspace nav item, near transactions/manual import.
- Backend API prefix: `/api/v1/ingestion`

## Sprint 1 Edit Targets

- Backend models and migration:
  - `overrides/backend/src/lidltool/db/models.py`
  - `overrides/backend/src/lidltool/db/migrations/versions/0028_ingestion_agent.py`
- Backend ingestion service/API:
  - `overrides/backend/src/lidltool/ingestion_agent/__init__.py`
  - `overrides/backend/src/lidltool/ingestion_agent/schemas.py`
  - `overrides/backend/src/lidltool/ingestion_agent/service.py`
  - `overrides/backend/src/lidltool/ingestion_agent/prompt.py`
  - `overrides/backend/src/lidltool/api/http_server.py`
  - `overrides/backend/src/lidltool/api/route_auth.py`
- Frontend:
  - `overrides/frontend/src/api/ingestion.ts`
  - `overrides/frontend/src/pages/IngestionPage.tsx`
  - `overrides/frontend/src/components/shared/AppShell.tsx`
  - `overrides/frontend/src/app/page-loaders.ts`
  - `overrides/frontend/src/i18n/literals.en.json`
  - `overrides/frontend/src/i18n/literals.de.json`
- Override manifests/patching:
  - `vendor/vendor-manifest.json`
  - `scripts/patch-vendored-backend.mjs` only if backend override copying needs explicit metadata.

## Local Dev Reset Policy

There is no external desktop user base for this feature yet. During ingestion-agent development:

- Prefer simple additive Alembic migrations.
- If schema churn makes a migration awkward, delete the local dev SQLite database and re-sync Amazon/Lidl.
- Before hardening, verify fresh database creation with all ingestion tables present.
- Do not add runtime or build-time references outside this repo.
