from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from lidltool.api.auth import issue_session_token
from lidltool.api.http_server import create_app
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
        credential_encryption_key="desktop-shared-groups-secret-key-1234567890",
        desktop_mode=True,
        connector_live_sync_enabled=False,
    )
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.document_storage_path.mkdir(parents=True, exist_ok=True)
    return config


def _create_user(app, *, username: str, is_admin: bool = False) -> str:
    with session_scope(app.state.request_context.sessions) as session:
        user = create_local_user(
            session,
            username=username,
            password="test-password",
            display_name=username.title(),
            is_admin=is_admin,
        )
        return user.user_id


def _issue_session(app, *, username: str) -> str:
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


def test_shared_group_lifecycle_and_membership_management(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    anna_id = _create_user(app, username="anna", is_admin=True)
    ben_id = _create_user(app, username="ben")

    with TestClient(app) as client:
        client.cookies.set("lidltool_session", _issue_session(app, username="anna"))

        create_response = client.post(
            "/api/v1/shared-groups",
            json={"name": "Miller Household", "group_type": "household"},
        )
        assert create_response.status_code == 200
        created = create_response.json()["result"]
        group_id = created["group_id"]
        assert created["viewer_role"] == "owner"
        assert created["member_count"] == 1
        assert created["members"][0]["user"]["user_id"] == anna_id

        add_member_response = client.post(
            f"/api/v1/shared-groups/{group_id}/members",
            json={"user_id": ben_id, "role": "manager"},
        )
        assert add_member_response.status_code == 200
        updated = add_member_response.json()["result"]
        assert updated["member_count"] == 2
        ben_membership = next(member for member in updated["members"] if member["user_id"] == ben_id)
        assert ben_membership["role"] == "manager"

        detail_response = client.get(f"/api/v1/shared-groups/{group_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()["result"]
        assert detail["group_type"] == "household"
        assert detail["member_count"] == 2

        archive_response = client.patch(
            f"/api/v1/shared-groups/{group_id}",
            json={"status": "archived"},
        )
        assert archive_response.status_code == 200
        assert archive_response.json()["result"]["status"] == "archived"

        remove_response = client.delete(f"/api/v1/shared-groups/{group_id}/members/{ben_id}")
        assert remove_response.status_code == 200
        remaining = remove_response.json()["result"]
        assert remaining["member_count"] == 1


def test_shared_group_access_requires_membership_and_owner_constraints(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app, username="anna", is_admin=True)
    ben_id = _create_user(app, username="ben")
    _create_user(app, username="cara")

    with TestClient(app) as owner_client:
        owner_client.cookies.set("lidltool_session", _issue_session(app, username="anna"))
        create_response = owner_client.post(
            "/api/v1/shared-groups",
            json={"name": "Flat 4", "group_type": "community"},
        )
        group_id = create_response.json()["result"]["group_id"]
        owner_client.post(
            f"/api/v1/shared-groups/{group_id}/members",
            json={"user_id": ben_id, "role": "manager"},
        )

    with TestClient(app) as outsider_client:
        outsider_client.cookies.set("lidltool_session", _issue_session(app, username="cara"))
        detail_response = outsider_client.get(f"/api/v1/shared-groups/{group_id}")
        assert detail_response.status_code == 400
        assert detail_response.json()["error"] == "shared group not found"

    with TestClient(app) as manager_client:
        manager_client.cookies.set("lidltool_session", _issue_session(app, username="ben"))

        promote_response = manager_client.patch(
            f"/api/v1/shared-groups/{group_id}/members/{ben_id}",
            json={"role": "owner"},
        )
        assert promote_response.status_code == 400
        assert promote_response.json()["error"] == "only owners can assign owner role"

    with TestClient(app) as owner_client:
        owner_client.cookies.set("lidltool_session", _issue_session(app, username="anna"))
        delete_owner_response = owner_client.delete(
            f"/api/v1/shared-groups/{group_id}/members/"
            f"{create_response.json()['result']['members'][0]['user_id']}"
        )
        assert delete_owner_response.status_code == 400
        assert delete_owner_response.json()["error"] == "shared group must keep at least one active owner"


def test_group_scope_requires_active_membership(tmp_path: Path) -> None:
    app = create_app(config=_desktop_config(tmp_path))
    _create_user(app, username="anna", is_admin=True)
    ben_id = _create_user(app, username="ben")
    _create_user(app, username="cara")

    with TestClient(app) as owner_client:
        owner_client.cookies.set("lidltool_session", _issue_session(app, username="anna"))
        create_response = owner_client.post(
            "/api/v1/shared-groups",
            json={"name": "Flat 4", "group_type": "community"},
        )
        assert create_response.status_code == 200
        group_id = create_response.json()["result"]["group_id"]
        add_member_response = owner_client.post(
            f"/api/v1/shared-groups/{group_id}/members",
            json={"user_id": ben_id, "role": "member"},
        )
        assert add_member_response.status_code == 200

    with TestClient(app) as member_client:
        member_client.cookies.set("lidltool_session", _issue_session(app, username="ben"))
        cards_response = member_client.get(
            f"/api/v1/dashboard/cards?year=2026&month=4&scope=group:{group_id}"
        )
        assert cards_response.status_code == 200

    with TestClient(app) as outsider_client:
        outsider_client.cookies.set("lidltool_session", _issue_session(app, username="cara"))
        cards_response = outsider_client.get(
            f"/api/v1/dashboard/cards?year=2026&month=4&scope=group:{group_id}"
        )
        assert cards_response.status_code == 403
        assert cards_response.json()["error"] == "shared group access denied"
