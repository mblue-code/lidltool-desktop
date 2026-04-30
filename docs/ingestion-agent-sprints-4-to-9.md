# Ingestion Agent Sprints 4-9

This note records the remaining implementation sprints for the desktop ingestion workspace.

## Sprint 4: YOLO Auto

- Added persisted ingestion-agent settings at `GET/POST /api/v1/settings/ingestion-agent`.
- Default approval mode remains `review_first`.
- The UI labels the default mode as Agent Review: the agent interprets and matches, but the user approves and commits.
- `yolo_auto` auto-approves and auto-commits complete agent proposals:
  - new transactions with required fields and without a high-scoring existing match
  - cashflow entries with required fields
  - already-covered/link proposals
  - ignore proposals
- Recurring candidates are never auto-committed.
- Incomplete rows and high-confidence existing matches that were not converted to already-covered proposals stay in review instead of creating duplicates.
- Auto-approval and commit paths write audit events.
- `/ingestion` shows an explicit mode panel and a visible toggle.

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
