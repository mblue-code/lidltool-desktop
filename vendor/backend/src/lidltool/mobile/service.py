from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lidltool.db.models import MobileDevice


def upsert_mobile_device(
    session: Session,
    *,
    user_id: str,
    session_id: str | None,
    installation_id: str,
    client_platform: str,
    push_provider: str,
    push_token: str,
    notifications_enabled: bool = True,
    device_label: str | None = None,
    client_name: str | None = None,
    app_version: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    normalized_platform = client_platform.strip().lower()
    normalized_provider = push_provider.strip().lower()
    normalized_installation_id = installation_id.strip()
    normalized_token = push_token.strip()
    normalized_locale = (locale or "").strip().lower() or None
    normalized_device_label = (device_label or "").strip() or None
    normalized_client_name = (client_name or "").strip() or None
    normalized_app_version = (app_version or "").strip() or None

    if normalized_platform not in {"ios", "android"}:
        raise RuntimeError("client_platform must be one of: ios, android")
    if normalized_provider not in {"apns", "fcm"}:
        raise RuntimeError("push_provider must be one of: apns, fcm")
    if normalized_platform == "ios" and normalized_provider != "apns":
        raise RuntimeError("ios devices must use push_provider='apns'")
    if normalized_platform == "android" and normalized_provider != "fcm":
        raise RuntimeError("android devices must use push_provider='fcm'")
    if len(normalized_installation_id) < 8:
        raise RuntimeError("installation_id must be at least 8 characters")
    if len(normalized_token) < 16:
        raise RuntimeError("push_token must be at least 16 characters")

    record = session.execute(
        select(MobileDevice).where(
            MobileDevice.user_id == user_id,
            MobileDevice.installation_id == normalized_installation_id,
        )
    ).scalar_one_or_none()
    now = datetime.now(tz=UTC)

    if record is None:
        record = MobileDevice(
            user_id=user_id,
            session_id=session_id,
            installation_id=normalized_installation_id,
            client_platform=normalized_platform,
            push_provider=normalized_provider,
            push_token=normalized_token,
            notifications_enabled=notifications_enabled,
            device_label=normalized_device_label,
            client_name=normalized_client_name,
            app_version=normalized_app_version,
            locale=normalized_locale,
            last_registered_at=now,
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return serialize_mobile_device(record)

    record.session_id = session_id
    record.client_platform = normalized_platform
    record.push_provider = normalized_provider
    record.push_token = normalized_token
    record.notifications_enabled = notifications_enabled
    record.device_label = normalized_device_label
    record.client_name = normalized_client_name
    record.app_version = normalized_app_version
    record.locale = normalized_locale
    record.last_registered_at = now
    session.flush()
    session.refresh(record)
    return serialize_mobile_device(record)


def list_mobile_devices(
    session: Session,
    *,
    user_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    clamped_limit = min(max(limit, 1), 200)
    clamped_offset = max(offset, 0)
    stmt = (
        select(MobileDevice)
        .where(MobileDevice.user_id == user_id)
        .order_by(MobileDevice.updated_at.desc(), MobileDevice.created_at.desc())
    )
    total = int(session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = session.execute(stmt.limit(clamped_limit).offset(clamped_offset)).scalars().all()
    items = [serialize_mobile_device(row) for row in rows]
    return {
        "count": len(rows),
        "total": total,
        "limit": clamped_limit,
        "offset": clamped_offset,
        "items": items,
        "devices": items,
        "pagination": {
            "count": len(rows),
            "total": total,
            "limit": clamped_limit,
            "offset": clamped_offset,
        },
    }


def delete_mobile_device(session: Session, *, user_id: str, device_id: str) -> dict[str, Any]:
    record = session.get(MobileDevice, device_id)
    if record is None or record.user_id != user_id:
        raise RuntimeError("mobile device not found")
    result = {"deleted": True, "device_id": record.device_id}
    session.delete(record)
    return result


def delete_mobile_devices_for_session(
    session: Session,
    *,
    user_id: str,
    session_id: str,
) -> dict[str, Any]:
    rows = session.execute(
        select(MobileDevice).where(
            MobileDevice.user_id == user_id,
            MobileDevice.session_id == session_id,
        )
    ).scalars().all()
    deleted_ids = [row.device_id for row in rows]
    for row in rows:
        session.delete(row)
    return {
        "deleted": True,
        "count": len(deleted_ids),
        "device_ids": deleted_ids,
    }


def serialize_mobile_device(record: MobileDevice) -> dict[str, Any]:
    return {
        "device_id": record.device_id,
        "user_id": record.user_id,
        "session_id": record.session_id,
        "installation_id": record.installation_id,
        "client_platform": record.client_platform,
        "push_provider": record.push_provider,
        "device_label": record.device_label,
        "client_name": record.client_name,
        "app_version": record.app_version,
        "locale": record.locale,
        "notifications_enabled": record.notifications_enabled,
        "last_registered_at": record.last_registered_at.isoformat(),
        "last_push_sent_at": record.last_push_sent_at.isoformat() if record.last_push_sent_at else None,
        "last_push_error_at": (
            record.last_push_error_at.isoformat() if record.last_push_error_at else None
        ),
        "last_push_error": record.last_push_error,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
