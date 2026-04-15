from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from lidltool.config import AppConfig
from lidltool.connectors.amazon_adapter import AmazonConnectorAdapter
from lidltool.db.engine import create_engine_for_url, init_db, session_factory, session_scope
from lidltool.db.models import (
    DiscountEvent,
    Receipt,
    ReceiptItem,
    Source,
    Transaction,
    TransactionItem,
)
from lidltool.ingest.sync import SyncService


class FakeAmazonClient:
    def __init__(self, orders: list[dict[str, Any]]) -> None:
        self._orders = orders

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int | None = None) -> list[dict[str, Any]]:
        del years, max_pages_per_year
        return list(self._orders)


class ValidatingAmazonClient(FakeAmazonClient):
    def __init__(self, orders: list[dict[str, Any]]) -> None:
        super().__init__(orders)
        self.validate_calls = 0
        self.fetch_calls = 0

    def validate_session(self) -> None:
        self.validate_calls += 1

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int | None = None) -> list[dict[str, Any]]:
        self.fetch_calls += 1
        return super().fetch_orders(years=years, max_pages_per_year=max_pages_per_year)


class StreamingAmazonClient(FakeAmazonClient):
    def validate_session(self) -> None:
        return None

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int | None = None) -> list[dict[str, Any]]:
        raise AssertionError("streaming sync should not call fetch_orders()")

    def iter_orders(
        self,
        *,
        years: int = 2,
        max_pages_per_year: int | None = None,
        max_pages: int | None = None,
        progress_cb=None,
    ):
        del years, max_pages_per_year, max_pages
        for index, order in enumerate(self._orders, start=1):
            if progress_cb is not None:
                progress_cb(
                    {
                        "pages": 1,
                        "discovered_receipts": index,
                        "current_year": 2026,
                        "current_page": 1,
                        "current_record_ref": str(order.get("orderId") or ""),
                    }
                )
            yield dict(order)


def _load_orders_fixture() -> list[dict[str, Any]]:
    fixture_path = Path(__file__).parent / "fixtures" / "amazon" / "orders_wave1a.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return [row for row in payload if isinstance(row, dict)]


def test_amazon_sync_dual_writes_canonical_discounts_and_provenance(tmp_path) -> None:
    db_file = tmp_path / "amazon.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(Source(id="amazon_de", kind="amazon", display_name="Amazon"))

    config = AppConfig(db_path=db_file, source="amazon_de")
    connector = AmazonConnectorAdapter(
        client=FakeAmazonClient(_load_orders_fixture()),  # type: ignore[arg-type]
        source="amazon_de",
    )
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=config,
        connector=connector,
    )

    first = service.sync(full=True)
    assert first.receipts_seen == 4
    assert first.new_receipts == 3
    assert first.new_items == 4
    assert first.validation["outcomes"]["quarantine"] == 1
    assert first.validation["outcomes"]["warn"] >= 1

    with session_scope(sessions) as session:
        assert session.execute(select(func.count(Receipt.id))).scalar_one() == 3
        assert session.execute(select(func.count(ReceiptItem.id))).scalar_one() == 4
        assert session.execute(select(func.count(Transaction.id))).scalar_one() == 3
        assert session.execute(select(func.count(TransactionItem.id))).scalar_one() == 4
        assert session.execute(select(func.count(DiscountEvent.id))).scalar_one() == 3

        discounts = session.execute(select(DiscountEvent).order_by(DiscountEvent.id)).scalars().all()
        assert any(discount.scope == "transaction" for discount in discounts)
        assert all(discount.amount_cents > 0 for discount in discounts)
        assert all(discount.source == "amazon_de" for discount in discounts)

        canonical = (
            session.execute(select(Transaction).order_by(Transaction.source_transaction_id))
            .scalars()
            .all()
        )
        assert canonical
        for row in canonical:
            assert row.raw_payload is not None
            assert row.raw_payload.get("source_record_detail") is not None
            assert row.raw_payload.get("connector_normalized") is not None
            source_detail = row.raw_payload.get("source_record_detail")
            assert isinstance(source_detail, dict)
            assert source_detail.get("originalOrder") is not None

    second = service.sync(full=True)
    assert second.new_receipts == 0
    assert second.new_items == 0

    with session_scope(sessions) as session:
        assert session.execute(select(func.count(Transaction.id))).scalar_one() == 3
        assert session.execute(select(func.count(TransactionItem.id))).scalar_one() == 4
        assert session.execute(select(func.count(DiscountEvent.id))).scalar_one() == 3


def test_adapter_preserves_parse_metadata_and_market_labels() -> None:
    order = {
        "orderId": "555-5555555-5555555",
        "orderDate": "5 février 2025",
        "totalAmount": 25.98,
        "currency": "EUR",
        "items": [{"title": "Livre", "asin": "B00FRTEST1", "quantity": 1, "price": 21.99, "discount": 0}],
        "promotions": [],
        "totalSavings": 0,
        "orderStatus": "Livré",
        "detailsUrl": "https://www.amazon.fr/gp/your-account/order-details?orderID=555-5555555-5555555",
        "shipping": 4.0,
        "parseStatus": "partial",
        "parseWarnings": ["missing_total_amount"],
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_fr",
    )
    detail = adapter.fetch_record_detail("555-5555555-5555555")

    shipping_items = [item for item in detail["items"] if item["name"] == "Frais de livraison"]
    assert len(shipping_items) == 1
    assert "2025-02-05" in detail["purchasedAt"]
    assert detail["parseStatus"] == "partial"
    assert detail["parseWarnings"] == ["missing_total_amount"]


def test_adapter_supports_gbp_marketplace() -> None:
    order = {
        "orderId": "888-8888888-8888888",
        "orderDate": "January 15, 2025",
        "totalAmount": 21.99,
        "currency": "GBP",
        "items": [{"title": "Tea bags", "asin": "B00GBTEST1", "quantity": 1, "price": 18.99, "discount": 0}],
        "promotions": [{"description": "Coupon savings", "amount": 1.5}],
        "totalSavings": 1.5,
        "orderStatus": "Delivered",
        "detailsUrl": "https://www.amazon.co.uk/gp/your-account/order-details?orderID=888-8888888-8888888",
        "shipping": 3.0,
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_gb",
    )
    detail = adapter.fetch_record_detail("888-8888888-8888888")

    shipping_items = [item for item in detail["items"] if item["name"] == "Delivery"]
    assert len(shipping_items) == 1
    assert detail["currency"] == "GBP"
    assert "2025-01-15" in detail["purchasedAt"]


def test_adapter_preserves_explicit_zero_total_orders() -> None:
    order = {
        "orderId": "999-9999999-9999999",
        "orderDate": "14. April 2025",
        "totalAmount": 0.0,
        "currency": "EUR",
        "items": [{"title": "Gifted item", "asin": "B00ZERO000", "quantity": 1, "price": 29.99, "discount": 0}],
        "promotions": [{"description": "Geschenkgutschein(e):", "amount": 29.99, "category": "coupon"}],
        "totalSavings": 29.99,
        "orderStatus": "Zugestellt",
        "detailsUrl": "https://www.amazon.de/gp/your-account/order-details?orderID=999-9999999-9999999",
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("999-9999999-9999999")

    assert detail["totalGross"] == 29.99
    assert detail["discountTotal"] is None
    assert detail["paymentAdjustments"] == [
        {
            "type": "payment_adjustment",
            "subkind": "gift_card_balance",
            "amount_cents": 2999,
            "label": "Geschenkgutschein(e):",
        }
    ]
    assert adapter.extract_discounts(detail) == []


def test_adapter_preserves_inferred_deposit_items() -> None:
    order = {
        "orderId": "777-7777777-7777777",
        "orderDate": "4. April 2026",
        "totalAmount": 19.04,
        "currency": "EUR",
        "items": [
            {
                "title": "Monster Energy Ultra White - in praktischen Einweg Dosen (12 x 500 ml)",
                "asin": "B0DEPOSIT1",
                "quantity": 1,
                "price": 17.88,
                "discount": 0,
            },
            {
                "title": "Einwegpfand",
                "asin": "",
                "quantity": 1,
                "price": 3.0,
                "discount": 0,
                "isDeposit": True,
                "category": "deposit",
            },
        ],
        "promotions": [{"description": "Gutschein eingelöst:", "amount": 1.84, "category": "coupon"}],
        "totalSavings": 1.84,
        "orderStatus": "Zugestellt",
        "detailsUrl": "https://www.amazon.de/gp/your-account/order-details?orderID=777-7777777-7777777",
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("777-7777777-7777777")
    deposit_items = [item for item in detail["items"] if item.get("is_deposit")]
    normalized = adapter.normalize(detail)
    normalized_deposit_items = [item for item in normalized["items"] if item.get("is_deposit")]

    assert detail["totalGross"] == 19.04
    assert detail["discountTotal"] is None
    assert len(deposit_items) == 1
    assert deposit_items[0]["name"] == "Einwegpfand"
    assert deposit_items[0]["lineTotal"] == 3.0
    assert len(normalized_deposit_items) == 1
    assert normalized_deposit_items[0]["line_total_cents"] == 300
    assert adapter.extract_discounts(detail) == []


def test_adapter_keeps_explicit_total_when_payment_adjustment_exists() -> None:
    order = {
        "orderId": "D01-7629149-7679000",
        "orderDate": "17. Januar 2025",
        "totalAmount": 3.99,
        "currency": "EUR",
        "items": [
            {
                "title": "Interstellar [dt./OV]",
                "quantity": 1,
                "price": 3.99,
                "discount": 0,
            }
        ],
        "promotions": [],
        "totalSavings": 0.0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-7629149-7679000",
        "subtotals": [
            {"label": "Artikel-Zwischensumme:", "amount": 3.35, "category": "subtotal"},
            {"label": "Gesamtbetrag vor Steuern:", "amount": 3.35, "category": "pre_tax_total"},
            {"label": "MwSt:", "amount": 0.64, "category": "tax"},
            {"label": "Betrage Geschenkgutschein/Karte:", "amount": -3.99, "category": "gift_card"},
            {"label": "Gesamtbetrag für diese Bestellung:", "amount": 3.99, "category": "order_total"},
        ],
        "paymentAdjustments": [
            {
                "type": "payment_adjustment",
                "subkind": "gift_card_balance",
                "amount_cents": 399,
                "label": "Betrage Geschenkgutschein/Karte:",
            }
        ],
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("D01-7629149-7679000")

    assert detail["totalGross"] == 3.99
    assert detail["discountTotal"] is None
    assert detail["paymentAdjustments"] == [
        {
            "type": "payment_adjustment",
            "subkind": "gift_card_balance",
            "amount_cents": 399,
            "label": "Betrage Geschenkgutschein/Karte:",
        }
    ]


def test_adapter_auth_steps_use_lightweight_session_validation_when_available() -> None:
    client = ValidatingAmazonClient(_load_orders_fixture())
    adapter = AmazonConnectorAdapter(
        client=client,  # type: ignore[arg-type]
        source="amazon_de",
    )

    assert adapter.authenticate() == {"authenticated": True}
    assert adapter.refresh_auth() == {"refreshed": True}
    assert adapter.healthcheck() == {"healthy": True, "sample_size": 0}
    assert client.validate_calls == 1
    assert client.fetch_calls == 0

    records = adapter.discover_new_records()
    assert records
    assert client.fetch_calls == 1


def test_adapter_uses_page_year_fallback_for_missing_order_dates() -> None:
    order = {
        "orderId": "D01-1089047-1659811",
        "orderDate": "",
        "pageYear": 2023,
        "dateSource": "page_year",
        "totalAmount": 3.99,
        "currency": "EUR",
        "items": [{"title": "Amazon order", "quantity": 1, "price": 3.99, "discount": 0}],
        "promotions": [],
        "totalSavings": 0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-1089047-1659811",
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("D01-1089047-1659811")
    normalized = adapter.normalize(detail)

    assert detail["dateSource"] == "page_year"
    assert detail["purchasedAt"].startswith("2023-01-01")
    assert normalized["date_source"] == "page_year"
    assert normalized["purchased_at"].startswith("2023-01-01")


def test_adapter_reallocates_single_item_total_when_detail_price_is_wrong() -> None:
    order = {
        "orderId": "028-6287898-0978762",
        "orderDate": "13. Oktober 2020",
        "totalAmount": 34.99,
        "currency": "EUR",
        "items": [
            {
                "title": "Anker PowerCore 26800mAh",
                "asin": "B01JIWQPMW",
                "quantity": 1,
                "price": 37.06,
                "discount": 0,
            }
        ],
        "promotions": [],
        "shipping": 0,
        "gift_wrap": 0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/your-orders/order-details?orderID=028-6287898-0978762",
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("028-6287898-0978762")

    assert detail["totalGross"] == 34.99
    assert detail["items"][0]["unitPrice"] == pytest.approx(34.99)
    assert detail["items"][0]["lineTotal"] == pytest.approx(34.99)


def test_adapter_reallocates_single_item_total_for_multi_qty_orders_without_discounts() -> None:
    order = {
        "orderId": "306-4081414-2825120",
        "orderDate": "14. Oktober 2020",
        "totalAmount": 59.98,
        "currency": "EUR",
        "items": [
            {
                "title": "SanDisk Extreme Pro SDXC",
                "asin": "B07H9DVLBB",
                "quantity": 2,
                "price": 26.37,
                "discount": 0,
            }
        ],
        "promotions": [],
        "shipping": 0,
        "gift_wrap": 0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/your-orders/order-details?orderID=306-4081414-2825120",
    }
    adapter = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )

    detail = adapter.fetch_record_detail("306-4081414-2825120")

    assert detail["totalGross"] == 59.98
    assert detail["items"][0]["unitPrice"] == pytest.approx(29.99)
    assert detail["items"][0]["lineTotal"] == pytest.approx(59.98)


def test_amazon_sync_does_not_regress_existing_purchased_at_on_reimport(tmp_path) -> None:
    db_file = tmp_path / "amazon-date-quality.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(Source(id="amazon_de", kind="amazon", display_name="Amazon"))

    first_order = {
        "orderId": "D01-1089047-1659811",
        "orderDate": "3. März 2023",
        "dateSource": "list_order_date",
        "totalAmount": 3.99,
        "currency": "EUR",
        "items": [{"title": "Amazon order", "quantity": 1, "price": 3.99, "discount": 0}],
        "promotions": [],
        "totalSavings": 0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-1089047-1659811",
    }
    connector = AmazonConnectorAdapter(
        client=FakeAmazonClient([first_order]),  # type: ignore[arg-type]
        source="amazon_de",
    )
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(db_path=db_file, source="amazon_de"),
        connector=connector,
    )

    first = service.sync(full=True)
    assert first.new_receipts == 1

    second_order = {
        "orderId": "D01-1089047-1659811",
        "orderDate": "",
        "pageYear": 2023,
        "dateSource": "page_year",
        "totalAmount": 3.99,
        "currency": "EUR",
        "items": [{"title": "Amazon order", "quantity": 1, "price": 3.99, "discount": 0}],
        "promotions": [],
        "totalSavings": 0,
        "orderStatus": "",
        "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-1089047-1659811",
    }
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(db_path=db_file, source="amazon_de"),
        connector=AmazonConnectorAdapter(
            client=FakeAmazonClient([second_order]),  # type: ignore[arg-type]
            source="amazon_de",
        ),
    )
    second = service.sync(full=True)
    assert second.new_receipts == 0

    with session_scope(sessions) as session:
        tx = session.execute(select(Transaction).where(Transaction.source_transaction_id == "amazon-D01-1089047-1659811")).scalar_one()
        assert str(tx.purchased_at.date()) == "2023-03-03"


def test_sync_does_not_merge_distinct_amazon_orders_by_fingerprint(tmp_path) -> None:
    db_file = tmp_path / "amazon-no-fingerprint-merge.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(Source(id="amazon_de", kind="amazon", display_name="Amazon"))

    shared_date = "2025-01-24T00:00:00+00:00"
    orders = [
        {
            "orderId": "D01-6405519-8543066",
            "orderDate": "24. Januar 2025",
            "totalAmount": 0.0,
            "currency": "EUR",
            "items": [{"title": "Amazon order", "quantity": 1, "price": 0.0, "discount": 0.0}],
            "promotions": [],
            "totalSavings": 0.0,
            "orderStatus": "",
            "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-6405519-8543066",
            "purchasedAt": shared_date,
        },
        {
            "orderId": "D01-5051746-5819837",
            "orderDate": "24. Januar 2025",
            "totalAmount": 0.0,
            "currency": "EUR",
            "items": [{"title": "Amazon order", "quantity": 1, "price": 0.0, "discount": 0.0}],
            "promotions": [],
            "totalSavings": 0.0,
            "orderStatus": "",
            "detailsUrl": "https://www.amazon.de/gp/css/order-details?orderID=D01-5051746-5819837",
            "purchasedAt": shared_date,
        },
    ]
    connector = AmazonConnectorAdapter(
        client=FakeAmazonClient(orders),  # type: ignore[arg-type]
        source="amazon_de",
    )
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(db_path=db_file, source="amazon_de"),
        connector=connector,
    )

    result = service.sync(full=True)

    assert result.new_receipts == 2
    assert result.new_items == 2

    with session_scope(sessions) as session:
        transactions = (
            session.execute(select(Transaction).order_by(Transaction.source_transaction_id))
            .scalars()
            .all()
        )
        assert [row.source_transaction_id for row in transactions] == [
            "amazon-D01-5051746-5819837",
            "amazon-D01-6405519-8543066",
        ]


def test_sync_skips_unsupported_amazon_orders(tmp_path) -> None:
    db_file = tmp_path / "amazon-unsupported.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(Source(id="amazon_de", kind="amazon", display_name="Amazon"))

    order = {
        "orderId": "555-5555555-5555555",
        "orderDate": "1. Februar 2026",
        "totalAmount": 0.0,
        "currency": "EUR",
        "items": [{"title": "Canceled item", "asin": "B00CANCEL1", "quantity": 1, "price": 0}],
        "promotions": [],
        "totalSavings": 0.0,
        "orderStatus": "Storniert",
        "detailsUrl": "",
        "parseStatus": "unsupported",
        "parseWarnings": ["missing_total_amount", "missing_details_url"],
        "unsupportedReason": "canceled_only",
    }
    connector = AmazonConnectorAdapter(
        client=FakeAmazonClient([order]),  # type: ignore[arg-type]
        source="amazon_de",
    )
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(db_path=db_file, source="amazon_de"),
        connector=connector,
    )

    result = service.sync(full=True)

    assert result.receipts_seen == 1
    assert result.new_receipts == 0
    assert result.new_items == 0

    with session_scope(sessions) as session:
        assert session.execute(select(func.count(Receipt.id))).scalar_one() == 0
        assert session.execute(select(func.count(Transaction.id))).scalar_one() == 0


def test_amazon_sync_can_ingest_incrementally_from_streaming_connector(tmp_path) -> None:
    db_file = tmp_path / "amazon-streaming.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        session.add(Source(id="amazon_de", kind="amazon", display_name="Amazon"))

    connector = AmazonConnectorAdapter(
        client=StreamingAmazonClient(_load_orders_fixture()),  # type: ignore[arg-type]
        source="amazon_de",
    )
    service = SyncService(
        client=None,
        session_factory=sessions,
        config=AppConfig(db_path=db_file, source="amazon_de"),
        connector=connector,
    )

    result = service.sync(full=True)

    assert result.receipts_seen == 4
    assert result.new_receipts == 3
    assert result.new_items == 4

    with session_scope(sessions) as session:
        assert session.execute(select(func.count(Receipt.id))).scalar_one() == 3
        assert session.execute(select(func.count(Transaction.id))).scalar_one() == 3
