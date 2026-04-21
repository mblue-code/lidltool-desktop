from __future__ import annotations

from datetime import date
from pathlib import Path

from lidltool.auth.users import create_local_user
from lidltool.budget.service import create_cashflow_entry, monthly_budget_summary
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.recurring.service import RecurringBillsService


def _build_sessions(tmp_path: Path):
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return engine, session_factory(engine)


def test_active_recurring_bill_create_and_update_feeds_overview_and_budget_summary(
    tmp_path: Path,
) -> None:
    engine, sessions = _build_sessions(tmp_path)
    service = RecurringBillsService(session_factory=sessions)
    today = date.today()
    anchor_date = today.replace(day=1)

    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="budget-admin",
            password="test-password",
            display_name="Budget Admin",
            is_admin=True,
        )
        user_id = user.user_id

    created = service.create_bill(
        user_id=user_id,
        name="Rent",
        frequency="monthly",
        anchor_date=anchor_date,
        merchant_canonical="qa rent",
        amount_cents=120_000,
        active=True,
    )

    overview = service.get_overview(user_id=user_id)
    assert overview["active_bills"] == 1
    assert overview["monthly_committed_cents"] == 120_000

    with session_scope(sessions) as session:
        summary = monthly_budget_summary(
            session,
            user_id=user_id,
            year=anchor_date.year,
            month=anchor_date.month,
        )
        assert summary["recurring"]["count"] == 1
        assert summary["totals"]["recurring_expected_cents"] == 120_000

    service.update_bill(
        user_id=user_id,
        bill_id=created["id"],
        payload={"amount_cents": 125_500},
    )

    updated_overview = service.get_overview(user_id=user_id)
    assert updated_overview["active_bills"] == 1
    assert updated_overview["monthly_committed_cents"] == 125_500

    with session_scope(sessions) as session:
        summary = monthly_budget_summary(
            session,
            user_id=user_id,
            year=anchor_date.year,
            month=anchor_date.month,
        )
        assert summary["recurring"]["count"] == 1
        assert summary["totals"]["recurring_expected_cents"] == 125_500
        assert summary["recurring"]["items"][0]["expected_amount_cents"] == 125_500

    engine.dispose()


def test_manual_cashflow_outflow_is_included_in_monthly_budget_summary(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    today = date.today()
    month_start = today.replace(day=1)

    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="cashflow-admin",
            password="test-password",
            display_name="Cashflow Admin",
            is_admin=True,
        )
        create_cashflow_entry(
            session,
            user_id=user.user_id,
            effective_date=month_start,
            direction="outflow",
            category="cash",
            amount_cents=5_000,
            description="Manual cash outflow",
            source_type="manual_cash",
            notes="qa cashflow",
        )
        summary = monthly_budget_summary(
            session,
            user_id=user.user_id,
            year=month_start.year,
            month=month_start.month,
        )

    assert summary["cashflow"]["count"] == 1
    assert summary["cashflow"]["outflow_count"] == 1
    assert summary["totals"]["manual_outflow_cents"] == 5_000
    assert summary["totals"]["total_outflow_cents"] == 5_000
    engine.dispose()
