from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import cast

from fastapi import HTTPException, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from starlette.requests import HTTPConnection

from lidltool.auth.agent_keys import AgentKeyAuthError, resolve_user_from_agent_key
from lidltool.auth.sessions import (
    UserSessionAuthError,
    require_active_user_session,
    touch_user_session,
)
from lidltool.auth.user_auth import UserAuthError, create_token, decode_token
from lidltool.auth.users import ensure_human_users_are_admin, ensure_service_user, human_user_count
from lidltool.config import AppConfig
from lidltool.db.models import User, UserSession

SESSION_COOKIE_NAME = "lidltool_session"
SESSION_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
SESSION_COOKIE_SAME_SITE = "lax"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthenticatedSessionContext:
    user: User
    session_record: UserSession | None = None
    auth_transport: str = "cookie"


def _connection_client_host(connection: HTTPConnection) -> str | None:
    if connection.client is None or not connection.client.host:
        return None
    return connection.client.host


def _host_in_cidrs(host: str | None, cidrs: list[str]) -> bool:
    if not host or not cidrs:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs)


def is_loopback_request(connection: HTTPConnection) -> bool:
    host = _connection_client_host(connection)
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.strip().lower() == "localhost"


def _forwarded_proto(connection: HTTPConnection, config: AppConfig) -> str | None:
    if not _host_in_cidrs(_connection_client_host(connection), config.http_trusted_proxy_cidrs):
        return None

    forwarded = (connection.headers.get("forwarded") or "").strip()
    if forwarded:
        first_hop = forwarded.split(",", 1)[0]
        for part in first_hop.split(";"):
            name, _, value = part.partition("=")
            if name.strip().lower() != "proto":
                continue
            proto = value.strip().strip('"').lower()
            if proto in {"http", "https"}:
                return proto

    x_forwarded_proto = (connection.headers.get("x-forwarded-proto") or "").strip().lower()
    if x_forwarded_proto:
        proto = x_forwarded_proto.split(",", 1)[0].strip()
        if proto in {"http", "https"}:
            return proto
    return None


def request_scheme(connection: HTTPConnection, config: AppConfig) -> str:
    forwarded_proto = _forwarded_proto(connection, config)
    if forwarded_proto is not None:
        return forwarded_proto
    return str(connection.scope.get("scheme") or connection.url.scheme or "http").lower()


def should_secure_session_cookie(connection: HTTPConnection, config: AppConfig) -> bool:
    return request_scheme(connection, config) == "https"


def is_session_transport(context: AuthenticatedSessionContext) -> bool:
    return context.session_record is not None


def is_service_api_key_transport(context: AuthenticatedSessionContext) -> bool:
    return context.auth_transport == "service_api_key"


def set_session_cookie(
    response: Response,
    *,
    token: str,
    request: HTTPConnection,
    config: AppConfig,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=SESSION_COOKIE_SAME_SITE,
        max_age=SESSION_COOKIE_MAX_AGE_SECONDS,
        path="/",
        secure=should_secure_session_cookie(request, config),
    )


def clear_session_cookie(
    response: Response,
    *,
    request: HTTPConnection,
    config: AppConfig,
) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite=SESSION_COOKIE_SAME_SITE,
        secure=should_secure_session_cookie(request, config),
    )


def _header_api_key(connection: HTTPConnection) -> str | None:
    x_api_key = connection.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()
    authorization = connection.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        return bearer or None
    return None


def _token_secret(config: AppConfig) -> str:
    secret = (config.credential_encryption_key or "").strip()
    if secret:
        return secret
    raise HTTPException(status_code=500, detail="missing token signing secret")


def _header_bearer_token(connection: HTTPConnection) -> str | None:
    authorization = connection.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
        return bearer or None
    return None


def _header_api_key_value(connection: HTTPConnection) -> str | None:
    x_api_key = connection.headers.get("x-api-key")
    if x_api_key:
        return x_api_key.strip()
    return None


def _client_ip(connection: HTTPConnection) -> str | None:
    return _connection_client_host(connection)


def issue_session_token(
    *,
    user: User,
    session_id: str,
    config: AppConfig,
) -> str:
    return create_token(
        user_id=user.user_id,
        username=user.username,
        is_admin=user.is_admin,
        session_id=session_id,
        secret=_token_secret(config),
    )


def get_current_auth_context(
    *,
    request: HTTPConnection,
    session: Session,
    config: AppConfig,
    required: bool = True,
) -> AuthenticatedSessionContext | None:
    cached = getattr(request.state, "auth_context", None)
    if isinstance(cached, AuthenticatedSessionContext):
        return cached

    ensure_human_users_are_admin(session)

    expected_api_key = (config.openclaw_api_key or "").strip()
    presented_api_key = _header_api_key_value(request)
    presented_bearer = _header_bearer_token(request)
    session_token = None
    if presented_bearer and "." in presented_bearer:
        session_token = presented_bearer
    elif request.cookies.get(SESSION_COOKIE_NAME):
        session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if session_token:
        try:
            claims = decode_token(token=session_token, secret=_token_secret(config))
            record = require_active_user_session(
                session,
                user_id=claims["sub"],
                session_id=claims["sid"],
            )
        except UserSessionAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except UserAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        session_user = cast(User | None, session.get(User, claims["sub"]))
        if session_user is None:
            raise HTTPException(status_code=401, detail="session user not found")
        resolved_user: User = session_user
        try:
            touch_user_session(
                session,
                record=record,
                ip_address=_client_ip(request),
                user_agent=request.headers.get("user-agent"),
            )
        except OperationalError as exc:
            session.rollback()
            LOGGER.warning("auth.session_touch_skipped reason=db_locked detail=%s", exc)
        context = AuthenticatedSessionContext(
            user=resolved_user,
            session_record=record,
            auth_transport="bearer" if presented_bearer and "." in presented_bearer else "cookie",
        )
        request.state.auth_context = context
        return context

    if expected_api_key and (
        presented_api_key == expected_api_key or presented_bearer == expected_api_key
    ):
        context = AuthenticatedSessionContext(
            user=ensure_service_user(session),
            session_record=None,
            auth_transport="service_api_key",
        )
        request.state.auth_context = context
        return context

    if presented_api_key:
        try:
            user = resolve_user_from_agent_key(session, token=presented_api_key)
        except AgentKeyAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        context = AuthenticatedSessionContext(
            user=user,
            session_record=None,
            auth_transport="api_key",
        )
        request.state.auth_context = context
        return context

    if presented_bearer and "." not in presented_bearer:
        try:
            user = resolve_user_from_agent_key(session, token=presented_bearer)
        except AgentKeyAuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        context = AuthenticatedSessionContext(
            user=user,
            session_record=None,
            auth_transport="bearer_api_key",
        )
        request.state.auth_context = context
        return context

    if not presented_bearer and not request.cookies.get(SESSION_COOKIE_NAME):
        if required and human_user_count(session) == 0:
            raise HTTPException(status_code=503, detail="setup required")
        if required:
            raise HTTPException(status_code=401, detail="authentication required")
        return None
    raise HTTPException(status_code=401, detail="authentication required")


def get_current_user(
    *,
    request: HTTPConnection,
    session: Session,
    config: AppConfig,
    required: bool = True,
) -> User | None:
    context = get_current_auth_context(
        request=request,
        session=session,
        config=config,
        required=required,
    )
    if context is None:
        return None
    return context.user
