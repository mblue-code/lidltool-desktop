from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lidltool.analytics.queries import dashboard_merchant_summary, dashboard_window_totals
from lidltool.analytics.scope import VisibilityContext
from lidltool.api.http_server import _dashboard_transaction_cashflow_outflows
from lidltool.db.models import Base, Source, Transaction, User


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_source_reporting_roles_keep_spending_and_cashflow_ledgers_separate() -> None:
    Session = _session_factory()
    user_id = "user-reporting-role"
    window_start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    window_end = datetime(2026, 5, 31, tzinfo=timezone.utc)

    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        session.add_all(
            [
                Source(
                    id="amazon_de",
                    user_id=user_id,
                    kind="connector",
                    display_name="Amazon",
                    reporting_role="spending_only",
                ),
                Source(
                    id="bank_account",
                    user_id=user_id,
                    kind="agent",
                    display_name="Bank account",
                    reporting_role="cashflow_only",
                ),
            ]
        )
        session.add_all(
            [
                Transaction(
                    id="amazon-order",
                    source_id="amazon_de",
                    user_id=user_id,
                    source_transaction_id="amazon-order",
                    purchased_at=datetime(2026, 5, 2, tzinfo=timezone.utc),
                    merchant_name="Amazon",
                    total_gross_cents=2500,
                    discount_total_cents=0,
                    direction="outflow",
                    ledger_scope="household",
                    dashboard_include=True,
                ),
                Transaction(
                    id="card-payment",
                    source_id="bank_account",
                    user_id=user_id,
                    source_transaction_id="card-payment",
                    purchased_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
                    merchant_name="Credit card payment",
                    total_gross_cents=2500,
                    discount_total_cents=0,
                    direction="outflow",
                    ledger_scope="household",
                    dashboard_include=True,
                ),
            ]
        )
        session.commit()

        visibility = VisibilityContext(user_id=user_id, is_service=False)

        totals = dashboard_window_totals(
            session,
            from_date=window_start,
            to_date=window_end,
            visibility=visibility,
        )
        cashflow_outflows = _dashboard_transaction_cashflow_outflows(
            session,
            from_dt=window_start,
            to_dt=window_end,
            visibility=visibility,
        )
        merchants = dashboard_merchant_summary(
            session,
            from_date=window_start,
            to_date=window_end,
            visibility=visibility,
        )

    assert totals["net_cents"] == 2500
    assert cashflow_outflows == [(datetime(2026, 5, 3, tzinfo=timezone.utc).date(), 2500)]
    assert merchants == [
        {
            "source_id": "amazon_de",
            "merchant": "Amazon",
            "receipt_count": 1,
            "spend_cents": 2500,
            "last_purchased_at": "2026-05-02T00:00:00",
        }
    ]
