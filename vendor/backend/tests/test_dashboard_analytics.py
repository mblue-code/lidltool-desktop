from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from lidltool.analytics.advanced import deposit_analytics
from lidltool.analytics.queries import dashboard_available_years, dashboard_totals
from lidltool.db.engine import session_scope
from lidltool.db.models import Base, Source, Transaction, TransactionItem


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_sources(factory: sessionmaker) -> None:
    with session_scope(factory) as session:
        session.add_all(
            [
                Source(id="amazon_de", kind="amazon", display_name="Amazon"),
                Source(id="lidl", kind="connector", display_name="Lidl"),
            ]
        )


def _transaction(
    *,
    source_id: str,
    source_transaction_id: str,
    purchased_at: datetime,
    total_gross_cents: int,
    merchant_name: str = "Test Merchant",
    raw_payload: dict[str, object] | None = None,
) -> Transaction:
    return Transaction(
        source_id=source_id,
        source_transaction_id=source_transaction_id,
        purchased_at=purchased_at,
        merchant_name=merchant_name,
        total_gross_cents=total_gross_cents,
        currency="EUR",
        discount_total_cents=0,
        raw_payload=raw_payload,
    )


def _deposit_item(*, transaction_id: str, line_no: int, name: str, line_total_cents: int) -> TransactionItem:
    return TransactionItem(
        transaction_id=transaction_id,
        line_no=line_no,
        name=name,
        qty=Decimal("1"),
        unit="pcs",
        unit_price_cents=abs(line_total_cents),
        line_total_cents=line_total_cents,
        is_deposit=True,
    )


def test_dashboard_available_years_and_totals_use_transaction_purchase_year_for_amazon_receipts() -> None:
    factory = _session_factory()
    _seed_sources(factory)

    with session_scope(factory) as session:
        session.add_all(
            [
                _transaction(
                    source_id="amazon_de",
                    source_transaction_id="amz-2017",
                    purchased_at=datetime(2017, 11, 3, 10, 30, tzinfo=UTC),
                    total_gross_cents=1099,
                    merchant_name="Amazon",
                    raw_payload={
                        "source_record_detail": {
                            "pageYear": 2020,
                            "originalOrder": {"orderDate": "2017-11-03"}
                        }
                    },
                ),
                _transaction(
                    source_id="amazon_de",
                    source_transaction_id="amz-2019",
                    purchased_at=datetime(2019, 2, 14, 12, 0, tzinfo=UTC),
                    total_gross_cents=2599,
                    merchant_name="Amazon",
                    raw_payload={"source_record_detail": {"pageYear": 2020}},
                ),
                _transaction(
                    source_id="lidl",
                    source_transaction_id="lidl-2020",
                    purchased_at=datetime(2020, 5, 1, 8, 15, tzinfo=UTC),
                    total_gross_cents=3199,
                    merchant_name="Lidl",
                ),
            ]
        )

    with session_scope(factory) as session:
        available_years = dashboard_available_years(session)
        amazon_years = dashboard_available_years(session, source_ids=["amazon_de"])
        totals_2017 = dashboard_totals(session, year=2017)
        totals_2019 = dashboard_totals(session, year=2019)
        totals_2020 = dashboard_totals(session, year=2020)

    assert available_years["years"] == [2017, 2019, 2020]
    assert available_years["min_year"] == 2017
    assert available_years["latest_year"] == 2020
    assert amazon_years["years"] == [2017, 2019]
    assert totals_2017["totals"]["gross_cents"] == 1099
    assert totals_2019["totals"]["gross_cents"] == 2599
    assert totals_2020["totals"]["gross_cents"] == 3199


def test_deposit_analytics_respects_dashboard_time_window_and_source_filter() -> None:
    factory = _session_factory()
    _seed_sources(factory)

    with session_scope(factory) as session:
        lidl_tx = _transaction(
            source_id="lidl",
            source_transaction_id="lidl-2025",
            purchased_at=datetime(2025, 3, 8, 9, 0, tzinfo=UTC),
            total_gross_cents=480,
            merchant_name="Lidl",
        )
        amazon_tx = _transaction(
            source_id="amazon_de",
            source_transaction_id="amz-2025",
            purchased_at=datetime(2025, 3, 9, 9, 0, tzinfo=UTC),
            total_gross_cents=250,
            merchant_name="Amazon",
        )
        session.add_all([lidl_tx, amazon_tx])
        session.flush()
        session.add_all(
            [
                _deposit_item(
                    transaction_id=lidl_tx.id,
                    line_no=1,
                    name="Einwegpfand",
                    line_total_cents=80,
                ),
                _deposit_item(
                    transaction_id=lidl_tx.id,
                    line_no=2,
                    name="Pfandrueckgabe",
                    line_total_cents=-25,
                ),
                _deposit_item(
                    transaction_id=amazon_tx.id,
                    line_no=1,
                    name="Bottle deposit",
                    line_total_cents=250,
                ),
            ]
        )

    with session_scope(factory) as session:
        lidl_2025 = deposit_analytics(
            session,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            source_ids=["lidl"],
        )
        lidl_2026 = deposit_analytics(
            session,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 12, 31),
            source_ids=["lidl"],
        )

    assert lidl_2025["total_paid_cents"] == 80
    assert lidl_2025["total_returned_cents"] == -25
    assert lidl_2025["net_outstanding_cents"] == 55
    assert lidl_2025["monthly"] == [
        {
            "month": "2025-03",
            "paid_cents": 80,
            "returned_cents": -25,
            "net_cents": 55,
        }
    ]
    assert lidl_2026["total_paid_cents"] == 0
    assert lidl_2026["total_returned_cents"] == 0
    assert lidl_2026["net_outstanding_cents"] == 0
    assert lidl_2026["monthly"] == []
