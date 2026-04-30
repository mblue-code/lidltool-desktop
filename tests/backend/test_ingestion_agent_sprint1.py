from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import AuditEvent, Transaction
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
            username="ingestion-admin",
            password="test-password",
            display_name="Ingestion Admin",
            is_admin=True,
        )
        return user.user_id


def test_free_text_proposal_commits_once_through_manual_ingest(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)

    created_session = service.create_session(
        user_id=user_id,
        shared_group_id=None,
        title="Cash notes",
    )
    message_result = service.create_message_proposals(
        session_id=created_session["id"],
        user_id=user_id,
        shared_group_id=None,
        message="I paid 25 euros cash at the ice cream store today.",
        actor_id=user_id,
    )
    proposal = message_result["proposals"][0]

    assert proposal["type"] == "create_transaction"
    assert proposal["status"] == "pending_review"
    assert proposal["payload_json"]["merchant_name"] == "Ice cream store"
    assert proposal["payload_json"]["total_gross_cents"] == 2500

    approved = service.approve_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    assert approved["status"] == "approved"

    committed = service.commit_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    repeated = service.commit_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert committed["status"] == "committed"
    assert committed["commit_result_json"]["transaction_id"] == repeated["commit_result_json"]["transaction_id"]
    with session_scope(sessions) as session:
        transaction_count = session.scalar(select(func.count(Transaction.id)))
        audit_actions = {
            row.action
            for row in session.execute(select(AuditEvent).where(AuditEvent.entity_id == proposal["id"])).scalars()
        }
    assert transaction_count == 1
    assert "ingestion.proposal_approved" in audit_actions
    assert "ingestion.proposal_committed" in audit_actions
    engine.dispose()


def test_rejected_proposal_does_not_commit(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    created_session = service.create_session(user_id=user_id, shared_group_id=None)
    proposal = service.create_message_proposals(
        session_id=created_session["id"],
        user_id=user_id,
        shared_group_id=None,
        message="I paid 25 euros cash at the ice cream store today.",
        actor_id=user_id,
    )["proposals"][0]

    rejected = service.reject_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    assert rejected["status"] == "rejected"
    with pytest.raises(ValueError, match="approved"):
        service.commit_proposal(
            proposal_id=proposal["id"],
            user_id=user_id,
            shared_group_id=None,
            actor_id=user_id,
        )

    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
    engine.dispose()


def test_invalid_model_originated_payload_is_rejected(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    created_session = service.create_session(user_id=user_id, shared_group_id=None)

    with pytest.raises(Exception):
        service.create_proposal(
            session_id=created_session["id"],
            user_id=user_id,
            shared_group_id=None,
            payload={
                "type": "create_transaction",
                "merchant_name": "Missing amount",
                "confidence": 0.9,
            },
            actor_id=user_id,
        )
    engine.dispose()
