from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from lidltool.budget.service import create_cashflow_entry
from lidltool.db.models import Base, CashflowEntry, User


def _session_factory():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_create_cashflow_entry_reuses_exact_duplicate() -> None:
    Session = _session_factory()
    user_id = "user-cashflow-dedupe"

    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        first = create_cashflow_entry(
            session,
            user_id=user_id,
            effective_date=date(2026, 4, 1),
            direction="inflow",
            category="salary",
            amount_cents=250000,
            description=" Einnahme ",
            source_type="manual_income",
        )
        second = create_cashflow_entry(
            session,
            user_id=user_id,
            effective_date=date(2026, 4, 1),
            direction="inflow",
            category="salary",
            amount_cents=250000,
            description="Einnahme",
            source_type="manual_income",
        )
        rows = session.execute(select(CashflowEntry)).scalars().all()

    assert second["id"] == first["id"]
    assert len(rows) == 1


def test_create_cashflow_entry_keeps_distinct_cashflow_lines() -> None:
    Session = _session_factory()
    user_id = "user-cashflow-distinct"

    with Session() as session:
        session.add(User(user_id=user_id, username="max", password_hash="test"))
        first = create_cashflow_entry(
            session,
            user_id=user_id,
            effective_date=date(2026, 4, 1),
            direction="inflow",
            category="salary",
            amount_cents=250000,
            description="Einnahme",
            source_type="manual_income",
        )
        second = create_cashflow_entry(
            session,
            user_id=user_id,
            effective_date=date(2026, 4, 1),
            direction="inflow",
            category="salary",
            amount_cents=250000,
            description="Bonus",
            source_type="manual_income",
        )
        rows = session.execute(select(CashflowEntry)).scalars().all()

    assert second["id"] != first["id"]
    assert len(rows) == 2
