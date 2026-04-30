from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import IngestionProposal, StatementRow, Transaction
from lidltool.ingest.manual_ingest import ManualIngestService, ManualTransactionInput
from lidltool.ingestion_agent import IngestionAgentService


def _build_sessions(tmp_path: Path):
    db_path = (tmp_path / "lidltool.sqlite").resolve()
    db_url = f"sqlite:///{db_path}"
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    return engine, session_factory(engine)


def _create_user(sessions) -> str:
    with session_scope(sessions) as session:
        user = create_local_user(
            session,
            username="csv-admin",
            password="test-password",
            display_name="CSV Admin",
            is_admin=True,
        )
        return user.user_id


def _seed_amazon(sessions, *, user_id: str) -> None:
    ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            merchant_name="Amazon Marketplace",
            total_gross_cents=2599,
            source_id="amazon_de",
            source_kind="connector",
            source_display_name="Amazon DE",
            source_account_ref="amazon",
            source_transaction_id="amazon-order-csv",
            user_id=user_id,
            currency="EUR",
            raw_payload={"fixture": "csv"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )


def test_csv_rows_are_staged_and_classified_without_duplicate_existing_match(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    _seed_amazon(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="csv")
    csv_text = (
        "Date,Payee,Description,Amount,Currency\n"
        "2026-04-30,Amazon Marketplace,Order,-25.99,EUR\n"
        "2026-04-30,Ice Cream Store,Cash,-5.50,EUR\n"
    )
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=csv_text.encode("utf-8"),
        file_name="bank.csv",
        mime_type="text/csv",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)
    assert parsed["count"] == 2
    classified = service.classify_rows(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    assert classified["count"] == 2

    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(StatementRow.id))) == 2
        assert session.scalar(select(func.count(Transaction.id))) == 1
        proposal_types = {
            row.type
            for row in session.execute(select(IngestionProposal)).scalars()
        }
    assert "already_covered" in proposal_types
    assert "create_transaction" in proposal_types
    engine.dispose()


def test_pasted_german_table_parses_amount_conventions(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)
    pasted = "Buchungstag;Empfänger;Verwendungszweck;Betrag;Währung\n30.04.2026;Bäckerei;Frühstück;-4,20;EUR\n"

    parsed = service.parse_pasted_table(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        text=pasted,
    )

    assert parsed["count"] == 1
    assert parsed["items"][0]["amount_cents"] == -420
    assert parsed["items"][0]["payee"] == "Bäckerei"
    engine.dispose()
