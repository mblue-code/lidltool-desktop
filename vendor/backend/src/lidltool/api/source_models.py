from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypedDict

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_orchestration import (
    ConnectorAuthOrchestrationService,
    ConnectorBootstrapSession,
    serialize_connector_bootstrap,
)
from lidltool.connectors.registry import source_manifest_payload
from lidltool.db.models import IngestionJob, Source, SourceAccount, SyncState

from .http_state import get_connector_command_sessions


class ConnectorBootstrapPayload(TypedDict):
    source_id: str
    status: str
    command: str
    pid: int | None
    started_at: str | None
    finished_at: str | None
    return_code: int | None
    output_tail: list[str]
    can_cancel: bool


class SourceAuthBootstrapPayload(TypedDict):
    source_id: str
    status: str
    started_at: str | None
    finished_at: str | None
    return_code: int | None
    can_cancel: bool


class SourceAuthStatusPayload(TypedDict):
    source_id: str
    state: str
    detail: str | None
    reauth_required: bool
    needs_connection: bool
    available_actions: list[str]
    implemented_actions: list[str]
    metadata: dict[str, Any]
    diagnostics: dict[str, Any]
    bootstrap: SourceAuthBootstrapPayload | None


class SourceSyncLatestJobPayload(TypedDict):
    job_id: str
    status: str
    trigger_type: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    summary: dict[str, object] | None


class SourceSyncStatusPayload(TypedDict):
    source_id: str
    status: str
    in_progress: bool
    current_run: ConnectorBootstrapPayload | None
    latest_job: SourceSyncLatestJobPayload | None
    last_success_at: str | None
    last_seen_receipt_at: str | None
    last_seen_receipt_id: str | None


class SourceAccountPayload(TypedDict):
    id: str | None
    account_ref: str | None
    status: str | None
    last_success_at: str | None


class SourceActionsPayload(TypedDict):
    can_sync: bool
    can_reauth: bool


class SourceStatusPayload(TypedDict):
    source_id: str
    display_name: str
    kind: str
    enabled: bool
    status: str
    created_at: str
    updated_at: str
    plugin: Mapping[str, object] | None
    account: SourceAccountPayload
    auth: SourceAuthStatusPayload
    sync: SourceSyncStatusPayload
    actions: SourceActionsPayload
    needs_attention: bool


def serialize_connector_bootstrap_payload(
    session: ConnectorBootstrapSession,
) -> ConnectorBootstrapPayload:
    snapshot = serialize_connector_bootstrap(session)
    return {
        "source_id": snapshot.source_id,
        "status": snapshot.state,
        "command": " ".join(snapshot.command or ()),
        "pid": snapshot.pid,
        "started_at": snapshot.started_at.isoformat() if snapshot.started_at is not None else None,
        "finished_at": (
            snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None
        ),
        "return_code": snapshot.return_code,
        "output_tail": list(snapshot.output_tail),
        "can_cancel": snapshot.can_cancel,
    }


def serialize_source_auth_status(
    *,
    auth_service: ConnectorAuthOrchestrationService,
    source_id: str,
    include_diagnostics: bool = True,
    validate_session: bool = True,
) -> SourceAuthStatusPayload:
    snapshot = auth_service.get_auth_status(
        source_id=source_id,
        validate_session=validate_session,
    )
    return {
        "source_id": source_id,
        "state": snapshot.state,
        "detail": snapshot.detail,
        "reauth_required": snapshot.state == "reauth_required",
        "needs_connection": snapshot.state == "not_connected",
        "available_actions": list(snapshot.available_actions),
        "implemented_actions": list(snapshot.implemented_actions),
        "metadata": dict(snapshot.metadata),
        "diagnostics": dict(snapshot.diagnostics) if include_diagnostics else {},
        "bootstrap": (
            {
                "source_id": snapshot.bootstrap.source_id,
                "status": snapshot.bootstrap.state,
                "started_at": (
                    snapshot.bootstrap.started_at.isoformat()
                    if snapshot.bootstrap.started_at is not None
                    else None
                ),
                "finished_at": (
                    snapshot.bootstrap.finished_at.isoformat()
                    if snapshot.bootstrap.finished_at is not None
                    else None
                ),
                "return_code": snapshot.bootstrap.return_code,
                "can_cancel": snapshot.bootstrap.can_cancel,
            }
            if snapshot.bootstrap is not None
            else None
        ),
    }


def serialize_source_sync_status(
    app: FastAPI,
    session: Session,
    *,
    source_id: str,
) -> SourceSyncStatusPayload:
    runtime = get_connector_command_sessions(app, kind="sync").get(source_id)
    latest_job = _latest_source_job(session, source_id=source_id)
    sync_state = session.get(SyncState, source_id)
    if runtime is not None:
        runtime_payload = serialize_connector_bootstrap_payload(runtime)
        status = runtime_payload["status"]
    elif latest_job is not None:
        latest_job_status = latest_job.status.lower()
        if latest_job_status in {"success", "partial_success"}:
            status = "succeeded"
        elif latest_job_status in {"failed", "canceled"}:
            status = latest_job_status
        else:
            status = latest_job_status
        runtime_payload = None
    else:
        status = "idle"
        runtime_payload = None
    return {
        "source_id": source_id,
        "status": status,
        "in_progress": status == "running",
        "current_run": runtime_payload,
        "latest_job": (
            {
                "job_id": latest_job.id,
                "status": latest_job.status,
                "trigger_type": latest_job.trigger_type,
                "started_at": (
                    latest_job.started_at.isoformat() if latest_job.started_at is not None else None
                ),
                "finished_at": (
                    latest_job.finished_at.isoformat() if latest_job.finished_at is not None else None
                ),
                "error": latest_job.error,
                "summary": latest_job.summary,
            }
            if latest_job is not None
            else None
        ),
        "last_success_at": (
            sync_state.last_success_at.isoformat()
            if sync_state is not None and sync_state.last_success_at is not None
            else None
        ),
        "last_seen_receipt_at": (
            sync_state.last_seen_receipt_at.isoformat()
            if sync_state is not None and sync_state.last_seen_receipt_at is not None
            else None
        ),
        "last_seen_receipt_id": (
            sync_state.last_seen_receipt_id if sync_state is not None else None
        ),
    }


def build_source_status_payload(
    app: FastAPI,
    session: Session,
    *,
    auth_service: ConnectorAuthOrchestrationService,
    config: AppConfig,
    source: Source,
    include_sensitive_plugin_details: bool = True,
    include_auth_diagnostics: bool = True,
) -> SourceStatusPayload:
    auth_payload = serialize_source_auth_status(
        auth_service=auth_service,
        source_id=source.id,
        include_diagnostics=include_auth_diagnostics,
    )
    sync_payload = serialize_source_sync_status(app, session, source_id=source.id)
    account = _first_source_account(session, source_id=source.id)
    health = _source_health_state(
        source=source,
        auth_payload=auth_payload,
        sync_payload=sync_payload,
    )
    return {
        "source_id": source.id,
        "display_name": source.display_name,
        "kind": source.kind,
        "enabled": source.enabled,
        "status": health,
        "created_at": source.created_at.isoformat(),
        "updated_at": source.updated_at.isoformat(),
        "plugin": source_manifest_payload(
            source.id,
            config=config,
            include_sensitive_details=include_sensitive_plugin_details,
        ),
        "account": {
            "id": account.id if account is not None else None,
            "account_ref": account.account_ref if account is not None else None,
            "status": account.status if account is not None else None,
            "last_success_at": (
                account.last_success_at.isoformat()
                if account is not None and account.last_success_at is not None
                else None
            ),
        },
        "auth": auth_payload,
        "sync": sync_payload,
        "actions": {
            "can_sync": health != "disabled" and not auth_payload["needs_connection"],
            "can_reauth": auth_payload["reauth_required"]
            or "start_auth" in auth_payload["available_actions"],
        },
        "needs_attention": health == "attention",
    }


def _first_source_account(session: Session, *, source_id: str) -> SourceAccount | None:
    return (
        session.execute(
            select(SourceAccount)
            .where(SourceAccount.source_id == source_id)
            .order_by(SourceAccount.created_at.asc())
            .limit(1)
        )
        .scalars()
        .one_or_none()
    )


def _latest_source_job(session: Session, *, source_id: str) -> IngestionJob | None:
    return (
        session.execute(
            select(IngestionJob)
            .where(IngestionJob.source_id == source_id)
            .order_by(IngestionJob.created_at.desc(), IngestionJob.id.desc())
            .limit(1)
        )
        .scalars()
        .one_or_none()
    )


def _source_health_state(
    *,
    source: Source,
    auth_payload: SourceAuthStatusPayload,
    sync_payload: SourceSyncStatusPayload,
) -> str:
    if not source.enabled:
        return "disabled"
    if auth_payload["reauth_required"] or auth_payload["needs_connection"]:
        return "attention"
    latest_job = sync_payload["latest_job"]
    if latest_job is not None and latest_job["status"].lower() in {"failed", "canceled"}:
        return "attention"
    if sync_payload["status"] == "running":
        return "syncing"
    return "healthy"
