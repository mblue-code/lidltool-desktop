from __future__ import annotations

import unittest

from lidltool.ingest.validation import validate_normalized_connector_payload
from lidltool.ingest.validation_results import ValidationOutcome


class ConnectorValidationDepositsTest(unittest.TestCase):
    def test_accepts_total_when_deposit_lines_explain_gross_delta(self) -> None:
        report = validate_normalized_connector_payload(
            source_record_ref="TR000001976131717",
            source_record_detail={"transaction": {"id": "TR000001976131717"}},
            connector_normalized={
                "id": "TR000001976131717",
                "purchased_at": "2026-01-29T17:45:07+01:00",
                "store_id": "kaufland_de",
                "store_name": "Kaufland Gifhorn",
                "store_address": "Eysselheideweg 5, Gifhorn",
                "total_gross_cents": 6834,
                "currency": "EUR",
                "discount_total_cents": 0,
                "fingerprint": "deposit-case-a",
                "items": [
                    {
                        "line_no": 1,
                        "source_item_id": "item-1",
                        "name": "Regular item",
                        "qty": "1",
                        "unit": "pcs",
                        "unit_price_cents": 6218,
                        "line_total_cents": 6218,
                        "is_deposit": False,
                        "discounts": [],
                    },
                    {
                        "line_no": 2,
                        "source_item_id": "item-2",
                        "name": "Pfandartikel",
                        "qty": "1",
                        "unit": "pcs",
                        "unit_price_cents": 616,
                        "line_total_cents": 616,
                        "is_deposit": True,
                        "discounts": [],
                    },
                ],
                "raw_json": {"source": "kaufland_de"},
            },
            extracted_discounts=[],
        )

        self.assertEqual(report.outcome, ValidationOutcome.ACCEPT)
        self.assertFalse(any(issue.code == "transaction_total_mismatch" for issue in report.issues))

    def test_accepts_total_when_deposit_lines_and_discounts_are_both_present(self) -> None:
        report = validate_normalized_connector_payload(
            source_record_ref="TR000001781108167",
            source_record_detail={"transaction": {"id": "TR000001781108167"}},
            connector_normalized={
                "id": "TR000001781108167",
                "purchased_at": "2025-12-12T15:14:49+01:00",
                "store_id": "kaufland_de",
                "store_name": "Kaufland Gifhorn",
                "store_address": "Eysselheideweg 5, Gifhorn",
                "total_gross_cents": 8721,
                "currency": "EUR",
                "discount_total_cents": 630,
                "fingerprint": "deposit-case-b",
                "items": [
                    {
                        "line_no": 1,
                        "source_item_id": "item-1",
                        "name": "Discounted item basket",
                        "qty": "1",
                        "unit": "pcs",
                        "unit_price_cents": 8271,
                        "line_total_cents": 8271,
                        "is_deposit": False,
                        "discounts": [],
                    },
                    {
                        "line_no": 2,
                        "source_item_id": "item-2",
                        "name": "Pfandartikel",
                        "qty": "1",
                        "unit": "pcs",
                        "unit_price_cents": 450,
                        "line_total_cents": 450,
                        "is_deposit": True,
                        "discounts": [],
                    },
                ],
                "raw_json": {"source": "kaufland_de"},
            },
            extracted_discounts=[
                {
                    "line_no": None,
                    "type": "promotion",
                    "promotion_id": "promo-1",
                    "amount_cents": 630,
                    "label": "Kaufland promotion",
                    "scope": "transaction",
                    "subkind": "promotion",
                    "funded_by": "retailer",
                }
            ],
        )

        self.assertEqual(report.outcome, ValidationOutcome.ACCEPT)
        self.assertFalse(any(issue.code == "transaction_total_mismatch" for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
