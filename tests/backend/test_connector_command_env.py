from __future__ import annotations

from pathlib import Path

from lidltool.api import http_server
from lidltool.api.http_server import create_app
from lidltool.config import AppConfig


def _desktop_config(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-env-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def test_connector_process_env_sets_repo_root(tmp_path: Path, monkeypatch) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    repo_root = (tmp_path / "repo-root").resolve()
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(http_server, "_repo_root", lambda: repo_root)

    env = http_server._connector_process_env(app, config=app.state.request_context.config)

    assert env["LIDLTOOL_REPO_ROOT"] == str(repo_root)


def test_connector_manual_confirm_route_is_registered(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))

    routes = {
        (route.path, method)
        for route in app.router.routes
        for method in getattr(route, "methods", set())
    }

    assert ("/api/v1/connectors/{source_id}/bootstrap/confirm", "POST") in routes
