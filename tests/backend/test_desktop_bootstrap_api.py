from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lidltool.api.http_server import create_app
from lidltool.config import AppConfig


def _desktop_config(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-bootstrap-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def test_fresh_desktop_requires_setup_and_reports_backend_pid(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))

    with TestClient(app) as client:
        health_response = client.get("/api/v1/health")
        assert health_response.status_code == 200
        health_payload = health_response.json()["result"]
        assert health_payload["ready"] is True
        assert isinstance(health_payload["pid"], int)
        assert health_payload["pid"] > 0

        setup_response = client.get("/api/v1/auth/setup-required")
        assert setup_response.status_code == 200
        assert setup_response.json()["result"] == {
            "required": True,
            "bootstrap_token_required": False,
        }
