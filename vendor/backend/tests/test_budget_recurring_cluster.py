from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from lidltool.budget.service import monthly_budget_summary
from lidltool.db.models import Base, User
from lidltool.db.engine import session_scope
from lidltool.recurring.service import RecurringBillsService


def _session_factory() -> sessionmaker:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_user(factory: sessionmaker) -> None:
    with session_scope(factory) as session:
        session.add(
            User(
                user_id="u1",
                username="tester",
                password_hash="not-used-in-test",
                is_admin=True,
            )
        )


def test_recurring_bill_create_and_update_syncs_budget_calendar_and_forecast(monkeypatch) -> None:
    factory = _session_factory()
    _seed_user(factory)

    monkeypatch.setattr(
        "lidltool.budget.service.dashboard_totals",
        lambda *args, **kwargs: {"totals": {"paid_cents": 0}},
    )

    service = RecurringBillsService(session_factory=factory)
    today = date.today()
    anchor_date = today.replace(day=min(15, today.day))

    created = service.create_bill(
        user_id="u1",
        name="Internet",
        frequency="monthly",
        anchor_date=anchor_date,
        amount_cents=350000,
        category="utilities",
    )

    occurrences = service.list_occurrences(user_id="u1", bill_id=created["id"])

    assert occurrences["count"] > 0
    assert any(item["due_date"].startswith(today.strftime("%Y-%m")) for item in occurrences["items"])

    service.update_bill(
        user_id="u1",
        bill_id=created["id"],
        payload={"amount_cents": 35000},
    )

    calendar = service.get_calendar(user_id="u1", year=today.year, month=today.month)
    current_month_items = [item for day in calendar["days"] for item in day["items"] if item["bill_id"] == created["id"]]
    assert current_month_items
    assert all(item["expected_amount_cents"] == 35000 for item in current_month_items)

    forecast = service.get_forecast(user_id="u1", months=1)
    assert forecast["points"][0]["projected_cents"] == 35000

    with session_scope(factory) as session:
        summary = monthly_budget_summary(
            session,
            user_id="u1",
            year=today.year,
            month=today.month,
        )

    matching_summary_rows = [item for item in summary["recurring"]["items"] if item["bill_id"] == created["id"]]
    assert matching_summary_rows
    assert all(item["expected_amount_cents"] == 35000 for item in matching_summary_rows)
