from __future__ import annotations

from fastapi.testclient import TestClient

from lidltool.api import http_server
from lidltool.api.http_server import create_app
from lidltool.api.http_state import get_automation_scheduler
from lidltool.config import AppConfig, build_config


def test_build_config_enables_desktop_mode_for_electron_host_kind(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("LIDLTOOL_CONNECTOR_HOST_KIND", "electron")
    monkeypatch.setenv("LIDLTOOL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("LIDLTOOL_DB", str(tmp_path / "lidltool.sqlite"))

    config = build_config()

    assert config.desktop_mode is True
    assert config.automations_scheduler_enabled is False
    assert config.connector_live_sync_enabled is False


def test_create_app_desktop_mode_skips_background_startup(
    tmp_path, monkeypatch
) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        desktop_mode=True,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.automations_scheduler_enabled = True
    config.connector_live_sync_enabled = True

    scheduler_started = {"value": False}

    def _fail_scheduler_start(self) -> None:  # type: ignore[no-untyped-def]
        scheduler_started["value"] = True
        raise AssertionError("automation scheduler should not start in desktop mode")

    class _UnexpectedThread:
        def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
            raise AssertionError("connector live-sync thread should not start in desktop mode")

    monkeypatch.setattr(http_server.AutomationScheduler, "start", _fail_scheduler_start)
    monkeypatch.setattr(http_server.threading, "Thread", _UnexpectedThread)

    app = create_app(config=config)

    with TestClient(app):
        assert app.state.desktop_mode is True
        assert get_automation_scheduler(app) is None

    assert scheduler_started["value"] is False
