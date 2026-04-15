from __future__ import annotations

from datetime import UTC, datetime

from lidltool.ingest.validation import validate_normalized_connector_payload


def _base_payload() -> dict[str, object]:
    return {
        "id": "amazon-1",
        "purchased_at": datetime(2026, 4, 14, tzinfo=UTC).isoformat(),
        "store_id": "amazon_de:www.amazon.de",
        "store_name": "Amazon",
        "store_address": "www.amazon.de",
        "total_gross_cents": 0,
        "currency": "EUR",
        "discount_total_cents": 0,
        "fingerprint": "fp-test",
        "items": [
            {
                "line_no": 1,
                "source_item_id": "amazon-1:1",
                "name": "Amazon order",
                "qty": "1",
                "unit": "pcs",
                "unit_price_cents": 0,
                "line_total_cents": 0,
                "discounts": [],
            }
        ],
        "raw_json": {"source": "amazon_de"},
    }


def test_zero_total_gross_is_allowed_for_fully_discounted_orders() -> None:
    normalized = _base_payload()
    normalized["discount_total_cents"] = 2999
    report = validate_normalized_connector_payload(
        source_record_ref="302-1147836-5055532",
        source_record_detail={"unsupportedReason": None},
        connector_normalized=normalized,
        extracted_discounts=[
            {
                "line_no": None,
                "type": "promotion",
                "promotion_id": "amazon_promotion",
                "amount_cents": 2999,
                "label": "Geschenkgutschein(e):",
                "scope": "transaction",
            }
        ],
    )

    assert report.outcome.value == "accept"
    assert [issue.code for issue in report.issues] == []


def test_zero_total_gross_is_allowed_for_unbilled_cancellations() -> None:
    normalized = _base_payload()
    report = validate_normalized_connector_payload(
        source_record_ref="302-2956157-7140343",
        source_record_detail={"unsupportedReason": "canceled_only"},
        connector_normalized=normalized,
        extracted_discounts=[],
    )

    assert report.outcome.value == "accept"
    assert [issue.code for issue in report.issues] == []


def test_payment_adjustments_count_toward_total_consistency() -> None:
    normalized = _base_payload()
    normalized["total_gross_cents"] = 1016
    normalized["items"] = [
        {
            "line_no": 1,
            "source_item_id": "amazon-1:1",
            "name": "Game of Thrones - Staffel 7 [dt./OV]",
            "qty": "1",
            "unit": "pcs",
            "unit_price_cents": 1999,
            "line_total_cents": 1999,
            "discounts": [],
        }
    ]
    normalized["raw_json"] = {
        "source": "amazon_de",
        "paymentAdjustments": [
            {
                "type": "payment_adjustment",
                "subkind": "gift_card_balance",
                "amount_cents": 983,
                "label": "Betrage Geschenkgutschein/Karte:",
            }
        ],
    }
    report = validate_normalized_connector_payload(
        source_record_ref="D01-7420653-4274230",
        source_record_detail={"unsupportedReason": None},
        connector_normalized=normalized,
        extracted_discounts=[],
    )

    assert report.outcome.value == "accept"
    assert [issue.code for issue in report.issues] == []
