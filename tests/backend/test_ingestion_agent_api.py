from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from lidltool.api.auth import SESSION_COOKIE_NAME, issue_session_token
from lidltool.api.http_server import DEFAULT_CHATGPT_CHAT_MODEL, _configured_oauth_chat_model, create_app
from lidltool.auth.sessions import (
    SESSION_MODE_COOKIE,
    SessionClientMetadata,
    create_user_session,
)
from lidltool.auth.users import create_local_user, get_user_by_username
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope


def _desktop_config(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-ingestion-api-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def _create_user(app: Any, *, username: str = "ingestion-api-admin") -> str:
    with session_scope(app.state.request_context.sessions) as session:
        user = create_local_user(
            session,
            username=username,
            password="test-password",
            display_name="Ingestion API Admin",
            is_admin=True,
        )
        return user.user_id


def _issue_session(app: Any, *, username: str = "ingestion-api-admin") -> str:
    with session_scope(app.state.request_context.sessions) as session:
        user = get_user_by_username(session, username=username)
        assert user is not None
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
            config=app.state.request_context.config,
        )


def test_authenticated_ingestion_message_route_creates_review_proposal(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        session_response = client.post(
            "/api/v1/ingestion/sessions",
            json={
                "title": "Manual text intake",
                "input_kind": "free_text",
                "approval_mode": "review_first",
            },
        )
        assert session_response.status_code == 200
        session_payload = session_response.json()
        assert session_payload["ok"] is True
        session_id = session_payload["result"]["id"]

        message_response = client.post(
            f"/api/v1/ingestion/sessions/{session_id}/message",
            json={"message": "I paid 25 euros cash at the ice cream store today."},
        )

    assert message_response.status_code == 200
    payload = message_response.json()
    assert payload["ok"] is True
    proposal = payload["result"]["proposals"][0]
    assert proposal["type"] == "create_transaction"
    assert proposal["status"] == "pending_review"
    assert proposal["payload_json"]["total_gross_cents"] == 2500


def test_codex_oauth_defaults_to_mini_model(tmp_path: Path) -> None:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        ai_oauth_provider="openai-codex",
        ai_oauth_model="gpt-5.4",
    )

    assert DEFAULT_CHATGPT_CHAT_MODEL == "gpt-5.4-mini"
    assert _configured_oauth_chat_model(config) == "gpt-5.4-mini"
