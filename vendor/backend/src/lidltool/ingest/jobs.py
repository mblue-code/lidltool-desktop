from __future__ import annotations

import argparse
import hashlib
import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from lidltool.amazon.client_playwright import AmazonPlaywrightClient
from lidltool.amazon.session import default_amazon_state_file
from lidltool.auth.token_store import TokenStore
from lidltool.auth.users import ensure_service_user
from lidltool.config import AppConfig, build_config, database_url
from lidltool.connectors.amazon_adapter import AmazonConnectorAdapter
from lidltool.connectors.base import (
    Connector,
    require_connector_action_scope,
    validate_connector_scope_contract,
)
from lidltool.connectors.dm_adapter import DmConnectorAdapter
from lidltool.connectors.kaufland_adapter import KauflandConnectorAdapter
from lidltool.connectors.lidl_adapter import LidlConnectorAdapter
from lidltool.connectors.rewe_adapter import ReweConnectorAdapter
from lidltool.connectors.rossmann_adapter import RossmannConnectorAdapter
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Document, IngestionJob, Source, SourceAccount
from lidltool.dm.client_playwright import DmPlaywrightClient
from lidltool.dm.session import default_dm_state_file
from lidltool.ingest.ocr_ingest import OcrIngestService
from lidltool.ingest.sync import SyncProgress, SyncResult, SyncService
from lidltool.kaufland.client_playwright import KauflandPlaywrightClient
from lidltool.kaufland.session import default_kaufland_state_file
from lidltool.lidl.client import create_lidl_client
from lidltool.rewe.client_playwright import RewePlaywrightClient
from lidltool.rewe.session import default_rewe_state_file
from lidltool.rossmann.client_playwright import RossmannPlaywrightClient
from lidltool.rossmann.session import default_rossmann_state_file

LOGGER = logging.getLogger(__name__)
RUNTIME_CONNECTOR_SCOPES = {
    "auth.session",
    "read.health",
    "read.receipts",
    "read.receipt_detail",
    "transform.normalize",
    "transform.discounts",
}

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_PARTIAL_SUCCESS = "partial_success"
JOB_STATUS_FAILED = "failed"
JOB_STATUS_CANCELED = "canceled"

TERMINAL_STATUSES = {
    JOB_STATUS_SUCCESS,
    JOB_STATUS_PARTIAL_SUCCESS,
    JOB_STATUS_FAILED,
    JOB_STATUS_CANCELED,
}
REUSABLE_IDEMPOTENT_STATUSES = {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, JOB_STATUS_SUCCESS}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    JOB_STATUS_QUEUED: {JOB_STATUS_RUNNING, JOB_STATUS_CANCELED},
    JOB_STATUS_RUNNING: {
        JOB_STATUS_SUCCESS,
        JOB_STATUS_PARTIAL_SUCCESS,
        JOB_STATUS_FAILED,
        JOB_STATUS_CANCELED,
    },
    JOB_STATUS_SUCCESS: set(),
    JOB_STATUS_PARTIAL_SUCCESS: set(),
    JOB_STATUS_FAILED: set(),
    JOB_STATUS_CANCELED: set(),
}


@dataclass(slots=True)
class JobSnapshot:
    id: str
    source_id: str
    source_account_id: str | None
    status: str
    idempotency_key: str | None
    started_at: datetime | None
    finished_at: datetime | None
    summary: dict[str, Any] | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class InvalidJobTransitionError(RuntimeError):
    pass


class JobService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        config: AppConfig,
        idempotency_ttl: timedelta = timedelta(hours=24),
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._idempotency_ttl = idempotency_ttl
        self._worker_host = socket.gethostname()
        self._worker_pid = os.getpid()
        self._worker_id = os.getenv("LIDLTOOL_WORKER_ID", f"{self._worker_host}:{self._worker_pid}")

    def create_sync_job(
        self,
        *,
        full: bool,
        source: str | None = None,
        trigger_type: str = "manual",
        retry: bool = False,
        idempotency_key: str | None = None,
        window_start: str | None = None,
        window_end: str | None = None,
        caller_token: str | None = None,
    ) -> tuple[JobSnapshot, bool]:
        now = datetime.now(tz=UTC)
        with session_scope(self._session_factory) as session:
            target_source = source or self._config.source
            source_model, account = self._ensure_source(session, source_id=target_source)
            base_key = idempotency_key or derive_idempotency_key(
                source_id=source_model.id,
                source_account_id=account.id if account is not None else "",
                trigger_type=trigger_type,
                window_start=window_start,
                window_end=window_end,
                caller_token=caller_token,
            )

            existing = self._find_reusable_job(session, base_key=base_key, now=now)
            if existing is not None:
                LOGGER.info(
                    "job.idempotency.reused source=%s job_id=%s key=%s status=%s",
                    source_model.id,
                    existing.id,
                    base_key,
                    existing.status,
                )
                return _to_snapshot(existing), True

            key_to_store = base_key
            retry_of_job_id: str | None = None
            failed_attempt = self._latest_failed_attempt(session, base_key=base_key, now=now)
            failed_attempt_count = self._failed_attempt_count(session, base_key=base_key, now=now)
            if retry and failed_attempt is not None:
                if failed_attempt_count >= self._config.retry_dead_letter_threshold:
                    dead_letter_job = IngestionJob(
                        source_id=source_model.id,
                        source_account_id=account.id if account is not None else None,
                        status=JOB_STATUS_FAILED,
                        trigger_type=trigger_type,
                        idempotency_key=self._next_retry_key(session, base_key=base_key),
                        started_at=now,
                        finished_at=now,
                        summary={
                            "full": full,
                            "progress": _empty_progress_summary(),
                            "retry_of_job_id": failed_attempt.id,
                            "warnings": [],
                            "dead_letter": {
                                "dead_lettered": True,
                                "reason": "repeated_failures",
                                "attempt_count": failed_attempt_count,
                                "threshold": self._config.retry_dead_letter_threshold,
                                "base_idempotency_key": base_key,
                                "failed_job_id": failed_attempt.id,
                            },
                            "timeline": [
                                _timeline_event(
                                    event="queued",
                                    status=JOB_STATUS_QUEUED,
                                    message="sync job queued",
                                ),
                                _timeline_event(
                                    event="dead_lettered",
                                    status=JOB_STATUS_FAILED,
                                    message="retry moved to dead-letter queue after repeated failures",
                                    details={
                                        "attempt_count": failed_attempt_count,
                                        "threshold": self._config.retry_dead_letter_threshold,
                                    },
                                ),
                            ],
                        },
                        error=(
                            "retry dead-lettered after repeated failures; "
                            "inspect source health and incident playbook"
                        ),
                    )
                    session.add(dead_letter_job)
                    session.flush()
                    LOGGER.warning(
                        "job.retry.dead_lettered source=%s job_id=%s key=%s attempts=%s threshold=%s",
                        source_model.id,
                        dead_letter_job.id,
                        base_key,
                        failed_attempt_count,
                        self._config.retry_dead_letter_threshold,
                    )
                    return _to_snapshot(dead_letter_job), False
                key_to_store = self._next_retry_key(session, base_key=base_key)
                retry_of_job_id = failed_attempt.id

            job = IngestionJob(
                source_id=source_model.id,
                source_account_id=account.id if account is not None else None,
                status=JOB_STATUS_QUEUED,
                trigger_type=trigger_type,
                idempotency_key=key_to_store,
                summary={
                    "full": full,
                    "progress": _empty_progress_summary(),
                    "retry_of_job_id": retry_of_job_id,
                    "warnings": [],
                    "timeline": [
                        _timeline_event(
                            event="queued",
                            status=JOB_STATUS_QUEUED,
                            message="sync job queued",
                        )
                    ],
                },
            )
            session.add(job)
            session.flush()
            LOGGER.info(
                "job.lifecycle.created source=%s job_id=%s status=%s key=%s",
                source_model.id,
                job.id,
                job.status,
                key_to_store,
            )
            return _to_snapshot(job), False

    def start_sync_job(self, *, job_id: str, full: bool) -> bool:
        del full
        snapshot = self.get_job(job_id=job_id)
        if snapshot is None:
            return False
        return snapshot.status == JOB_STATUS_QUEUED

    def create_ocr_job(
        self,
        *,
        document_id: str,
        source: str = "ocr_upload",
        trigger_type: str = "manual",
        caller_token: str | None = None,
    ) -> tuple[JobSnapshot, bool]:
        now = datetime.now(tz=UTC)
        with session_scope(self._session_factory) as session:
            source_model, account = self._ensure_source(session, source_id=source)
            base_key = hashlib.sha256(
                f"ocr|{document_id}|{caller_token or 'system'}".encode()
            ).hexdigest()
            existing = self._find_reusable_job(session, base_key=base_key, now=now)
            if existing is not None:
                return _to_snapshot(existing), True

            job = IngestionJob(
                source_id=source_model.id,
                source_account_id=account.id if account is not None else None,
                status=JOB_STATUS_QUEUED,
                trigger_type=trigger_type,
                idempotency_key=base_key,
                summary={
                    "job_type": "ocr_process",
                    "document_id": document_id,
                    "progress": _empty_progress_summary(),
                    "warnings": [],
                    "timeline": [
                        _timeline_event(
                            event="queued",
                            status=JOB_STATUS_QUEUED,
                            message="ocr job queued",
                        )
                    ],
                },
            )
            session.add(job)
            session.flush()
            return _to_snapshot(job), False

    def start_ocr_job(self, *, job_id: str, document_id: str) -> bool:
        del document_id
        snapshot = self.get_job(job_id=job_id)
        if snapshot is None:
            return False
        return snapshot.status == JOB_STATUS_QUEUED

    def run_worker_once(self) -> bool:
        snapshot = self._claim_next_job()
        if snapshot is None:
            return False
        summary = snapshot.summary or {}
        if summary.get("job_type") == "ocr_process":
            document_id = str(summary.get("document_id", "")).strip()
            if not document_id:
                self._finalize_failure(job_id=snapshot.id, error="ocr job missing document_id")
                return True
            self._run_ocr_job(snapshot.id, document_id)
            return True
        self._run_sync_job(snapshot.id, bool(summary.get("full", False)))
        return True

    def run_worker_loop(
        self,
        *,
        poll_interval_s: float = 1.0,
        max_jobs: int | None = None,
        idle_exit: bool = False,
    ) -> int:
        processed = 0
        while max_jobs is None or processed < max_jobs:
            claimed = self.run_worker_once()
            if claimed:
                processed += 1
                continue
            if idle_exit:
                break
            time.sleep(max(poll_interval_s, 0.1))
        return processed

    def reconcile_stale_running_jobs(
        self, *, stale_after: timedelta = timedelta(minutes=30)
    ) -> int:
        now = datetime.now(tz=UTC)
        cutoff = now - stale_after
        with session_scope(self._session_factory) as session:
            stale_jobs = (
                session.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.status == JOB_STATUS_RUNNING,
                        IngestionJob.started_at.is_not(None),
                        IngestionJob.started_at < cutoff,
                    )
                    .order_by(IngestionJob.started_at.asc(), IngestionJob.id.asc())
                )
                .scalars()
                .all()
            )
            for job in stale_jobs:
                summary = dict(job.summary or {})
                _append_timeline_event(
                    summary,
                    event="recovered_failed",
                    status=JOB_STATUS_FAILED,
                    message="stale running job reconciled as failed",
                    details={"cutoff": cutoff.isoformat()},
                )
                summary["recovery"] = {
                    "reconciled_at": now.isoformat(),
                    "reason": "stale_running_on_worker_start",
                }
                job.summary = summary
                job.status = JOB_STATUS_FAILED
                job.error = "job marked failed by worker recovery after stale running state"
                job.finished_at = now
                if (
                    isinstance(summary.get("job_type"), str)
                    and summary.get("job_type") == "ocr_process"
                ):
                    document_id = str(summary.get("document_id", "")).strip()
                    if document_id:
                        document = session.get(Document, document_id)
                        if document is not None:
                            document.ocr_status = "failed"
            return len(stale_jobs)

    def cancel_job(self, *, job_id: str) -> bool:
        return self._transition_job(job_id=job_id, new_status=JOB_STATUS_CANCELED)

    def get_job(self, *, job_id: str) -> JobSnapshot | None:
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return None
            return _to_snapshot(job)

    def get_job_status_payload(self, *, job_id: str) -> dict[str, Any] | None:
        snapshot = self.get_job(job_id=job_id)
        if snapshot is None:
            return None
        summary = snapshot.summary or {}
        return {
            "job_id": snapshot.id,
            "source": snapshot.source_id,
            "source_account_id": snapshot.source_account_id,
            "status": snapshot.status,
            "started_at": (
                snapshot.started_at.isoformat() if snapshot.started_at is not None else None
            ),
            "finished_at": (
                snapshot.finished_at.isoformat() if snapshot.finished_at is not None else None
            ),
            "summary": summary,
            "progress": _summary_progress(summary),
            "timeline": _summary_timeline(summary),
            "warnings": _summary_warnings(summary),
            "dead_letter": _summary_dead_letter(summary),
            "error": snapshot.error,
        }

    def _run_sync_job(self, job_id: str, full: bool) -> None:
        LOGGER.info("job.lifecycle.running job_id=%s", job_id)
        try:
            snapshot = self.get_job(job_id=job_id)
            source_id = snapshot.source_id if snapshot is not None else self._config.source
            source_config = self._config.model_copy(update={"source": source_id})
            client, connector = self._build_source_connector(source_config=source_config)
            sync_service = SyncService(
                client=client,
                session_factory=self._session_factory,
                config=source_config,
                connector=connector,
            )

            def progress_cb(progress: SyncProgress) -> None:
                try:
                    self._update_progress(job_id=job_id, progress=progress)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning(
                        "job.lifecycle.progress_update_failed job_id=%s error=%s",
                        job_id,
                        exc,
                    )

            result = sync_service.sync(full=full, progress_cb=progress_cb)
            self._finalize_success(job_id=job_id, result=result)
        except Exception as exc:  # noqa: BLE001
            self._finalize_failure(job_id=job_id, error=str(exc))

    def _claim_next_job(self) -> JobSnapshot | None:
        now = datetime.now(tz=UTC)
        with session_scope(self._session_factory) as session:
            queued_job_id_subquery = (
                select(IngestionJob.id)
                .where(IngestionJob.status == JOB_STATUS_QUEUED)
                .order_by(IngestionJob.created_at.asc(), IngestionJob.id.asc())
                .limit(1)
                .scalar_subquery()
            )
            claim_stmt = (
                update(IngestionJob)
                .where(
                    IngestionJob.id == queued_job_id_subquery,
                    IngestionJob.status == JOB_STATUS_QUEUED,
                )
                .values(
                    status=JOB_STATUS_RUNNING,
                    started_at=now,
                    updated_at=now,
                )
                .returning(IngestionJob)
            )
            job = session.execute(claim_stmt).scalars().one_or_none()
            if job is None:
                return None
            summary = dict(job.summary or {})
            worker_claim = {
                "worker_id": self._worker_id,
                "host": self._worker_host,
                "pid": self._worker_pid,
                "claimed_at": now.isoformat(),
            }
            summary["worker_claim"] = worker_claim
            _append_timeline_event(
                summary,
                event="started",
                status=JOB_STATUS_RUNNING,
                message="job started by durable worker",
                details={"worker_claim": worker_claim},
            )
            job.summary = summary
            LOGGER.info(
                "job.worker.claimed job_id=%s worker_id=%s host=%s pid=%s",
                job.id,
                self._worker_id,
                self._worker_host,
                self._worker_pid,
            )
            return _to_snapshot(job)

    def _run_ocr_job(self, job_id: str, document_id: str) -> None:
        LOGGER.info("job.lifecycle.running_ocr job_id=%s document_id=%s", job_id, document_id)
        try:
            service = OcrIngestService(session_factory=self._session_factory, config=self._config)
            result = service.process_document(document_id=document_id)
            self._finalize_ocr_success(job_id=job_id, result=result)
        except Exception as exc:  # noqa: BLE001
            with session_scope(self._session_factory) as session:
                document = session.get(Document, document_id)
                if document is not None:
                    document.ocr_status = "failed"
            self._finalize_failure(job_id=job_id, error=str(exc))

    def _build_source_connector(self, *, source_config: AppConfig) -> tuple[Any | None, Connector]:
        source_id = source_config.source
        if source_id == "lidl_plus_de":
            token_store = TokenStore.from_config(source_config)
            refresh_token = token_store.get_refresh_token()
            if not refresh_token:
                raise RuntimeError("auth token missing; run lidltool auth bootstrap")
            lidl_client = create_lidl_client(source_config, refresh_token, token_store=token_store)
            connector: Connector = LidlConnectorAdapter(
                client=lidl_client, page_size=source_config.page_size
            )
            self._validate_connector_security(connector)
            return lidl_client, connector
        if source_id == "amazon_de":
            amazon_client = AmazonPlaywrightClient(
                state_file=default_amazon_state_file(source_config),
                domain="amazon.de",
                headless=True,
            )
            connector = AmazonConnectorAdapter(client=amazon_client, source=source_id)
            self._validate_connector_security(connector)
            return None, connector
        if source_id == "rewe_de":
            rewe_client = RewePlaywrightClient(
                state_file=default_rewe_state_file(source_config),
                domain="shop.rewe.de",
                headless=True,
            )
            connector = ReweConnectorAdapter(client=rewe_client, source=source_id)
            self._validate_connector_security(connector)
            return None, connector
        if source_id == "kaufland_de":
            kaufland_client = KauflandPlaywrightClient(
                state_file=default_kaufland_state_file(source_config),
                domain="www.kaufland.de",
                headless=True,
            )
            connector = KauflandConnectorAdapter(client=kaufland_client, source=source_id)
            self._validate_connector_security(connector)
            return None, connector
        if source_id == "dm_de":
            dm_client = DmPlaywrightClient(
                state_file=default_dm_state_file(source_config),
                domain="www.dm.de",
                headless=True,
            )
            connector = DmConnectorAdapter(client=dm_client, source=source_id)
            self._validate_connector_security(connector)
            return None, connector
        if source_id == "rossmann_de":
            rossmann_client = RossmannPlaywrightClient(
                state_file=default_rossmann_state_file(source_config),
                domain="www.rossmann.de",
                headless=True,
            )
            connector = RossmannConnectorAdapter(client=rossmann_client, source=source_id)
            self._validate_connector_security(connector)
            return None, connector
        raise RuntimeError(f"unsupported source connector: {source_id}")

    def _validate_connector_security(self, connector: Connector) -> None:
        validate_connector_scope_contract(connector)
        for action in (
            "authenticate",
            "refresh_auth",
            "healthcheck",
            "discover_new_records",
            "fetch_record_detail",
            "normalize",
            "extract_discounts",
        ):
            require_connector_action_scope(
                connector,
                action=action,
                granted_scopes=RUNTIME_CONNECTOR_SCOPES,
            )

    def _update_progress(self, *, job_id: str, progress: SyncProgress) -> None:
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None or job.status != JOB_STATUS_RUNNING:
                return
            summary = dict(job.summary or {})
            next_progress = _progress_to_dict(progress)
            previous_progress = summary.get("progress")
            summary["progress"] = next_progress
            if previous_progress != next_progress:
                _append_timeline_event(
                    summary,
                    event="progress",
                    status=job.status,
                    message="sync progress update",
                    details=next_progress,
                )
            job.summary = summary
            LOGGER.info(
                "job.lifecycle.progress job_id=%s pages=%s receipts_seen=%s new_receipts=%s",
                job_id,
                progress.pages,
                progress.receipts_seen,
                progress.new_receipts,
            )

    def _finalize_success(self, *, job_id: str, result: SyncResult) -> None:
        final_status = JOB_STATUS_PARTIAL_SUCCESS if result.warnings else JOB_STATUS_SUCCESS
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            self._validate_transition(current_status=job.status, next_status=final_status)
            summary = dict(job.summary or {})
            summary["result"] = {
                "ok": result.ok,
                "full": result.full,
                "pages": result.pages,
                "receipts_seen": result.receipts_seen,
                "new_receipts": result.new_receipts,
                "new_items": result.new_items,
                "skipped_existing": result.skipped_existing,
                "cutoff_hit": result.cutoff_hit,
                "warnings": list(result.warnings),
            }
            if job.started_at is not None:
                started_at = _as_utc(job.started_at)
                result_summary = summary.get("result")
                if not isinstance(result_summary, dict):
                    result_summary = {}
                result_summary["duration_ms"] = max(
                    int((datetime.now(tz=UTC) - started_at).total_seconds() * 1000), 0
                )
                summary["result"] = result_summary
            summary["warnings"] = list(result.warnings)
            summary["progress"] = {
                "pages": result.pages,
                "receipts_seen": result.receipts_seen,
                "new_receipts": result.new_receipts,
                "new_items": result.new_items,
                "skipped_existing": result.skipped_existing,
            }
            _append_timeline_event(
                summary,
                event="completed",
                status=final_status,
                message="sync job completed",
                details={"warnings": len(result.warnings)},
            )
            job.summary = summary
            job.error = None
            job.status = final_status
            job.finished_at = datetime.now(tz=UTC)
            LOGGER.info("job.lifecycle.finished job_id=%s status=%s", job_id, final_status)

    def _finalize_ocr_success(self, *, job_id: str, result: dict[str, Any]) -> None:
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            self._validate_transition(current_status=job.status, next_status=JOB_STATUS_SUCCESS)
            summary = dict(job.summary or {})
            summary["result"] = result
            summary["progress"] = {
                "pages": 1,
                "receipts_seen": 1,
                "new_receipts": 1,
                "new_items": 0,
                "skipped_existing": 0,
            }
            _append_timeline_event(
                summary,
                event="completed",
                status=JOB_STATUS_SUCCESS,
                message="ocr job completed",
            )
            job.summary = summary
            job.error = None
            job.status = JOB_STATUS_SUCCESS
            job.finished_at = datetime.now(tz=UTC)
            LOGGER.info("job.lifecycle.finished_ocr job_id=%s", job_id)

    def _finalize_failure(self, *, job_id: str, error: str) -> None:
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return
            if job.status == JOB_STATUS_CANCELED:
                return
            self._validate_transition(current_status=job.status, next_status=JOB_STATUS_FAILED)
            summary = dict(job.summary or {})
            _append_timeline_event(
                summary,
                event="failed",
                status=JOB_STATUS_FAILED,
                message="sync job failed",
                details={"error": error},
            )
            if job.started_at is not None:
                started_at = _as_utc(job.started_at)
                summary["last_duration_ms"] = max(
                    int((datetime.now(tz=UTC) - started_at).total_seconds() * 1000), 0
                )
            job.summary = summary
            job.status = JOB_STATUS_FAILED
            job.error = error
            job.finished_at = datetime.now(tz=UTC)
            LOGGER.error("job.lifecycle.failed job_id=%s error=%s", job_id, error)

    def _transition_job(self, *, job_id: str, new_status: str) -> bool:
        with session_scope(self._session_factory) as session:
            job = session.get(IngestionJob, job_id)
            if job is None:
                return False
            self._validate_transition(current_status=job.status, next_status=new_status)
            job.status = new_status
            summary = dict(job.summary or {})
            if new_status == JOB_STATUS_RUNNING and job.started_at is None:
                job.started_at = datetime.now(tz=UTC)
                _append_timeline_event(
                    summary,
                    event="started",
                    status=new_status,
                    message="sync job started",
                )
            elif new_status == JOB_STATUS_CANCELED:
                _append_timeline_event(
                    summary,
                    event="canceled",
                    status=new_status,
                    message="sync job canceled",
                )
            job.summary = summary
            if new_status in TERMINAL_STATUSES:
                job.finished_at = datetime.now(tz=UTC)
            LOGGER.info("job.lifecycle.transition job_id=%s status=%s", job_id, new_status)
            return True

    def _find_reusable_job(
        self, session: Session, *, base_key: str, now: datetime
    ) -> IngestionJob | None:
        cutoff = now - self._idempotency_ttl
        stmt = (
            select(IngestionJob)
            .where(
                IngestionJob.idempotency_key == base_key,
                IngestionJob.created_at >= cutoff,
                IngestionJob.status.in_(REUSABLE_IDEMPOTENT_STATUSES),
            )
            .order_by(IngestionJob.created_at.desc())
        )
        return session.execute(stmt).scalar_one_or_none()

    def _latest_failed_attempt(
        self, session: Session, *, base_key: str, now: datetime
    ) -> IngestionJob | None:
        cutoff = now - self._idempotency_ttl
        retry_like = f"{base_key}:retry:%"
        stmt = (
            select(IngestionJob)
            .where(
                IngestionJob.idempotency_key.is_not(None),
                (IngestionJob.idempotency_key == base_key)
                | IngestionJob.idempotency_key.like(retry_like),
                IngestionJob.created_at >= cutoff,
                IngestionJob.status == JOB_STATUS_FAILED,
            )
            .order_by(IngestionJob.created_at.desc())
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def _failed_attempt_count(self, session: Session, *, base_key: str, now: datetime) -> int:
        cutoff = now - self._idempotency_ttl
        retry_like = f"{base_key}:retry:%"
        stmt = select(IngestionJob.id).where(
            IngestionJob.idempotency_key.is_not(None),
            (IngestionJob.idempotency_key == base_key)
            | IngestionJob.idempotency_key.like(retry_like),
            IngestionJob.created_at >= cutoff,
            IngestionJob.status == JOB_STATUS_FAILED,
        )
        return len(session.execute(stmt).scalars().all())

    def _next_retry_key(self, session: Session, *, base_key: str) -> str:
        like_pattern = f"{base_key}:retry:%"
        stmt = select(IngestionJob.idempotency_key).where(
            IngestionJob.idempotency_key.is_not(None),
            IngestionJob.idempotency_key.like(like_pattern),
        )
        existing_keys = [
            key for key in session.execute(stmt).scalars().all() if isinstance(key, str)
        ]
        retries = [0]
        for key in existing_keys:
            suffix = key.rsplit(":", 1)[-1]
            if suffix.isdigit():
                retries.append(int(suffix))
        return f"{base_key}:retry:{max(retries) + 1}"

    def _validate_transition(self, *, current_status: str, next_status: str) -> None:
        if next_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
            raise InvalidJobTransitionError(
                f"invalid ingestion_jobs transition: {current_status} -> {next_status}"
            )

    def _ensure_source(self, session: Session, *, source_id: str) -> tuple[Source, SourceAccount]:
        service_user = ensure_service_user(session)
        source = session.get(Source, source_id)
        if source is None:
            source = Source(
                id=source_id,
                user_id=service_user.user_id,
                kind="connector",
                display_name=source_id.replace("_", " ").title(),
                status="healthy",
                enabled=True,
            )
            session.add(source)
            session.flush()
        elif source.user_id is None:
            source.user_id = service_user.user_id
        account = session.execute(
            select(SourceAccount).where(SourceAccount.source_id == source.id).limit(1)
        ).scalar_one_or_none()
        if account is None:
            account = SourceAccount(source_id=source.id, account_ref="default", status="connected")
            session.add(account)
            session.flush()
        return source, account


def derive_idempotency_key(
    *,
    source_id: str,
    source_account_id: str,
    trigger_type: str,
    window_start: str | None,
    window_end: str | None,
    caller_token: str | None,
) -> str:
    now = datetime.now(tz=UTC)
    default_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    default_end = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()
    payload = "|".join(
        [
            source_id,
            source_account_id,
            trigger_type,
            window_start or default_start,
            window_end or default_end,
            caller_token or "system",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _empty_progress_summary() -> dict[str, int]:
    return {
        "pages": 0,
        "receipts_seen": 0,
        "new_receipts": 0,
        "new_items": 0,
        "skipped_existing": 0,
    }


def _progress_to_dict(progress: SyncProgress) -> dict[str, int]:
    return {
        "pages": progress.pages,
        "receipts_seen": progress.receipts_seen,
        "new_receipts": progress.new_receipts,
        "new_items": progress.new_items,
        "skipped_existing": progress.skipped_existing,
    }


def _timeline_event(
    *,
    event: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timeline_event: dict[str, Any] = {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "event": event,
        "status": status,
        "message": message,
    }
    if details:
        timeline_event["details"] = details
    return timeline_event


def _append_timeline_event(
    summary: dict[str, Any],
    *,
    event: str,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    timeline = _summary_timeline(summary)
    timeline.append(_timeline_event(event=event, status=status, message=message, details=details))
    summary["timeline"] = timeline[-100:]


def _summary_progress(summary: dict[str, Any]) -> dict[str, int]:
    progress = summary.get("progress")
    if isinstance(progress, dict):
        return {
            "pages": int(progress.get("pages", 0) or 0),
            "receipts_seen": int(progress.get("receipts_seen", 0) or 0),
            "new_receipts": int(progress.get("new_receipts", 0) or 0),
            "new_items": int(progress.get("new_items", 0) or 0),
            "skipped_existing": int(progress.get("skipped_existing", 0) or 0),
        }
    return _empty_progress_summary()


def _summary_timeline(summary: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = summary.get("timeline")
    if not isinstance(timeline, list):
        return []
    return [item for item in timeline if isinstance(item, dict)]


def _summary_warnings(summary: dict[str, Any]) -> list[str]:
    warnings = summary.get("warnings")
    if isinstance(warnings, list):
        return [str(warning) for warning in warnings]
    result = summary.get("result")
    if isinstance(result, dict):
        result_warnings = result.get("warnings")
        if isinstance(result_warnings, list):
            return [str(warning) for warning in result_warnings]
    return []


def _summary_dead_letter(summary: dict[str, Any]) -> dict[str, Any] | None:
    dead_letter = summary.get("dead_letter")
    if isinstance(dead_letter, dict):
        return dead_letter
    return None


def _to_snapshot(job: IngestionJob) -> JobSnapshot:
    return JobSnapshot(
        id=job.id,
        source_id=job.source_id,
        source_account_id=job.source_account_id,
        status=job.status,
        idempotency_key=job.idempotency_key,
        started_at=job.started_at,
        finished_at=job.finished_at,
        summary=job.summary,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _worker_config(*, db: str | None, config_path: str | None) -> AppConfig:
    return build_config(
        config_path=Path(config_path).expanduser() if config_path else None,
        db_override=Path(db).expanduser() if db else None,
    )


def run_worker(
    *,
    db: str | None = None,
    config_path: str | None = None,
    poll_interval_s: float = 1.0,
    max_jobs: int | None = None,
    once: bool = False,
    stale_after_minutes: int = 30,
) -> int:
    config = _worker_config(db=db, config_path=config_path)
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    sessions = session_factory(engine)
    service = JobService(session_factory=sessions, config=config)
    reconciled = service.reconcile_stale_running_jobs(
        stale_after=timedelta(minutes=max(stale_after_minutes, 1))
    )
    LOGGER.info("job.worker.reconcile reconciled=%s", reconciled)
    return service.run_worker_loop(
        poll_interval_s=poll_interval_s,
        max_jobs=max_jobs,
        idle_exit=once,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable ingestion job worker")
    parser.add_argument("--db", default=None, help="SQLite DB path override")
    parser.add_argument("--config", default=None, help="Config TOML path override")
    parser.add_argument("--poll-interval-s", type=float, default=1.0)
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--once", action="store_true", help="Exit when queue is empty")
    parser.add_argument("--stale-after-minutes", type=int, default=30)
    args = parser.parse_args()
    processed = run_worker(
        db=args.db,
        config_path=args.config,
        poll_interval_s=args.poll_interval_s,
        max_jobs=args.max_jobs,
        once=args.once,
        stale_after_minutes=args.stale_after_minutes,
    )
    LOGGER.info("job.worker.exited processed=%s", processed)


if __name__ == "__main__":
    main()
