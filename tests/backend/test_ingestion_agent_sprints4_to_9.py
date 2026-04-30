from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.config import AppConfig
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import AuditEvent, CashflowEntry, IngestionProposal, Transaction
from lidltool.ingestion_agent import IngestionAgentService
from lidltool.ocr.providers.base import OcrResult


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


def test_yolo_auto_commits_complete_transaction_but_keeps_recurring_candidate_in_review(tmp_path: Path) -> None:
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
    complete_transaction = service.create_proposal(
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
    assert complete_transaction["status"] == "committed"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
    engine.dispose()


def test_yolo_auto_commits_complete_inflow_or_non_household_transactions(tmp_path: Path) -> None:
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
            "merchant_name": "Broker Dividend",
            "total_gross_cents": 4200,
            "direction": "inflow",
            "ledger_scope": "investment",
            "dashboard_include": False,
            "currency": "EUR",
            "source_id": "agent_ingest",
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank_statement",
            "source_transaction_id": None,
            "idempotency_key": "test-yolo-investment-inflow",
            "confidence": 0.99,
            "items": [],
            "discounts": [],
            "raw_payload": {"fixture": "investment-inflow"},
        },
        actor_id=user_id,
    )

    assert proposal["status"] == "committed"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
    engine.dispose()


def test_ingestion_settings_store_personal_system_prompt(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)

    settings = service.update_settings(
        user_id=user_id,
        shared_group_id=None,
        payload={"personal_system_prompt": "Never ingest rental income into the household book."},
    )

    assert settings["personal_system_prompt"] == "Never ingest rental income into the household book."
    assert service.get_settings(user_id=user_id, shared_group_id=None)["personal_system_prompt"] == settings["personal_system_prompt"]
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


def test_pdf_intake_uses_model_extraction_for_review_proposal_without_direct_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-ingestion-test-secret-key",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.document_storage_path.mkdir(parents=True, exist_ok=True)

    class FakeRouter:
        def __init__(self, _config):
            pass

        def extract(self, *, payload: bytes, mime_type: str, file_name: str):
            assert payload == b"%PDF-1.7\nfake receipt"
            assert mime_type == "application/pdf"
            return type(
                "Routed",
                (),
                {
                    "result": OcrResult(
                        provider="fake_vision_model",
                        text="Eis Laden\n30.04.2026\nSumme 25,00",
                        confidence=0.91,
                        latency_ms=12,
                        metadata={"fixture": "pdf"},
                    ),
                    "fallback_used": False,
                    "attempted_providers": ["fake_vision_model"],
                },
            )()

    monkeypatch.setattr("lidltool.ingestion_agent.service.OcrProviderRouter", FakeRouter)

    service = IngestionAgentService(session_factory=sessions, config=config)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="file")
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=b"%PDF-1.7\nfake receipt",
        file_name="receipt.pdf",
        mime_type="application/pdf",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    assert parsed["count"] == 0
    proposal = parsed["proposals"][0]
    assert proposal["type"] == "create_transaction"
    assert proposal["status"] == "pending_review"
    assert proposal["payload_json"]["merchant_name"] == "Eis Laden"
    assert proposal["payload_json"]["total_gross_cents"] == 2500
    assert proposal["payload_json"]["raw_payload"]["input_kind"] == "document"
    assert proposal["model_metadata_json"]["strategy"] == "deterministic_document_receipt_fallback"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
        stored = session.get(IngestionProposal, proposal["id"])
        assert stored is not None
        assert stored.payload_json["idempotency_key"].startswith("ingest-doc:")
    engine.dispose()


def test_document_semantic_model_can_create_recurring_candidate_without_direct_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-ingestion-test-secret-key",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.document_storage_path.mkdir(parents=True, exist_ok=True)

    class FakeRouter:
        def __init__(self, _config):
            pass

        def extract(self, *, payload: bytes, mime_type: str, file_name: str):
            return type(
                "Routed",
                (),
                {
                    "result": OcrResult(
                        provider="fake_vision_model",
                        text="Fitness Studio Rechnung\nmonatlich 49,99 EUR\n01.04.2026",
                        confidence=0.94,
                        latency_ms=10,
                        metadata={},
                    ),
                    "fallback_used": False,
                    "attempted_providers": ["fake_vision_model"],
                },
            )()

    def fake_semantic(self, *, text: str, file_id: str):
        return (
            {
                "document_kind": "invoice",
                "confidence": 0.91,
                "proposals": [
                    {
                        "payload": {
                            "type": "create_recurring_bill_candidate",
                            "name": "Fitness Studio",
                            "merchant_canonical": "Fitness Studio",
                            "amount_cents": 4999,
                            "currency": "EUR",
                            "frequency": "monthly",
                            "first_seen_date": "2026-04-01",
                            "evidence": "document_text",
                            "confidence": 0.92,
                        },
                        "explanation": "Monthly invoice detected.",
                        "confidence": 0.92,
                    }
                ],
            },
            "fake_semantic_model",
            15,
        )

    monkeypatch.setattr("lidltool.ingestion_agent.service.OcrProviderRouter", FakeRouter)
    monkeypatch.setattr(IngestionAgentService, "_call_semantic_document_model", fake_semantic)

    service = IngestionAgentService(session_factory=sessions, config=config)
    session_row = service.create_session(user_id=user_id, shared_group_id=None, input_kind="file")
    file_row = service.create_file(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        content=b"%PDF-1.7\nfake invoice",
        file_name="invoice.pdf",
        mime_type="application/pdf",
    )

    parsed = service.parse_file(file_id=file_row["id"], user_id=user_id, shared_group_id=None)

    proposal = parsed["proposals"][0]
    assert proposal["type"] == "create_recurring_bill_candidate"
    assert proposal["status"] == "pending_review"
    assert proposal["payload_json"]["evidence"] == f"ingestion_file:{file_row['id']}"
    assert proposal["confidence"] < 0.9
    assert proposal["model_metadata_json"]["strategy"] == "semantic_document_model"
    assert proposal["model_metadata_json"]["diagnostics"]["semantic_status"] == "completed"
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

    assert proposal["status"] == "committed"
    with pytest.raises(ValueError, match="undone safely"):
        service.undo_proposal_commit(
            proposal_id=proposal["id"],
            user_id=user_id,
            shared_group_id=None,
            actor_id=user_id,
        )
    engine.dispose()


def test_repeated_cashflow_commit_reuses_existing_entry(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)

    payload = {
        "type": "create_cashflow_entry",
        "effective_date": "2026-04-28",
        "direction": "inflow",
        "category": "salary",
        "amount_cents": 260814,
        "currency": "EUR",
        "description": "RUHRMEDIC GMBH",
        "source_type": "agent_ingest",
        "confidence": 0.92,
    }
    first = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload=payload,
        actor_id=user_id,
    )
    second = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload=payload,
        actor_id=user_id,
    )

    service.approve_proposal(proposal_id=first["id"], user_id=user_id, shared_group_id=None, actor_id=user_id)
    committed_first = service.commit_proposal(
        proposal_id=first["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    service.approve_proposal(proposal_id=second["id"], user_id=user_id, shared_group_id=None, actor_id=user_id)
    committed_second = service.commit_proposal(
        proposal_id=second["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert committed_first["commit_result_json"]["reused"] is False
    assert committed_second["commit_result_json"]["reused"] is True
    assert committed_first["commit_result_json"]["cashflow_entry_id"] == committed_second["commit_result_json"]["cashflow_entry_id"]
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(CashflowEntry.id))) == 1
    engine.dispose()


def test_repeated_agent_transaction_commit_reuses_same_merchant_amount_date(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)

    base_payload = {
        "type": "create_transaction",
        "purchased_at": "2026-04-14T00:00:00+00:00",
        "merchant_name": "M..V..CUNHA.SUBSTACK/CARTAXO",
        "total_gross_cents": 2600,
        "direction": "outflow",
        "ledger_scope": "household",
        "dashboard_include": True,
        "currency": "EUR",
        "source_id": "agent_ingest",
        "source_display_name": "Agent Ingestion",
        "source_account_ref": "bank_statement",
        "source_transaction_id": None,
        "confidence": 0.91,
        "items": [],
        "discounts": [],
        "raw_payload": {"input_kind": "statement_row"},
    }
    first = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={**base_payload, "idempotency_key": "substack-first-model-key"},
        actor_id=user_id,
    )
    second = service.create_proposal(
        session_id=session_row["id"],
        user_id=user_id,
        shared_group_id=None,
        payload={
            **base_payload,
            "purchased_at": "2026-04-13T22:00:00+00:00",
            "idempotency_key": "substack-second-model-key",
        },
        actor_id=user_id,
    )

    service.approve_proposal(proposal_id=first["id"], user_id=user_id, shared_group_id=None, actor_id=user_id)
    committed_first = service.commit_proposal(
        proposal_id=first["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )
    service.approve_proposal(proposal_id=second["id"], user_id=user_id, shared_group_id=None, actor_id=user_id)
    committed_second = service.commit_proposal(
        proposal_id=second["id"],
        user_id=user_id,
        shared_group_id=None,
        actor_id=user_id,
    )

    assert committed_first["commit_result_json"]["reused"] is False
    assert committed_second["commit_result_json"]["reused"] is True
    assert committed_first["commit_result_json"]["transaction_id"] == committed_second["commit_result_json"]["transaction_id"]
    with pytest.raises(ValueError, match="reused commits cannot be undone"):
        service.undo_proposal_commit(
            proposal_id=second["id"],
            user_id=user_id,
            shared_group_id=None,
            actor_id=user_id,
        )
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 1
    engine.dispose()
