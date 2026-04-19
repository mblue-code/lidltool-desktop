from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lidltool.config import AppConfig, database_url
from lidltool.db.engine import create_engine_for_url, migrate_db, session_factory, session_scope
from lidltool.db.models import Document, IngestionJob
from lidltool.ingest.jobs import JobService


def _job_service(tmp_path) -> tuple[JobService, object]:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        desktop_mode=True,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    db_url = database_url(config)
    migrate_db(db_url)
    engine = create_engine_for_url(db_url)
    sessions = session_factory(engine)
    return JobService(session_factory=sessions, config=config), sessions


def test_ocr_job_worker_consumes_queue_and_updates_document_status(
    tmp_path, monkeypatch
) -> None:
    service, sessions = _job_service(tmp_path)

    with session_scope(sessions) as session:
        document = Document(
            storage_uri="file:///tmp/receipt.pdf",
            mime_type="application/pdf",
            file_name="receipt.pdf",
            ocr_status="queued",
        )
        session.add(document)
        session.flush()
        document_id = document.id

    job, reused = service.create_ocr_job(document_id=document_id)
    assert reused is False

    transitions: list[str] = []
    original_mark_document_status = service._mark_document_ocr_status

    def _record_transition(*, job_id: str, document_id: str, status: str, message: str) -> None:
        transitions.append(status)
        original_mark_document_status(
            job_id=job_id,
            document_id=document_id,
            status=status,
            message=message,
        )

    monkeypatch.setattr(service, "_mark_document_ocr_status", _record_transition)

    def _fake_run_ocr_with_timeout_retry(*, service, job_id: str, document_id: str):  # type: ignore[no-untyped-def]
        del service, job_id
        with session_scope(sessions) as session:
            document = session.get(Document, document_id)
            assert document is not None
            assert document.ocr_status == "processing"
            document.ocr_status = "completed"
            document.review_status = "approved"
            document.ocr_provider = "desktop_local"
        return {
            "document_id": document_id,
            "transaction_id": "tx-1",
            "ocr_provider": "desktop_local",
            "fallback_used": False,
            "attempted_providers": ["desktop_local"],
            "transaction_confidence": 0.97,
            "review_status": "approved",
        }

    monkeypatch.setattr(service, "_run_ocr_with_timeout_retry", _fake_run_ocr_with_timeout_retry)

    claimed = service.run_worker_once()

    assert claimed is True
    assert transitions == ["starting_engine", "processing"]

    with session_scope(sessions) as session:
        stored_document = session.get(Document, document_id)
        stored_job = session.get(IngestionJob, job.id)

        assert stored_document is not None
        assert stored_document.ocr_status == "completed"
        assert stored_document.ocr_provider == "desktop_local"
        assert stored_job is not None
        assert stored_job.status == "success"


def test_run_worker_loop_exits_after_idle_timeout(tmp_path) -> None:
    service, _sessions = _job_service(tmp_path)

    processed = service.run_worker_loop(
        poll_interval_s=0.01,
        max_jobs=None,
        idle_exit=False,
        idle_exit_after_s=0.05,
    )

    assert processed == 0


def test_worker_module_help_starts_without_import_error() -> None:
    backend_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        f"{backend_src}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else str(backend_src)
    )

    result = subprocess.run(
        [sys.executable, "-m", "lidltool.ingest.jobs", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert "Durable ingestion job worker" in result.stdout
