from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lidltool.auth.user_auth import SESSION_TTL
from lidltool.db.models import User, UserSession

SESSION_TOUCH_INTERVAL = timedelta(seconds=60)
SESSION_MODE_COOKIE = "cookie"
SESSION_MODE_TOKEN = "token"
SESSION_MODE_BOTH = "both"
VALID_SESSION_MODES = {SESSION_MODE_COOKIE, SESSION_MODE_TOKEN, SESSION_MODE_BOTH}


class UserSessionAuthError(RuntimeError):
    """Raised when request session state is invalid."""


@dataclass(frozen=True, slots=True)
class SessionClientMetadata:
    auth_transport: str
    device_label: str | None = None
    client_name: str | None = None
    client_platform: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_optional_text(value: str | None, *, max_length: int = 120) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    if not normalized:
        return None
    return normalized[:max_length]


def _normalize_auth_transport(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in VALID_SESSION_MODES:
        raise RuntimeError("session_mode must be one of: cookie, token, both")
    return normalized


def available_auth_transports(session_mode: str) -> list[str]:
    normalized = _normalize_auth_transport(session_mode)
    if normalized == SESSION_MODE_COOKIE:
        return ["cookie"]
    if normalized == SESSION_MODE_TOKEN:
        return ["bearer"]
    return ["cookie", "bearer"]


def _derived_device_label(metadata: SessionClientMetadata) -> str | None:
    explicit = _normalize_optional_text(metadata.device_label, max_length=80)
    if explicit is not None:
        return explicit
    if metadata.client_name and metadata.client_platform:
        return f"{_normalize_optional_text(metadata.client_name, max_length=40)} on {_normalize_optional_text(metadata.client_platform, max_length=30)}"
    if metadata.client_name:
        return _normalize_optional_text(metadata.client_name, max_length=80)
    if metadata.client_platform:
        return _normalize_optional_text(metadata.client_platform, max_length=80)
    user_agent = _normalize_optional_text(metadata.user_agent, max_length=80)
    return user_agent


def create_user_session(
    session: Session,
    *,
    user: User,
    metadata: SessionClientMetadata,
    expires_in: timedelta = SESSION_TTL,
) -> UserSession:
    now = _utcnow()
    record = UserSession(
        user_id=user.user_id,
        device_label=_derived_device_label(metadata),
        client_name=_normalize_optional_text(metadata.client_name, max_length=80),
        client_platform=_normalize_optional_text(metadata.client_platform, max_length=40),
        auth_transport=_normalize_auth_transport(metadata.auth_transport),
        user_agent=_normalize_optional_text(metadata.user_agent, max_length=400),
        last_seen_ip=_normalize_optional_text(metadata.ip_address, max_length=64),
        created_at=now,
        last_seen_at=now,
        expires_at=now + expires_in,
    )
    session.add(record)
    session.flush()
    return record


def require_active_user_session(
    session: Session,
    *,
    user_id: str,
    session_id: str,
) -> UserSession:
    record = session.get(UserSession, session_id)
    if record is None or record.user_id != user_id:
        raise UserSessionAuthError("session not found")
    if record.revoked_at is not None:
        raise UserSessionAuthError("session revoked")
    if _as_utc(record.expires_at) <= _utcnow():
        raise UserSessionAuthError("session expired")
    return record


def touch_user_session(
    session: Session,
    *,
    record: UserSession,
    ip_address: str | None,
    user_agent: str | None,
) -> UserSession:
    now = _utcnow()
    if _as_utc(record.last_seen_at) >= now - SESSION_TOUCH_INTERVAL:
        return record
    record.last_seen_at = now
    normalized_ip = _normalize_optional_text(ip_address, max_length=64)
    normalized_agent = _normalize_optional_text(user_agent, max_length=400)
    if normalized_ip is not None:
        record.last_seen_ip = normalized_ip
    if normalized_agent is not None:
        record.user_agent = normalized_agent
    session.flush()
    return record


def revoke_user_session(
    session: Session,
    *,
    record: UserSession,
    reason: str,
) -> UserSession:
    if record.revoked_at is None:
        record.revoked_at = _utcnow()
        record.revoked_reason = _normalize_optional_text(reason, max_length=120)
        session.flush()
    return record


def revoke_user_sessions_for_user(
    session: Session,
    *,
    user_id: str,
    reason: str,
    exclude_session_id: str | None = None,
) -> int:
    values = {
        "revoked_at": _utcnow(),
        "revoked_reason": _normalize_optional_text(reason, max_length=120),
    }
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(**values)
    )
    if exclude_session_id is not None:
        stmt = stmt.where(UserSession.session_id != exclude_session_id)
    result = session.execute(stmt)
    session.flush()
    return int(cast(Any, result).rowcount or 0)


def list_active_user_sessions(session: Session, *, user_id: str) -> list[UserSession]:
    return list(
        session.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id)
            .order_by(UserSession.last_seen_at.desc(), UserSession.created_at.desc())
        )
        .scalars()
        .all()
    )


def serialize_user_session(
    record: UserSession,
    *,
    current: bool = False,
) -> dict[str, object]:
    return {
        "session_id": record.session_id,
        "user_id": record.user_id,
        "device_label": record.device_label,
        "client_name": record.client_name,
        "client_platform": record.client_platform,
        "auth_transport": record.auth_transport,
        "session_mode": record.auth_transport,
        "available_auth_transports": available_auth_transports(record.auth_transport),
        "user_agent": record.user_agent,
        "last_seen_ip": record.last_seen_ip,
        "created_at": _as_utc(record.created_at).isoformat(),
        "last_seen_at": _as_utc(record.last_seen_at).isoformat(),
        "expires_at": _as_utc(record.expires_at).isoformat(),
        "revoked_at": _as_utc(record.revoked_at).isoformat() if record.revoked_at is not None else None,
        "revoked_reason": record.revoked_reason,
        "current": current,
    }
