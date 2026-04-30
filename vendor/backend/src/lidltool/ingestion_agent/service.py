from __future__ import annotations

import hashlib
import csv
import io
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.budget.service import create_cashflow_entry
from lidltool.db.audit import record_audit_event
from lidltool.db.engine import session_scope
from lidltool.db.models import (
    IngestionAgentSettings,
    IngestionFile,
    IngestionProposal,
    IngestionProposalMatch,
    IngestionSession,
    StatementRow,
    Transaction,
)
from lidltool.ingest.manual_ingest import (
    AGENT_SOURCE_ID,
    ManualDiscountInput,
    ManualIngestService,
    ManualItemInput,
    ManualTransactionInput,
)
from lidltool.ingestion_agent.schemas import (
    CreateTransactionPayload,
    CreateCashflowEntryPayload,
    CreateRecurringBillCandidatePayload,
    AlreadyCoveredPayload,
    LinkExistingTransactionPayload,
    IgnorePayload,
    ProposalPayload,
    validate_proposal_payload,
)

SESSION_STATUSES = {"draft", "extracting", "proposing", "reviewing", "committing", "completed", "failed", "archived"}
APPROVAL_MODES = {"review_first", "yolo_auto"}
PROPOSAL_STATUSES = {"draft", "pending_review", "auto_approved", "approved", "committing", "committed", "rejected", "failed"}

DEFAULT_INGESTION_SETTINGS = {
    "approval_mode": "review_first",
    "auto_commit_confidence_threshold": 0.95,
    "auto_link_confidence_threshold": 0.98,
    "auto_ignore_confidence_threshold": 0.98,
    "auto_create_recurring_enabled": False,
}


class IngestionAgentService:
    def __init__(self, *, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_session(
        self,
        *,
        user_id: str | None,
        shared_group_id: str | None,
        title: str | None = None,
        input_kind: str = "free_text",
        approval_mode: str = "review_first",
    ) -> dict[str, Any]:
        now = _utcnow()
        with session_scope(self._session_factory) as session:
            settings = _get_or_create_settings(
                session,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            resolved_approval_mode = approval_mode or settings.approval_mode
            if resolved_approval_mode not in APPROVAL_MODES:
                raise ValueError("approval_mode must be review_first or yolo_auto")
            row = IngestionSession(
                user_id=user_id,
                shared_group_id=shared_group_id,
                title=(title or "Ingestion session").strip() or "Ingestion session",
                input_kind=input_kind.strip() or "free_text",
                approval_mode=resolved_approval_mode,
                status="draft",
                summary_json={},
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return _serialize_session(row)

    def get_settings(self, *, user_id: str | None, shared_group_id: str | None = None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            row = _get_or_create_settings(session, user_id=user_id, shared_group_id=shared_group_id)
            session.flush()
            return _serialize_settings(row)

    def update_settings(
        self,
        *,
        user_id: str | None,
        shared_group_id: str | None = None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            row = _get_or_create_settings(session, user_id=user_id, shared_group_id=shared_group_id)
            if "approval_mode" in payload:
                approval_mode = str(payload["approval_mode"]).strip()
                if approval_mode not in APPROVAL_MODES:
                    raise ValueError("approval_mode must be review_first or yolo_auto")
                row.approval_mode = approval_mode
            for key in (
                "auto_commit_confidence_threshold",
                "auto_link_confidence_threshold",
                "auto_ignore_confidence_threshold",
            ):
                if key in payload:
                    value = float(payload[key])
                    if value < 0 or value > 1:
                        raise ValueError(f"{key} must be between 0 and 1")
                    setattr(row, key, value)
            if "auto_create_recurring_enabled" in payload:
                row.auto_create_recurring_enabled = bool(payload["auto_create_recurring_enabled"])
            row.updated_at = _utcnow()
            session.flush()
            return _serialize_settings(row)

    def list_sessions(self, *, user_id: str | None, shared_group_id: str | None = None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            stmt = select(IngestionSession)
            if shared_group_id:
                stmt = stmt.where(IngestionSession.shared_group_id == shared_group_id)
            elif user_id:
                stmt = stmt.where(IngestionSession.user_id == user_id)
            rows = session.execute(stmt.order_by(IngestionSession.created_at.desc())).scalars().all()
            return {"count": len(rows), "items": [_serialize_session(row) for row in rows]}

    def get_session(self, *, session_id: str, user_id: str | None, shared_group_id: str | None = None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            row = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            proposals = (
                session.execute(
                    select(IngestionProposal)
                    .where(IngestionProposal.session_id == row.id)
                    .order_by(IngestionProposal.created_at.asc(), IngestionProposal.id.asc())
                )
                .scalars()
                .all()
            )
            payload = _serialize_session(row)
            payload["proposals"] = [_serialize_proposal(proposal) for proposal in proposals]
            return payload

    def update_session(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            row = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if "title" in payload:
                row.title = str(payload["title"]).strip() or row.title
            if "status" in payload:
                status = str(payload["status"]).strip()
                if status not in SESSION_STATUSES:
                    raise ValueError("unsupported ingestion session status")
                row.status = status
            row.updated_at = _utcnow()
            session.flush()
            return _serialize_session(row)

    def archive_session(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any]:
        return self.update_session(
            session_id=session_id,
            user_id=user_id,
            shared_group_id=shared_group_id,
            payload={"status": "archived"},
        )

    def create_message_proposals(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        message: str,
        actor_id: str | None,
    ) -> dict[str, Any]:
        text = message.strip()
        if not text:
            raise ValueError("message is required")
        proposal_payload = _proposal_from_free_text(
            session_id=session_id,
            text=text,
            today=date.today(),
        )
        proposal = self.create_proposal(
            session_id=session_id,
            user_id=user_id,
            shared_group_id=shared_group_id,
            payload=proposal_payload,
            statement_row_id=None,
            explanation=_proposal_explanation(proposal_payload),
            model_metadata={
                "agent": "ingestion_agent",
                "strategy": "deterministic_free_text_sprint_1",
            },
            actor_id=actor_id,
        )
        return {"message_received": True, "proposals": [proposal]}

    def create_file(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        content: bytes,
        file_name: str | None,
        mime_type: str | None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        now = _utcnow()
        with session_scope(self._session_factory) as session:
            parent = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            parent.input_kind = "csv" if (file_name or "").lower().endswith(".csv") else "file"
            parent.status = "extracting"
            parent.updated_at = now
            row = IngestionFile(
                session_id=session_id,
                storage_uri=f"ingestion://sha256/{digest}",
                file_name=file_name,
                mime_type=mime_type,
                sha256=digest,
                metadata_json={
                    "size_bytes": len(content),
                    "content_text": _decode_text_file(content),
                },
                created_at=now,
            )
            session.add(row)
            session.flush()
            return _serialize_file(row)

    def parse_file(self, *, file_id: str, user_id: str | None, shared_group_id: str | None) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            file_row = session.get(IngestionFile, file_id)
            if file_row is None:
                raise RuntimeError("ingestion file not found")
            self._require_session(
                session,
                session_id=file_row.session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            content_text = str((file_row.metadata_json or {}).get("content_text") or "")
            looks_like_document = _looks_like_document_file(file_row.file_name, file_row.mime_type)
            if looks_like_document:
                parsed = []
            else:
                try:
                    parsed = _parse_statement_text(content_text)
                except ValueError:
                    raise
            if not parsed and looks_like_document:
                proposal_payload = _proposal_from_document_placeholder(file_row)
                proposal_session_id = file_row.session_id
                proposal_file_id = file_row.id
                parent = session.get(IngestionSession, file_row.session_id)
                if parent is not None:
                    parent.status = "reviewing"
                    parent.summary_json = {
                        **(parent.summary_json or {}),
                        "document_intake_files": int((parent.summary_json or {}).get("document_intake_files") or 0) + 1,
                    }
                    parent.updated_at = _utcnow()
                session.flush()
            else:
                created = _store_statement_rows(
                    session,
                    session_id=file_row.session_id,
                    file_id=file_row.id,
                    parsed_rows=parsed,
                )
                parent = session.get(IngestionSession, file_row.session_id)
                if parent is not None:
                    parent.status = "reviewing"
                    parent.summary_json = {**(parent.summary_json or {}), "parsed_rows": created["count"]}
                    parent.updated_at = _utcnow()
                session.flush()
                return created
        if not parsed and looks_like_document:
            proposal = self.create_proposal(
                session_id=proposal_session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                payload=proposal_payload,
                statement_row_id=None,
                explanation=_proposal_explanation(proposal_payload),
                model_metadata={
                    "agent": "ingestion_agent",
                    "strategy": "document_ai_intake_placeholder_sprint_5",
                    "file_id": proposal_file_id,
                },
                actor_id=None,
            )
            return {"count": 0, "items": [], "proposals": [proposal]}
        raise RuntimeError("ingestion file could not be parsed")

    def parse_pasted_table(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        text: str,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            parent = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            parsed = _parse_statement_text(text)
            created = _store_statement_rows(
                session,
                session_id=session_id,
                file_id=None,
                parsed_rows=parsed,
            )
            parent.input_kind = "pasted_table"
            parent.status = "reviewing"
            parent.summary_json = {**(parent.summary_json or {}), "parsed_rows": created["count"]}
            parent.updated_at = _utcnow()
            session.flush()
            return created

    def list_rows(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            rows = (
                session.execute(
                    select(StatementRow)
                    .where(StatementRow.session_id == session_id)
                    .order_by(StatementRow.row_index.asc(), StatementRow.id.asc())
                )
                .scalars()
                .all()
            )
            return {"count": len(rows), "items": [_serialize_statement_row(row) for row in rows]}

    def classify_rows(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        proposals: list[dict[str, Any]] = []
        with session_scope(self._session_factory) as session:
            self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            rows = (
                session.execute(
                    select(StatementRow)
                    .where(StatementRow.session_id == session_id)
                    .order_by(StatementRow.row_index.asc(), StatementRow.id.asc())
                )
                .scalars()
                .all()
            )
            row_snapshots = [_serialize_statement_row(row) for row in rows]
        for row in row_snapshots:
            if row["status"] in {"committed", "ignored"}:
                continue
            payload = _proposal_from_statement_row(row)
            proposal = self.create_proposal(
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                payload=payload,
                statement_row_id=row["id"],
                explanation=_proposal_explanation(payload),
                model_metadata={"agent": "ingestion_agent", "strategy": "deterministic_statement_row_sprint_3"},
                actor_id=actor_id,
            )
            if proposal["type"] == "create_transaction":
                matches = self.refresh_match_candidates(
                    proposal_id=proposal["id"],
                    user_id=user_id,
                    shared_group_id=shared_group_id,
                )
                top = matches["items"][0] if matches["items"] else None
                if top and top["score"] >= 0.9:
                    proposal = self.update_proposal(
                        proposal_id=proposal["id"],
                        user_id=user_id,
                        shared_group_id=shared_group_id,
                        payload={
                            "payload": {
                                "type": "already_covered",
                                "statement_row_id": row["id"],
                                "transaction_id": top["transaction_id"],
                                "confidence": top["score"],
                                "reason": "Statement row matches an existing transaction.",
                                "match_score": top["score"],
                            }
                        },
                    )
                    self._update_row_status(row["id"], "matched")
                else:
                    self._update_row_status(row["id"], "new_expense")
            elif proposal["type"] == "ignore":
                self._update_row_status(row["id"], "ignored")
            else:
                self._update_row_status(row["id"], "needs_review")
            proposals.append(proposal)
        return {"count": len(proposals), "items": proposals}

    def create_proposal(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        payload: dict[str, Any],
        statement_row_id: str | None = None,
        explanation: str | None = None,
        model_metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        validated = validate_proposal_payload(payload)
        now = _utcnow()
        with session_scope(self._session_factory) as session:
            parent = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            parent.status = "reviewing"
            parent.updated_at = now
            proposal = IngestionProposal(
                session_id=parent.id,
                statement_row_id=statement_row_id,
                type=validated.type,
                status="pending_review",
                confidence=Decimal(str(getattr(validated, "confidence", 0))),
                payload_json=validated.model_dump(mode="json"),
                explanation=explanation,
                model_metadata_json=model_metadata or {},
                created_at=now,
                updated_at=now,
            )
            session.add(proposal)
            session.flush()
            record_audit_event(
                session,
                action="ingestion.proposal_created",
                source="ingestion_agent",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={
                    "session_id": session_id,
                    "proposal_type": proposal.type,
                    "status": proposal.status,
                },
            )
            session.flush()
            serialized = _serialize_proposal(proposal)
        return self.apply_approval_policy(
            proposal_id=serialized["id"],
            user_id=user_id,
            shared_group_id=shared_group_id,
            actor_id=None,
        )

    def list_proposals(
        self,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            rows = (
                session.execute(
                    select(IngestionProposal)
                    .where(IngestionProposal.session_id == session_id)
                    .order_by(IngestionProposal.created_at.asc(), IngestionProposal.id.asc())
                )
                .scalars()
                .all()
            )
            return {"count": len(rows), "items": [_serialize_proposal(row) for row in rows]}

    def update_proposal(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if proposal.status in {"committing", "committed"}:
                raise ValueError("committed proposals cannot be edited")
            if "payload" in payload:
                validated = validate_proposal_payload(dict(payload["payload"]))
                proposal.payload_json = validated.model_dump(mode="json")
                proposal.type = validated.type
                proposal.confidence = Decimal(str(getattr(validated, "confidence", 0)))
            if "explanation" in payload:
                proposal.explanation = str(payload["explanation"]) if payload["explanation"] else None
            proposal.updated_at = _utcnow()
            session.flush()
            serialized = _serialize_proposal(proposal)
        return self.apply_approval_policy(
            proposal_id=serialized["id"],
            user_id=user_id,
            shared_group_id=shared_group_id,
            actor_id=None,
        )

    def apply_approval_policy(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            parent = session.get(IngestionSession, proposal.session_id)
            if parent is None:
                raise RuntimeError("ingestion session not found")
            settings = _get_or_create_settings(
                session,
                user_id=parent.user_id,
                shared_group_id=parent.shared_group_id,
            )
            if proposal.status != "pending_review" or parent.approval_mode != "yolo_auto":
                return _serialize_proposal(proposal)
            payload = validate_proposal_payload(proposal.payload_json)
            decision = _auto_approval_decision(
                session,
                proposal=proposal,
                payload=payload,
                settings=settings,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if not decision["allowed"]:
                proposal.model_metadata_json = {
                    **(proposal.model_metadata_json or {}),
                    "auto_policy": decision,
                }
                proposal.updated_at = _utcnow()
                return _serialize_proposal(proposal)
            proposal.status = "auto_approved"
            proposal.model_metadata_json = {
                **(proposal.model_metadata_json or {}),
                "auto_policy": decision,
            }
            proposal.updated_at = _utcnow()
            record_audit_event(
                session,
                action="ingestion.proposal_auto_approved",
                source="ingestion_agent",
                actor_type="system",
                actor_id=actor_id,
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={
                    "session_id": proposal.session_id,
                    "proposal_type": proposal.type,
                    "approval_mode": parent.approval_mode,
                    "confidence": float(proposal.confidence or 0),
                    "deterministic_score": decision.get("deterministic_score"),
                },
            )
            session.flush()
        return self.commit_proposal(
            proposal_id=proposal_id,
            user_id=user_id,
            shared_group_id=shared_group_id,
            actor_id=None,
        )

    def approve_proposal(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        return self._transition_proposal(
            proposal_id=proposal_id,
            user_id=user_id,
            shared_group_id=shared_group_id,
            actor_id=actor_id,
            status="approved",
            action="ingestion.proposal_approved",
        )

    def reject_proposal(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        return self._transition_proposal(
            proposal_id=proposal_id,
            user_id=user_id,
            shared_group_id=shared_group_id,
            actor_id=actor_id,
            status="rejected",
            action="ingestion.proposal_rejected",
        )

    def commit_proposal(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if proposal.status == "committed" and proposal.commit_result_json:
                return _serialize_proposal(proposal)
            if proposal.status not in {"approved", "auto_approved"}:
                raise ValueError("proposal must be approved before commit")
            payload = validate_proposal_payload(proposal.payload_json)
            proposal.status = "committing"
            proposal.updated_at = _utcnow()
            session.flush()

        try:
            if isinstance(payload, CreateTransactionPayload):
                commit_result = self._commit_create_transaction(
                    payload=payload,
                    user_id=user_id,
                    shared_group_id=shared_group_id,
                    actor_id=actor_id,
                )
            elif isinstance(payload, AlreadyCoveredPayload | LinkExistingTransactionPayload):
                commit_result = self._commit_existing_match(payload=payload)
            elif isinstance(payload, CreateCashflowEntryPayload):
                commit_result = self._commit_cashflow_entry(
                    payload=payload,
                    user_id=user_id,
                    actor_id=actor_id,
                )
            elif isinstance(payload, CreateRecurringBillCandidatePayload):
                commit_result = {"kind": "recurring_bill_candidate", "candidate": payload.model_dump(mode="json"), "reused": True}
            elif isinstance(payload, IgnorePayload):
                commit_result = {"kind": "ignore", "reason": payload.reason, "reused": True}
            else:
                raise ValueError(f"proposal type {payload.type} is not committable")
        except Exception as exc:
            with session_scope(self._session_factory) as session:
                proposal = session.get(IngestionProposal, proposal_id)
                if proposal is None:
                    raise
                proposal.status = "failed"
                proposal.error = str(exc)
                proposal.updated_at = _utcnow()
                record_audit_event(
                    session,
                    action="ingestion.proposal_commit_failed",
                    source="ingestion_agent",
                    actor_type="user" if actor_id else "system",
                    actor_id=actor_id,
                    entity_type="ingestion_proposal",
                    entity_id=proposal.id,
                    details={"session_id": proposal.session_id, "proposal_type": proposal.type},
                )
            raise

        with session_scope(self._session_factory) as session:
            proposal = session.get(IngestionProposal, proposal_id)
            if proposal is None:
                raise RuntimeError("proposal not found after commit")
            proposal.status = "committed"
            proposal.commit_result_json = commit_result
            proposal.error = None
            proposal.updated_at = _utcnow()
            parent = session.get(IngestionSession, proposal.session_id)
            if parent is not None:
                parent.status = "completed"
                parent.updated_at = _utcnow()
            record_audit_event(
                session,
                action="ingestion.proposal_committed",
                source="ingestion_agent",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={
                    "session_id": proposal.session_id,
                    "proposal_type": proposal.type,
                    "result_kind": commit_result.get("kind", "transaction"),
                    "transaction_id": commit_result.get("transaction_id"),
                    "reused": bool(commit_result.get("reused")),
                },
            )
            session.flush()
            return _serialize_proposal(proposal)

    def batch_approve_proposals(
        self,
        *,
        proposal_ids: list[str],
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        items = [
            self.approve_proposal(
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                actor_id=actor_id,
            )
            for proposal_id in proposal_ids
        ]
        return {"count": len(items), "items": items}

    def batch_reject_proposals(
        self,
        *,
        proposal_ids: list[str],
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        items = [
            self.reject_proposal(
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                actor_id=actor_id,
            )
            for proposal_id in proposal_ids
        ]
        return {"count": len(items), "items": items}

    def batch_commit_proposals(
        self,
        *,
        proposal_ids: list[str],
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        items = [
            self.commit_proposal(
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                actor_id=actor_id,
            )
            for proposal_id in proposal_ids
        ]
        return {"count": len(items), "items": items}

    def undo_proposal_commit(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if proposal.status != "committed" or not proposal.commit_result_json:
                raise ValueError("only committed proposals can be undone")
            result = dict(proposal.commit_result_json or {})
            if not result.get("transaction_id"):
                raise ValueError("this commit has no safe undo operation")
            transaction = session.get(Transaction, str(result["transaction_id"]))
            if transaction is None:
                raise ValueError("transaction is already absent")
            if transaction.source_id != AGENT_SOURCE_ID:
                raise ValueError("only agent-created transactions can be undone")
            if transaction.documents:
                raise ValueError("transaction has linked documents and cannot be safely undone")
            session.delete(transaction)
            proposal.status = "approved"
            proposal.commit_result_json = {
                **result,
                "undone": True,
                "undone_at": _utcnow().isoformat(),
            }
            proposal.updated_at = _utcnow()
            record_audit_event(
                session,
                action="ingestion.proposal_undone",
                source="ingestion_agent",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={"session_id": proposal.session_id, "transaction_id": result["transaction_id"]},
            )
            session.flush()
            return _serialize_proposal(proposal)

    def refresh_match_candidates(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any]:
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            payload = validate_proposal_payload(proposal.payload_json)
            if not isinstance(payload, CreateTransactionPayload):
                return {"count": 0, "items": []}
            candidates = _find_transaction_matches(
                session,
                payload=payload,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            existing = session.execute(
                select(IngestionProposalMatch).where(IngestionProposalMatch.proposal_id == proposal.id)
            ).scalars().all()
            for row in existing:
                session.delete(row)
            session.flush()
            for candidate in candidates:
                session.add(
                    IngestionProposalMatch(
                        proposal_id=proposal.id,
                        transaction_id=candidate["transaction_id"],
                        score=Decimal(str(candidate["score"])),
                        reason_json=candidate["reason"],
                        selected=False,
                        created_at=_utcnow(),
                    )
                )
            record_audit_event(
                session,
                action="ingestion.matches_refreshed",
                source="ingestion_agent",
                actor_type="system",
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={
                    "session_id": proposal.session_id,
                    "proposal_type": proposal.type,
                    "candidate_count": len(candidates),
                    "top_score": candidates[0]["score"] if candidates else None,
                },
            )
            session.flush()
            return {"count": len(candidates), "items": candidates}

    def _transition_proposal(
        self,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
        status: str,
        action: str,
    ) -> dict[str, Any]:
        if status not in PROPOSAL_STATUSES:
            raise ValueError("unsupported proposal status")
        with session_scope(self._session_factory) as session:
            proposal = self._require_proposal(
                session,
                proposal_id=proposal_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            if proposal.status == "committed":
                raise ValueError("committed proposals cannot change approval state")
            proposal.status = status
            proposal.updated_at = _utcnow()
            record_audit_event(
                session,
                action=action,
                source="ingestion_agent",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                entity_type="ingestion_proposal",
                entity_id=proposal.id,
                details={"session_id": proposal.session_id, "proposal_type": proposal.type},
            )
            session.flush()
            return _serialize_proposal(proposal)

    def _commit_create_transaction(
        self,
        *,
        payload: CreateTransactionPayload,
        user_id: str | None,
        shared_group_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        service = ManualIngestService(session_factory=self._session_factory)
        manual_input = ManualTransactionInput(
            purchased_at=payload.purchased_at,
            merchant_name=payload.merchant_name,
            total_gross_cents=payload.total_gross_cents,
            source_id=payload.source_id or AGENT_SOURCE_ID,
            source_kind="agent",
            source_display_name=payload.source_display_name or "Agent Ingestion",
            source_account_ref=payload.source_account_ref or "cash",
            source_transaction_id=payload.source_transaction_id,
            idempotency_key=payload.idempotency_key,
            user_id=user_id,
            shared_group_id=shared_group_id,
            currency=payload.currency,
            allocation_mode="personal",
            confidence=payload.confidence,
            items=_manual_items(payload.items),
            discounts=_manual_discounts(payload.discounts),
            raw_payload={
                **payload.raw_payload,
                "ingestion_proposal_type": payload.type,
            },
            ingest_channel="ingestion_agent",
        )
        return service.ingest_transaction(
            payload=manual_input,
            actor_type="user" if actor_id else "system",
            actor_id=actor_id,
            audit_action="transaction.ingestion_agent_ingested",
            reason="approved ingestion proposal",
        )

    def _commit_existing_match(
        self,
        *,
        payload: AlreadyCoveredPayload | LinkExistingTransactionPayload,
    ) -> dict[str, Any]:
        return {
            "kind": payload.type,
            "transaction_id": payload.transaction_id,
            "match_score": getattr(payload, "match_score", None),
            "reused": True,
        }

    def _commit_cashflow_entry(
        self,
        *,
        payload: CreateCashflowEntryPayload,
        user_id: str | None,
        actor_id: str | None,
    ) -> dict[str, Any]:
        if not user_id:
            raise ValueError("cashflow proposals require a user")
        with session_scope(self._session_factory) as session:
            result = create_cashflow_entry(
                session,
                user_id=user_id,
                effective_date=payload.effective_date,
                direction=payload.direction,
                category=payload.category,
                amount_cents=payload.amount_cents,
                currency=payload.currency,
                description=payload.description,
                source_type=payload.source_type,
                linked_transaction_id=payload.linked_transaction_id,
                linked_recurring_occurrence_id=payload.linked_recurring_occurrence_id,
                notes=payload.notes,
            )
            record_audit_event(
                session,
                action="cashflow.ingestion_agent_created",
                source="ingestion_agent",
                actor_type="user" if actor_id else "system",
                actor_id=actor_id,
                entity_type="cashflow_entry",
                entity_id=str(result["id"]),
                details={"proposal_type": payload.type},
            )
            return {"kind": "cashflow_entry", "cashflow_entry_id": result["id"], "entry": result, "reused": False}

    def _update_row_status(self, row_id: str, status: str) -> None:
        with session_scope(self._session_factory) as session:
            row = session.get(StatementRow, row_id)
            if row is not None:
                row.status = status
                row.updated_at = _utcnow()

    def _require_session(
        self,
        session: Session,
        *,
        session_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> IngestionSession:
        row = session.get(IngestionSession, session_id)
        if row is None or not _session_visible(row, user_id=user_id, shared_group_id=shared_group_id):
            raise RuntimeError("ingestion session not found")
        return row

    def _require_proposal(
        self,
        session: Session,
        *,
        proposal_id: str,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> IngestionProposal:
        proposal = session.get(IngestionProposal, proposal_id)
        if proposal is None:
            raise RuntimeError("ingestion proposal not found")
        parent = session.get(IngestionSession, proposal.session_id)
        if parent is None or not _session_visible(parent, user_id=user_id, shared_group_id=shared_group_id):
            raise RuntimeError("ingestion proposal not found")
        return proposal


def _proposal_from_free_text(*, session_id: str, text: str, today: date) -> dict[str, Any]:
    recurring = _recurring_candidate_from_text(text, today=today)
    if recurring is not None:
        return recurring
    parsed = _parse_free_text_transaction(text)
    if parsed is None:
        return {
            "type": "needs_review",
            "reason": "Could not confidently extract merchant and amount from the text.",
            "evidence": text,
            "confidence": 0.2,
        }
    merchant, amount_cents, currency, source_account_ref = parsed
    purchased_at = datetime(today.year, today.month, today.day, 12, 0, tzinfo=UTC)
    if not _mentions_today(text):
        purchased_at = _utcnow()
    idempotency_key = _free_text_idempotency_key(
        session_id=session_id,
        text=text,
        merchant=merchant,
        amount_cents=amount_cents,
        purchased_at=purchased_at,
    )
    return {
        "type": "create_transaction",
        "purchased_at": purchased_at.isoformat(),
        "merchant_name": merchant,
        "total_gross_cents": amount_cents,
        "currency": currency,
        "source_id": AGENT_SOURCE_ID,
        "source_display_name": "Agent Ingestion",
        "source_account_ref": source_account_ref,
        "source_transaction_id": None,
        "idempotency_key": idempotency_key,
        "confidence": 0.86,
        "items": [],
        "discounts": [],
        "raw_payload": {
            "input_kind": "free_text",
            "evidence": text,
        },
    }


def _proposal_from_statement_row(row: StatementRow | dict[str, Any]) -> dict[str, Any]:
    row_id = row.id if isinstance(row, StatementRow) else str(row["id"])
    payee = row.payee if isinstance(row, StatementRow) else row.get("payee")
    row_description = row.description if isinstance(row, StatementRow) else row.get("description")
    amount_cents_raw = row.amount_cents if isinstance(row, StatementRow) else row.get("amount_cents")
    occurred_at = row.occurred_at if isinstance(row, StatementRow) else (
        datetime.fromisoformat(row["occurred_at"]) if row.get("occurred_at") else None
    )
    currency = row.currency if isinstance(row, StatementRow) else str(row.get("currency") or "EUR")
    row_hash = row.row_hash if isinstance(row, StatementRow) else str(row.get("row_hash"))
    description = " ".join(str(part) for part in [payee, row_description] if part).strip()
    recurring = _recurring_candidate_from_statement_row(
        row_id=row_id,
        description=description,
        occurred_at=occurred_at,
        amount_cents_raw=amount_cents_raw,
        currency=currency,
    )
    if recurring is not None:
        return recurring
    if re.search(r"\b(transfer|umbuchung|internal|refund|erstattung)\b", description, re.I):
        return {
            "type": "ignore",
            "statement_row_id": row_id,
            "reason": "Statement row looks like an internal transfer, refund, or non-expense movement.",
            "confidence": 0.86,
        }
    if amount_cents_raw is None or occurred_at is None or not (payee or row_description):
        return {
            "type": "needs_review",
            "reason": "Statement row is missing date, amount, or payee.",
            "evidence": description or None,
            "confidence": 0.2,
        }
    amount_cents = abs(int(amount_cents_raw))
    merchant = str(payee or row_description or "Statement row").strip()[:120]
    return {
        "type": "create_transaction",
        "purchased_at": occurred_at.isoformat(),
        "merchant_name": merchant,
        "total_gross_cents": amount_cents,
        "currency": currency or "EUR",
        "source_id": AGENT_SOURCE_ID,
        "source_display_name": "Agent Ingestion",
        "source_account_ref": "bank_statement",
        "source_transaction_id": None,
        "idempotency_key": f"ingest-row:{row_hash}",
        "confidence": 0.82,
        "items": [],
        "discounts": [],
        "raw_payload": {
            "input_kind": "statement_row",
            "statement_row_id": row_id,
            "evidence": description,
        },
    }


def _parse_free_text_transaction(text: str) -> tuple[str, int, str, str] | None:
    amount_match = re.search(r"(?P<amount>\d+(?:[.,]\d{1,2})?)\s*(?P<currency>euros|euro|eur|€)", text, re.I)
    if amount_match is None:
        amount_match = re.search(r"(?P<currency>€)\s*(?P<amount>\d+(?:[.,]\d{1,2})?)", text, re.I)
    if amount_match is None:
        return None
    amount = Decimal(amount_match.group("amount").replace(",", "."))
    amount_cents = int((amount * Decimal("100")).quantize(Decimal("1")))
    after_amount = text[amount_match.end() :].strip(" .")
    merchant = _extract_merchant(after_amount)
    if not merchant:
        return None
    source_account_ref = "cash" if re.search(r"\bcash\b|\bbar\b", text, re.I) else "manual"
    return merchant, amount_cents, "EUR", source_account_ref


def _extract_merchant(text_after_amount: str) -> str | None:
    cleaned = re.sub(r"^(?:in\s+)?(?:cash\s+)?(?:for|at|to|by|with)\s+", "", text_after_amount, flags=re.I)
    cleaned = re.sub(r"\b(today|yesterday|tomorrow)\b.*$", "", cleaned, flags=re.I).strip(" .")
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    if not cleaned:
        return None
    merchant = cleaned[:80].strip()
    return merchant[:1].upper() + merchant[1:]


def _mentions_today(text: str) -> bool:
    return re.search(r"\btoday\b|\bheute\b", text, re.I) is not None


def _free_text_idempotency_key(
    *,
    session_id: str,
    text: str,
    merchant: str,
    amount_cents: int,
    purchased_at: datetime,
) -> str:
    normalized = "|".join(
        [
            session_id,
            purchased_at.date().isoformat(),
            merchant.casefold().strip(),
            str(amount_cents),
            re.sub(r"\s+", " ", text.casefold()).strip(),
        ]
    )
    return "ingest-free-text:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _proposal_explanation(payload: dict[str, Any]) -> str:
    if payload.get("type") == "create_transaction":
        return "Extracted a cash/manual expense from the text. Review merchant, date, amount, and source before committing."
    if payload.get("type") == "create_recurring_bill_candidate":
        return "Detected a recurring-looking obligation. This stays a candidate until explicitly approved."
    if payload.get("type") == "create_cashflow_entry":
        return "Prepared a cashflow entry proposal for review before it is added to the budget timeline."
    return str(payload.get("reason") or "Needs review before any write can happen.")


def _manual_items(items: list[dict[str, Any]]) -> list[ManualItemInput]:
    result: list[ManualItemInput] = []
    for idx, item in enumerate(items, start=1):
        name = str(item.get("name") or f"Item {idx}").strip()
        line_total = int(item.get("line_total_cents") or 0)
        if not name or line_total < 0:
            raise ValueError("invalid transaction item proposal")
        result.append(
            ManualItemInput(
                name=name,
                line_total_cents=line_total,
                qty=Decimal(str(item.get("qty") or "1")),
                unit=str(item["unit"]) if item.get("unit") else None,
                unit_price_cents=int(item["unit_price_cents"]) if item.get("unit_price_cents") is not None else None,
                category=str(item["category"]) if item.get("category") else None,
                raw_payload=dict(item.get("raw_payload") or {}),
            )
        )
    return result


def _manual_discounts(discounts: list[dict[str, Any]]) -> list[ManualDiscountInput]:
    result: list[ManualDiscountInput] = []
    for discount in discounts:
        label = str(discount.get("source_label") or "Discount").strip()
        amount = int(discount.get("amount_cents") or 0)
        if not label or amount <= 0:
            raise ValueError("invalid discount proposal")
        result.append(
            ManualDiscountInput(
                source_label=label,
                amount_cents=amount,
                raw_payload=dict(discount.get("raw_payload") or {}),
            )
        )
    return result


def _find_transaction_matches(
    session: Session,
    *,
    payload: CreateTransactionPayload,
    user_id: str | None,
    shared_group_id: str | None,
) -> list[dict[str, Any]]:
    lower_bound = payload.purchased_at.date().toordinal() - 2
    upper_bound = payload.purchased_at.date().toordinal() + 2
    stmt = select(Transaction)
    if shared_group_id:
        stmt = stmt.where(Transaction.shared_group_id == shared_group_id)
    elif user_id:
        stmt = stmt.where(Transaction.user_id == user_id)
    rows = session.execute(stmt.order_by(Transaction.purchased_at.desc()).limit(500)).scalars().all()
    candidates: list[dict[str, Any]] = []
    for transaction in rows:
        reason: dict[str, Any] = {}
        score = 0.0
        if int(transaction.total_gross_cents) == int(payload.total_gross_cents):
            score += 0.45
            reason["amount"] = "exact"
        else:
            delta = abs(int(transaction.total_gross_cents) - int(payload.total_gross_cents))
            if delta <= 100:
                score += 0.18
                reason["amount"] = "near"
            else:
                reason["amount"] = "different"
        tx_ordinal = transaction.purchased_at.date().toordinal()
        if tx_ordinal == payload.purchased_at.date().toordinal():
            score += 0.35
            reason["date"] = "same_day"
        elif lower_bound <= tx_ordinal <= upper_bound:
            score += 0.18
            reason["date"] = "within_2_days"
        else:
            reason["date"] = "outside_window"
        merchant_score = _merchant_similarity(payload.merchant_name, transaction.merchant_name or "")
        score += merchant_score * 0.2
        reason["merchant_similarity"] = round(merchant_score, 3)
        if score < 0.35:
            continue
        candidates.append(
            {
                "transaction_id": transaction.id,
                "score": round(min(score, 1.0), 3),
                "reason": reason,
                "transaction": {
                    "id": transaction.id,
                    "merchant_name": transaction.merchant_name,
                    "purchased_at": transaction.purchased_at.isoformat(),
                    "total_gross_cents": transaction.total_gross_cents,
                    "currency": transaction.currency,
                    "source_id": transaction.source_id,
                },
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:5]


def _merchant_similarity(left: str, right: str) -> float:
    left_norm = re.sub(r"[^a-z0-9]+", " ", left.casefold()).strip()
    right_norm = re.sub(r"[^a-z0-9]+", " ", right.casefold()).strip()
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        return 1.0
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _decode_text_file(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_statement_text(text: str) -> list[dict[str, Any]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("statement table must include a header row")
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(reader, start=1):
        normalized = {str(key or "").strip(): (value or "").strip() for key, value in raw.items()}
        if not any(normalized.values()):
            continue
        mapped = _map_statement_row(normalized, index=index)
        rows.append(mapped)
    if not rows:
        raise ValueError("statement table did not contain any rows")
    return rows


def _map_statement_row(raw: dict[str, str], *, index: int) -> dict[str, Any]:
    fields = {key.casefold(): key for key in raw}
    occurred_raw = _field(raw, fields, ["date", "transaction date", "buchungstag", "wertstellung", "valuta", "booking date"])
    booked_raw = _field(raw, fields, ["booked", "booking date", "buchung", "buchungsdatum"])
    payee = _field(raw, fields, ["payee", "merchant", "name", "empfänger", "empfaenger", "beguenstigter", "begünstigter"])
    description = _field(raw, fields, ["description", "memo", "purpose", "verwendungszweck", "beschreibung", "text"])
    amount_raw = _field(raw, fields, ["amount", "betrag", "value", "umsatz"])
    debit_raw = _field(raw, fields, ["debit", "belastung", "soll"])
    credit_raw = _field(raw, fields, ["credit", "gutschrift", "haben"])
    currency = _field(raw, fields, ["currency", "währung", "waehrung"]) or "EUR"
    amount_cents = _parse_amount_cents(amount_raw)
    if amount_cents is None:
        debit_cents = _parse_amount_cents(debit_raw)
        credit_cents = _parse_amount_cents(credit_raw)
        if debit_cents is not None:
            amount_cents = -abs(debit_cents)
        elif credit_cents is not None:
            amount_cents = abs(credit_cents)
    occurred_at = _parse_statement_date(occurred_raw) or _parse_statement_date(booked_raw)
    booked_at = _parse_statement_date(booked_raw)
    row_hash = hashlib.sha256(
        "|".join([str(index), occurred_raw or "", payee or "", description or "", str(amount_cents), currency]).encode("utf-8")
    ).hexdigest()
    return {
        "row_index": index,
        "row_hash": row_hash,
        "occurred_at": occurred_at,
        "booked_at": booked_at,
        "payee": payee,
        "description": description,
        "amount_cents": amount_cents,
        "currency": currency.strip().upper()[:8] or "EUR",
        "raw_json": raw,
    }


def _field(raw: dict[str, str], fields: dict[str, str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        key = fields.get(candidate.casefold())
        if key and raw.get(key):
            return raw[key]
    for normalized, original in fields.items():
        if any(candidate.casefold() in normalized for candidate in candidates) and raw.get(original):
            return raw[original]
    return None


def _parse_amount_cents(raw: str | None) -> int | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    negative = value.startswith("-") or value.endswith("-")
    value = value.strip("+-")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    else:
        value = value.replace(",", ".")
    try:
        cents = int((Decimal(value) * Decimal("100")).quantize(Decimal("1")))
    except Exception:
        return None
    return -abs(cents) if negative else cents


def _parse_statement_date(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _store_statement_rows(
    session: Session,
    *,
    session_id: str,
    file_id: str | None,
    parsed_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    created: list[StatementRow] = []
    skipped = 0
    for parsed in parsed_rows:
        existing = session.execute(
            select(StatementRow).where(
                StatementRow.session_id == session_id,
                StatementRow.row_hash == parsed["row_hash"],
            )
        ).scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue
        row = StatementRow(
            session_id=session_id,
            file_id=file_id,
            row_index=int(parsed["row_index"]),
            row_hash=str(parsed["row_hash"]),
            occurred_at=parsed["occurred_at"],
            booked_at=parsed["booked_at"],
            payee=parsed["payee"],
            description=parsed["description"],
            amount_cents=parsed["amount_cents"],
            currency=parsed["currency"],
            raw_json=parsed["raw_json"],
            status="parsed",
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        session.add(row)
        created.append(row)
    session.flush()
    return {
        "count": len(created),
        "skipped_duplicates": skipped,
        "items": [_serialize_statement_row(row) for row in created],
    }


def _get_or_create_settings(
    session: Session,
    *,
    user_id: str | None,
    shared_group_id: str | None,
) -> IngestionAgentSettings:
    stmt = select(IngestionAgentSettings)
    if shared_group_id:
        stmt = stmt.where(IngestionAgentSettings.shared_group_id == shared_group_id)
    else:
        stmt = stmt.where(
            IngestionAgentSettings.user_id == user_id,
            IngestionAgentSettings.shared_group_id.is_(None),
        )
    row = session.execute(stmt).scalar_one_or_none()
    if row is not None:
        return row
    now = _utcnow()
    row = IngestionAgentSettings(
        user_id=user_id,
        shared_group_id=shared_group_id,
        approval_mode=str(DEFAULT_INGESTION_SETTINGS["approval_mode"]),
        auto_commit_confidence_threshold=float(DEFAULT_INGESTION_SETTINGS["auto_commit_confidence_threshold"]),
        auto_link_confidence_threshold=float(DEFAULT_INGESTION_SETTINGS["auto_link_confidence_threshold"]),
        auto_ignore_confidence_threshold=float(DEFAULT_INGESTION_SETTINGS["auto_ignore_confidence_threshold"]),
        auto_create_recurring_enabled=bool(DEFAULT_INGESTION_SETTINGS["auto_create_recurring_enabled"]),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    return row


def _serialize_settings(row: IngestionAgentSettings) -> dict[str, Any]:
    return {
        "approval_mode": row.approval_mode,
        "auto_commit_confidence_threshold": row.auto_commit_confidence_threshold,
        "auto_link_confidence_threshold": row.auto_link_confidence_threshold,
        "auto_ignore_confidence_threshold": row.auto_ignore_confidence_threshold,
        "auto_create_recurring_enabled": row.auto_create_recurring_enabled,
        "updated_at": row.updated_at.isoformat(),
    }


def _auto_approval_decision(
    session: Session,
    *,
    proposal: IngestionProposal,
    payload: ProposalPayload,
    settings: IngestionAgentSettings,
    user_id: str | None,
    shared_group_id: str | None,
) -> dict[str, Any]:
    confidence = float(proposal.confidence or 0)
    if isinstance(payload, CreateTransactionPayload):
        if not payload.merchant_name or not payload.purchased_at or payload.total_gross_cents <= 0:
            return {"allowed": False, "reason": "missing_required_transaction_fields"}
        candidates = _find_transaction_matches(
            session,
            payload=payload,
            user_id=user_id,
            shared_group_id=shared_group_id,
        )
        top_score = float(candidates[0]["score"]) if candidates else 0.0
        if top_score >= settings.auto_link_confidence_threshold:
            return {"allowed": False, "reason": "high_confidence_existing_match", "deterministic_score": top_score}
        if confidence >= settings.auto_commit_confidence_threshold:
            return {"allowed": True, "reason": "high_confidence_new_transaction", "deterministic_score": top_score}
        return {"allowed": False, "reason": "below_create_threshold", "deterministic_score": top_score}
    if isinstance(payload, AlreadyCoveredPayload | LinkExistingTransactionPayload):
        score = float(getattr(payload, "match_score", 0) or getattr(payload, "confidence", 0) or 0)
        return {
            "allowed": score >= settings.auto_link_confidence_threshold,
            "reason": "link_score_threshold",
            "deterministic_score": score,
        }
    if isinstance(payload, IgnorePayload):
        return {
            "allowed": confidence >= settings.auto_ignore_confidence_threshold,
            "reason": "ignore_confidence_threshold",
            "deterministic_score": confidence,
        }
    if isinstance(payload, CreateRecurringBillCandidatePayload):
        return {"allowed": False, "reason": "recurring_candidates_require_review"}
    return {"allowed": False, "reason": "proposal_type_requires_review"}


def _recurring_candidate_from_text(text: str, *, today: date) -> dict[str, Any] | None:
    if not re.search(r"\b(monthly|every month|recurring|subscription|monatlich|abo|wiederkehrend)\b", text, re.I):
        return None
    parsed = _parse_free_text_transaction(text)
    if parsed is None:
        return None
    merchant, amount_cents, currency, _source_account_ref = parsed
    return {
        "type": "create_recurring_bill_candidate",
        "name": merchant,
        "merchant_canonical": merchant,
        "amount_cents": amount_cents,
        "currency": currency,
        "frequency": "monthly",
        "first_seen_date": today.isoformat(),
        "evidence": text,
        "confidence": 0.82,
    }


def _recurring_candidate_from_statement_row(
    *,
    row_id: str,
    description: str,
    occurred_at: datetime | None,
    amount_cents_raw: int | None,
    currency: str,
) -> dict[str, Any] | None:
    if occurred_at is None or amount_cents_raw is None:
        return None
    if not re.search(r"\b(subscription|monthly|abo|rate|miete|rent|insurance|versicherung)\b", description, re.I):
        return None
    name = description.strip()[:120] or "Recurring bill"
    return {
        "type": "create_recurring_bill_candidate",
        "name": name,
        "merchant_canonical": name,
        "amount_cents": abs(int(amount_cents_raw)),
        "currency": currency or "EUR",
        "frequency": "monthly",
        "first_seen_date": occurred_at.date().isoformat(),
        "evidence": f"statement_row:{row_id}",
        "confidence": 0.8,
    }


def _looks_like_document_file(file_name: str | None, mime_type: str | None) -> bool:
    lower_name = (file_name or "").casefold()
    lower_mime = (mime_type or "").casefold()
    return lower_name.endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic")) or lower_mime in {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/heic",
    }


def _proposal_from_document_placeholder(file_row: IngestionFile) -> dict[str, Any]:
    return {
        "type": "needs_review",
        "reason": "Uploaded document or image was captured for AI intake, but deterministic extraction needs review before any write.",
        "evidence": f"ingestion_file:{file_row.id}",
        "confidence": 0.3,
    }


def _session_visible(
    row: IngestionSession,
    *,
    user_id: str | None,
    shared_group_id: str | None,
) -> bool:
    if shared_group_id:
        return row.shared_group_id == shared_group_id
    if user_id:
        return row.user_id == user_id or row.user_id is None
    return True


def _serialize_session(row: IngestionSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "shared_group_id": row.shared_group_id,
        "title": row.title,
        "input_kind": row.input_kind,
        "approval_mode": row.approval_mode,
        "status": row.status,
        "summary_json": row.summary_json or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_file(row: IngestionFile) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "storage_uri": row.storage_uri,
        "file_name": row.file_name,
        "mime_type": row.mime_type,
        "sha256": row.sha256,
        "metadata_json": {
            key: value
            for key, value in (row.metadata_json or {}).items()
            if key != "content_text"
        },
        "created_at": row.created_at.isoformat(),
    }


def _serialize_statement_row(row: StatementRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "file_id": row.file_id,
        "row_index": row.row_index,
        "row_hash": row.row_hash,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "booked_at": row.booked_at.isoformat() if row.booked_at else None,
        "payee": row.payee,
        "description": row.description,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _serialize_proposal(row: IngestionProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "statement_row_id": row.statement_row_id,
        "type": row.type,
        "status": row.status,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "payload_json": row.payload_json,
        "explanation": row.explanation,
        "model_metadata_json": row.model_metadata_json or {},
        "commit_result_json": row.commit_result_json,
        "error": row.error,
        "matches": [
            {
                "id": match.id,
                "transaction_id": match.transaction_id,
                "score": float(match.score),
                "reason_json": match.reason_json or {},
                "selected": match.selected,
                "created_at": match.created_at.isoformat(),
            }
            for match in sorted(row.matches, key=lambda item: float(item.score), reverse=True)
        ],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)
