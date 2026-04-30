from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import AuditEvent, IngestionProposal, Transaction
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
            username="ingestion-hardening-admin",
            password="test-password",
            display_name="Ingestion Hardening Admin",
            is_admin=True,
        )
        return user.user_id


def test_yolo_auto_commits_only_high_confidence_safe_transaction(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    service.update_settings(
        user_id=user_id,
        shared_group_id=None,
        payload={"approval_mode": "yolo_auto", "auto_commit_confidence_threshold": 0.9},
    )
    session_row = service.create_session(user_id=user_id, shared_group_id=None, approval_mode="yolo_auto")

    proposal = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            "type": "create_transaction",
            "purchased_at": datetime(2026, 4, 30, 12, 0, tzinfo=UTC).isoformat(),
            "merchant_name": "Safe Bakery",
            "total_gross_cents": 420,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "cash",
            "source_transaction_id": None,
            "idempotency_key": "test-yolo-safe-transaction",
            "confidence": 0.96,
            "items": [],
            "discounts": [],
            "raw_payload": {"fixture": "yolo"},
        },
        actor_id=user_id,
    )

    assert proposal["status"] == "committed"
    assert proposal["commit_result_json"]["transaction_id"]
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
        actions = {
            row.action
            for row in session.execute(select(AuditEvent).where(AuditEvent.entity_id == proposal["id"])).scalars()
        }
    assert "ingestion.proposal_auto_approved" in actions
    engine.dispose()


def test_yolo_auto_keeps_ambiguous_and_recurring_inputs_in_review(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    service.update_settings(user_id=user_id, shared_group_id=None, payload={"approval_mode": "yolo_auto"})
    session_row = service.create_session(user_id=user_id, shared_group_id=None, approval_mode="yolo_auto")

    recurring = service.create_message_proposals(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        message="I pay 39.99 euros monthly to Vodafone for my phone subscription.",
        actor_id=user_id,
    )["proposals"][0]
    ambiguous = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            "type": "create_transaction",
            "purchased_at": datetime(2026, 4, 30, 12, 0, tzinfo=UTC).isoformat(),
            "merchant_name": "Unclear Shop",
            "total_gross_cents": 1000,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "cash",
            "source_transaction_id": None,
            "idempotency_key": "test-yolo-low-confidence",
            "confidence": 0.5,
            "items": [],
            "discounts": [],
            "raw_payload": {"fixture": "low"},
        },
        actor_id=user_id,
    )

    assert recurring["type"] == "create_recurring_bill_candidate"
    assert recurring["status"] == "pending_review"
    assert ambiguous["status"] == "pending_review"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
    engine.dispose()


def test_pdf_intake_creates_review_proposal_without_direct_write(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="file")
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=b"%PDF-1.7\nnot a parseable bank table",
        file_name="receipt.pdf",
        mime_type="application/pdf",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    assert parsed["count"] == 0
    assert parsed["proposals"][0]["type"] == "needs_review"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
    engine.dispose()


def test_batch_review_and_undo_recent_agent_transaction(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)
    proposals = [
        service.create_message_proposals(
            session_id=session_row["id"],
            user_id=user_id,
            shared_group_id=None,
            message=f"I paid {amount} euros cash at Shop {amount} today.",
            actor_id=user_id,
        )["proposals"][0]
        for amount in (5, 6)
    ]

    approved = service.batch_approve_proposals(
        proposal_ids=[proposal["id"] for proposal in proposals],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    committed = service.batch_commit_proposals(
        proposal_ids=[proposal["id"] for proposal in approved["items"]],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    undone = service.undo_proposal_commit(
        proposal_id=committed["items"][0]["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert committed["count"] == 2
    assert undone["status"] == "approved"
    assert undone["commit_result_json"]["undone"] is True
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
        assert session.scalar(select(func.count(IngestionProposal.id))) == 2
    engine.dispose()


def test_non_transaction_commit_cannot_be_undone(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)
    proposal = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={"type": "ignore", "reason": "Internal transfer", "confidence": 0.99},
        actor_id=user_id,
    )
    service.approve_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    committed = service.commit_proposal(
        proposal_id=proposal["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert committed["status"] == "committed"
    with pytest.raises(ValueError, match="safe undo"):
        service.undo_proposal_commit(
            proposal_id=proposal["id"],
            user_id=user_id,
            shared_group_id=None,
            actor_id=user_id,
        )
    engine.dispose()
