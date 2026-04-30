from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.db.engine import session_scope
from lidltool.db.models import Transaction
from lidltool.ingestion_agent.schemas import validate_proposal_payload
from lidltool.ingestion_agent.service import IngestionAgentService, _parse_statement_text

IngestionToolName = Literal[
    "parse_statement_preview",
    "classify_statement_rows",
    "search_transactions",
    "search_match_candidates",
    "create_ingestion_proposal",
    "update_ingestion_proposal",
    "render_ingestion_summary",
]


@dataclass(frozen=True)
class IngestionToolContext:
    user_id: str | None
    shared_group_id: str | None = None
    actor_id: str | None = None


class ParseStatementPreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    max_rows: int = Field(default=10, ge=1, le=50)


class ClassifyStatementRowsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)


class SearchTransactionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_query: str | None = None
    amount_cents: int | None = Field(default=None, ge=0)
    occurred_on: date | None = None
    date_window_days: int = Field(default=2, ge=0, le=31)
    limit: int = Field(default=10, ge=1, le=25)


class SearchMatchCandidatesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)


class CreateIngestionProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    statement_row_id: str | None = None
    payload: dict[str, Any]
    explanation: str | None = None
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateIngestionProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(min_length=1)
    payload: dict[str, Any] | None = None
    explanation: str | None = None


class RenderIngestionSummaryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)


ToolInput = (
    ParseStatementPreviewInput
    | ClassifyStatementRowsInput
    | SearchTransactionsInput
    | SearchMatchCandidatesInput
    | CreateIngestionProposalInput
    | UpdateIngestionProposalInput
    | RenderIngestionSummaryInput
)

TOOL_INPUT_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "parse_statement_preview": TypeAdapter(ParseStatementPreviewInput),
    "classify_statement_rows": TypeAdapter(ClassifyStatementRowsInput),
    "search_transactions": TypeAdapter(SearchTransactionsInput),
    "search_match_candidates": TypeAdapter(SearchMatchCandidatesInput),
    "create_ingestion_proposal": TypeAdapter(CreateIngestionProposalInput),
    "update_ingestion_proposal": TypeAdapter(UpdateIngestionProposalInput),
    "render_ingestion_summary": TypeAdapter(RenderIngestionSummaryInput),
}


class IngestionAgentToolRunner:
    """Constrained tool surface for model-driven ingestion.

    This runner intentionally exposes narrow ingestion operations only. It does
    not provide arbitrary Python execution, filesystem access, SQL execution, or
    direct canonical ledger writes.
    """

    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._service = IngestionAgentService(session_factory=session_factory)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(TOOL_INPUT_ADAPTERS.keys())

    def run_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        context: IngestionToolContext,
    ) -> dict[str, Any]:
        adapter = TOOL_INPUT_ADAPTERS.get(name)
        if adapter is None:
            raise ValueError(f"unsupported ingestion tool: {name}")
        parsed = adapter.validate_python(arguments)
        if isinstance(parsed, ParseStatementPreviewInput):
            return self._parse_statement_preview(parsed)
        if isinstance(parsed, ClassifyStatementRowsInput):
            return self._service.classify_rows(
                session_id=parsed.session_id,
                user_id=context.user_id,
                shared_group_id=context.shared_group_id,
                actor_id=context.actor_id,
            )
        if isinstance(parsed, SearchTransactionsInput):
            return self._search_transactions(parsed, context=context)
        if isinstance(parsed, SearchMatchCandidatesInput):
            return self._service.refresh_match_candidates(
                proposal_id=parsed.proposal_id,
                user_id=context.user_id,
                shared_group_id=context.shared_group_id,
            )
        if isinstance(parsed, CreateIngestionProposalInput):
            validate_proposal_payload(parsed.payload)
            return self._service.create_proposal(
                session_id=parsed.session_id,
                user_id=context.user_id,
                shared_group_id=context.shared_group_id,
                payload=parsed.payload,
                statement_row_id=parsed.statement_row_id,
                explanation=parsed.explanation,
                model_metadata={
                    **parsed.model_metadata,
                    "tool": "create_ingestion_proposal",
                },
                actor_id=context.actor_id,
            )
        if isinstance(parsed, UpdateIngestionProposalInput):
            if parsed.payload is not None:
                validate_proposal_payload(parsed.payload)
            return self._service.update_proposal(
                proposal_id=parsed.proposal_id,
                user_id=context.user_id,
                shared_group_id=context.shared_group_id,
                payload=parsed.model_dump(exclude_none=True),
            )
        if isinstance(parsed, RenderIngestionSummaryInput):
            return self._render_summary(parsed, context=context)
        raise ValueError(f"unsupported ingestion tool input for {name}")

    def _parse_statement_preview(self, parsed: ParseStatementPreviewInput) -> dict[str, Any]:
        rows = _parse_statement_text(parsed.text)
        visible_rows = rows[: parsed.max_rows]
        return {
            "count": len(rows),
            "items": [
                {
                    "row_index": row["row_index"],
                    "occurred_at": row["occurred_at"].isoformat() if row.get("occurred_at") else None,
                    "booked_at": row["booked_at"].isoformat() if row.get("booked_at") else None,
                    "payee": row.get("payee"),
                    "description": row.get("description"),
                    "amount_cents": row.get("amount_cents"),
                    "currency": row.get("currency"),
                }
                for row in visible_rows
            ],
        }

    def _search_transactions(
        self,
        parsed: SearchTransactionsInput,
        *,
        context: IngestionToolContext,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            stmt = select(Transaction)
            if context.shared_group_id:
                stmt = stmt.where(Transaction.shared_group_id == context.shared_group_id)
            elif context.user_id:
                stmt = stmt.where(Transaction.user_id == context.user_id)
            if parsed.amount_cents is not None:
                stmt = stmt.where(Transaction.total_gross_cents == parsed.amount_cents)
            if parsed.occurred_on is not None:
                start = datetime.combine(
                    parsed.occurred_on - timedelta(days=parsed.date_window_days),
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                end = datetime.combine(
                    parsed.occurred_on + timedelta(days=parsed.date_window_days + 1),
                    datetime.min.time(),
                    tzinfo=UTC,
                )
                stmt = stmt.where(Transaction.purchased_at >= start, Transaction.purchased_at < end)
            rows = session.execute(
                stmt.order_by(Transaction.purchased_at.desc()).limit(min(parsed.limit * 5, 100))
            ).scalars().all()
            merchant_query = (parsed.merchant_query or "").casefold().strip()
            if merchant_query:
                rows = [
                    row
                    for row in rows
                    if merchant_query in (row.merchant_name or "").casefold()
                ]
            limited = rows[: parsed.limit]
            return {
                "count": len(limited),
                "items": [
                    {
                        "transaction_id": row.id,
                        "merchant_name": row.merchant_name,
                        "purchased_at": row.purchased_at.isoformat(),
                        "total_gross_cents": row.total_gross_cents,
                        "currency": row.currency,
                        "source_id": row.source_id,
                    }
                    for row in limited
                ],
            }

    def _render_summary(
        self,
        parsed: RenderIngestionSummaryInput,
        *,
        context: IngestionToolContext,
    ) -> dict[str, Any]:
        session_payload = self._service.get_session(
            session_id=parsed.session_id,
            user_id=context.user_id,
            shared_group_id=context.shared_group_id,
        )
        proposals = session_payload.get("proposals") if isinstance(session_payload.get("proposals"), list) else []
        by_status: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for proposal in proposals:
            if not isinstance(proposal, dict):
                continue
            status = str(proposal.get("status") or "unknown")
            proposal_type = str(proposal.get("type") or "unknown")
            by_status[status] = by_status.get(status, 0) + 1
            by_type[proposal_type] = by_type.get(proposal_type, 0) + 1
        return {
            "session": {
                "id": session_payload["id"],
                "title": session_payload["title"],
                "approval_mode": session_payload["approval_mode"],
                "status": session_payload["status"],
            },
            "proposal_count": len(proposals),
            "by_status": by_status,
            "by_type": by_type,
        }
