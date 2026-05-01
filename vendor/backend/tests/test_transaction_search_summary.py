from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lidltool.analytics.queries import search_transactions
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
