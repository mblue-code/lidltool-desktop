# Ingestion Agent Sprints 4-9

This note records the remaining implementation sprints for the desktop ingestion workspace.

## Sprint 4: YOLO Auto

- Added persisted ingestion-agent settings at `GET/POST /api/v1/settings/ingestion-agent`.
- Default approval mode remains `review_first`.
- `yolo_auto` can auto-approve and auto-commit only safe high-confidence actions:
  - new transactions above the create threshold and without a high-scoring existing match
  - already-covered/link proposals above the deterministic link threshold
  - ignore proposals above the ignore threshold
- Recurring candidates are never auto-committed.
- Auto-approval and commit paths write audit events.
- `/ingestion` shows a persistent mode indicator and a visible toggle.

## Sprint 5: PDF, Image, Photo, and Screenshot Intake

- PDF/image uploads are accepted by the ingestion file endpoint.
- These files create review proposals through the AI intake path instead of trying to write transactions directly.
- Raw document text, screenshots, prompts, and personal statement contents are not logged to diagnostics.

## Sprint 6: Recurring Bill Integration

- Added strict `create_recurring_bill_candidate` proposal validation.
- Recurring-looking text and statement rows produce candidates, not active recurring bills.
- Candidate commit records review/audit metadata only; active bill creation remains explicit user work.

## Sprint 7: Batch Review UX

- Added batch approve, batch reject, and batch commit endpoints.
- `/ingestion` exposes batch controls for monthly reconciliation.

## Sprint 8: Undo, Repair, and Trust

- Added `POST /api/v1/ingestion/proposals/{proposal_id}/undo`.
- Undo is constrained to recent ingestion proposals that created an agent-owned transaction.
- Existing matches, ignore proposals, and document proposals are not destructively undone.
- Undo writes an audit event and leaves the proposal visible for review.

## Sprint 9: Hardening and Release Readiness

- Fresh install database creation is covered by migration-backed backend tests.
- Proposal payloads remain strict Pydantic contracts with `extra="forbid"`.
- Model-facing freedom is constrained to `IngestionAgentToolRunner`, which allowlists ingestion tools for statement previews, transaction search, match search, proposal creation/update, row classification, and summaries.
- The model does not receive arbitrary Python, shell, filesystem, SQL, delete, overwrite, or direct ledger commit tools.
- Runtime/build paths remain local to this side repo.
- Final verification should run:
  - `npm run typecheck`
  - `npm run build`
  - backend ingestion pytest suite
  - frontend ingestion page test
