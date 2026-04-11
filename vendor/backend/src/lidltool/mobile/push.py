from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.config import AppConfig
from lidltool.db.models import AlertEvent, MobileDevice

_APNS_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}
_FCM_ACCESS_TOKEN_CACHE: dict[str, tuple[str, datetime, str]] = {}


@dataclass(frozen=True, slots=True)
class PushDispatchResult:
    attempted: int = 0
    delivered: int = 0
    failed: int = 0


def dispatch_offer_alert_pushes(
    session: Session,
    *,
    config: AppConfig,
    alert_event: AlertEvent,
) -> PushDispatchResult:
    if not config.mobile_push_enabled:
        return PushDispatchResult()

    devices = session.execute(
        select(MobileDevice).where(
            MobileDevice.user_id == alert_event.user_id,
            MobileDevice.notifications_enabled.is_(True),
        )
    ).scalars().all()
    if not devices:
        return PushDispatchResult()

    attempted = 0
    delivered = 0
    failed = 0
    now = datetime.now(tz=UTC)

    for device in devices:
        attempted += 1
        try:
            _send_push_to_device(config=config, device=device, alert_event=alert_event)
            device.last_push_sent_at = now
            device.last_push_error_at = None
            device.last_push_error = None
            delivered += 1
        except Exception as exc:  # noqa: BLE001
            device.last_push_error_at = now
            device.last_push_error = str(exc)[:500]
            failed += 1

    if delivered > 0:
        alert_event.delivered_at = now
    session.flush()
    return PushDispatchResult(attempted=attempted, delivered=delivered, failed=failed)


def _send_push_to_device(*, config: AppConfig, device: MobileDevice, alert_event: AlertEvent) -> None:
    if device.push_provider == "apns":
        _send_apns_push(config=config, device=device, alert_event=alert_event)
        return
    if device.push_provider == "fcm":
        _send_fcm_push(config=config, device=device, alert_event=alert_event)
        return
    raise RuntimeError(f"unsupported push provider: {device.push_provider}")


def _send_apns_push(*, config: AppConfig, device: MobileDevice, alert_event: AlertEvent) -> None:
    team_id = (config.mobile_push_apns_team_id or "").strip()
    key_id = (config.mobile_push_apns_key_id or "").strip()
    topic = (config.mobile_push_apns_topic or "").strip()
    key_path = config.mobile_push_apns_private_key_path
    if not team_id or not key_id or not topic or key_path is None:
        raise RuntimeError("apns provider is not fully configured")

    bearer = _apns_bearer_token(team_id=team_id, key_id=key_id, private_key_path=key_path)
    host = "https://api.sandbox.push.apple.com" if config.mobile_push_apns_use_sandbox else "https://api.push.apple.com"
    payload = {
        "aps": {
            "alert": {
                "title": alert_event.title,
                "body": alert_event.body or "",
            },
            "sound": "default",
        },
        "lidltool_kind": "offer_alert",
        "alert_id": alert_event.id,
        "event_type": alert_event.event_type,
    }
    response = httpx.post(
        f"{host}/3/device/{device.push_token}",
        headers={
            "authorization": f"bearer {bearer}",
            "apns-topic": topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        json=payload,
        timeout=10.0,
    )
    if response.status_code not in {200}:
        raise RuntimeError(f"apns push failed with status {response.status_code}: {response.text}")


def _send_fcm_push(*, config: AppConfig, device: MobileDevice, alert_event: AlertEvent) -> None:
    access_token, project_id = _fcm_access_token_and_project(config)
    if not access_token or not project_id:
        raise RuntimeError("fcm provider is not fully configured")
    payload = {
        "message": {
            "token": device.push_token,
            "data": {
                "kind": "offer_alert",
                "alert_id": alert_event.id,
                "event_type": alert_event.event_type,
                "title": alert_event.title,
                "body": alert_event.body or "",
            },
            "android": {
                "priority": "HIGH",
            },
        }
    }
    response = httpx.post(
        f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send",
        headers={
            "authorization": f"Bearer {access_token}",
            "content-type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=10.0,
    )
    if response.status_code not in {200}:
        raise RuntimeError(f"fcm push failed with status {response.status_code}: {response.text}")


def _apns_bearer_token(*, team_id: str, key_id: str, private_key_path: Path) -> str:
    cache_key = f"{team_id}:{key_id}:{private_key_path}"
    cached = _APNS_TOKEN_CACHE.get(cache_key)
    now = datetime.now(tz=UTC)
    if cached is not None and cached[1] > now:
        return cached[0]

    private_key = private_key_path.read_text(encoding="utf-8")
    token = jwt.encode(
        {"iss": team_id, "iat": int(now.timestamp())},
        private_key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )
    _APNS_TOKEN_CACHE[cache_key] = (token, now + timedelta(minutes=50))
    return token


def _fcm_access_token_and_project(config: AppConfig) -> tuple[str | None, str | None]:
    credentials = _load_fcm_service_account(config)
    if credentials is None:
        return None, None
    client_email = str(credentials.get("client_email") or "").strip()
    private_key = str(credentials.get("private_key") or "").strip()
    project_id = (config.mobile_push_fcm_project_id or str(credentials.get("project_id") or "")).strip()
    if not client_email or not private_key or not project_id:
        return None, None

    cache_key = f"{client_email}:{project_id}"
    cached = _FCM_ACCESS_TOKEN_CACHE.get(cache_key)
    now = datetime.now(tz=UTC)
    if cached is not None and cached[1] > now:
        return cached[0], cached[2]

    issued_at = int(now.timestamp())
    assertion = jwt.encode(
        {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": issued_at,
            "exp": issued_at + 3600,
        },
        private_key,
        algorithm="RS256",
    )
    response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = str(payload.get("access_token") or "").strip()
    expires_in = int(payload.get("expires_in") or 3600)
    if not access_token:
        raise RuntimeError("fcm oauth token response did not include access_token")
    _FCM_ACCESS_TOKEN_CACHE[cache_key] = (
        access_token,
        now + timedelta(seconds=max(expires_in - 60, 60)),
        project_id,
    )
    return access_token, project_id


def _load_fcm_service_account(config: AppConfig) -> dict[str, Any] | None:
    inline_payload = (config.mobile_push_fcm_service_account_json or "").strip()
    if inline_payload:
        return json.loads(inline_payload)
    path = config.mobile_push_fcm_service_account_path
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))
