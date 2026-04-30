from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from lidltool.auth.users import create_local_user
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import IngestionProposal, Transaction
from lidltool.ingest.manual_ingest import ManualIngestService, ManualTransactionInput
from lidltool.ingestion_agent import IngestionAgentService, IngestionAgentToolRunner, IngestionToolContext


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
            username="ingestion-tools-admin",
            password="test-password",
            display_name="Ingestion Tools Admin",
            is_admin=True,
        )
        return user.user_id


def test_tool_runner_exposes_only_constrained_ingestion_tools(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    runner = IngestionAgentToolRunner(session_factory=sessions)
    context = IngestionToolContext(user_id=user_id, actor_id=user_id)

    assert "commit_ingestion_proposal" not in runner.tool_names
    assert "python" not in runner.tool_names
    with pytest.raises(ValueError, match="unsupported ingestion tool"):
        runner.run_tool("python", {"code": "print('no')"}, context=context)
    with pytest.raises(ValidationError):
        runner.run_tool(
            "parse_statement_preview",
            {
                "text": "Date,Payee,Amount\n2026-04-30,Bakery,-4.20",
                "filesystem_path": "/tmp/statement.csv",
            },
            context=context,
        )
    engine.dispose()


def test_tool_runner_can_parse_preview_without_staging_or_writing(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    runner = IngestionAgentToolRunner(session_factory=sessions)

    preview = runner.run_tool(
        "parse_statement_preview",
        {"text": "Date,Payee,Amount,Currency\n2026-04-30,Bakery,-4.20,EUR", "max_rows": 5},
        context=IngestionToolContext(user_id=user_id, actor_id=user_id),
    )

    assert preview["count"] == 1
    assert preview["items"][0]["payee"] == "Bakery"
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
        assert session.scalar(select(func.count(IngestionProposal.id))) == 0
    engine.dispose()


def test_tool_runner_creates_validated_proposals_but_not_transactions(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    service = IngestionAgentService(session_factory=sessions)
    session_row = service.create_session(user_id=user_id, shared_group_id=None)
    runner = IngestionAgentToolRunner(session_factory=sessions)
    context = IngestionToolContext(user_id=user_id, actor_id=user_id)

    proposal = runner.run_tool(
        "create_ingestion_proposal",
        {
            "session_id": session_row["id"],
            "payload": {
                "type": "create_transaction",
                "purchased_at": datetime(2026, 4, 30, 12, 0, tzinfo=UTC).isoformat(),
                "merchant_name": "Tool Bakery",
                "total_gross_cents": 420,
                "currency": "EUR",
                "source_id": "agent_ingest",
                "source_display_name": "Agent Ingestion",
                "source_account_ref": "cash",
                "source_transaction_id": None,
                "idempotency_key": "tool-layer-test-transaction",
                "confidence": 0.88,
                "items": [],
                "discounts": [],
                "raw_payload": {"input_kind": "tool_test"},
            },
            "explanation": "Tool-created proposal for review.",
        },
        context=context,
    )
    summary = runner.run_tool(
        "render_ingestion_summary",
        {"session_id": session_row["id"]},
        context=context,
    )

    assert proposal["status"] == "pending_review"
    assert summary["proposal_count"] == 1
    assert summary["by_type"]["create_transaction"] == 1
    with session_scope(sessions) as session:
        assert session.scalar(select(func.count(Transaction.id))) == 0
        assert session.scalar(select(func.count(IngestionProposal.id))) == 1
    engine.dispose()


def test_tool_runner_searches_existing_transactions_with_minimal_result_shape(tmp_path: Path) -> None:
    engine, sessions = _build_sessions(tmp_path)
    user_id = _create_user(sessions)
    ManualIngestService(session_factory=sessions).ingest_transaction(
        payload=ManualTransactionInput(
            purchased_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
            merchant_name="Amazon Marketplace",
            total_gross_cents=2599,
            source_id="amazon_de",
            source_kind="connector",
            source_display_name="Amazon DE",
            source_account_ref="amazon",
            source_transaction_id="tool-search-existing",
            user_id=user_id,
            currency="EUR",
            raw_payload={"private": "not returned by tool"},
            ingest_channel="test",
        ),
        actor_type="system",
        actor_id=None,
        audit_action="transaction.test_seeded",
    )
    runner = IngestionAgentToolRunner(session_factory=sessions)

    result = runner.run_tool(
        "search_transactions",
        {
            "merchant_query": "amazon",
            "amount_cents": 2599,
            "occurred_on": "2026-04-30",
        },
        context=IngestionToolContext(user_id=user_id, actor_id=user_id),
    )

    assert result["count"] == 1
    item = result["items"][0]
    assert item["merchant_name"] == "Amazon Marketplace"
    assert "raw_payload" not in item
    assert "items" not in item
    engine.dispose()
