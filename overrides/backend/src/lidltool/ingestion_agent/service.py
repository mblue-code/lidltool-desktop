from __future__ import annotations

import hashlib
import csv
import io
import json
import re
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from lidltool.ai.codex_oauth import complete_text_with_codex_oauth
from lidltool.ai.config import get_ai_oauth_access_token
from lidltool.ai.runtime.models import JsonCompletionRequest, RuntimePolicyMode, RuntimeTask
from lidltool.ai.runtime.providers import parse_completion_text
from lidltool.ai.runtime.resolver import resolve_runtime
from lidltool.budget.service import create_cashflow_entry
from lidltool.config import AppConfig
from lidltool.db.audit import record_audit_event
from lidltool.db.engine import session_scope
from lidltool.db.models import (
    CashflowEntry,
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
from lidltool.ocr.parser import normalize_receipt_text, parse_receipt_text
from lidltool.ocr.provider_router import OcrProviderRouter
from lidltool.storage.document_storage import DocumentStorage, DocumentStorageError

SESSION_STATUSES = {"draft", "extracting", "proposing", "reviewing", "committing", "completed", "failed", "archived"}
APPROVAL_MODES = {"review_first", "yolo_auto"}
PROPOSAL_STATUSES = {"draft", "pending_review", "auto_approved", "approved", "committing", "committed", "rejected", "failed"}

DEFAULT_INGESTION_SETTINGS = {
    "approval_mode": "review_first",
    "auto_commit_confidence_threshold": 0.95,
    "auto_link_confidence_threshold": 0.98,
    "auto_ignore_confidence_threshold": 0.98,
    "auto_create_recurring_enabled": False,
    "personal_system_prompt": "",
}

DEFAULT_CODEX_OAUTH_INGESTION_MODEL = "gpt-5.4-mini"


def _preferred_codex_oauth_model(config: AppConfig) -> str:
    configured = (getattr(config, "ai_oauth_model", None) or "").strip()
    if configured and "mini" in configured.casefold():
        return configured
    if getattr(config, "ai_oauth_provider", None) == "openai-codex":
        return DEFAULT_CODEX_OAUTH_INGESTION_MODEL
    return configured or (getattr(config, "ai_model", "") or "").strip()

DOCUMENT_SEMANTIC_EXTRACTION_PROMPT = """You are the Outlays ingestion document extraction model.
Return only compact JSON. Do not write to a database. Do not invent missing facts.

Extract proposal payloads from OCR text for a personal finance ingestion review flow.
The optional user_context field is authoritative user guidance for the uploaded evidence. Use it to disambiguate dates, recurrence, merchants, and intent when it does not contradict the evidence.
The optional user_policy field contains persistent user instructions. Follow it unless it conflicts with safety rules or the evidence.
Allowed output proposal payload types:
- create_transaction
- create_cashflow_entry
- create_recurring_bill_candidate
- needs_review
- ignore

Rules:
- Every proposal must be reviewable by a user.
- Required create_transaction fields: purchased_at ISO datetime, merchant_name, total_gross_cents, currency, confidence.
- create_transaction must include direction ("outflow" or "inflow"), ledger_scope ("household", "investment", "internal", or "unknown"), and dashboard_include.
- Use dashboard_include true only for household spending or household income the user wants in the household book. Use false for investments, securities trades, broker transfers, internal account transfers, and landlord/rental/business income unless the user policy says otherwise.
- Prefer create_cashflow_entry for salary, child benefit, and other household income when it should affect household cashflow but is not a purchase receipt.
- Use source_id "agent_ingest", source_display_name "Agent Ingestion", source_account_ref "document_upload", source_transaction_id null.
- Leave idempotency_key as "MODEL_SUPPLIED_PLACEHOLDER"; backend will replace it.
- Use recurring bill candidates for subscriptions, invoices, contracts, utilities, rent, insurance, memberships, or monthly wording.
- Do not create active recurring bills.
- If required facts are absent or ambiguous, return one needs_review proposal with a short reason.
- Use evidence references like "document_text" only; do not quote long raw text.

Return shape:
{
  "document_kind": "receipt|invoice|statement|email|screenshot|unknown",
  "confidence": 0.0,
  "proposals": [
    {"payload": {...}, "explanation": "short user-facing explanation", "confidence": 0.0}
  ]
}
"""

STATEMENT_ROW_SEMANTIC_PROMPT = """You are the Outlays bank statement ingestion model.
Return only compact JSON for one staged CSV/table row. Do not write to a database.

Your job is to interpret the raw row and its surrounding file context, not mechanically copy a column into merchant_name.
Use optional raw_json.user_context as user guidance for the whole upload when present.
Use optional user_policy as persistent user guidance for bank statements. Follow it unless it conflicts with safety rules or the evidence.
Different banks, countries, and export formats use different columns. Infer the statement semantics from the raw cells, nearby headers, preamble, signs, debit/credit columns, and descriptions.
For outgoing payments, the merchant/counterparty is usually the recipient/payee.
For incoming payments, the counterparty is usually the payer/sender.
If the staged row is only a header, preamble, balance line, account metadata, internal transfer, card settlement noise, refund, fee reversal, or duplicate-looking movement, return ignore or needs_review.
Classify every money movement by direction and household relevance:
- Outgoing household expenses may become create_transaction with direction "outflow", ledger_scope "household", dashboard_include true.
- Salary, child support/Kindergeld, refunds that should affect household income, or other household inflows should usually become create_cashflow_entry with direction "inflow" and ledger_scope "household".
- Stock sales, dividends, broker movements, rental income, business revenue, taxes unrelated to household spending, and internal transfers should be ignore or needs_review by default, with ledger_scope "investment" or "internal" in the reasoning if available.
- Never turn an inflow into an outflow transaction just because the transaction schema uses positive amounts.

Allowed proposal payload types:
- create_transaction
- create_cashflow_entry
- create_recurring_bill_candidate
- already_covered only if an existing transaction id was supplied by deterministic matching context
- ignore
- needs_review

Required create_transaction fields: purchased_at ISO datetime, merchant_name, total_gross_cents, currency, confidence, direction, ledger_scope, dashboard_include.
Use source_id "agent_ingest", source_display_name "Agent Ingestion", source_account_ref "bank_statement", source_transaction_id null.
Leave idempotency_key as "MODEL_SUPPLIED_PLACEHOLDER"; backend will replace it.
Do not invent missing dates, amounts, or merchants. If unsure, return needs_review.
Return shape:
{"payload": {...}, "explanation": "short user-facing explanation", "confidence": 0.0}
"""


class IngestionAgentService:
    def __init__(self, *, session_factory: sessionmaker[Session], config: AppConfig | None = None) -> None:
        self._session_factory = session_factory
        self._config = config

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
            if "personal_system_prompt" in payload:
                row.personal_system_prompt = _short_text(str(payload.get("personal_system_prompt") or ""), 4000)
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
            if "approval_mode" in payload:
                approval_mode = str(payload["approval_mode"]).strip()
                if approval_mode not in APPROVAL_MODES:
                    raise ValueError("approval_mode must be review_first or yolo_auto")
                row.approval_mode = approval_mode
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
        user_context: str | None = None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(content).hexdigest()
        now = _utcnow()
        normalized_mime_type = (mime_type or "application/octet-stream").split(";", 1)[0].strip().lower()
        looks_like_document = _looks_like_document_file(file_name, normalized_mime_type)
        storage_uri = f"ingestion://sha256/{digest}"
        metadata: dict[str, Any] = {
            "size_bytes": len(content),
            "content_text": _decode_text_file(content),
        }
        context_text = _short_text((user_context or "").strip(), 4000)
        if context_text:
            metadata["user_context"] = context_text
        if looks_like_document:
            metadata["content_text"] = ""
            if self._config is not None:
                try:
                    storage = DocumentStorage(self._config)
                    storage_uri, stored_sha = storage.store(
                        file_name=file_name or "ingestion-upload.bin",
                        mime_type=normalized_mime_type,
                        payload=content,
                    )
                    digest = stored_sha
                    metadata["document_storage"] = "document_storage"
                except DocumentStorageError as exc:
                    metadata["document_storage_error"] = str(exc)
        with session_scope(self._session_factory) as session:
            parent = self._require_session(
                session,
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
            )
            parent.input_kind = "document" if looks_like_document else ("csv" if (file_name or "").lower().endswith(".csv") else "file")
            parent.status = "extracting"
            parent.updated_at = now
            row = IngestionFile(
                session_id=session_id,
                storage_uri=storage_uri,
                file_name=file_name,
                mime_type=normalized_mime_type,
                sha256=digest,
                metadata_json=metadata,
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
                extraction = self._extract_document_text(file_row)
                content_text = extraction.get("text", "")
                parsed = []
                metadata = dict(file_row.metadata_json or {})
                metadata["document_extraction"] = {
                    key: value
                    for key, value in extraction.items()
                    if key != "text"
                }
                if content_text:
                    metadata["extracted_text_sha256"] = hashlib.sha256(content_text.encode("utf-8")).hexdigest()
                    metadata["extracted_text_preview"] = _privacy_preserving_text_preview(content_text)
                file_row.metadata_json = metadata
            else:
                try:
                    parsed = _parse_statement_text(content_text)
                    parsed = _attach_user_context_to_rows(
                        parsed,
                        context=str((file_row.metadata_json or {}).get("user_context") or ""),
                    )
                except ValueError:
                    raise
            if not parsed and looks_like_document:
                document_proposals = self._proposals_from_document_text(file_row, content_text)
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
            proposals = [
                self.create_proposal(
                    session_id=proposal_session_id,
                    user_id=user_id,
                    shared_group_id=shared_group_id,
                    payload=item["payload"],
                    statement_row_id=None,
                    explanation=item.get("explanation") or _proposal_explanation(item["payload"]),
                    model_metadata={
                        "agent": "ingestion_agent",
                        "strategy": item.get("strategy") or "model_document_extraction_sprint_5",
                        "file_id": proposal_file_id,
                        "document_kind": item.get("document_kind"),
                        "extraction_provider": item.get("extraction_provider"),
                        "semantic_provider": item.get("semantic_provider"),
                        "semantic_latency_ms": item.get("semantic_latency_ms"),
                        "diagnostics": item.get("diagnostics") or {},
                    },
                    actor_id=None,
                )
                for item in document_proposals
            ]
            return {"count": 0, "items": [], "proposals": proposals}
        raise RuntimeError("ingestion file could not be parsed")

    def _proposals_from_document_text(self, file_row: IngestionFile, text: str) -> list[dict[str, Any]]:
        normalized = normalize_receipt_text(text)
        extraction = dict((file_row.metadata_json or {}).get("document_extraction") or {})
        provider = extraction.get("provider")
        if not normalized:
            return [
                {
                    "payload": _proposal_from_document_placeholder(file_row),
                    "explanation": "Document was captured, but no extractable text was produced.",
                    "strategy": "document_extraction_needs_review",
                    "extraction_provider": provider,
                    "document_kind": "unknown",
                    "diagnostics": _document_diagnostics(extraction, semantic_status="no_text"),
                }
            ]

        semantic = self._semantic_document_extraction(file_row=file_row, text=normalized)
        if semantic:
            return semantic

        payload = _proposal_from_document_text(file_row, normalized)
        return [
            {
                "payload": payload,
                "explanation": _proposal_explanation(payload),
                "strategy": "deterministic_document_receipt_fallback",
                "extraction_provider": provider,
                "document_kind": "receipt" if payload["type"] == "create_transaction" else "unknown",
                "diagnostics": _document_diagnostics(extraction, semantic_status="fallback"),
            }
        ]

    def _semantic_document_extraction(self, *, file_row: IngestionFile, text: str) -> list[dict[str, Any]]:
        if self._config is None:
            return []
        extraction = dict((file_row.metadata_json or {}).get("document_extraction") or {})
        try:
            try:
                model_result = self._call_semantic_document_model(file_row=file_row, text=text)
            except TypeError:
                model_result = self._call_semantic_document_model(text=text, file_id=file_row.id)  # type: ignore[call-arg]
        except Exception:
            return []
        if model_result is None:
            return []
        data, provider, latency_ms = model_result
        proposals = _validated_semantic_document_proposals(
            data=data,
            file_row=file_row,
            text=text,
            extraction=extraction,
            semantic_provider=provider,
            semantic_latency_ms=latency_ms,
        )
        return proposals

    def _call_semantic_document_model(self, *, file_row: IngestionFile, text: str) -> tuple[dict[str, Any], str, int] | None:
        assert self._config is not None
        user_policy = self._settings_policy_for_session(file_row.session_id)
        user_json = {
            "file_id": file_row.id,
            "ocr_text": text[:12000],
            "user_context": _short_text(str((file_row.metadata_json or {}).get("user_context") or ""), 4000),
            "user_policy": user_policy,
            "today": date.today().isoformat(),
        }
        resolution = resolve_runtime(
            self._config,
            task=RuntimeTask.OCR_TEXT_FALLBACK,
            policy_mode=RuntimePolicyMode.LOCAL_PREFERRED,
        )
        if resolution.runtime is not None:
            response = resolution.runtime.complete_json(
                JsonCompletionRequest(
                    task=RuntimeTask.OCR_TEXT_FALLBACK,
                    model_name=resolution.runtime.model_name or getattr(self._config, "ai_model", "gpt-5.2-codex"),
                    system_prompt=DOCUMENT_SEMANTIC_EXTRACTION_PROMPT,
                    user_json=user_json,
                    temperature=0,
                    max_tokens=1800,
                    metadata={"feature": "ingestion_document_semantic_extraction"},
                )
            )
            if isinstance(response.data, dict):
                return response.data, f"{response.provider_kind.value}:{response.model_name}", response.latency_ms

        token = get_ai_oauth_access_token(self._config)
        model = _preferred_codex_oauth_model(self._config)
        if token and model:
            started = time.perf_counter()
            response = complete_text_with_codex_oauth(
                bearer_token=token,
                model=model,
                instructions=DOCUMENT_SEMANTIC_EXTRACTION_PROMPT,
                input_items=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(user_json, ensure_ascii=False),
                            }
                        ],
                    }
                ],
                timeout_s=max(float(getattr(self._config, "request_timeout_s", 30.0) or 30.0), 120.0),
            )
            data = parse_completion_text(response.text)
            if isinstance(data, dict):
                latency_ms = response.latency_ms or int((time.perf_counter() - started) * 1000)
                return data, f"chatgpt_codex_oauth:{model}", latency_ms
        return None

    def _extract_document_text(self, file_row: IngestionFile) -> dict[str, Any]:
        if self._config is None:
            return {
                "text": "",
                "status": "model_unavailable",
                "reason": "Ingestion document extraction requires desktop app configuration.",
            }
        if not file_row.storage_uri.startswith("file://"):
            return {
                "text": "",
                "status": "document_not_stored",
                "reason": "Uploaded document was captured before persistent document storage was available.",
            }
        storage = DocumentStorage(self._config)
        payload = storage.read_bytes(storage_uri=file_row.storage_uri)
        router = OcrProviderRouter(self._config)
        routed = router.extract(
            payload=payload,
            mime_type=file_row.mime_type or "application/octet-stream",
            file_name=file_row.file_name or f"{file_row.id}.bin",
        )
        return {
            "text": normalize_receipt_text(routed.result.text),
            "status": "completed",
            "provider": routed.result.provider,
            "fallback_used": routed.fallback_used,
            "attempted_providers": routed.attempted_providers,
            "confidence": routed.result.confidence,
            "latency_ms": routed.result.latency_ms,
            "metadata": routed.result.metadata or {},
        }

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
            semantic = self._semantic_statement_row_proposal(row)
            payload = semantic["payload"] if semantic is not None else _proposal_from_statement_row(row)
            fallback_strategy = _statement_row_fallback_strategy(row) if semantic is None else None
            proposal = self.create_proposal(
                session_id=session_id,
                user_id=user_id,
                shared_group_id=shared_group_id,
                payload=payload,
                statement_row_id=row["id"],
                explanation=(semantic or {}).get("explanation") or _proposal_explanation(payload),
                model_metadata={
                    "agent": "ingestion_agent",
                    "strategy": (semantic or {}).get("strategy") or fallback_strategy or "deterministic_statement_row_sprint_3",
                    "semantic_provider": (semantic or {}).get("semantic_provider"),
                    "semantic_latency_ms": (semantic or {}).get("semantic_latency_ms"),
                    "fallback_reason": "model_unavailable_or_invalid" if semantic is None and fallback_strategy else None,
                },
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
            elif proposal["type"] in {"already_covered", "link_existing_transaction"}:
                self._update_row_status(row["id"], "matched")
            elif proposal["type"] == "ignore":
                self._update_row_status(row["id"], "ignored")
            else:
                self._update_row_status(row["id"], "needs_review")
            proposals.append(proposal)
        return {"count": len(proposals), "items": proposals}

    def _semantic_statement_row_proposal(self, row: dict[str, Any]) -> dict[str, Any] | None:
        if self._config is None:
            return None
        try:
            model_result = self._call_semantic_statement_row_model(row=row)
        except Exception:
            return None
        if model_result is None:
            return None
        data, provider, latency_ms = model_result
        raw_payload = data.get("payload")
        if not isinstance(raw_payload, dict):
            return None
        payload = _prepare_model_statement_row_payload(raw_payload, row=row)
        try:
            validate_proposal_payload(payload)
        except Exception:
            return None
        return {
            "payload": payload,
            "explanation": _short_text(str(data.get("explanation") or _proposal_explanation(payload)), 240),
            "strategy": "semantic_statement_row_model",
            "semantic_provider": provider,
            "semantic_latency_ms": latency_ms,
        }

    def _call_semantic_statement_row_model(self, *, row: dict[str, Any]) -> tuple[dict[str, Any], str, int] | None:
        assert self._config is not None
        user_policy = self._settings_policy_for_session(str(row.get("session_id") or ""))
        user_json = {
            "row": {
                "id": row.get("id"),
                "row_index": row.get("row_index"),
                "occurred_at": row.get("occurred_at"),
                "booked_at": row.get("booked_at"),
                "payee": row.get("payee"),
                "description": row.get("description"),
                "amount_cents": row.get("amount_cents"),
                "currency": row.get("currency"),
                "raw_json": row.get("raw_json"),
            },
            "instructions": {
                "raw_csv_is_authoritative": True,
                "parser_semantics_are_untrusted": True,
                "return_ignore_for_headers_preamble_and_balance_rows": True,
            },
            "user_policy": user_policy,
            "today": date.today().isoformat(),
        }
        resolution = resolve_runtime(
            self._config,
            task=RuntimeTask.OCR_TEXT_FALLBACK,
            policy_mode=RuntimePolicyMode.LOCAL_PREFERRED,
        )
        if resolution.runtime is not None:
            response = resolution.runtime.complete_json(
                JsonCompletionRequest(
                    task=RuntimeTask.OCR_TEXT_FALLBACK,
                    model_name=resolution.runtime.model_name or getattr(self._config, "ai_model", "gpt-5.2-codex"),
                    system_prompt=STATEMENT_ROW_SEMANTIC_PROMPT,
                    user_json=user_json,
                    temperature=0,
                    max_tokens=1200,
                    metadata={"feature": "ingestion_statement_row_semantic_classification"},
                )
            )
            if isinstance(response.data, dict):
                return response.data, f"{response.provider_kind.value}:{response.model_name}", response.latency_ms
        token = get_ai_oauth_access_token(self._config)
        model = _preferred_codex_oauth_model(self._config)
        if token and model:
            started = time.perf_counter()
            response = complete_text_with_codex_oauth(
                bearer_token=token,
                model=model,
                instructions=STATEMENT_ROW_SEMANTIC_PROMPT,
                input_items=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": json.dumps(user_json, ensure_ascii=False),
                            }
                        ],
                    }
                ],
                timeout_s=max(float(getattr(self._config, "request_timeout_s", 30.0) or 30.0), 120.0),
            )
            data = parse_completion_text(response.text)
            if isinstance(data, dict):
                latency_ms = response.latency_ms or int((time.perf_counter() - started) * 1000)
                return data, f"chatgpt_codex_oauth:{model}", latency_ms
        return None

    def _settings_policy_for_session(self, session_id: str) -> str:
        if not session_id:
            return ""
        with session_scope(self._session_factory) as session:
            row = session.get(IngestionSession, session_id)
            if row is None:
                return ""
            settings = _get_or_create_settings(
                session,
                user_id=row.user_id,
                shared_group_id=row.shared_group_id,
            )
            return _short_text(settings.personal_system_prompt or "", 4000)

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
        matched = self._auto_match_transaction_proposal_before_review(
            proposal=serialized,
            user_id=user_id,
            shared_group_id=shared_group_id,
        )
        if matched is not None:
            return matched
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

    def _auto_match_transaction_proposal_before_review(
        self,
        *,
        proposal: dict[str, Any],
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any] | None:
        if proposal.get("type") != "create_transaction":
            return None
        matches = self.refresh_match_candidates(
            proposal_id=str(proposal["id"]),
            user_id=user_id,
            shared_group_id=shared_group_id,
        )
        top = matches["items"][0] if matches["items"] else None
        if top and float(top["score"]) >= 0.9:
            return self.update_proposal(
                proposal_id=str(proposal["id"]),
                user_id=user_id,
                shared_group_id=shared_group_id,
                payload={
                    "payload": {
                        "type": "already_covered",
                        "statement_row_id": proposal.get("statement_row_id"),
                        "transaction_id": top["transaction_id"],
                        "confidence": top["score"],
                        "reason": "Proposal matches an existing transaction.",
                        "match_score": top["score"],
                    },
                    "explanation": "Already covered by an existing connector transaction.",
                },
            )
        return None

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
            if proposal.status != "pending_review":
                return _serialize_proposal(proposal)
            payload = validate_proposal_payload(proposal.payload_json)
            if isinstance(payload, AlreadyCoveredPayload | IgnorePayload):
                proposal.status = "auto_approved"
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
                        "reason": "safe_no_write_proposal",
                    },
                )
                session.flush()
                auto_commit_id = proposal.id
            else:
                auto_commit_id = None
            if auto_commit_id is not None:
                pass
            elif parent.approval_mode != "yolo_auto":
                return _serialize_proposal(proposal)
            if auto_commit_id is not None:
                pass
            else:
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
            if result.get("reused"):
                raise ValueError("reused commits cannot be undone safely from ingestion")
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
        duplicate = self._find_existing_agent_transaction_duplicate(
            payload=payload,
            user_id=user_id,
            shared_group_id=shared_group_id,
        )
        if duplicate is not None:
            return duplicate
        service = ManualIngestService(session_factory=self._session_factory)
        manual_input = ManualTransactionInput(
            purchased_at=payload.purchased_at,
            merchant_name=payload.merchant_name,
            total_gross_cents=payload.total_gross_cents,
            direction=payload.direction,
            ledger_scope=payload.ledger_scope,
            dashboard_include=payload.dashboard_include,
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

    def _find_existing_agent_transaction_duplicate(
        self,
        *,
        payload: CreateTransactionPayload,
        user_id: str | None,
        shared_group_id: str | None,
    ) -> dict[str, Any] | None:
        source_id = payload.source_id or AGENT_SOURCE_ID
        if source_id != AGENT_SOURCE_ID:
            return None
        lower = payload.purchased_at.date() - timedelta(days=1)
        upper = payload.purchased_at.date() + timedelta(days=1)
        with session_scope(self._session_factory) as session:
            stmt = select(Transaction).where(
                Transaction.source_id == AGENT_SOURCE_ID,
                Transaction.total_gross_cents == int(payload.total_gross_cents),
                Transaction.currency == payload.currency,
                Transaction.direction == payload.direction,
            )
            if shared_group_id:
                stmt = stmt.where(Transaction.shared_group_id == shared_group_id)
            elif user_id:
                stmt = stmt.where(Transaction.user_id == user_id)
            rows = session.execute(stmt.order_by(Transaction.purchased_at.desc()).limit(250)).scalars().all()
            for transaction in rows:
                purchased_date = transaction.purchased_at.date()
                if purchased_date < lower or purchased_date > upper:
                    continue
                if _merchant_similarity(payload.merchant_name, transaction.merchant_name or "") < 0.92:
                    continue
                return {
                    "kind": "transaction",
                    "transaction_id": transaction.id,
                    "transaction": _serialize_transaction_commit_result(transaction),
                    "reused": True,
                    "dedupe": "agent_same_merchant_amount_date",
                }
        return None

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
            duplicate = self._find_existing_cashflow_entry_duplicate(
                session,
                payload=payload,
                user_id=user_id,
            )
            if duplicate is not None:
                record_audit_event(
                    session,
                    action="cashflow.ingestion_agent_reused",
                    source="ingestion_agent",
                    actor_type="user" if actor_id else "system",
                    actor_id=actor_id,
                    entity_type="cashflow_entry",
                    entity_id=duplicate.id,
                    details={"proposal_type": payload.type, "dedupe": "same_cashflow_fields"},
                )
                return {
                    "kind": "cashflow_entry",
                    "cashflow_entry_id": duplicate.id,
                    "entry": _serialize_cashflow_commit_result(duplicate),
                    "reused": True,
                    "dedupe": "same_cashflow_fields",
                }
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

    def _find_existing_cashflow_entry_duplicate(
        self,
        session: Session,
        *,
        payload: CreateCashflowEntryPayload,
        user_id: str,
    ) -> CashflowEntry | None:
        stmt = select(CashflowEntry).where(
            CashflowEntry.user_id == user_id,
            CashflowEntry.effective_date == payload.effective_date,
            CashflowEntry.direction == payload.direction,
            CashflowEntry.category == payload.category,
            CashflowEntry.amount_cents == int(payload.amount_cents),
            CashflowEntry.currency == payload.currency,
            CashflowEntry.source_type == payload.source_type,
        )
        if payload.linked_transaction_id:
            stmt = stmt.where(CashflowEntry.linked_transaction_id == payload.linked_transaction_id)
        else:
            stmt = stmt.where(CashflowEntry.linked_transaction_id.is_(None))
        if payload.linked_recurring_occurrence_id:
            stmt = stmt.where(CashflowEntry.linked_recurring_occurrence_id == payload.linked_recurring_occurrence_id)
        else:
            stmt = stmt.where(CashflowEntry.linked_recurring_occurrence_id.is_(None))
        rows = session.execute(stmt.order_by(CashflowEntry.created_at.desc()).limit(25)).scalars().all()
        expected_description = (payload.description or "").strip()
        expected_notes = (payload.notes or "").strip()
        for entry in rows:
            if (entry.description or "").strip() != expected_description:
                continue
            if (entry.notes or "").strip() != expected_notes:
                continue
            return entry
        return None

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
        "direction": "outflow",
        "ledger_scope": "household",
        "dashboard_include": True,
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
    row_index = row.row_index if isinstance(row, StatementRow) else int(row.get("row_index") or 0)
    payee = row.payee if isinstance(row, StatementRow) else row.get("payee")
    row_description = row.description if isinstance(row, StatementRow) else row.get("description")
    amount_cents_raw = row.amount_cents if isinstance(row, StatementRow) else row.get("amount_cents")
    occurred_at = row.occurred_at if isinstance(row, StatementRow) else (
        datetime.fromisoformat(row["occurred_at"]) if row.get("occurred_at") else None
    )
    currency = row.currency if isinstance(row, StatementRow) else str(row.get("currency") or "EUR")
    row_hash = row.row_hash if isinstance(row, StatementRow) else str(row.get("row_hash"))
    raw_json = row.raw_json if isinstance(row, StatementRow) else row.get("raw_json")
    if isinstance(raw_json, dict) and raw_json.get("parser_mode") == "raw_table_row":
        return _proposal_from_raw_table_row(row_id=row_id, row_index=row_index, row_hash=row_hash, raw_json=raw_json)
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
    direction = "inflow" if int(amount_cents_raw) > 0 else "outflow"
    ledger_scope = _ledger_scope_from_text(description)
    dashboard_include = direction == "outflow" and ledger_scope == "household"
    if direction == "inflow":
        return {
            "type": "needs_review",
            "reason": "Incoming bank movement needs classification as household income, investment, internal transfer, or ignored before it can be committed.",
            "evidence": f"statement_row:{row_id}",
            "confidence": 0.35,
            "summary": f"{merchant} · {format(abs(amount_cents) / 100, '.2f')} {currency or 'EUR'}",
            "row_index": row_index,
            "direction": "inflow",
            "ledger_scope": ledger_scope,
            "amount_cents": amount_cents,
            "currency": currency or "EUR",
            "counterparty": merchant,
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
        }
    return {
        "type": "create_transaction",
        "purchased_at": occurred_at.isoformat(),
        "merchant_name": merchant,
        "total_gross_cents": amount_cents,
        "direction": direction,
        "ledger_scope": ledger_scope,
        "dashboard_include": dashboard_include,
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
            "direction": direction,
            "ledger_scope": ledger_scope,
        },
    }


def _statement_row_fallback_strategy(row: dict[str, Any]) -> str | None:
    raw_json = row.get("raw_json")
    if isinstance(raw_json, dict) and raw_json.get("parser_mode") == "raw_table_row":
        return "generic_header_fallback_after_model"
    return None


def _proposal_from_raw_table_row(*, row_id: str, row_index: int, row_hash: str, raw_json: dict[str, Any]) -> dict[str, Any]:
    cells = [str(value or "").strip() for value in raw_json.get("cells", []) if str(value or "").strip()]
    row_text = str(raw_json.get("row_text") or " | ".join(cells)).strip()
    if _raw_table_row_is_non_transaction(cells):
        return {
            "type": "ignore",
            "statement_row_id": row_id,
            "reason": "Bank-Metadaten, Header, Leerzeile oder Kontostand; keine Haushalts-Transaktion.",
            "confidence": 0.9,
        }

    header = _raw_table_header_cells(raw_json)
    amount_cents, amount_from_header = _amount_from_raw_cells(cells, header=header)
    direction = _direction_from_raw_cells(cells=cells, header=header, amount_cents=amount_cents)
    counterparty, counterparty_from_header = _counterparty_from_raw_cells(cells=cells, header=header, direction=direction)
    occurred_at, date_from_header = _date_from_raw_cells(cells, header=header)
    merchant = _merchant_from_raw_cells(cells=cells, header=header, direction=direction, counterparty=counterparty)
    ledger_scope = _ledger_scope_from_text(row_text)
    clear_header_evidence = amount_from_header and date_from_header and counterparty_from_header
    summary_parts = [
        part for part in [
            occurred_at.date().isoformat() if occurred_at else None,
            merchant or counterparty,
            format(abs(amount_cents) / 100, ".2f") + " EUR" if amount_cents is not None else None,
        ] if part
    ]
    summary = " · ".join(summary_parts) or _short_text(row_text, 160)
    # This is a conservative safety fallback, not a bank-specific parser. It only
    # proposes writes when generic headers clearly identify date, amount, and counterparty.
    if clear_header_evidence and amount_cents is not None and occurred_at is not None and (merchant or counterparty) and direction in {"outflow", "inflow"}:
        amount = abs(amount_cents)
        if direction == "inflow":
            return {
                "type": "create_cashflow_entry",
                "effective_date": occurred_at.date().isoformat(),
                "direction": "inflow",
                "ledger_scope": ledger_scope,
                "dashboard_include": ledger_scope == "household",
                "category": "income" if ledger_scope == "household" else ledger_scope,
                "amount_cents": amount,
                "currency": "EUR",
                "description": (merchant or counterparty or "Bank row")[:180],
                "source_type": "agent_ingest",
                "linked_transaction_id": None,
                "linked_recurring_occurrence_id": None,
                "notes": "Generic header fallback after unavailable or invalid model output.",
                "confidence": 0.54,
            }
        return {
            "type": "create_transaction",
            "purchased_at": occurred_at.isoformat(),
            "merchant_name": (merchant or counterparty or "Bank row")[:120],
            "total_gross_cents": amount,
            "direction": direction,
            "ledger_scope": ledger_scope,
            "dashboard_include": direction == "outflow" and ledger_scope == "household",
            "currency": "EUR",
            "source_id": AGENT_SOURCE_ID,
            "source_display_name": "Agent Ingestion",
            "source_account_ref": "bank_statement",
            "source_transaction_id": None,
            "idempotency_key": f"ingest-row:{row_hash}",
            "confidence": 0.58,
            "items": [],
            "discounts": [],
            "raw_payload": {
                "input_kind": "statement_row",
                "semantic_source": "generic_header_fallback",
                "statement_row_id": row_id,
                "row_hash": row_hash,
                "evidence": row_text,
                "raw_cells": cells[:24],
                "direction": direction,
                "ledger_scope": ledger_scope,
                "counterparty": counterparty,
            },
        }
    if direction == "inflow":
        reason = "Eingang aus der Bankzeile braucht Entscheidung: Haushalts-Einnahme, Investment, interne Umbuchung oder ignorieren."
        confidence = 0.45
    elif direction == "outflow":
        reason = "Ausgang aus der Bankzeile braucht Agent-/User-Prüfung, bevor daraus eine Transaktion wird."
        confidence = 0.4
    else:
        reason = "Bankzeile konnte nicht sicher als Zahlung interpretiert werden und braucht Prüfung."
        confidence = 0.25
    return {
        "type": "needs_review",
        "reason": reason,
        "evidence": f"statement_row:{row_id}",
        "confidence": confidence,
        "summary": summary,
        "raw_cells": cells[:24],
        "row_index": row_index,
        "direction": direction,
        "ledger_scope": ledger_scope,
        "amount_cents": abs(amount_cents) if amount_cents is not None else None,
        "currency": "EUR",
        "counterparty": counterparty or merchant,
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
    }


def _raw_table_header_cells(raw_json: dict[str, Any]) -> list[str] | None:
    context = raw_json.get("file_context")
    preview_rows = context.get("preview_rows") if isinstance(context, dict) else None
    if not isinstance(preview_rows, list):
        return None
    best: list[str] | None = None
    best_score = 0
    current_line = int(raw_json.get("line_number") or 0)
    for row in preview_rows:
        if not isinstance(row, dict):
            continue
        line_number = int(row.get("line_number") or 0)
        if current_line and line_number >= current_line:
            continue
        cells = [str(value or "").strip() for value in row.get("cells", [])]
        score = _statement_header_score([cell.casefold() for cell in cells])
        if score > best_score:
            best = cells
            best_score = score
    return best if best_score >= 2 else None


def _raw_header_index(header: list[str] | None, candidates: list[str]) -> int | None:
    if not header:
        return None
    normalized = [_normalize_header_label(cell) for cell in header]
    normalized_candidates = [_normalize_header_label(candidate) for candidate in candidates]
    for index, cell in enumerate(normalized):
        if any(candidate in cell for candidate in normalized_candidates):
            return index
    return None


def _normalize_header_label(value: str) -> str:
    normalized = value.casefold()
    normalized = (
        normalized
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _raw_has_header(header: list[str] | None) -> bool:
    return bool(header)


def _raw_table_row_is_non_transaction(cells: list[str]) -> bool:
    if not cells:
        return True
    normalized_cells = [cell.casefold().strip(" :") for cell in cells]
    joined = " | ".join(normalized_cells)
    header_score = _statement_header_score(normalized_cells)
    if header_score >= 2:
        return True
    if len(cells) <= 3 and any(token in joined for token in ("girokonto", "kontostand", "saldo", "balance", "zeitraum", "iban", "bic")):
        return True
    if re.fullmatch(r"[a-z]{2}\d{2}[a-z0-9]{8,30}", "".join(normalized_cells).replace(" ", "")):
        return True
    return False


def _amount_from_raw_cells(cells: list[str], *, header: list[str] | None = None) -> tuple[int | None, bool]:
    amount_index = _raw_header_index(header, ["betrag", "amount", "umsatzbetrag", "transactionamount"])
    if amount_index is not None and amount_index < len(cells):
        parsed = _parse_amount_cents(cells[amount_index])
        if parsed is not None:
            return parsed, True
    if not _raw_has_header(header):
        return None, False
    for cell in reversed(cells):
        if re.search(r"[a-zA-Z]{2}\d{8,}|[A-Z]{2}\d{2}[A-Z0-9]{8,}|[A-Z0-9]{10,}", cell) or re.fullmatch(r"\d{8,}", cell.strip()):
            continue
        parsed = _parse_amount_cents(cell)
        if parsed is not None:
            return parsed, False
    return None, False


def _date_from_raw_cells(cells: list[str], *, header: list[str] | None = None) -> tuple[datetime | None, bool]:
    date_index = _raw_header_index(header, ["buchungsdatum", "buchungstag", "date", "datum", "wertstellung", "valuta"])
    if date_index is not None and date_index < len(cells):
        parsed = _parse_statement_date(cells[date_index])
        if parsed is not None:
            return parsed, True
    if not _raw_has_header(header):
        return None, False
    for cell in cells[:6]:
        parsed = _parse_statement_date(cell)
        if parsed is not None:
            return parsed, False
    return None, False


def _direction_from_raw_cells(*, cells: list[str], header: list[str] | None, amount_cents: int | None) -> str | None:
    type_index = _raw_header_index(header, ["umsatztyp", "type", "richtung", "direction"])
    if type_index is not None and type_index < len(cells):
        value = cells[type_index].casefold()
        if any(token in value for token in ("ausgang", "soll", "debit", "belastung")):
            return "outflow"
        if any(token in value for token in ("eingang", "haben", "credit", "gutschrift")):
            return "inflow"
    if amount_cents is not None:
        return "inflow" if amount_cents > 0 else "outflow"
    return None


def _counterparty_from_raw_cells(*, cells: list[str], header: list[str] | None = None, direction: str | None) -> tuple[str | None, bool]:
    payer_index = _raw_header_index(header, ["zahlungspflichtige", "payer", "sender", "auftraggeber", "absender"])
    recipient_index = _raw_header_index(header, ["zahlungsempfänger", "zahlungsempfaenger", "empfänger", "empfaenger", "recipient", "payee"])
    payer = cells[payer_index].strip() if payer_index is not None and payer_index < len(cells) else ""
    recipient = cells[recipient_index].strip() if recipient_index is not None and recipient_index < len(cells) else ""
    if payer or recipient:
        if direction == "inflow":
            return payer or recipient or None, True
        if direction == "outflow":
            return recipient or payer or None, True
    if not _raw_has_header(header):
        return None, False
    if len(cells) >= 8:
        payer = cells[3].strip() if len(cells) > 3 else ""
        recipient = cells[4].strip() if len(cells) > 4 else ""
        if direction == "inflow":
            return payer or recipient or None, False
        if direction == "outflow":
            return recipient or payer or None, False
    for cell in cells:
        cleaned = cell.strip()
        if not cleaned or _parse_statement_date(cleaned) is not None or _parse_amount_cents(cleaned) is not None:
            continue
        if cleaned.casefold() in {"gebucht", "eingang", "ausgang", "kartenzahlung", "lastschrift"}:
            continue
        return cleaned[:120], False
    return None, False


def _merchant_from_raw_cells(*, cells: list[str], header: list[str] | None, direction: str | None, counterparty: str | None) -> str | None:
    purpose_index = _raw_header_index(header, ["verwendungszweck", "purpose", "description", "beschreibung"])
    purpose = cells[purpose_index].strip() if purpose_index is not None and purpose_index < len(cells) else ""
    if purpose:
        for canonical in ("Lidl", "Penny", "REWE", "Rossmann", "DM", "Zwift"):
            if re.search(rf"\b{re.escape(canonical)}\b", purpose, re.I):
                return canonical
        match = re.search(r"\b(Lidl|Penny|Rewe|Rossmann|DM|Klinikum Braunschweig|Marktkauf|Getsafe|Zwift)\b[^\d,;]*", purpose, re.I)
        if match:
            return _clean_counterparty(match.group(0))
        paypal_purchase = re.search(r"(?:Ihr Einkauf bei|sagt Danke)\s+(.+)$", purpose, re.I)
        if paypal_purchase:
            return _clean_counterparty(paypal_purchase.group(1))
    if direction == "outflow":
        return _clean_counterparty(counterparty or "")
    return _clean_counterparty(counterparty or "")


def _clean_counterparty(value: str) -> str | None:
    cleaned = re.sub(r"\s+", " ", value).strip(" ,.;")
    return cleaned[:120] or None


def _proposal_from_document_text(file_row: IngestionFile, text: str) -> dict[str, Any]:
    normalized = normalize_receipt_text(text)
    if not normalized:
        return _proposal_from_document_placeholder(file_row)

    recurring = _recurring_candidate_from_text(normalized, today=date.today())
    if recurring is not None:
        recurring["evidence"] = f"ingestion_file:{file_row.id}"
        return recurring

    has_date = _document_text_has_date(normalized)
    has_amount = _document_text_has_amount(normalized)
    if not has_date or not has_amount:
        return {
            "type": "needs_review",
            "reason": "Document text was extracted, but required date or amount facts are missing.",
            "evidence": f"ingestion_file:{file_row.id}",
            "confidence": 0.35,
        }

    parsed = parse_receipt_text(normalized, fallback_store="Document Upload")
    if parsed.total_gross_cents <= 0 or not parsed.store_name or parsed.store_name == "Document Upload":
        return {
            "type": "needs_review",
            "reason": "Document text was extracted, but merchant or total is ambiguous.",
            "evidence": f"ingestion_file:{file_row.id}",
            "confidence": 0.45,
        }

    text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return {
        "type": "create_transaction",
        "purchased_at": parsed.purchased_at.isoformat(),
        "merchant_name": parsed.store_name[:120],
        "total_gross_cents": parsed.total_gross_cents,
        "direction": "outflow",
        "ledger_scope": "household",
        "dashboard_include": True,
        "currency": parsed.currency or "EUR",
        "source_id": AGENT_SOURCE_ID,
        "source_display_name": "Agent Ingestion",
        "source_account_ref": "document_upload",
        "source_transaction_id": None,
        "idempotency_key": f"ingest-doc:{file_row.sha256}:{text_hash[:16]}",
        "confidence": 0.78,
        "items": parsed.items,
        "discounts": [],
        "raw_payload": {
            "input_kind": "document",
            "ingestion_file_id": file_row.id,
            "file_sha256": file_row.sha256,
            "text_sha256": text_hash,
            "evidence": f"ingestion_file:{file_row.id}",
        },
    }


def _validated_semantic_document_proposals(
    *,
    data: dict[str, Any],
    file_row: IngestionFile,
    text: str,
    extraction: dict[str, Any],
    semantic_provider: str,
    semantic_latency_ms: int,
) -> list[dict[str, Any]]:
    raw_items = data.get("proposals")
    if not isinstance(raw_items, list) or not raw_items:
        return []
    document_kind = str(data.get("document_kind") or "unknown")[:40]
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    proposals: list[dict[str, Any]] = []
    for index, raw_item in enumerate(raw_items[:12], start=1):
        if not isinstance(raw_item, dict):
            continue
        raw_payload = raw_item.get("payload")
        if not isinstance(raw_payload, dict):
            continue
        payload = _prepare_model_document_payload(
            raw_payload,
            file_row=file_row,
            text_hash=text_hash,
            index=index,
        )
        try:
            validate_proposal_payload(payload)
        except Exception:
            continue
        proposals.append(
            {
                "payload": payload,
                "explanation": _short_text(str(raw_item.get("explanation") or _proposal_explanation(payload)), 240),
                "strategy": "semantic_document_model",
                "document_kind": document_kind,
                "extraction_provider": extraction.get("provider"),
                "semantic_provider": semantic_provider,
                "semantic_latency_ms": semantic_latency_ms,
                "diagnostics": _document_diagnostics(extraction, semantic_status="completed"),
            }
        )
    if proposals:
        return proposals
    return [
        {
            "payload": {
                "type": "needs_review",
                "reason": "Document model response did not contain any schema-valid proposal.",
                "evidence": f"ingestion_file:{file_row.id}",
                "confidence": 0.2,
            },
            "explanation": "Document extraction needs review because the model output could not be validated.",
            "strategy": "semantic_document_model_invalid",
            "document_kind": document_kind,
            "extraction_provider": extraction.get("provider"),
            "semantic_provider": semantic_provider,
            "semantic_latency_ms": semantic_latency_ms,
            "diagnostics": _document_diagnostics(extraction, semantic_status="invalid_schema"),
        }
    ]


def _prepare_model_document_payload(
    payload: dict[str, Any],
    *,
    file_row: IngestionFile,
    text_hash: str,
    index: int,
) -> dict[str, Any]:
    prepared = dict(payload)
    proposal_type = str(prepared.get("type") or "")
    confidence = _clamped_confidence(prepared.get("confidence"), default=0.65)
    prepared["confidence"] = min(confidence, 0.89)
    if proposal_type == "create_transaction":
        direction = str(prepared.get("direction") or "outflow").strip().lower()
        ledger_scope = str(prepared.get("ledger_scope") or "household").strip().lower()
        prepared["direction"] = direction if direction in {"outflow", "inflow"} else "outflow"
        prepared["ledger_scope"] = ledger_scope if ledger_scope in {"household", "investment", "internal", "unknown"} else "unknown"
        prepared["dashboard_include"] = bool(prepared.get("dashboard_include", prepared["direction"] == "outflow" and prepared["ledger_scope"] == "household"))
        prepared["source_id"] = AGENT_SOURCE_ID
        prepared["source_display_name"] = "Agent Ingestion"
        prepared["source_account_ref"] = "document_upload"
        prepared["source_transaction_id"] = None
        prepared["idempotency_key"] = f"ingest-doc:{file_row.sha256}:{text_hash[:16]}:{index}"
        prepared["items"] = prepared.get("items") if isinstance(prepared.get("items"), list) else []
        prepared["discounts"] = prepared.get("discounts") if isinstance(prepared.get("discounts"), list) else []
        raw_payload = prepared.get("raw_payload") if isinstance(prepared.get("raw_payload"), dict) else {}
        prepared["raw_payload"] = {
            **raw_payload,
            "input_kind": "document",
            "ingestion_file_id": file_row.id,
            "file_sha256": file_row.sha256,
            "text_sha256": text_hash,
            "evidence": f"ingestion_file:{file_row.id}",
        }
    elif proposal_type == "create_cashflow_entry":
        prepared.setdefault("source_type", "agent_ingest")
        prepared.setdefault("ledger_scope", "household")
        prepared.setdefault("dashboard_include", prepared.get("ledger_scope") == "household")
        prepared["confidence"] = min(confidence, 0.86)
    elif proposal_type == "create_recurring_bill_candidate":
        prepared["evidence"] = f"ingestion_file:{file_row.id}"
        prepared["confidence"] = min(confidence, 0.86)
    elif proposal_type == "needs_review":
        prepared["evidence"] = f"ingestion_file:{file_row.id}"
        prepared["confidence"] = min(confidence, 0.6)
    elif proposal_type == "ignore":
        prepared["confidence"] = min(confidence, 0.86)
    return prepared


def _prepare_model_statement_row_payload(payload: dict[str, Any], *, row: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(payload)
    proposal_type = str(prepared.get("type") or "")
    confidence = _clamped_confidence(prepared.get("confidence"), default=0.72)
    prepared["confidence"] = min(confidence, 0.93)
    row_hash = str(row.get("row_hash") or row.get("id") or hashlib.sha256(json.dumps(row, sort_keys=True, default=str).encode("utf-8")).hexdigest())
    if proposal_type == "create_transaction":
        direction = str(prepared.get("direction") or _direction_from_statement_row(row)).strip().lower()
        ledger_scope = str(prepared.get("ledger_scope") or _ledger_scope_from_statement_row(row)).strip().lower()
        prepared["direction"] = direction if direction in {"outflow", "inflow"} else "outflow"
        prepared["ledger_scope"] = ledger_scope if ledger_scope in {"household", "investment", "internal", "unknown"} else "unknown"
        prepared["dashboard_include"] = bool(prepared.get("dashboard_include", prepared["direction"] == "outflow" and prepared["ledger_scope"] == "household"))
        prepared["source_id"] = AGENT_SOURCE_ID
        prepared["source_display_name"] = "Agent Ingestion"
        prepared["source_account_ref"] = "bank_statement"
        prepared["source_transaction_id"] = None
        prepared["idempotency_key"] = f"ingest-row:{row_hash}"
        prepared["items"] = prepared.get("items") if isinstance(prepared.get("items"), list) else []
        prepared["discounts"] = prepared.get("discounts") if isinstance(prepared.get("discounts"), list) else []
        raw_payload = prepared.get("raw_payload") if isinstance(prepared.get("raw_payload"), dict) else {}
        prepared["raw_payload"] = {
            **raw_payload,
            "input_kind": "statement_row",
            "statement_row_id": row.get("id"),
            "row_hash": row_hash,
            "evidence": f"statement_row:{row.get('id')}",
        }
    elif proposal_type in {"ignore", "already_covered", "link_existing_transaction"}:
        prepared.setdefault("statement_row_id", row.get("id"))
    elif proposal_type == "create_cashflow_entry":
        prepared.setdefault("ledger_scope", _ledger_scope_from_statement_row(row))
        prepared.setdefault("dashboard_include", prepared.get("ledger_scope") == "household")
        prepared["confidence"] = min(confidence, 0.86)
    elif proposal_type == "create_recurring_bill_candidate":
        prepared["evidence"] = f"statement_row:{row.get('id')}"
        prepared["confidence"] = min(confidence, 0.86)
    elif proposal_type == "needs_review":
        prepared["evidence"] = f"statement_row:{row.get('id')}"
        prepared["confidence"] = min(confidence, 0.6)
    return prepared


def _direction_from_statement_row(row: dict[str, Any]) -> str:
    amount = row.get("amount_cents")
    if isinstance(amount, (int, float)) and amount > 0:
        return "inflow"
    raw_json = row.get("raw_json")
    text = json.dumps(raw_json, ensure_ascii=False).casefold() if isinstance(raw_json, dict) else ""
    if re.search(r"\b(haben|gutschrift|credit|eingang|income|salary|gehalt)\b", text):
        return "inflow"
    return "outflow"


def _ledger_scope_from_statement_row(row: dict[str, Any]) -> str:
    raw_json = row.get("raw_json")
    text = " ".join(
        str(part)
        for part in [
            row.get("payee"),
            row.get("description"),
            json.dumps(raw_json, ensure_ascii=False) if isinstance(raw_json, dict) else "",
        ]
        if part
    )
    return _ledger_scope_from_text(text)


def _ledger_scope_from_text(text: str) -> str:
    normalized = text.casefold()
    if re.search(r"\b(depot|broker|trade republic|scalable|dividende|dividend|wertpapier|aktie|etf|zins|securities|stock)\b", normalized):
        return "investment"
    if re.search(r"\b(umbuchung|eigenuebertrag|eigenübertrag|internal|transfer|übertrag|uebertrag)\b", normalized):
        return "internal"
    if re.search(r"\b(mieteinnahme|rental income|vermietung|airbnb|business|invoice paid|rechnung bezahlt)\b", normalized):
        return "investment"
    return "household"


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
    proposal_ordinal = payload.purchased_at.date().toordinal()
    near_lower_bound = proposal_ordinal - 3
    near_upper_bound = proposal_ordinal + 3
    settlement_lower_bound = proposal_ordinal - 10
    settlement_upper_bound = proposal_ordinal + 10
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
        amount_exact = int(transaction.total_gross_cents) == int(payload.total_gross_cents)
        if amount_exact:
            score += 0.5
            reason["amount"] = "exact"
        else:
            delta = abs(int(transaction.total_gross_cents) - int(payload.total_gross_cents))
            if delta <= 100:
                score += 0.18
                reason["amount"] = "near"
            else:
                reason["amount"] = "different"
        tx_ordinal = transaction.purchased_at.date().toordinal()
        if tx_ordinal == proposal_ordinal:
            score += 0.35
            reason["date"] = "same_day"
        elif near_lower_bound <= tx_ordinal <= near_upper_bound:
            score += 0.25
            reason["date"] = "within_3_days"
        elif settlement_lower_bound <= tx_ordinal <= settlement_upper_bound:
            score += 0.18
            reason["date"] = "within_10_day_settlement_window"
        else:
            reason["date"] = "outside_window"
        evidence_text = " ".join(
            str(part)
            for part in [
                payload.merchant_name,
                payload.raw_payload.get("evidence") if isinstance(payload.raw_payload, dict) else None,
                json.dumps(payload.raw_payload, ensure_ascii=False) if isinstance(payload.raw_payload, dict) else None,
            ]
            if part
        )
        merchant_score = max(
            _merchant_similarity(payload.merchant_name, transaction.merchant_name or ""),
            _merchant_similarity(evidence_text, transaction.merchant_name or ""),
        )
        score += merchant_score * 0.2
        reason["merchant_similarity"] = round(merchant_score, 3)
        if amount_exact and near_lower_bound <= tx_ordinal <= near_upper_bound and merchant_score >= 0.6:
            score = max(score, 0.93)
            reason["deterministic_match"] = "exact_amount_near_date_merchant_in_evidence"
        if amount_exact and settlement_lower_bound <= tx_ordinal <= settlement_upper_bound and merchant_score >= 0.72:
            score = max(score, 0.93)
            reason["deterministic_match"] = "exact_amount_settlement_window_merchant_in_evidence"
        if (
            amount_exact
            and settlement_lower_bound <= tx_ordinal <= settlement_upper_bound
            and _is_lidl_like_match(
                proposal_text=evidence_text,
                transaction_merchant=transaction.merchant_name or "",
                transaction_source=transaction.source_id or "",
            )
        ):
            score = max(score, 0.93)
            reason["deterministic_match"] = "exact_amount_near_date_lidl_connector"
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


def _is_lidl_like_match(*, proposal_text: str, transaction_merchant: str, transaction_source: str) -> bool:
    proposal_norm = proposal_text.casefold()
    merchant_norm = transaction_merchant.casefold()
    source_norm = transaction_source.casefold()
    return "lidl" in proposal_norm and ("lidl" in merchant_norm or "lidl" in source_norm)


def _decode_text_file(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _parse_statement_text(text: str) -> list[dict[str, Any]]:
    return _stage_raw_table_rows(text)


def _stage_raw_table_rows(text: str) -> list[dict[str, Any]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    table_rows = list(csv.reader(io.StringIO(text), dialect=dialect))
    non_empty_rows: list[tuple[int, list[str]]] = []
    for line_number, values in enumerate(table_rows, start=1):
        cells = [str(value or "").strip().lstrip("\ufeff") for value in values]
        if any(cells):
            non_empty_rows.append((line_number, cells))
    if not non_empty_rows:
        raise ValueError("statement table did not contain any rows")
    delimiter = getattr(dialect, "delimiter", ",") or ","
    preview_rows = [
        {"line_number": line_number, "cells": cells}
        for line_number, cells in non_empty_rows[:30]
    ]
    rows: list[dict[str, Any]] = []
    for index, (line_number, cells) in enumerate(non_empty_rows, start=1):
        raw = {
            "parser_mode": "raw_table_row",
            "line_number": line_number,
            "cells": cells,
            "row_text": delimiter.join(cells),
            "detected_delimiter": delimiter,
            "file_context": {
                "total_non_empty_rows": len(non_empty_rows),
                "preview_rows": preview_rows,
            },
        }
        row_hash = hashlib.sha256(
            json.dumps(
                {
                    "line_number": line_number,
                    "cells": cells,
                    "total_non_empty_rows": len(non_empty_rows),
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "row_index": index,
                "row_hash": row_hash,
                "occurred_at": None,
                "booked_at": None,
                "payee": None,
                "description": None,
                "amount_cents": None,
                "currency": "EUR",
                "raw_json": raw,
            }
        )
    return rows


def _attach_user_context_to_rows(rows: list[dict[str, Any]], *, context: str) -> list[dict[str, Any]]:
    context_text = _short_text(context.strip(), 4000)
    if not context_text:
        return rows
    attached: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        raw_json = next_row.get("raw_json") if isinstance(next_row.get("raw_json"), dict) else {}
        next_row["raw_json"] = {**raw_json, "user_context": context_text}
        attached.append(next_row)
    return attached


def _statement_header_index(rows: list[list[str]]) -> int | None:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows):
        normalized = [str(value or "").strip().lstrip("\ufeff").casefold() for value in row]
        if not any(normalized):
            continue
        score = _statement_header_score(normalized)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index if best_score >= 2 else None


def _statement_header_score(headers: list[str]) -> int:
    joined = " | ".join(headers)
    score = 0
    if any(candidate in joined for candidate in ("date", "datum", "buchung", "wertstellung", "valuta")):
        score += 1
    if any(candidate in joined for candidate in ("amount", "betrag", "umsatz", "debit", "credit")):
        score += 1
    if any(candidate in joined for candidate in ("payee", "merchant", "empfänger", "empfaenger", "zahlungsempfänger")):
        score += 1
    if any(candidate in joined for candidate in ("description", "purpose", "verwendungszweck", "beschreibung")):
        score += 1
    return score


def _statement_record_from_values(fieldnames: list[str], values: list[str]) -> dict[str, str]:
    record: dict[str, str] = {}
    for index, fieldname in enumerate(fieldnames):
        normalized_name = fieldname.strip()
        if not normalized_name:
            continue
        value = values[index] if index < len(values) else ""
        record[normalized_name] = str(value or "").strip()
    if len(values) > len(fieldnames):
        extras = [str(value or "").strip() for value in values[len(fieldnames) :] if str(value or "").strip()]
        if extras:
            record["_extra"] = " ".join(extras)
    return record


def _map_statement_row(raw: dict[str, str], *, index: int) -> dict[str, Any]:
    fields = {key.casefold(): key for key in raw}
    occurred_raw = _field(raw, fields, ["date", "transaction date", "buchungstag", "wertstellung", "valuta", "booking date"])
    booked_raw = _field(raw, fields, ["booked", "booking date", "buchung", "buchungsdatum"])
    recipient = _field(
        raw,
        fields,
        [
            "payee",
            "merchant",
            "empfänger",
            "empfaenger",
            "zahlungsempfänger",
            "zahlungsempfaenger",
            "beguenstigter",
            "begünstigter",
        ],
    )
    payer = _field(
        raw,
        fields,
        [
            "payer",
            "sender",
            "auftraggeber",
            "absender",
            "zahlungspflichtige",
            "zahlungspflichtiger",
            "name",
        ],
    )
    description = _field(raw, fields, ["description", "memo", "purpose", "verwendungszweck", "beschreibung", "text"])
    amount_raw = _field(raw, fields, ["amount", "betrag", "betrag (€)", "betrag eur", "value", "umsatz"])
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
    payee = _statement_counterparty_for_direction(
        amount_cents=amount_cents,
        recipient=recipient,
        payer=payer,
    )
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


def _statement_counterparty_for_direction(
    *,
    amount_cents: int | None,
    recipient: str | None,
    payer: str | None,
) -> str | None:
    if amount_cents is not None and amount_cents < 0:
        return recipient or payer
    if amount_cents is not None and amount_cents > 0:
        return payer or recipient
    return recipient or payer


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
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%m/%d/%y"):
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
        personal_system_prompt=str(DEFAULT_INGESTION_SETTINGS["personal_system_prompt"]),
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
        "personal_system_prompt": row.personal_system_prompt or "",
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
        return {"allowed": True, "reason": "yolo_complete_transaction", "deterministic_score": top_score}
    if isinstance(payload, CreateCashflowEntryPayload):
        if payload.amount_cents <= 0 or not payload.effective_date or not payload.category:
            return {"allowed": False, "reason": "missing_required_cashflow_fields"}
        return {"allowed": True, "reason": "yolo_complete_cashflow_entry", "deterministic_score": confidence}
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


def _document_text_has_date(text: str) -> bool:
    return bool(re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", text))


def _document_text_has_amount(text: str) -> bool:
    return bool(re.search(r"\b\d+[.,]\d{2}\b", text))


def _document_diagnostics(extraction: dict[str, Any], *, semantic_status: str) -> dict[str, Any]:
    return {
        "ocr_status": extraction.get("status"),
        "ocr_provider": extraction.get("provider"),
        "ocr_fallback_used": extraction.get("fallback_used"),
        "ocr_latency_ms": extraction.get("latency_ms"),
        "ocr_confidence": extraction.get("confidence"),
        "semantic_status": semantic_status,
    }


def _clamped_confidence(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, 0.0), 1.0)


def _short_text(value: str, max_chars: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars].rstrip()}..."


def _privacy_preserving_text_preview(text: str, *, max_chars: int = 280) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars].rstrip()}..."


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
        "raw_json": row.raw_json,
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


def _serialize_transaction_commit_result(transaction: Transaction) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "purchased_at": transaction.purchased_at.isoformat(),
        "merchant_name": transaction.merchant_name,
        "total_gross_cents": transaction.total_gross_cents,
        "direction": transaction.direction,
        "ledger_scope": transaction.ledger_scope,
        "dashboard_include": transaction.dashboard_include,
        "currency": transaction.currency,
        "source_id": transaction.source_id,
        "source_transaction_id": transaction.source_transaction_id,
    }


def _serialize_cashflow_commit_result(entry: CashflowEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "shared_group_id": entry.shared_group_id,
        "workspace_kind": "shared_group" if entry.shared_group_id else "personal",
        "effective_date": entry.effective_date.isoformat(),
        "direction": entry.direction,
        "category": entry.category,
        "amount_cents": entry.amount_cents,
        "currency": entry.currency,
        "description": entry.description,
        "source_type": entry.source_type,
        "linked_transaction_id": entry.linked_transaction_id,
        "linked_recurring_occurrence_id": entry.linked_recurring_occurrence_id,
        "notes": entry.notes,
        "created_at": entry.created_at.isoformat(),
        "updated_at": entry.updated_at.isoformat(),
    }


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)
