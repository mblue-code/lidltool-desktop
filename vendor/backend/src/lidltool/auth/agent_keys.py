from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import User, UserApiKey

API_KEY_PREFIX = "ltk_"
DISPLAY_PREFIX_LENGTH = 16


class AgentKeyAuthError(RuntimeError):
    pass


def _to_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def hash_agent_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_user_agent_key(
    session: Session,
    *,
    user_id: str,
    label: str,
    expires_at: datetime | None = None,
) -> tuple[UserApiKey, str]:
    normalized_label = label.strip()
    if not normalized_label:
        raise RuntimeError("label must not be empty")
    if expires_at is not None:
        expires_at = _to_utc_datetime(expires_at)
        if expires_at <= datetime.now(tz=UTC):
            raise RuntimeError("expires_at must be in the future")

    # Retry on extremely unlikely token hash collisions.
    for _ in range(5):
        plain_token = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        key_hash = hash_agent_key(plain_token)
        prefix = plain_token[:DISPLAY_PREFIX_LENGTH]
        existing = (
            session.execute(select(UserApiKey.key_id).where(UserApiKey.key_hash == key_hash).limit(1))
            .scalar_one_or_none()
        )
        if existing is not None:
            continue
        key = UserApiKey(
            user_id=user_id,
            label=normalized_label,
            key_prefix=prefix,
            key_hash=key_hash,
            is_active=True,
            last_used_at=None,
            expires_at=expires_at,
            created_at=datetime.now(tz=UTC),
        )
        session.add(key)
        session.flush()
        return key, plain_token
    raise RuntimeError("failed to generate unique API key")


def resolve_user_from_agent_key(session: Session, *, token: str) -> User:
    if not token.strip():
        raise AgentKeyAuthError("invalid API key")
    key_hash = hash_agent_key(token.strip())
    key = session.execute(select(UserApiKey).where(UserApiKey.key_hash == key_hash).limit(1)).scalar_one_or_none()
    if key is None:
        raise AgentKeyAuthError("invalid API key")
    if not key.is_active:
        raise AgentKeyAuthError("API key inactive")
    if key.expires_at is not None and _to_utc_datetime(key.expires_at) <= datetime.now(tz=UTC):
        raise AgentKeyAuthError("API key expired")
    key.last_used_at = datetime.now(tz=UTC)
    session.flush()
    return key.user
