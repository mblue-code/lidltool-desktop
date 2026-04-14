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
LEGACY_ACCOUNT = "lidl_plus_de_refresh_token"
LOGGER = logging.getLogger(__name__)
_SOURCE_FIELDS = {
    "refresh_token",
    "access_token",
    "access_token_expires_at",
    "reauth_required",
}


@dataclass(slots=True)
class TokenStore:
    fallback_file: Path
    encryption_key: str | None = None
    encryption_key_id: str = "v1"
    encryption_required: bool = True
    source_id: str = "lidl_plus_de"

    @classmethod
    def from_config(cls, config: AppConfig) -> TokenStore:
        return cls(
            fallback_file=config.token_file,
            encryption_key=config.credential_encryption_key,
            encryption_key_id=config.credential_encryption_key_id,
            encryption_required=config.credential_encryption_required,
            source_id=config.source,
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

                token = keyring.get_password(SERVICE, self._account_name())
                if token:
                    return token
            except Exception:
                pass
        _, source_store = self._load_source_store()
        return source_store.get("refresh_token") or None

    def set_refresh_token(self, token: str) -> None:
        if self._keyring_available():
            try:
                import keyring

                keyring.set_password(SERVICE, self._account_name(), token)
                # Still persist to file so access-cache and flags work
                store, source_store = self._load_source_store()
                source_store["refresh_token"] = token
                source_store.pop("reauth_required", None)
                self._write_source_store(store, source_store)
                return
            except Exception:
                pass
        store, source_store = self._load_source_store()
        source_store["refresh_token"] = token
        source_store.pop("reauth_required", None)
        self._write_source_store(store, source_store)

    def clear_refresh_token(self) -> None:
        if self._keyring_available():
            try:
                import keyring

                keyring.delete_password(SERVICE, self._account_name())
            except Exception:
                pass
        store, source_store = self._load_source_store()
        removed = source_store.pop("refresh_token", None)
        if removed is None:
            return
        self._write_source_store(store, source_store)

    # ------------------------------------------------------------------
    # Access token cache (always in the JSON file — short-lived, 0600)
    # ------------------------------------------------------------------

    def get_access_cache(self) -> tuple[str, datetime] | None:
        """Return (access_token, expires_at) if a valid cache entry exists."""
        _, source_store = self._load_source_store()
        token = source_store.get("access_token")
        expires_str = source_store.get("access_token_expires_at")
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
        store, source_store = self._load_source_store()
        source_store["access_token"] = access_token
        source_store["access_token_expires_at"] = expires_at.isoformat()
        source_store.pop("reauth_required", None)  # successful refresh clears the flag
        self._write_source_store(store, source_store)

    def clear_access_cache(self) -> None:
        store, source_store = self._load_source_store()
        removed_token = source_store.pop("access_token", None)
        removed_exp = source_store.pop("access_token_expires_at", None)
        if removed_token is None and removed_exp is None:
            return
        self._write_source_store(store, source_store)

    # ------------------------------------------------------------------
    # Reauth-required flag
    # ------------------------------------------------------------------

    def set_reauth_required(self) -> None:
        """Mark that the refresh token has been rejected and re-auth is needed."""
        store, source_store = self._load_source_store()
        source_store["reauth_required"] = True
        source_store.pop("access_token", None)
        source_store.pop("access_token_expires_at", None)
        self._write_source_store(store, source_store)

    def is_reauth_required(self) -> bool:
        _, source_store = self._load_source_store()
        return bool(source_store.get("reauth_required"))

    def clear_reauth_required(self) -> None:
        store, source_store = self._load_source_store()
        removed = source_store.pop("reauth_required", None)
        if removed is None:
            return
        self._write_source_store(store, source_store)

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

    def _account_name(self) -> str:
        if self.source_id == "lidl_plus_de":
            return LEGACY_ACCOUNT
        return f"{self.source_id}_refresh_token"

    def _load_source_store(self) -> tuple[dict, dict]:  # type: ignore[type-arg]
        store = self._read_json_store()
        sources = store.get("sources")
        if isinstance(sources, dict):
            source_store = sources.get(self.source_id)
            if isinstance(source_store, dict):
                return store, dict(source_store)
        if self.source_id == "lidl_plus_de":
            legacy = {
                key: value
                for key, value in store.items()
                if key in _SOURCE_FIELDS
            }
            return store, legacy
        return store, {}

    def _write_source_store(self, store: dict, source_store: dict) -> None:  # type: ignore[type-arg]
        sources = store.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        if source_store:
            sources[self.source_id] = source_store
        else:
            sources.pop(self.source_id, None)
        if sources:
            store["sources"] = sources
        else:
            store.pop("sources", None)

        if self.source_id == "lidl_plus_de":
            for key in _SOURCE_FIELDS:
                if key in source_store:
                    store[key] = source_store[key]
                else:
                    store.pop(key, None)

        self._write_json_store(store)

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
