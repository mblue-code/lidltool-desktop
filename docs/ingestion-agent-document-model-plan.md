# Ingestion Agent Document Model Path

## Goal

PDFs, screenshots, photos, and text-like documents should enter the same Ingestion Agent review flow as typed text and statement rows. The model may extract facts, but it must not write canonical transactions, cashflow entries, recurring bills, or links directly.

## Flow

1. The user uploads a document in `/ingestion`.
2. The backend stores the file as ingestion evidence using local desktop document storage.
3. The ingestion service runs the existing OCR/model provider router to extract text from PDFs and images.
4. Extracted text is converted into one of the existing validated proposal contracts:
   - `create_transaction`
   - `create_recurring_bill_candidate`
   - `needs_review`
   - staged `statement_rows` when the extracted text is table-like
5. The proposal remains in Review First unless the existing deterministic approval policy later allows auto-approval.
6. Commits still use the existing deterministic commit path, primarily `ManualIngestService`.

## Guardrails

- Do not call the legacy OCR ingest service from the Ingestion Agent path; that service writes transactions directly.
- Do not give the model a general Python runtime, shell, SQL, filesystem, or hidden write tools.
- Store evidence references and hashes for review and idempotency.
- Do not log raw document text, screenshots, raw bank rows, or prompts in diagnostics.
- Never auto-delete or overwrite existing transactions.
- Keep recurring-looking document inputs as recurring bill candidates unless explicitly approved by the user.

## Current Implementation Slice

- CSV/text uploads are parsed and staged locally as statement rows.
- PDF/image uploads are stored in local document storage.
- PDF/image parsing uses the configured OCR/model provider router to extract text.
- Receipt-like extracted text becomes a `create_transaction` review proposal when merchant, date, and amount are present.
- Missing or ambiguous facts become `needs_review`.
- Table-like extracted text is staged as statement rows for the existing classify/match flow.
- A dedicated semantic extraction prompt returns proposal JSON that is validated against existing schemas before storage.
- The constrained tool layer exposes document proposal extraction by ingestion file ID; it still has no filesystem, SQL, Python, shell, or commit tools.
- The review UI shows document evidence, extraction provider, semantic provider/status, and confidence beside document-derived proposals.
- Per-provider diagnostics stored on proposals contain status/provider/timing/confidence only, not raw document text.
- Document-derived model confidence is capped below YOLO Auto thresholds, so early document proposals remain review-first unless a later deterministic policy explicitly raises trust.

## Later Hardening

- Render true inline PDF/image thumbnails beside proposals.
- Add multi-page statement grouping controls for documents that contain many rows.
- Add provider-specific calibration datasets before enabling any document-derived YOLO Auto commits.
