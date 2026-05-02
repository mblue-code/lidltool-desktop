from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lidltool.analytics.queries import reports_pattern_summary, search_transactions
from lidltool.analytics.scope import VisibilityContext
from lidltool.db.models import Base, Source, Transaction, User


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_transaction_search_summary_uses_full_filtered_result_not_page() -> None:
    Session = _session_factory()
    user_id = "summary-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add(Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"))
        session.add_all(
            [
                Transaction(
                    id="outflow-one",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="outflow-one",
                    purchased_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
                    merchant_name="Rent",
                    total_gross_cents=100_000,
                    discount_total_cents=0,
                    direction="outflow",
                ),
                Transaction(
                    id="outflow-two",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="outflow-two",
                    purchased_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
                    merchant_name="Power",
                    total_gross_cents=20_000,
                    discount_total_cents=0,
                    direction="outflow",
                ),
            ]
        )
        session.commit()

        result = search_transactions(
            session,
            purchased_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
            limit=1,
            offset=0,
            visibility=VisibilityContext(user_id=user_id, is_service=False),
        )

    assert result["count"] == 1
    assert result["total"] == 2
    assert result["summary"] == {
        "count": 2,
        "total_cents": 120_000,
        "inflow_cents": 0,
        "outflow_cents": 120_000,
    }


def test_reports_pattern_summary_builds_report_sankey_for_amounts_and_counts() -> None:
    Session = _session_factory()
    user_id = "report-user"
    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add_all(
            [
                Source(id="bank", user_id=user_id, kind="agent", display_name="Bank"),
                Source(id="wallet", user_id=user_id, kind="agent", display_name="Wallet"),
            ]
        )
        session.add_all(
            [
                Transaction(
                    id="rent-april",
                    source_id="bank",
                    user_id=user_id,
                    source_transaction_id="rent-april",
                    purchased_at=datetime(2026, 4, 1, 9, tzinfo=timezone.utc),
                    merchant_name="Landlord",
                    total_gross_cents=100_000,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="housing:rent",
                ),
                Transaction(
                    id="groceries-one",
                    source_id="wallet",
                    user_id=user_id,
                    source_transaction_id="groceries-one",
                    purchased_at=datetime(2026, 4, 2, 18, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=4_200,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
                Transaction(
                    id="groceries-two",
                    source_id="wallet",
                    user_id=user_id,
                    source_transaction_id="groceries-two",
                    purchased_at=datetime(2026, 4, 4, 11, tzinfo=timezone.utc),
                    merchant_name="Lidl",
                    total_gross_cents=3_100,
                    discount_total_cents=0,
                    direction="outflow",
                    finance_category_id="groceries",
                ),
            ]
        )
        session.commit()

        amount_result = reports_pattern_summary(
            session,
            from_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            value_mode="amount",
        )
        count_result = reports_pattern_summary(
            session,
            from_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
            visibility=VisibilityContext(user_id=user_id, is_service=False),
            value_mode="count",
        )

    amount_links = {
        (link["source"], link["target"]): link["value"]
        for link in amount_result["sankey"]["links"]
    }
    count_links = {
        (link["source"], link["target"]): link["value"]
        for link in count_result["sankey"]["links"]
    }

    assert ("source:bank", "category:housing") in amount_links
    assert ("source:wallet", "category:groceries") in amount_links
    assert ("category:housing", "merchant:Landlord") in amount_links
    assert ("category:groceries", "merchant:Lidl") in amount_links
    assert amount_links[("source:bank", "category:housing")] == 100_000
    assert amount_links[("source:wallet", "category:groceries")] == 7_300
    assert amount_links[("category:groceries", "merchant:Lidl")] == 7_300

    assert count_links[("source:bank", "category:housing")] == 1
    assert count_links[("source:wallet", "category:groceries")] == 2
    assert count_links[("category:groceries", "merchant:Lidl")] == 2
