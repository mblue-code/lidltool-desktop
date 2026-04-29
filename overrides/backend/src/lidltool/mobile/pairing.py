from __future__ import annotations

import hashlib
import secrets
import socket
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import MobilePairedDevice, MobilePairingSession

PROTOCOL_VERSION = 1
DEFAULT_PAIRING_EXPIRES_IN_SECONDS = 600
MIN_PAIRING_EXPIRES_IN_SECONDS = 60
MAX_PAIRING_EXPIRES_IN_SECONDS = 600
DEFAULT_TRANSPORT = "lan_http"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def desktop_id() -> str:
    return f"desktop:{socket.gethostname()}"


def desktop_name() -> str:
    return socket.gethostname() or "Outlays"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def create_pairing_session(
    session: Session,
    *,
    endpoint_url: str,
    created_by_user_id: str | None,
    expires_in_seconds: int = DEFAULT_PAIRING_EXPIRES_IN_SECONDS,
    transport: str = DEFAULT_TRANSPORT,
) -> dict[str, Any]:
    pairing_token = secrets.token_urlsafe(32)
    fingerprint = hashlib.sha256(f"{desktop_id()}:{pairing_token}".encode("utf-8")).hexdigest()[:32]
    now = datetime.now(tz=UTC)
    expires_at = now + timedelta(
        seconds=max(
            MIN_PAIRING_EXPIRES_IN_SECONDS,
            min(expires_in_seconds, MAX_PAIRING_EXPIRES_IN_SECONDS),
        )
    )
    record = MobilePairingSession(
        desktop_id=desktop_id(),
        desktop_name=desktop_name(),
        endpoint_url=endpoint_url.rstrip("/"),
        pairing_token_hash=token_hash(pairing_token),
        public_key_fingerprint=fingerprint,
        status="pending",
        created_by_user_id=created_by_user_id,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    session.flush()
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "desktop_id": record.desktop_id,
        "desktop_name": record.desktop_name,
        "endpoint_url": record.endpoint_url,
        "pairing_token": pairing_token,
        "public_key_fingerprint": record.public_key_fingerprint,
        "expires_at": record.expires_at.isoformat(),
        "transport": transport,
        "listener_expires_at": record.expires_at.isoformat(),
    }
    return {
        "session_id": record.session_id,
        "status": record.status,
        "payload": payload,
        "qr_payload": payload,
        "expires_at": record.expires_at.isoformat(),
        "listener_expires_at": record.expires_at.isoformat(),
    }


def complete_pairing_handshake(
    session: Session,
    *,
    pairing_token: str,
    device_id: str,
    device_name: str | None,
    platform: str,
    public_key_fingerprint: str | None,
) -> tuple[dict[str, Any], str]:
    now = datetime.now(tz=UTC)
    pairing = session.execute(
        select(MobilePairingSession).where(
            MobilePairingSession.pairing_token_hash == token_hash(pairing_token),
            MobilePairingSession.status == "pending",
        )
    ).scalar_one_or_none()
    if pairing is None or _as_utc(pairing.expires_at) < now:
        raise RuntimeError("invalid or expired pairing token")
    if platform not in {"ios", "android"}:
        raise RuntimeError("platform must be one of: ios, android")
    if pairing.created_by_user_id is None:
        raise RuntimeError("pairing session is missing an owner")

    sync_token = secrets.token_urlsafe(48)
    existing = session.execute(
        select(MobilePairedDevice).where(
            MobilePairedDevice.desktop_id == pairing.desktop_id,
            MobilePairedDevice.device_id == device_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = MobilePairedDevice(
            paired_device_id=str(uuid4()),
            user_id=pairing.created_by_user_id,
            desktop_id=pairing.desktop_id,
            device_id=device_id,
            device_name=device_name,
            platform=platform,
            sync_token_hash=token_hash(sync_token),
            public_key_fingerprint=public_key_fingerprint,
            protocol_version=PROTOCOL_VERSION,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.user_id = pairing.created_by_user_id
        existing.device_name = device_name
        existing.platform = platform
        existing.sync_token_hash = token_hash(sync_token)
        existing.public_key_fingerprint = public_key_fingerprint
        existing.protocol_version = PROTOCOL_VERSION
        existing.last_seen_at = now
        existing.revoked_at = None
        existing.updated_at = now

    pairing.status = "paired"
    pairing.paired_device_id = existing.paired_device_id
    pairing.updated_at = now
    session.flush()
    return (
        {
            "paired_device_id": existing.paired_device_id,
            "desktop_id": pairing.desktop_id,
            "desktop_name": pairing.desktop_name,
            "endpoint_url": pairing.endpoint_url,
            "sync_token": sync_token,
            "issued_at": now.isoformat(),
            "expires_at": _as_utc(pairing.expires_at).isoformat(),
            "protocol_version": PROTOCOL_VERSION,
            "device_id": existing.device_id,
            "transport": DEFAULT_TRANSPORT,
        },
        sync_token,
    )


def require_paired_device(session: Session, *, bearer_token: str | None) -> MobilePairedDevice:
    token = (bearer_token or "").strip()
    if not token:
        raise RuntimeError("mobile sync token required")
    record = session.execute(
        select(MobilePairedDevice).where(
            MobilePairedDevice.sync_token_hash == token_hash(token),
            MobilePairedDevice.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if record is None:
        raise RuntimeError("invalid mobile sync token")
    record.last_seen_at = datetime.now(tz=UTC)
    return record
