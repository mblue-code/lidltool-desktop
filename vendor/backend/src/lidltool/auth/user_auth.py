from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast

import bcrypt
import jwt

SESSION_TTL = timedelta(days=7)


class TokenClaims(TypedDict):
    sub: str
    username: str
    is_admin: bool
    sid: str
    exp: int


class UserAuthError(RuntimeError):
    """Raised when auth inputs are malformed or token validation fails."""


def hash_password(password: str) -> str:
    raw = password.strip()
    if not raw:
        raise UserAuthError("password must not be empty")
    encoded = raw.encode("utf-8")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bool(
            bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        )
    except Exception:  # noqa: BLE001
        return False


def create_token(
    *,
    user_id: str,
    username: str,
    is_admin: bool,
    session_id: str,
    secret: str,
    expires_in: timedelta = SESSION_TTL,
) -> str:
    if not (secret or "").strip():
        raise UserAuthError("missing token signing secret")
    now = datetime.now(tz=UTC)
    payload: TokenClaims = {
        "sub": user_id,
        "username": username,
        "is_admin": is_admin,
        "sid": session_id,
        "exp": int((now + expires_in).timestamp()),
    }
    token = jwt.encode(cast(dict[str, Any], payload), secret, algorithm="HS256")
    if not isinstance(token, str):
        raise UserAuthError("failed to encode token")
    return token


def decode_token(*, token: str, secret: str) -> TokenClaims:
    if not token:
        raise UserAuthError("missing session token")
    if not (secret or "").strip():
        raise UserAuthError("missing token signing secret")
    try:
        decoded = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise UserAuthError("invalid or expired session token") from exc
    if not isinstance(decoded, dict):
        raise UserAuthError("token payload is malformed")

    sub = decoded.get("sub")
    username = decoded.get("username")
    is_admin = decoded.get("is_admin")
    session_id = decoded.get("sid")
    exp = decoded.get("exp")

    if not isinstance(sub, str) or not sub:
        raise UserAuthError("token subject is malformed")
    if not isinstance(username, str) or not username:
        raise UserAuthError("token username is malformed")
    if not isinstance(is_admin, bool):
        raise UserAuthError("token admin flag is malformed")
    if not isinstance(session_id, str) or not session_id:
        raise UserAuthError("token session id is malformed")
    if not isinstance(exp, int):
        raise UserAuthError("token expiration is malformed")

    return {
        "sub": sub,
        "username": username,
        "is_admin": is_admin,
        "sid": session_id,
        "exp": exp,
    }


def token_payload_for_user(*, user_id: str, username: str, is_admin: bool) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
    }
