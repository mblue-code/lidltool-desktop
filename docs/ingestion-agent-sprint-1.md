# Ingestion Agent Sprint 1 Notes

Sprint 1 implements the manual text intake loop.

## Implemented Scope

- Frontend route: `/ingestion`
- Default approval mode: `review_first`
- Supported proposal type:
  - `create_transaction`
- Supported input:
  - free text such as `I paid 25 euros cash at the ice cream store today.`
- Commit path:
  - `IngestionAgentService.commit_proposal()`
  - `ManualIngestService.ingest_transaction()`

## Safety Contract

- The message endpoint creates proposals only.
- The model-originated payload is validated with strict Pydantic schemas before persistence or commit.
- Users can edit merchant, date, amount, currency, and source before approval.
- A proposal must be `approved` or `auto_approved` before commit.
- Sprint 1 does not enable YOLO Auto behavior.
- Re-running commit on a committed proposal returns the stored commit result and does not duplicate the transaction.
- Audit events are written for proposal creation, approval, rejection, commit, and failed commit.

## API Surface Added

- `POST /api/v1/ingestion/sessions`
- `GET /api/v1/ingestion/sessions`
- `GET /api/v1/ingestion/sessions/{session_id}`
- `PATCH /api/v1/ingestion/sessions/{session_id}`
- `DELETE /api/v1/ingestion/sessions/{session_id}`
- `POST /api/v1/ingestion/sessions/{session_id}/message`
- `POST /api/v1/ingestion/sessions/{session_id}/run`
- `GET /api/v1/ingestion/sessions/{session_id}/proposals`
- `POST /api/v1/ingestion/sessions/{session_id}/proposals`
- `PATCH /api/v1/ingestion/proposals/{proposal_id}`
- `POST /api/v1/ingestion/proposals/{proposal_id}/approve`
- `POST /api/v1/ingestion/proposals/{proposal_id}/reject`
- `POST /api/v1/ingestion/proposals/{proposal_id}/commit`

## Verification

Run from the desktop repo root after applying backend/frontend overrides:

```bash
npm run vendor:patch-backend
npm run vendor:patch-frontend
PYTHONPATH=vendor/backend/src LIDLTOOL_REPO_ROOT=$PWD/vendor/backend vendor/backend/.venv/bin/pytest tests/backend/test_ingestion_agent_sprint1.py
npm --prefix vendor/frontend run test -- src/pages/__tests__/IngestionPage.test.tsx
npm --prefix vendor/frontend run build
npm run typecheck
```
