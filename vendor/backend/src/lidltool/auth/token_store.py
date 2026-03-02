from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from lidltool.auth.crypto import (
    CredentialCryptoError,
    decrypt_payload,
    encrypt_payload,
    is_encrypted_envelope,
)

if TYPE_CHECKING:
    from lidltool.config import AppConfig

SERVICE = "lidltool"
ACCOUNT = "lidl_plus_de_refresh_token"
LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenStore:
    fallback_file: Path
    encryption_key: str | None = None
    encryption_key_id: str = "v1"
    encryption_required: bool = True

    @classmethod
    def from_config(cls, config: AppConfig) -> TokenStore:
        return cls(
            fallback_file=config.token_file,
            encryption_key=config.credential_encryption_key,
            encryption_key_id=config.credential_encryption_key_id,
            encryption_required=config.credential_encryption_required,
        )

    # ------------------------------------------------------------------
    # Refresh token (keyring-first, file fallback)
    # ------------------------------------------------------------------

    def _keyring_available(self) -> bool:
        try:
            import keyring  # noqa: F401
        except Exception:
            return False
        return True

    def get_refresh_token(self) -> str | None:
        if self._keyring_available():
            try:
                import keyring

                token = keyring.get_password(SERVICE, ACCOUNT)
                if token:
                    return token
            except Exception:
                pass
        return self._read_json_store().get("refresh_token") or None

    def set_refresh_token(self, token: str) -> None:
        if self._keyring_available():
            try:
                import keyring

                keyring.set_password(SERVICE, ACCOUNT, token)
                # Still persist to file so access-cache and flags work
                store = self._read_json_store()
                store["refresh_token"] = token
                store.pop("reauth_required", None)
                self._write_json_store(store)
                return
            except Exception:
                pass
        store = self._read_json_store()
        store["refresh_token"] = token
        store.pop("reauth_required", None)
        self._write_json_store(store)

    def clear_refresh_token(self) -> None:
        if self._keyring_available():
            try:
                import keyring

                keyring.delete_password(SERVICE, ACCOUNT)
            except Exception:
                pass
        store = self._read_json_store()
        removed = store.pop("refresh_token", None)
        if removed is None:
            return
        self._write_json_store(store)

    # ------------------------------------------------------------------
    # Access token cache (always in the JSON file — short-lived, 0600)
    # ------------------------------------------------------------------

    def get_access_cache(self) -> tuple[str, datetime] | None:
        """Return (access_token, expires_at) if a valid cache entry exists."""
        store = self._read_json_store()
        token = store.get("access_token")
        expires_str = store.get("access_token_expires_at")
        if not isinstance(token, str) or not token:
            return None
        if not isinstance(expires_str, str):
            return None
        try:
            expires_at = datetime.fromisoformat(expires_str)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            return token, expires_at
        except ValueError:
            return None

    def set_access_cache(self, access_token: str, expires_at: datetime) -> None:
        """Persist a freshly issued access token and its expiry timestamp."""
        store = self._read_json_store()
        store["access_token"] = access_token
        store["access_token_expires_at"] = expires_at.isoformat()
        store.pop("reauth_required", None)  # successful refresh clears the flag
        self._write_json_store(store)

    def clear_access_cache(self) -> None:
        store = self._read_json_store()
        removed_token = store.pop("access_token", None)
        removed_exp = store.pop("access_token_expires_at", None)
        if removed_token is None and removed_exp is None:
            return
        self._write_json_store(store)

    # ------------------------------------------------------------------
    # Reauth-required flag
    # ------------------------------------------------------------------

    def set_reauth_required(self) -> None:
        """Mark that the refresh token has been rejected and re-auth is needed."""
        store = self._read_json_store()
        store["reauth_required"] = True
        store.pop("access_token", None)
        store.pop("access_token_expires_at", None)
        self._write_json_store(store)

    def is_reauth_required(self) -> bool:
        return bool(self._read_json_store().get("reauth_required"))

    def clear_reauth_required(self) -> None:
        store = self._read_json_store()
        removed = store.pop("reauth_required", None)
        if removed is None:
            return
        self._write_json_store(store)

    # ------------------------------------------------------------------
    # Internal JSON store helpers
    # ------------------------------------------------------------------

    def _read_json_store(self) -> dict:  # type: ignore[type-arg]
        if not self.fallback_file.exists():
            return {}
        try:
            with self.fallback_file.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict):
                return {}
            if is_encrypted_envelope(payload):
                key = self._require_encryption_key(operation="read")
                return decrypt_payload(payload, secret=key)
            return payload
        except CredentialCryptoError:
            raise
        except Exception:
            return {}

    def _write_json_store(self, payload: dict) -> None:  # type: ignore[type-arg]
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)
        key = (self.encryption_key or "").strip()
        if key:
            stored_payload = encrypt_payload(payload, secret=key, key_id=self.encryption_key_id)
        elif self.encryption_required:
            raise CredentialCryptoError(
                "credential encryption key is required for token store write; "
                "set LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"
            )
        else:
            LOGGER.warning(
                "Credential encryption is disabled. Token file is stored in plaintext."
            )
            stored_payload = payload
        with self.fallback_file.open("w", encoding="utf-8") as fh:
            json.dump(stored_payload, fh, indent=2)
        os.chmod(self.fallback_file, 0o600)

    def _require_encryption_key(self, *, operation: str) -> str:
        key = (self.encryption_key or "").strip()
        if key:
            return key
        if self.encryption_required:
            raise CredentialCryptoError(
                f"credential encryption key is required for token store {operation}; "
                "set LIDLTOOL_CREDENTIAL_ENCRYPTION_KEY"
            )
        raise CredentialCryptoError(
            f"credential encryption key is missing for token store {operation}; "
            "encrypted token payloads cannot be processed without a key"
        )

    # ------------------------------------------------------------------
    # Legacy helpers kept for backwards compat (used by bootstrap)
    # ------------------------------------------------------------------

    def _write_fallback_token(self, token: str) -> None:
        store = self._read_json_store()
        store["refresh_token"] = token
        self._write_json_store(store)

    def _read_fallback_token(self) -> str | None:
        val = self._read_json_store().get("refresh_token")
        return val if isinstance(val, str) and val else None
