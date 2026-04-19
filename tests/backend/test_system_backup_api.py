from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from lidltool.api import http_server
from lidltool.api.auth import issue_session_token
from lidltool.api.http_server import create_app
from lidltool.auth.sessions import (
    SESSION_MODE_COOKIE,
    SessionClientMetadata,
    create_user_session,
)
from lidltool.auth.users import create_local_user
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope


def _desktop_config(tmp_path: Path, *, credential_key: str | None) -> AppConfig:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key=credential_key,
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def _issue_admin_session(app) -> str:
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
                client_name="pytest",
                client_platform="tests",
            ),
        )
        return issue_session_token(
            user=user,
            session_id=session_record.session_id,
            config=context.config,
        )


def test_system_backup_succeeds_for_fresh_desktop_profile(tmp_path: Path) -> None:
    config = _desktop_config(
        tmp_path,
        credential_key="desktop-backup-secret-key-with-sufficient-entropy-123456",
    )
    app = create_app(config=config)

    with TestClient(app) as client:
        client.cookies.set("lidltool_session", _issue_admin_session(app))
        output_dir = tmp_path / "backup-success"

        response = client.post(
            "/api/v1/system/backup",
            json={
                "output_dir": str(output_dir),
                "include_documents": True,
                "include_export_json": True,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    result = payload["result"]
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["output_dir"] == str(output_dir.resolve())
    assert Path(result["db_artifact"]).is_file()
    assert result["token_artifact"] is None
    assert result["documents_artifact"] is not None
    assert Path(result["documents_artifact"]).is_dir()
    assert result["credential_key_artifact"] is not None
    assert (
        Path(result["credential_key_artifact"]).read_text(encoding="utf-8")
        == f"{config.credential_encryption_key}\n"
    )
    assert result["export_artifact"] is not None
    assert Path(result["export_artifact"]).is_file()
    assert result["export_records"] == 0
    assert "token file not found" in result["skipped"]
    assert str(manifest_path) in result["copied"]

    assert manifest["output_dir"] == str(output_dir.resolve())
    assert manifest["include_documents"] is True
    assert manifest["include_export_json"] is True
    assert manifest["export_records"] == 0
    assert manifest["requested_by_user_id"]


def test_system_backup_skips_missing_optional_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    config = _desktop_config(
        tmp_path,
        credential_key="desktop-backup-secret-key-with-sufficient-entropy-123456",
    )
    app = create_app(config=config)
    shutil.rmtree(config.document_storage_path)

    with TestClient(app) as client:
        app.state.request_context.config.credential_encryption_key = None
        monkeypatch.setattr(
            http_server,
            "_require_user_session_auth_context",
            lambda **_: SimpleNamespace(
                user=SimpleNamespace(user_id="admin-test-user", is_admin=True)
            ),
        )
        output_dir = tmp_path / "backup-missing-optional"

        response = client.post(
            "/api/v1/system/backup",
            json={
                "output_dir": str(output_dir),
                "include_documents": True,
                "include_export_json": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True

    result = payload["result"]
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert result["token_artifact"] is None
    assert result["documents_artifact"] is None
    assert result["credential_key_artifact"] is None
    assert result["export_artifact"] is None
    assert result["export_records"] is None
    assert "token file not found" in result["skipped"]
    assert "documents directory not found" in result["skipped"]
    assert "credential encryption key not available" in result["skipped"]
    assert manifest["documents_artifact"] is None
    assert manifest["credential_key_artifact"] is None


def test_system_backup_rejects_non_empty_output_dir(tmp_path: Path) -> None:
    config = _desktop_config(
        tmp_path,
        credential_key="desktop-backup-secret-key-with-sufficient-entropy-123456",
    )
    app = create_app(config=config)
    output_dir = (tmp_path / "backup-non-empty").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "existing.txt").write_text("occupied", encoding="utf-8")

    with TestClient(app) as client:
        client.cookies.set("lidltool_session", _issue_admin_session(app))
        response = client.post(
            "/api/v1/system/backup",
            json={
                "output_dir": str(output_dir),
                "include_documents": True,
                "include_export_json": False,
            },
        )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == f"backup output directory must be empty: {output_dir}"
    assert payload["error_code"] is None
    assert not (output_dir / "backup-manifest.json").exists()
