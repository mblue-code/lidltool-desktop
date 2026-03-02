from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lidltool.auth.user_auth import hash_password
from lidltool.db.models import User

SERVICE_USER_ID = "00000000-0000-0000-0000-000000000000"
SERVICE_USERNAME = "_service"


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not normalized:
        raise RuntimeError("username must not be empty")
    if " " in normalized:
        raise RuntimeError("username must not contain spaces")
    return normalized


def get_user_by_username(session: Session, *, username: str) -> User | None:
    normalized = normalize_username(username)
    return session.execute(select(User).where(User.username == normalized).limit(1)).scalar_one_or_none()


def ensure_service_user(session: Session) -> User:
    existing = session.get(User, SERVICE_USER_ID)
    if existing is not None:
        return existing
    existing = get_user_by_username(session, username=SERVICE_USERNAME)
    if existing is not None:
        return existing
    service_user = User(
        user_id=SERVICE_USER_ID,
        username=SERVICE_USERNAME,
        display_name="Service account",
        password_hash="!",
        is_admin=True,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    try:
        session.add(service_user)
        session.flush()
        return service_user
    except IntegrityError:
        session.rollback()
        by_id = session.get(User, SERVICE_USER_ID)
        if by_id is not None:
            return by_id
        by_name = get_user_by_username(session, username=SERVICE_USERNAME)
        if by_name is not None:
            return by_name
        raise


def human_user_count(session: Session) -> int:
    stmt = select(func.count(User.user_id)).where(User.username != SERVICE_USERNAME)
    return int(session.execute(stmt).scalar_one() or 0)


def create_local_user(
    session: Session,
    *,
    username: str,
    password: str,
    display_name: str | None,
    is_admin: bool,
) -> User:
    normalized = normalize_username(username)
    existing = get_user_by_username(session, username=normalized)
    if existing is not None:
        raise RuntimeError("username already exists")
    user = User(
        username=normalized,
        display_name=(display_name.strip() if display_name else None) or None,
        password_hash=hash_password(password),
        is_admin=is_admin,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    session.add(user)
    session.flush()
    return user


def set_user_password(session: Session, *, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    user.updated_at = datetime.now(tz=UTC)
    session.flush()
