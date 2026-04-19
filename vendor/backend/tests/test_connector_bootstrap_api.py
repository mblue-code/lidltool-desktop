from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from lidltool.api import http_server
from lidltool.api.auth import issue_session_token
from lidltool.api.http_server import create_app
from lidltool.api.http_state import get_connector_command_sessions
from lidltool.auth.sessions import SESSION_MODE_COOKIE, SessionClientMetadata, create_user_session
from lidltool.auth.users import create_local_user
from lidltool.config import AppConfig
from lidltool.connectors.auth.auth_status import AuthBootstrapSnapshot
from lidltool.connectors.manifest import ConnectorManifest
from lidltool.connectors.release_policy import release_policy_payload
from lidltool.db.engine import session_scope


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


def _preview_test_manifest(*, source_id: str, maturity: str) -> SimpleNamespace:
    return SimpleNamespace(source_id=source_id, metadata={"maturity": maturity})


def test_start_connector_bootstrap_resolves_runtime_options(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
        captured: dict[str, object] = {}

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=SimpleNamespace(source_id=source_id))

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                captured["connector_options"] = dict(connector_options or {})
                bootstrap_sessions[source_id] = object()
                return SimpleNamespace(status="started", bootstrap=object())

        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "amazon_de",
                "status": "running",
                "command": "python -m lidltool.cli connectors auth bootstrap --source-id amazon_de",
                "pid": 1234,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/amazon_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["source_id"] == "amazon_de"
    assert payload["result"]["reused"] is False
    assert payload["result"]["bootstrap"]["status"] == "running"
    assert captured["connector_options"] == {
        "years": 1,
        "headless": True,
    }


def test_start_connector_bootstrap_prefers_local_browser_for_loopback_requests(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
        captured: dict[str, object] = {}

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=SimpleNamespace(source_id=source_id))

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                captured["env"] = env
                captured["connector_options"] = dict(connector_options or {})
                bootstrap_sessions[source_id] = object()
                return SimpleNamespace(status="started", bootstrap=object())

        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "amazon_de",
                "status": "running",
                "command": "python -m lidltool.cli connectors auth bootstrap --source-id amazon_de",
                "pid": 1234,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )
        monkeypatch.setattr(
            http_server,
            "_ensure_vnc_runtime",
            lambda app: (_ for _ in ()).throw(AssertionError("loopback requests should not start VNC")),
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/amazon_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["source_id"] == "amazon_de"
    assert payload["result"]["remote_login_url"] is None
    assert captured["env"] is None


def test_kaufland_manifest_is_not_classified_as_preview() -> None:
    manifest_path = Path(__file__).resolve().parents[5] / "plugins" / "kaufland_de" / "manifest.json"
    manifest = ConnectorManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    release = release_policy_payload(source_id=manifest.source_id, manifest=manifest)

    assert release["maturity"] == "working"
    assert release["label"] == "Working"


def test_start_connector_bootstrap_omits_preview_warning_for_working_kaufland(
    tmp_path, monkeypatch
) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
        manifest = _preview_test_manifest(source_id="kaufland_de", maturity="working")

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=manifest)

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                bootstrap_sessions[source_id] = object()
                return SimpleNamespace(status="started", bootstrap=object())

        monkeypatch.setattr(http_server, "assert_connector_operation_allowed", lambda *args, **kwargs: None)
        monkeypatch.setattr(http_server, "is_loopback_request", lambda request: True)
        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "kaufland_de",
                "status": "running",
                "command": "python -m lidltool.cli connectors auth bootstrap --source-id kaufland_de",
                "pid": 1234,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/kaufland_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["warnings"] == []
    assert payload["warning_details"] == []


def test_start_connector_bootstrap_keeps_preview_warning_for_preview_connectors(
    tmp_path, monkeypatch
) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        bootstrap_sessions = get_connector_command_sessions(app, kind="bootstrap")
        manifest = _preview_test_manifest(source_id="preview_fixture_de", maturity="preview")

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=manifest)

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                bootstrap_sessions[source_id] = object()
                return SimpleNamespace(status="started", bootstrap=object())

        monkeypatch.setattr(http_server, "assert_connector_operation_allowed", lambda *args, **kwargs: None)
        monkeypatch.setattr(http_server, "is_loopback_request", lambda request: True)
        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "preview_fixture_de",
                "status": "running",
                "command": "python -m lidltool.cli connectors auth bootstrap --source-id preview_fixture_de",
                "pid": 1234,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/preview_fixture_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["warning_details"] == [
        {
            "message": "preview connector bootstrap started; this connector is not live-validated yet",
            "code": "connector_preview_bootstrap_started",
        }
    ]
    assert payload["warnings"] == [
        "preview connector bootstrap started; this connector is not live-validated yet"
    ]


def test_start_connector_bootstrap_accepts_immediate_plugin_bootstrap_without_session(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=SimpleNamespace(source_id=source_id))

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                return SimpleNamespace(
                    status="confirmed",
                    bootstrap=AuthBootstrapSnapshot(
                        source_id=source_id,
                        state="succeeded",
                        command=None,
                        pid=None,
                        started_at=None,
                        finished_at=None,
                        return_code=0,
                        output_tail=("Imported Netto Plus session bundle into plugin-local state.",),
                        can_cancel=False,
                    ),
                )

        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/amazon_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["source_id"] == "amazon_de"
    assert payload["result"]["reused"] is False
    assert payload["result"]["bootstrap"]["status"] == "succeeded"
    assert payload["result"]["bootstrap"]["return_code"] == 0
    assert payload["result"]["bootstrap"]["output_tail"] == [
        "Imported Netto Plus session bundle into plugin-local state."
    ]


def test_start_connector_bootstrap_returns_immediate_plugin_result_without_session(
    tmp_path, monkeypatch
) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                return SimpleNamespace(manifest=SimpleNamespace(source_id=source_id))

            def start_bootstrap(
                self,
                *,
                source_id: str,
                env=None,
                connector_options=None,
                extra_args=(),
            ):
                return SimpleNamespace(
                    source_id=source_id,
                    state="connected",
                    status="confirmed",
                    ok=True,
                    detail="plugin bootstrap completed",
                    bootstrap=None,
                )

        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        client.cookies.set("lidltool_session", token)
        response = client.post("/api/v1/connectors/amazon_de/bootstrap/start")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["source_id"] == "amazon_de"
    assert payload["result"]["reused"] is False
    assert payload["result"]["bootstrap"]["status"] == "succeeded"
    assert payload["result"]["bootstrap"]["command"] is None
    assert payload["result"]["bootstrap"]["return_code"] == 0


def test_start_connector_sync_includes_saved_connector_options(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)
        client.cookies.set("lidltool_session", token)

        config_response = client.post(
            "/api/v1/connectors/amazon_de/config",
            json={
                "values": {
                    "years": 1,
                    "headless": False,
                    "dump_html": str(tmp_path / "amazon-debug"),
                }
            },
        )
        assert config_response.status_code == 200

        captured: dict[str, object] = {}

        def fake_start_connector_command_session(*args, **kwargs):
            captured["command"] = list(kwargs["command"])
            return object()

        monkeypatch.setattr(
            http_server,
            "_start_connector_command_session",
            fake_start_connector_command_session,
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "amazon_de",
                "status": "running",
                "command": " ".join(captured["command"]),
                "pid": 4321,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        response = client.post("/api/v1/connectors/amazon_de/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    command = captured["command"]
    assert "--option" in command
    joined = " ".join(command)
    assert "years=1" in joined
    assert "headless=false" in joined
    assert f"dump_html={tmp_path / 'amazon-debug'}" in joined
    assert "owner_user_id=" in joined


def test_start_connector_full_sync_uses_wide_amazon_default_when_no_saved_years(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)
        client.cookies.set("lidltool_session", token)

        captured: dict[str, object] = {}

        def fake_start_connector_command_session(*args, **kwargs):
            captured["command"] = list(kwargs["command"])
            return object()

        monkeypatch.setattr(
            http_server,
            "_start_connector_command_session",
            fake_start_connector_command_session,
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "amazon_de",
                "status": "running",
                "command": " ".join(captured["command"]),
                "pid": 4321,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        response = client.post("/api/v1/connectors/amazon_de/sync?full=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    joined = " ".join(captured["command"])
    assert "years=10" in joined
    assert "headless=false" in joined


def test_start_connector_full_sync_overrides_stale_single_year_setting(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)
        client.cookies.set("lidltool_session", token)

        config_response = client.post(
            "/api/v1/connectors/amazon_de/config",
            json={
                "values": {
                    "years": 1,
                    "headless": False,
                }
            },
        )
        assert config_response.status_code == 200

        captured: dict[str, object] = {}

        def fake_start_connector_command_session(*args, **kwargs):
            captured["command"] = list(kwargs["command"])
            return object()

        monkeypatch.setattr(
            http_server,
            "_start_connector_command_session",
            fake_start_connector_command_session,
        )
        monkeypatch.setattr(
            http_server,
            "_serialize_connector_bootstrap",
            lambda _session: {
                "source_id": "amazon_de",
                "status": "running",
                "command": " ".join(captured["command"]),
                "pid": 4321,
                "started_at": None,
                "finished_at": None,
                "return_code": None,
                "output_tail": [],
                "can_cancel": True,
            },
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        response = client.post("/api/v1/connectors/amazon_de/sync?full=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    joined = " ".join(captured["command"])
    assert "years=10" in joined
    assert "headless=false" in joined


def test_get_connector_auth_status_validates_session(tmp_path, monkeypatch) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        credential_encryption_key="test-secret-key-with-sufficient-entropy-123456",
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(config=config)

    with TestClient(app) as client:
        token = _issue_admin_session(app)
        client.cookies.set("lidltool_session", token)

        captured: dict[str, object] = {}

        class FakeService:
            def get_auth_status(self, *, source_id: str, validate_session: bool = True):
                captured["validate_session"] = validate_session
                return SimpleNamespace(
                    source_id=source_id,
                    state="reauth_required",
                    detail="saved browser session expired",
                    available_actions=("start_auth", "cancel_auth"),
                )

        monkeypatch.setattr(
            http_server,
            "_connector_auth_service",
            lambda app, config: FakeService(),
        )
        monkeypatch.setattr(
            http_server,
            "_connector_is_preview_source",
            lambda *args, **kwargs: False,
        )

        response = client.get("/api/v1/connectors/amazon_de/auth/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["source_id"] == "amazon_de"
    assert payload["result"]["state"] == "reauth_required"
    assert payload["result"]["detail"] == "saved browser session expired"
    assert payload["result"]["available_actions"] == ["start_auth", "cancel_auth"]
    assert captured["validate_session"] is True
