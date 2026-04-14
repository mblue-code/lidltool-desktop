from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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

    def fetch_orders(self, *, years: int = 2, max_pages_per_year: int = 8) -> list[dict[str, Any]]:
        del years, max_pages_per_year
        return list(self._orders)


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
