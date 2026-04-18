from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.auth.auth_status import AuthActionResult


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 12345
        self.stdout = iter(())
        self.returncode = 0

    def poll(self) -> int:
        return 0

    def wait(self) -> int:
        return 0


def test_browser_session_bootstrap_filters_sync_only_options(tmp_path: Path) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)

    captured: dict[str, object] = {}

    def _fake_process_factory(command, **kwargs):  # type: ignore[no-untyped-def]
        captured["command"] = list(command)
        captured["kwargs"] = kwargs
        return _FakeProcess()

    service = ConnectorAuthOrchestrationService(
        config=config,
        repo_root=Path("/Users/max/projekte/lidltool/apps/desktop/vendor/backend"),
        process_factory=_fake_process_factory,
    )

    result = service.start_bootstrap(
        source_id="amazon_de",
        connector_options={
            "years": 8,
            "headless": True,
            "dump_html": str(tmp_path / "amazon-debug"),
        },
    )

    assert result.ok is True
    command = captured["command"]
    assert "--option" in command
    joined = " ".join(command)
    assert f"dump_html={tmp_path / 'amazon-debug'}" in joined
    assert "years=8" not in joined
    assert "headless=true" not in joined


def test_plugin_bootstrap_falls_back_when_no_command_bridge(tmp_path: Path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)

    service = ConnectorAuthOrchestrationService(
        config=config,
        repo_root=Path("/Users/max/projekte/lidltool/apps/desktop/vendor/backend"),
    )
    manifest = SimpleNamespace(
        plugin_family="receipt",
        runtime_kind="subprocess_python",
        source_id="rossmann_de",
        auth=SimpleNamespace(auth_kind="manual_only"),
    )
    expected = AuthActionResult(
        manifest=manifest,
        source_id="rossmann_de",
        state="connected",
        status="confirmed",
        ok=True,
        detail="plugin bootstrap completed",
    )

    monkeypatch.setattr(service._registry, "require_manifest", lambda _source_id: manifest)
    monkeypatch.setattr(
        ConnectorAuthOrchestrationService,
        "_build_bootstrap_command",
        lambda self, *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        ConnectorAuthOrchestrationService,
        "_run_plugin_bootstrap",
        lambda self, **kwargs: expected,
    )

    result = service.start_bootstrap(
        source_id="rossmann_de",
        connector_options={"email": "user@example.com"},
    )

    assert result is expected
