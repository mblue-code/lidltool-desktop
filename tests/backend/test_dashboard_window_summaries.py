from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from lidltool.analytics.queries import grocery_workspace_summary
from lidltool.analytics.scope import VisibilityContext
from lidltool.api.http_server import _dashboard_overview_payload
from lidltool.auth.users import create_local_user
from lidltool.budget.service import create_cashflow_entry
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import (
    RecurringBill,
    RecurringBillMatch,
    RecurringBillOccurrence,
    Source,
    Transaction,
    TransactionItem,
)


def _build_sessions(tmp_path: Path):
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return engine, session_factory(engine)


def _add_source(
    session,
    *,
    user_id: str,
    source_id: str = "test_source",
    kind: str = "connector",
) -> Source:
    source = Source(
        id=source_id,
        user_id=user_id,
        kind=kind,
        display_name="Test Source",
        status="healthy",
        enabled=True,
    )
    session.add(source)
    return source


def _add_transaction(
    session,
    *,
    user_id: str,
    purchased_at: datetime,
    gross_cents: int,
    item_cents: int | None = None,
    category: str = "groceries:produce",
    source_id: str = "test_source",
    index: int = 0,
) -> Transaction:
    transaction = Transaction(
        source_id=source_id,
        user_id=user_id,
        source_transaction_id=f"tx-{purchased_at.isoformat()}-{index}",
        purchased_at=purchased_at,
        merchant_name=f"Market {index % 3}",
        total_gross_cents=gross_cents,
        discount_total_cents=0,
        currency="EUR",
    )
    transaction.items.append(
        TransactionItem(
            line_no=1,
            name="Groceries",
            qty=Decimal("1"),
            line_total_cents=item_cents if item_cents is not None else gross_cents,
            category=category,
        )
    )
    session.add(transaction)
    return transaction


def test_dashboard_overview_compares_groceries_and_cashflow_against_previous_window(
    tmp_path: Path,
) -> None:
    engine, sessions = _build_sessions(tmp_path)

    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="dashboard-admin",
            password="test-password",
            display_name="Dashboard Admin",
            is_admin=True,
        )
        _add_source(session, user_id=user.user_id)
        visibility = VisibilityContext(user_id=user.user_id, is_service=False)
        _add_source(session, user_id=user.user_id, source_id="manual_entry", kind="manual")

        _add_transaction(
            session,
            user_id=user.user_id,
            purchased_at=datetime(2026, 4, 20, 10, tzinfo=UTC),
            gross_cents=1000,
            index=1,
        )
        _add_transaction(
            session,
            user_id=user.user_id,
            purchased_at=datetime(2026, 4, 27, 10, tzinfo=UTC),
            gross_cents=1615,
            item_cents=1316,
            index=2,
        )
        _add_transaction(
            session,
            user_id=user.user_id,
            purchased_at=datetime(2026, 4, 28, 10, tzinfo=UTC),
            gross_cents=385,
            category="household",
            source_id="manual_entry",
            index=3,
        )
        _add_transaction(
            session,
            user_id=user.user_id,
            purchased_at=datetime(2026, 4, 28, 11, tzinfo=UTC),
            gross_cents=9999,
            category="rent",
            source_id="manual_entry",
            index=4,
        )
        recurring_transaction = _add_transaction(
            session,
            user_id=user.user_id,
            purchased_at=datetime(2026, 4, 29, 10, tzinfo=UTC),
            gross_cents=8888,
            category="insurance",
            index=5,
        )
        bill = RecurringBill(
            user_id=user.user_id,
            name="Insurance",
            category="insurance",
            anchor_date="2026-04-29",
            amount_cents=8888,
        )
        occurrence = RecurringBillOccurrence(
            bill=bill,
            due_date=date(2026, 4, 29),
            status="paid",
            expected_amount_cents=8888,
            actual_amount_cents=8888,
        )
        session.add(bill)
        session.flush()
        session.add(
            RecurringBillMatch(
                occurrence_id=occurrence.id,
                transaction_id=recurring_transaction.id,
                match_confidence=1.0,
                match_method="manual",
            )
        )
        create_cashflow_entry(
            session,
            user_id=user.user_id,
            effective_date=date(2026, 4, 20),
            direction="outflow",
            category="cash",
            amount_cents=500,
        )
        create_cashflow_entry(
            session,
            user_id=user.user_id,
            effective_date=date(2026, 4, 27),
            direction="outflow",
            category="cash",
            amount_cents=750,
        )
        create_cashflow_entry(
            session,
            user_id=user.user_id,
            effective_date=date(2026, 4, 20),
            direction="inflow",
            category="cash",
            amount_cents=2000,
        )
        create_cashflow_entry(
            session,
            user_id=user.user_id,
            effective_date=date(2026, 4, 27),
            direction="inflow",
            category="cash",
            amount_cents=2500,
        )

        overview = _dashboard_overview_payload(
            session,
            user=user,
            visibility=visibility,
            from_dt=datetime(2026, 4, 27, tzinfo=UTC),
            to_dt=datetime(2026, 5, 3, tzinfo=UTC),
        )

    assert overview["period"]["comparison_from_date"] == "2026-04-20"
    assert overview["period"]["comparison_to_date"] == "2026-04-26"
    assert overview["kpis"]["groceries"]["current_cents"] == 2000
    assert overview["recent_grocery_transactions"]["total_cents"] == 2000
    assert overview["recent_grocery_transactions"]["average_basket_cents"] == 1000
    assert overview["kpis"]["groceries"]["previous_cents"] == 1000
    assert overview["kpis"]["groceries"]["delta_pct"] == 1.0
    assert overview["kpis"]["cash_outflow"]["current_cents"] == 21637
    assert overview["kpis"]["cash_outflow"]["previous_cents"] == 1500
    assert overview["kpis"]["cash_outflow"]["delta_pct"] == 13.4247
    assert overview["kpis"]["cash_inflow"]["previous_cents"] == 2000
    assert overview["kpis"]["cash_inflow"]["delta_pct"] == 0.25
    assert overview["cash_flow_summary"]["totals"]["outflow_cents"] == 21637
    assert overview["cash_flow_summary"]["points"] == [
        {
            "date": "2026-04-27",
            "inflow_cents": 2500,
            "outflow_cents": 2365,
            "net_cents": 135,
        },
        {
            "date": "2026-04-28",
            "inflow_cents": 0,
            "outflow_cents": 10384,
            "net_cents": -10384,
        },
        {
            "date": "2026-04-29",
            "inflow_cents": 0,
            "outflow_cents": 8888,
            "net_cents": -8888,
        },
    ]
    engine.dispose()


def test_grocery_workspace_summary_totals_cover_full_window_not_recent_limit(
    tmp_path: Path,
) -> None:
    engine, sessions = _build_sessions(tmp_path)

    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="groceries-admin",
            password="test-password",
            display_name="Groceries Admin",
            is_admin=True,
        )
        _add_source(session, user_id=user.user_id)
        visibility = VisibilityContext(user_id=user.user_id, is_service=False)
        for index in range(30):
            _add_transaction(
                session,
                user_id=user.user_id,
                purchased_at=datetime(2026, 4, 1 + index, 10, tzinfo=UTC),
                gross_cents=100 + index,
                index=index,
            )
        session.flush()

        summary = grocery_workspace_summary(
            session,
            from_date=datetime(2026, 4, 1, tzinfo=UTC),
            to_date=datetime(2026, 4, 30, tzinfo=UTC),
            visibility=visibility,
            limit=12,
        )

    assert summary["totals"]["receipt_count"] == 30
    assert summary["totals"]["spend_cents"] == sum(100 + index for index in range(30))
    assert summary["totals"]["average_basket_cents"] == round(
        sum(100 + index for index in range(30)) / 30
    )
    assert len(summary["recent_transactions"]) == 12
    engine.dispose()
