from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _desktop_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _build_python() -> Path:
    desktop_root = _desktop_root()
    if os.name == "nt":
        return desktop_root / "build" / "backend-venv" / "Scripts" / "python.exe"
    return desktop_root / "build" / "backend-venv" / "bin" / "python"


def _ensure_build_backend_src_on_path() -> Path:
    desktop_root = _desktop_root()
    packaged_src = desktop_root / "build" / "backend-src" / "src"
    if not packaged_src.exists():
        raise RuntimeError(
            f"Packaged backend source directory was not found at {packaged_src}. Run 'npm run build' first."
        )
    sys.path.insert(0, str(packaged_src))
    leaked_checkout_paths = [
        entry
        for entry in sys.path
        if isinstance(entry, str) and entry.replace("\\", "/").endswith("/vendor/backend/src")
    ]
    if leaked_checkout_paths:
        raise RuntimeError(
            "Packaged OCR smoke unexpectedly resolved checkout backend source paths: "
            + ", ".join(leaked_checkout_paths)
        )
    return packaged_src


PACKAGED_SRC = _ensure_build_backend_src_on_path()

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from lidltool.api.auth import issue_session_token
from lidltool.api.http_server import create_app
from lidltool.auth.sessions import (
    SESSION_MODE_COOKIE,
    SessionClientMetadata,
    create_user_session,
)
from lidltool.auth.users import create_local_user
from lidltool.config import build_config
from lidltool.db.engine import session_scope
from lidltool.db.models import Document, Transaction, TransactionItem


def _font_path_candidates() -> list[Path]:
    return [
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _make_scanned_pdf(pdf_path: Path) -> None:
    font_path = next((candidate for candidate in _font_path_candidates() if candidate.exists()), None)
    if font_path is None:
        raise RuntimeError("No supported OCR smoke font was found on this machine.")
    font = ImageFont.truetype(str(font_path), 44)
    image = Image.new("RGB", (1400, 1200), "white")
    draw = ImageDraw.Draw(image)
    lines = [
        "LIDL",
        "19.04.2026",
        "BANANAS",
        "1,99",
        "MILK 3.5%",
        "2,49",
        "TOTAL 4,48",
    ]
    y = 80
    for line in lines:
        draw.text((80, y), line, fill="black", font=font)
        y += 120
    image.save(pdf_path, "PDF", resolution=200.0)


def main() -> None:
    desktop_root = _desktop_root()
    build_python = _build_python()
    if Path(sys.executable).resolve() != build_python.resolve():
        raise RuntimeError(
            f"Packaged OCR smoke must run under the build backend runtime. Expected {build_python}, got {sys.executable}."
        )

    with tempfile.TemporaryDirectory(prefix="desktop-ocr-packaged-") as tmpdir:
        root = Path(tmpdir)
        db_path = root / "desktop-ocr-smoke.sqlite"
        pdf_path = root / "ocr-smoke.pdf"
        config_dir = root / "config"
        documents_dir = root / "documents"
        config_dir.mkdir(parents=True, exist_ok=True)
        documents_dir.mkdir(parents=True, exist_ok=True)

        os.environ["LIDLTOOL_CONFIG_DIR"] = str(config_dir)
        os.environ["LIDLTOOL_DOCUMENT_STORAGE_PATH"] = str(documents_dir)
        os.environ["LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"] = (
            "desktop-smoke-test-secret-key-1234567890abcdef"
        )
        os.environ["LIDLTOOL_DESKTOP_MODE"] = "true"
        os.environ["LIDLTOOL_CONNECTOR_HOST_KIND"] = "electron"
        os.environ["LIDLTOOL_OCR_DEFAULT_PROVIDER"] = "glm_ocr_local"
        os.environ["LIDLTOOL_OCR_FALLBACK_ENABLED"] = "false"
        os.environ["LIDLTOOL_ITEM_CATEGORIZER_ENABLED"] = "false"

        _make_scanned_pdf(pdf_path)

        config = build_config(db_override=db_path)
        app = create_app(config=config)

        with TestClient(app) as client:
            context = app.state.request_context
            with session_scope(context.sessions) as session:
                user = create_local_user(
                    session,
                    username="admin",
                    password="test-password",
                    display_name="Admin",
                    is_admin=True,
                )
                session_record = create_user_session(
                    session,
                    user=user,
                    metadata=SessionClientMetadata(
                        auth_transport=SESSION_MODE_COOKIE,
                        client_name="desktop-smoke",
                        client_platform="tests",
                    ),
                )
                token = issue_session_token(
                    user=user,
                    session_id=session_record.session_id,
                    config=context.config,
                )

            client.cookies.set("lidltool_session", token)
            upload_response = client.post(
                "/api/v1/documents/upload",
                data={"source": "ocr_upload"},
                files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
            )
            upload_payload = upload_response.json()
            if upload_response.status_code != 200 or upload_payload.get("ok") is not True:
                raise RuntimeError(f"upload failed: {upload_response.status_code} {upload_response.text}")
            document_id = str(upload_payload["result"]["document_id"])

            process_response = client.post(
                f"/api/v1/documents/{document_id}/process",
                data={"scope": "personal"},
            )
            process_payload = process_response.json()
            if process_response.status_code != 200 or process_payload.get("ok") is not True:
                raise RuntimeError(
                    f"process start failed: {process_response.status_code} {process_response.text}"
                )
            job_id = str(process_payload["result"]["job_id"])

            worker = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lidltool.ingest.jobs",
                    "--db",
                    str(db_path),
                    "--poll-interval-s",
                    "0.2",
                    "--idle-exit-after-s",
                    "2",
                ],
                cwd=desktop_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=os.environ.copy(),
            )
            try:
                timeline_events: list[str] = []
                final_status_payload: dict[str, object] | None = None
                deadline = time.time() + 60
                while time.time() < deadline:
                    status_response = client.get(
                        f"/api/v1/documents/{document_id}/status",
                        params={"job_id": job_id},
                    )
                    status_payload = status_response.json()
                    if status_response.status_code != 200 or status_payload.get("ok") is not True:
                        raise RuntimeError(
                            f"status poll failed: {status_response.status_code} {status_response.text}"
                        )
                    result = status_payload["result"]
                    job = result.get("job") or {}
                    timeline_events = [
                        str(event.get("event")) for event in (job.get("timeline") or [])
                    ]
                    if result.get("status") == "failed":
                        raise RuntimeError(json.dumps(status_payload, indent=2))
                    if result.get("status") == "completed" and result.get("transaction_id"):
                        final_status_payload = status_payload
                        break
                    time.sleep(0.5)

                if final_status_payload is None:
                    raise RuntimeError(
                        f"document never completed in packaged OCR smoke; last timeline={timeline_events}"
                    )

                worker.wait(timeout=15)
                worker_output = worker.stdout.read() if worker.stdout is not None else ""
                if worker.returncode != 0:
                    raise RuntimeError(
                        f"packaged OCR worker exited {worker.returncode}: {worker_output}"
                    )

                with session_scope(context.sessions) as session:
                    document = session.get(Document, document_id)
                    if document is None:
                        raise RuntimeError("document row was not found after OCR processing")
                    transaction = session.get(Transaction, document.transaction_id)
                    if transaction is None:
                        raise RuntimeError("OCR did not create a transaction row")
                    item_count = (
                        session.query(TransactionItem)
                        .filter(TransactionItem.transaction_id == transaction.id)
                        .count()
                    )
                    merchant_name = transaction.merchant_name
                    total_gross_cents = transaction.total_gross_cents
                    stored_ocr_provider = document.ocr_provider

                result = final_status_payload["result"]
                summary = {
                    "python": sys.executable,
                    "packaged_src": str(PACKAGED_SRC),
                    "document_id": document_id,
                    "job_id": job_id,
                    "document_status": result["status"],
                    "transaction_id": result["transaction_id"],
                    "ocr_provider": result["ocr_provider"],
                    "stored_ocr_provider": stored_ocr_provider,
                    "review_status": result["review_status"],
                    "timeline_events": timeline_events,
                    "merchant_name": merchant_name,
                    "total_gross_cents": total_gross_cents,
                    "item_count": item_count,
                    "worker_exit_code": worker.returncode,
                    "worker_output_tail": worker_output.strip().splitlines()[-8:],
                }
                print(json.dumps(summary, indent=2))
            finally:
                if worker.poll() is None:
                    worker.terminate()
                    try:
                        worker.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        worker.kill()
                        worker.wait(timeout=5)


if __name__ == "__main__":
    main()
