from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from lidltool.api.auth import SESSION_COOKIE_NAME, issue_session_token
from lidltool.api.http_server import create_app
from lidltool.auth.sessions import (
    SESSION_MODE_COOKIE,
    SessionClientMetadata,
    create_user_session,
)
from lidltool.auth.users import create_local_user, get_user_by_username
from lidltool.config import AppConfig
from lidltool.db.engine import session_scope
from lidltool.db.models import MobilePairedDevice, MobilePairingSession
from lidltool.mobile.pairing import token_hash


def _desktop_config(tmp_path: Path) -> AppConfig:
    config = AppConfig(
        db_path=tmp_path / "lidltool.sqlite",
        config_dir=tmp_path / "config",
        document_storage_path=tmp_path / "documents",
        credential_encryption_key="desktop-mobile-pairing-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def _create_user(app: Any, *, username: str = "anna") -> str:
    with session_scope(app.state.request_context.sessions) as session:
        user = create_local_user(
            session,
            username=username,
            password="test-password",
            display_name=username.title(),
            is_admin=True,
        )
        return user.user_id


def _issue_session(app: Any, *, username: str = "anna") -> str:
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


def _create_pairing_payload(
    client: TestClient,
    *,
    endpoint_url: str = "http://192.168.1.42:18766",
) -> dict[str, Any]:
    response = client.post(
        "/api/mobile-pair/v1/sessions",
        json={
            "bridge_endpoint_url": endpoint_url,
            "expires_in_seconds": 60,
            "transport": "lan_http",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    return body["result"]


def _handshake(
    client: TestClient,
    *,
    pairing_token: str,
    device_id: str = "phone-device-1",
) -> Any:
    return client.post(
        "/api/mobile-pair/v1/handshake",
        json={
            "device_id": device_id,
            "device_name": "Test Phone",
            "platform": "ios",
            "pairing_token": pairing_token,
            "public_key_fingerprint": "phone-fingerprint",
        },
    )


def test_mobile_pairing_qr_uses_bridge_endpoint_and_hashes_pairing_token(
    tmp_path: Path,
) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        result = _create_pairing_payload(client)

    qr_payload = result["qr_payload"]
    pairing_token = qr_payload["pairing_token"]
    assert qr_payload["protocol_version"] == 1
    assert qr_payload["endpoint_url"] == "http://192.168.1.42:18766"
    assert qr_payload["transport"] == "lan_http"
    assert qr_payload["listener_expires_at"] == qr_payload["expires_at"]
    assert set(qr_payload) >= {
        "protocol_version",
        "desktop_id",
        "desktop_name",
        "endpoint_url",
        "pairing_token",
        "public_key_fingerprint",
        "expires_at",
        "transport",
        "listener_expires_at",
    }

    with session_scope(app.state.request_context.sessions) as session:
        record = session.get(MobilePairingSession, result["session_id"])
        assert record is not None
        assert record.endpoint_url == "http://192.168.1.42:18766"
        assert record.pairing_token_hash == token_hash(pairing_token)
        assert record.pairing_token_hash != pairing_token


def test_expired_pairing_token_fails(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        result = _create_pairing_payload(client)
        pairing_token = result["qr_payload"]["pairing_token"]

        with session_scope(app.state.request_context.sessions) as session:
            record = session.get(MobilePairingSession, result["session_id"])
            assert record is not None
            record.expires_at = datetime.now(tz=UTC) - timedelta(seconds=1)

        response = _handshake(client, pairing_token=pairing_token)
        assert response.status_code == 400
        body = response.json()
        assert body["ok"] is False
        assert body["error"] == "invalid or expired pairing token"


def test_reused_pairing_token_fails(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        result = _create_pairing_payload(client)
        pairing_token = result["qr_payload"]["pairing_token"]

        first_response = _handshake(client, pairing_token=pairing_token)
        assert first_response.status_code == 200
        assert first_response.json()["ok"] is True

        reused_response = _handshake(
            client,
            pairing_token=pairing_token,
            device_id="phone-device-2",
        )
        assert reused_response.status_code == 400
        body = reused_response.json()
        assert body["ok"] is False
        assert body["error"] == "invalid or expired pairing token"


def test_valid_pairing_through_bridge_returns_endpoint_and_can_sync(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        result = _create_pairing_payload(client, endpoint_url="http://10.0.0.8:19001")

        response = _handshake(client, pairing_token=result["qr_payload"]["pairing_token"])
        assert response.status_code == 200
        handshake = response.json()["result"]
        assert handshake["endpoint_url"] == "http://10.0.0.8:19001"
        assert handshake["protocol_version"] == 1
        assert handshake["device_id"] == "phone-device-1"
        assert handshake["transport"] == "lan_http"
        assert isinstance(handshake["sync_token"], str)
        assert handshake["sync_token"]

        with session_scope(app.state.request_context.sessions) as session:
            paired = session.execute(
                select(MobilePairedDevice).where(
                    MobilePairedDevice.device_id == handshake["device_id"]
                )
            ).scalar_one()
            assert paired.sync_token_hash == token_hash(handshake["sync_token"])
            assert paired.sync_token_hash != handshake["sync_token"]

        sync_response = client.get(
            "/api/mobile-sync/v1/changes",
            headers={"Authorization": f"Bearer {handshake['sync_token']}"},
        )
        assert sync_response.status_code == 200
        sync_body = sync_response.json()
        assert sync_body["ok"] is True
        assert sync_body["result"]["protocol_version"] == 1


def test_invalid_or_revoked_sync_token_cannot_sync(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app)

    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE_NAME, _issue_session(app))
        result = _create_pairing_payload(client)
        response = _handshake(client, pairing_token=result["qr_payload"]["pairing_token"])
        assert response.status_code == 200
        sync_token = response.json()["result"]["sync_token"]

        invalid_response = client.get(
            "/api/mobile-sync/v1/changes",
            headers={"Authorization": "Bearer definitely-not-valid"},
        )
        assert invalid_response.status_code == 401
        assert invalid_response.json()["error"] == "invalid mobile sync token"

        with session_scope(app.state.request_context.sessions) as session:
            paired = session.execute(
                select(MobilePairedDevice).where(
                    MobilePairedDevice.sync_token_hash == token_hash(sync_token)
                )
            ).scalar_one()
            paired.revoked_at = datetime.now(tz=UTC)

        revoked_response = client.get(
            "/api/mobile-sync/v1/changes",
            headers={"Authorization": f"Bearer {sync_token}"},
        )
        assert revoked_response.status_code == 401
        assert revoked_response.json()["error"] == "invalid mobile sync token"
