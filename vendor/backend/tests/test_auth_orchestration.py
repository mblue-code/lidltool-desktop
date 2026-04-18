from __future__ import annotations

from pathlib import Path

from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService
from lidltool.connectors.registry import ConnectorRegistry


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


def test_start_bootstrap_falls_back_to_immediate_plugin_bootstrap(tmp_path: Path) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "plugin_id": "local.netto_plus_de",
        "plugin_version": "0.1.0",
        "connector_api_version": "1",
        "plugin_family": "receipt",
        "source_id": "netto_plus_de",
        "display_name": "Netto Plus",
        "merchant_name": "Netto Plus",
        "country_code": "DE",
        "maintainer": "lidltool",
        "license": "MIT",
        "runtime_kind": "subprocess_python",
        "entrypoint": "plugin.py:NettoPlusReceiptPlugin",
        "auth_kind": "file_import",
        "auth": {
            "auth_kind": "file_import",
            "supports_live_session_bootstrap": False,
            "supports_reauth": True,
            "supports_headless_refresh": False,
            "supports_manual_confirm": False,
            "supports_oauth_callback": False,
            "supports_session_file": False,
            "implemented_actions": ["start_auth", "cancel_auth", "confirm_auth"],
            "compatibility_actions": [],
            "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
        },
        "capabilities": ["healthcheck", "historical_sync", "incremental_sync"],
        "trust_class": "local_custom",
        "plugin_origin": "local_path",
        "install_status": "installed",
        "compatibility": {
            "min_core_version": "0.1.0",
            "supported_host_kinds": ["self_hosted", "electron"],
        },
    }

    process_called = False

    def _fake_process_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal process_called
        process_called = True
        raise AssertionError("immediate plugin bootstrap should not spawn a subprocess session")

    class _FakeConnector:
        def start_auth(self) -> dict[str, object]:
            return {
                "status": "confirmed",
                "detail": "Imported Netto Plus session bundle into plugin-local state.",
                "metadata": {"receipt_count": 1},
            }

        def get_auth_status(self) -> dict[str, object]:
            return {
                "status": "authenticated",
                "is_authenticated": True,
                "available_actions": ["start_auth"],
                "implemented_actions": ["start_auth", "cancel_auth", "confirm_auth"],
                "compatibility_actions": [],
                "reserved_actions": ["start_auth", "cancel_auth", "confirm_auth"],
                "detail": "Netto Plus session bundle is stored locally.",
                "metadata": {"receipt_count": 1},
            }

    class _ResolvedConnector:
        def __init__(self) -> None:
            self.connector = _FakeConnector()

    service = ConnectorAuthOrchestrationService(
        config=config,
        registry=ConnectorRegistry.from_definitions([manifest]),
        connector_builder=lambda **_: _ResolvedConnector(),
        process_factory=_fake_process_factory,
    )

    result = service.start_bootstrap(
        source_id="netto_plus_de",
        connector_options={"session_bundle_file": str(tmp_path / "netto-session-bundle.json")},
    )

    assert result.ok is True
    assert result.status == "confirmed"
    assert result.state == "connected"
    assert result.bootstrap is not None
    assert result.bootstrap.state == "succeeded"
    assert result.bootstrap.return_code == 0
    assert process_called is False
