## German Receipts Eval Pack

This fixture pack contains publicly available German receipt images curated for
desktop OCR evaluation.

Source:
- Repository: `knipknap/receiptparser`
- URL: `https://github.com/knipknap/receiptparser`
- Source paths: `tests/data/germany/img/*.jpg`
- License: MIT (`COPYING` in the upstream repository)

The goal of this pack is not broad statistical coverage. It is a small,
traceable benchmark for:
- merchant extraction
- purchase date extraction
- total extraction
- basket item extraction
- deposit handling
- deposit-return / voucher discount handling

Ground truth is normalized in [ground_truth.json](/Volumes/macminiExtern/lidl-receipts-cli/apps/desktop/tests/fixtures/german_receipts_eval/ground_truth.json).
