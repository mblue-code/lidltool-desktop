from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lidltool.auth.crypto import decrypt_payload, encrypt_payload

if TYPE_CHECKING:
    from lidltool.config import AppConfig


def _require_encryption_secret(config: AppConfig) -> str:
    key = (config.credential_encryption_key or "").strip()
    if key:
        return key
    raise RuntimeError(
        "credential encryption key is required for AI settings; "
        "set LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"
    )


def _encrypt_secret(config: AppConfig, value: str) -> str:
    payload = encrypt_payload(
        {"value": value},
        secret=_require_encryption_secret(config),
        key_id=config.credential_encryption_key_id,
    )
    return json.dumps(payload, separators=(",", ":"))


def _decrypt_secret(config: AppConfig, encrypted_value: str | None) -> str | None:
    if not encrypted_value:
        return None
    try:
        envelope = json.loads(encrypted_value)
        if not isinstance(envelope, dict):
            return None
        payload = decrypt_payload(envelope, secret=_require_encryption_secret(config))
    except Exception:
        return None
    value = payload.get("value")
    if isinstance(value, str) and value:
        return value
    return None


def get_ai_api_key(config: AppConfig) -> str | None:
    return _decrypt_secret(config, config.ai_api_key_encrypted)


def set_ai_api_key(config: AppConfig, key: str | None) -> None:
    normalized = (key or "").strip()
    config.ai_api_key_encrypted = _encrypt_secret(config, normalized) if normalized else None


def get_ai_oauth_access_token(config: AppConfig) -> str | None:
    return _decrypt_secret(config, config.ai_oauth_access_token_encrypted)


def set_ai_oauth_access_token(config: AppConfig, token: str | None) -> None:
    normalized = (token or "").strip()
    config.ai_oauth_access_token_encrypted = (
        _encrypt_secret(config, normalized) if normalized else None
    )


def get_ai_oauth_refresh_token(config: AppConfig) -> str | None:
    return _decrypt_secret(config, config.ai_oauth_refresh_token_encrypted)


def set_ai_oauth_refresh_token(config: AppConfig, token: str | None) -> None:
    normalized = (token or "").strip()
    config.ai_oauth_refresh_token_encrypted = (
        _encrypt_secret(config, normalized) if normalized else None
    )


def persist_config_values(config_path: Path, updates: dict[str, Any]) -> None:
    config_path = config_path.expanduser().resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = existing_text.splitlines()

    for key, value in updates.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        next_lines: list[str] = []
        replaced = False
        for line in lines:
            if not pattern.match(line):
                next_lines.append(line)
                continue
            if value is None:
                continue
            if not replaced:
                next_lines.append(f"{key} = {_toml_value(value)}")
                replaced = True
        if value is not None and not replaced:
            if next_lines and next_lines[-1].strip():
                next_lines.append("")
            next_lines.append(f"{key} = {_toml_value(value)}")
        lines = next_lines

    output = "\n".join(lines).strip()
    config_path.write_text(f"{output}\n" if output else "", encoding="utf-8")
    os.chmod(config_path, 0o600)


def persist_ai_settings(config_path: Path, config: AppConfig) -> None:
    persist_config_values(
        config_path,
        {
            "ai_base_url": config.ai_base_url,
            "ai_api_key_encrypted": config.ai_api_key_encrypted,
            "ai_model": config.ai_model,
            "ai_enabled": config.ai_enabled,
            "ai_oauth_provider": config.ai_oauth_provider,
            "ai_oauth_access_token_encrypted": config.ai_oauth_access_token_encrypted,
            "ai_oauth_refresh_token_encrypted": config.ai_oauth_refresh_token_encrypted,
            "ai_oauth_expires_at": config.ai_oauth_expires_at,
        },
    )


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)

