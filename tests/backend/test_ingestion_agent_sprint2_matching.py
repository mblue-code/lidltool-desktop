from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Transaction
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
            username="match-admin",
            password="test-password",
            display_name="Match Admin",
            is_admin=True,
        )
        return user.user_id


def _seed_existing_transaction(sessions, *, user_id: str) -> str:
    result = ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            merchant_name="Amazon Marketplace",
            total_gross_cents=2599,
            source_id="amazon_de",
            source_kind="connector",
            source_display_name="Amazon DE",
            source_account_ref="amazon",
            source_transaction_id="amazon-order-1",
            user_id=user_id,
            currency="EUR",
            raw_payload={"fixture": "matching"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )
    return str(result["transaction_id"])


def _seed_lidl_connector_transaction(
    sessions,
    *,
    user_id: str,
    purchased_at: datetime,
    amount_cents: int,
) -> str:
    result = ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=purchased_at,
            merchant_name="Lidl Isenbüttel",
            total_gross_cents=amount_cents,
            source_id="lidl_plus_de",
            source_kind="connector",
            source_display_name="Lidl Plus",
            source_account_ref="lidl_plus",
            source_transaction_id=f"lidl-{purchased_at.date().isoformat()}-{amount_cents}",
            user_id=user_id,
            currency="EUR",
            raw_payload={"fixture": "lidl-settlement-matching"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )
    return str(result["transaction_id"])


def test_exact_existing_transaction_match_can_be_marked_covered(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    existing_transaction_id = _seed_existing_transaction(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    created_session = service.create_session(user_id=user_id, shared_group_id=None)
    proposal = service.create_proposal(
        session_id=created_session["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            "type": "create_transaction",
            "purchased_at": "2026-04-30T12:00:00+00:00",
            "merchant_name": "Amazon",
            "total_gross_cents": 2599,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank",
            "source_transaction_id": None,
            "idempotency_key": "test-match-idempotency-key",
            "confidence": 0.92,
            "items": [],
            "discounts": [],
            "raw_payload": {"input_kind": "statement_row"},
        },
        actor_id=user_id,
    )

    assert proposal["type"] == "already_covered"
    assert proposal["status"] == "committed"
    assert proposal["payload_json"]["transaction_id"] == existing_transaction_id
    assert proposal["payload_json"]["match_score"] >= 0.9
    assert proposal["commit_result_json"]["kind"] == "already_covered"
    assert proposal["commit_result_json"]["transaction_id"] == existing_transaction_id
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
    engine.dispose()


def test_same_amount_different_merchant_stays_lower_confidence(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    _seed_existing_transaction(sessions, user_id=user_id)
    service = IngestionAgentService(session_factory=sessions)
    created_session = service.create_session(user_id=user_id, shared_group_id=None)
    proposal = service.create_proposal(
        session_id=created_session["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            "type": "create_transaction",
            "purchased_at": "2026-04-30T12:00:00+00:00",
            "merchant_name": "Ice Cream Store",
            "total_gross_cents": 2599,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "cash",
            "source_transaction_id": None,
            "idempotency_key": "test-ambiguous-idempotency-key",
            "confidence": 0.88,
            "items": [],
            "discounts": [],
            "raw_payload": {"input_kind": "free_text"},
        },
        actor_id=user_id,
    )

    matches = service.refresh_match_candidates(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
    )

    assert matches["count"] == 1
    assert 0.7 <= matches["items"][0]["score"] < 0.9
    engine.dispose()


def test_lidl_connector_match_uses_exact_amount_in_settlement_window(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    existing_transaction_id = _seed_lidl_connector_transaction(
        sessions,
        user_id=user_id,
        purchased_at=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
        amount_cents=1136,
    )
    service = IngestionAgentService(session_factory=sessions)
    created_session = service.create_session(user_id=user_id, shared_group_id=None)
    proposal = service.create_proposal(
        session_id=created_session["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            "type": "create_transaction",
            "purchased_at": "2026-04-30T12:00:00+00:00",
            "merchant_name": "S. Payment Solutions GmbH",
            "total_gross_cents": 1136,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank",
            "source_transaction_id": None,
            "idempotency_key": "test-lidl-settlement-idempotency-key",
            "confidence": 0.88,
            "items": [],
            "discounts": [],
            "raw_payload": {
                "input_kind": "statement_row",
                "evidence": "Lidl sagt Danke DE501883007399117261 Lidl Pay",
                "raw_cells": [
                    "30.04.26",
                    "S. Payment Solutions GmbH",
                    "Lidl sagt Danke DE501883007399117261 Lidl Pay",
                    "Ausgang",
                    "-11,36",
                ],
            },
        },
        actor_id=user_id,
    )

    assert proposal["type"] == "already_covered"
    assert proposal["status"] == "committed"
    assert proposal["payload_json"]["transaction_id"] == existing_transaction_id
    assert proposal["payload_json"]["match_score"] >= 0.9
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
    engine.dispose()
