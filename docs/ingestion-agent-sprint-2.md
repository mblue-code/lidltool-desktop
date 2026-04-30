# Ingestion Agent Sprint 2 Notes

Sprint 2 adds deterministic matching against existing transactions.

## Implemented Scope

- Backend match refresh endpoint:
  - `POST /api/v1/ingestion/proposals/{proposal_id}/refresh-matches`
- Deterministic matching inputs:
  - date
  - amount
  - merchant/payee text
  - workspace ownership
- Supported match proposal types:
  - `already_covered`
  - `link_existing_transaction`
- The backend owns the score. The UI can display and explain candidates but does not calculate confidence.

## Scoring

- Exact amount contributes the largest score.
- Same-day date contributes high score.
- Plus/minus two days contributes medium score.
- Merchant similarity contributes a smaller score.
- Candidates below a low deterministic threshold are omitted.

## Current Commit Behavior

`already_covered` and `link_existing_transaction` commits do not create duplicate transactions. They store commit metadata on the ingestion proposal. A dedicated statement-row link/reconciliation table can be added in a later sprint when CSV rows exist.

## Frontend

The `/ingestion` proposal card now supports:

- Refreshing match candidates.
- Viewing candidate amount/date/source/score.
- Marking a proposal as already covered by an existing transaction.
- Keeping the original create-transaction proposal when the user chooses to create new anyway.

## Verification

```bash
npm run vendor:patch-backend
PYTHONPATH=vendor/backend/src LIDLTOOL_REPO_ROOT=$PWD/vendor/backend vendor/backend/.venv/bin/pytest tests/backend/test_ingestion_agent_sprint1.py tests/backend/test_ingestion_agent_sprint2_matching.py
npm run vendor:patch-frontend
npm --prefix vendor/frontend run test -- src/pages/__tests__/IngestionPage.test.tsx
npm --prefix vendor/frontend run build
```
