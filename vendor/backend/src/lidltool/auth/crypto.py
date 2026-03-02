from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_ENVELOPE_VERSION = 1
_AAD = b"lidltool.tokenstore.v1"


class CredentialCryptoError(RuntimeError):
    """Raised when encrypted credential payloads cannot be processed."""


def is_encrypted_envelope(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    required_keys = {"version", "alg", "kdf", "salt", "nonce", "ciphertext"}
    return required_keys.issubset(payload.keys())


def encrypt_payload(
    payload: dict[str, Any],
    *,
    secret: str,
    key_id: str = "v1",
) -> dict[str, Any]:
    key_material = _decode_secret(secret)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(key_material=key_material, salt=salt)
    aesgcm = AESGCM(key)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, _AAD)
    return {
        "version": _ENVELOPE_VERSION,
        "alg": "AES-256-GCM",
        "kdf": "scrypt",
        "kdf_n": 16384,
        "kdf_r": 8,
        "kdf_p": 1,
        "key_id": key_id,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
        "ciphertext": _b64e(ciphertext),
    }


def decrypt_payload(envelope: dict[str, Any], *, secret: str) -> dict[str, Any]:
    try:
        raw_version = envelope.get("version")
        if not isinstance(raw_version, int | str):
            raise CredentialCryptoError("malformed credential envelope version")
        version = int(raw_version)
        if version != _ENVELOPE_VERSION:
            raise CredentialCryptoError(f"unsupported credential envelope version: {version}")
        if envelope.get("kdf") != "scrypt":
            raise CredentialCryptoError("unsupported credential envelope KDF")
        salt = _b64d(str(envelope["salt"]))
        nonce = _b64d(str(envelope["nonce"]))
        ciphertext = _b64d(str(envelope["ciphertext"]))
    except KeyError as exc:
        raise CredentialCryptoError(f"malformed credential envelope: missing {exc}") from exc
    except ValueError as exc:
        raise CredentialCryptoError("malformed credential envelope") from exc

    key_material = _decode_secret(secret)
    key = _derive_key(key_material=key_material, salt=salt)
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, _AAD)
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError("unable to decrypt credential envelope") from exc

    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise CredentialCryptoError("decrypted credential envelope is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CredentialCryptoError("decrypted credential envelope must be a JSON object")
    return payload


def _derive_key(*, key_material: bytes, salt: bytes) -> bytes:
    scrypt = Scrypt(salt=salt, length=32, n=16384, r=8, p=1)
    return scrypt.derive(key_material)


def _decode_secret(value: str) -> bytes:
    raw = value.strip()
    if not raw:
        raise CredentialCryptoError("credential encryption secret is empty")
    if raw.startswith("base64:"):
        encoded = raw.removeprefix("base64:").strip()
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise CredentialCryptoError("invalid base64 credential encryption secret") from exc
        if not decoded:
            raise CredentialCryptoError("decoded credential encryption secret is empty")
        return decoded
    return raw.encode("utf-8")


def _b64e(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)
