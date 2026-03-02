from __future__ import annotations

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from lidltool.auth.agent_keys import AgentKeyAuthError, resolve_user_from_agent_key
from lidltool.auth.user_auth import UserAuthError, create_token, decode_token
from lidltool.auth.users import ensure_service_user
from lidltool.config import AppConfig
from lidltool.db.models import User

SESSION_COOKIE_NAME = "lidltool_session"
SESSION_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def set_session_cookie(response: Response, *, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def _header_api_key(request: Request) -> str | None:
    x_api_key = request.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        return bearer or None
    return None


def _token_secret(config: AppConfig) -> str:
    secret = (config.credential_encryption_key or "").strip()
    if secret:
        return secret
    raise HTTPException(status_code=500, detail="missing token signing secret")


def issue_session_token(*, user: User, config: AppConfig) -> str:
    return create_token(
        user_id=user.user_id,
        username=user.username,
        is_admin=user.is_admin,
        secret=_token_secret(config),
    )


def get_current_user(
    *,
    request: Request,
    session: Session,
    config: AppConfig,
    required: bool = True,
) -> User | None:
    expected_api_key = (config.openclaw_api_key or "").strip()
    presented_api_key = _header_api_key(request)
    if expected_api_key and presented_api_key == expected_api_key:
        return ensure_service_user(session)
    if presented_api_key:
        try:
            return resolve_user_from_agent_key(session, token=presented_api_key)
        except AgentKeyAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        if required:
            raise HTTPException(status_code=401, detail="authentication required")
        return None

    try:
        claims = decode_token(token=token, secret=_token_secret(config))
    except UserAuthError as exc:
        if required:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return None

    user = session.get(User, claims["sub"])
    if user is None:
        if required:
            raise HTTPException(status_code=401, detail="session user not found")
        return None
    return user
