## German Public Receipts Eval

Curated benchmark subset built from the public German receipts catalog in:

- `/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/.tmp/public_german_receipts_db/public_german_receipts.sqlite`

Selection rules:

- downloaded public assets only
- German-market receipts only
- chain coverage over raw volume
- mix of photo receipts and text-layer REWE eBon PDFs
- manually normalized ground truth for merchant, date, total, items, and discounts

Current coverage:

- REWE
- PENNY
- real
- Kaiser's Tengelmann
- dm

Sources:

- `knipknap/receiptparser`
- `oraies/eBonsParser`
- `webD97/rewe-ebon-parser`

This fixture pack is intended for OCR/parser regression checks, not training.
