# Ingestion Agent Sprint 3

Sprint 3 adds bank statement intake for monthly reconciliation.

Implemented:

- `POST /api/v1/ingestion/sessions/{session_id}/files` stores uploaded file metadata and a SHA-256 hash.
- `POST /api/v1/ingestion/files/{file_id}/parse` parses CSV/text statement files into `statement_rows`.
- `POST /api/v1/ingestion/sessions/{session_id}/pasted-table` stages pasted CSV, semicolon, or tabular statement text.
- `POST /api/v1/ingestion/sessions/{session_id}/classify-rows` converts staged rows into proposals.
- Deterministic column inference covers common English and German bank headers.
- Row hashes make repeated file parsing idempotent inside a session.
- Existing transaction matches become `already_covered` proposals instead of duplicate transactions.
- The `/ingestion` workspace supports CSV upload, pasted tables, parsed row preview, and row classification.

Notes:

- CSV parsing uses Python's structured `csv` module. It does not split CSV rows manually.
- Spreadsheet parsing is intentionally deferred because this side repo does not currently ship a backend spreadsheet parser dependency. Excel exports should be saved as CSV for this sprint.
- Statement rows are staged first. Canonical transactions are only written after proposal approval and commit.

Verification:

- `vendor/backend/.venv/bin/pytest tests/backend/test_ingestion_agent_sprint1.py tests/backend/test_ingestion_agent_sprint2_matching.py tests/backend/test_ingestion_agent_sprint3_csv.py`
- `npm --prefix vendor/frontend run test -- src/pages/__tests__/IngestionPage.test.tsx`
- `npm --prefix vendor/frontend run build`
