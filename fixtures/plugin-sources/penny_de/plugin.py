from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import urllib.parse
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    ConnectorError,
    DiagnosticsOutput,
    DiscoverRecordsOutput,
    ExtractDiscountsOutput,
    FetchRecordOutput,
    GetAuthStatusOutput,
    GetDiagnosticsResponse,
    GetManifestOutput,
    GetManifestResponse,
    HealthcheckOutput,
    HealthcheckResponse,
    NormalizedDiscountRow,
    NormalizedReceiptItem,
    NormalizedReceiptRecord,
    NormalizeRecordOutput,
    ReceiptActionRequest,
    ReceiptActionResponse,
    ReceiptConnector,
    RecordReference,
    validate_receipt_action_request,
)
from lidltool.connectors.sdk.runtime import (
    AuthBrowserPlan,
    build_auth_browser_metadata,
    load_plugin_runtime_context,
    parse_auth_browser_runtime_context,
)
from lidltool.ingest.dedupe import compute_fingerprint

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH_CANDIDATES = (
    ROOT / "manifest.json",
    ROOT.parent / "manifest.json",
)

STATE_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_AUTH_TIMEOUT_SECONDS = 900
DEFAULT_DISCOVERY_LIMIT = 100
DEFAULT_DISCOVERY_URL = "https://account.penny.de/realms/penny/.well-known/openid-configuration"
DEFAULT_AUTH_ENDPOINT = "https://account.penny.de/realms/penny/protocol/openid-connect/auth"
DEFAULT_TOKEN_ENDPOINT = "https://account.penny.de/realms/penny/protocol/openid-connect/token"
DEFAULT_CLIENT_ID = "pennyandroid"
DEFAULT_REDIRECT_URI = "https://www.penny.de/app/login"
DEFAULT_SCOPE = "openid profile email"
DEFAULT_ACCOUNT_URL = "https://account.penny.de/realms/penny/cookie-setter?redirect=account-ui"
DEFAULT_ACCOUNT_UI_URL = "https://account.penny.de/account-ui"
DEFAULT_EBON_API_BASE_URL = "https://api.penny.de"
DEFAULT_EBON_PAGE_SIZE = 20
DEFAULT_MERCHANT_NAME = "PENNY"
_CHROME_SAFE_STORAGE_SERVICE = "Chrome Safe Storage"
_CHROME_SAFE_STORAGE_ACCOUNT = "Chrome"
_CHROME_COOKIE_EPOCH_OFFSET_SECONDS = 11_644_473_600
_DEFAULT_CHROME_EXECUTABLE = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
_PENNY_ITEM_LINE_RE = re.compile(r"^(?P<name>.+?)\s+(?P<amount>-?\d+,\d{2})\s+(?P<vat>[A-Z])$")
_PENNY_SUM_LINE_RE = re.compile(r"^SUMME\s+EUR\s+(?P<amount>\d+,\d{2})$")
_PENNY_PAYMENT_LINE_RE = re.compile(r"^Geg\.\s+(?P<method>.+?)\s+EUR\s+(?P<amount>\d+,\d{2})$")
_PENNY_RECEIPT_NUMBER_RE = re.compile(r"^Beleg-Nr\.\s*(?P<value>\d+)$")
_PENNY_MARKET_ID_RE = re.compile(r"^Markt:(?P<value>\d+)\b")
_PENNY_SAVINGS_LINE_RE = re.compile(r"^(?P<amount>\d+,\d{2})\s+EUR gespart$")
_PENNY_VAT_RATE_RE = re.compile(r"^(?P<code>[A-Z])=\s*(?P<rate>\d+,\d+)%")
_PENNY_POSTAL_CITY_RE = re.compile(r"^(?P<postal>\d{5})\s+(?P<city>.+)$")
_PENNY_DATE_LINE_RE = re.compile(r"^Datum:\s*(?P<value>\d{2}\.\d{2}\.\d{4})$")
_PENNY_TIME_LINE_RE = re.compile(r"^Uhrzeit:\s*(?P<value>\d{2}:\d{2}:\d{2})\s*Uhr$")
_PENNY_DEFAULT_VAT_RATES = {"A": "19%", "B": "7%"}


class PennyPluginError(RuntimeError):
    def __init__(self, message: str, *, code: str = "internal_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(slots=True, frozen=True)
class OauthSession:
    access_token: str
    refresh_token: str
    expires_at: str | None
    scope: str | None = None
    token_type: str | None = None
    id_token: str | None = None
    client_id: str = DEFAULT_CLIENT_ID
    redirect_uri: str = DEFAULT_REDIRECT_URI
    auth_endpoint: str = DEFAULT_AUTH_ENDPOINT
    token_endpoint: str = DEFAULT_TOKEN_ENDPOINT
    discovery_url: str = DEFAULT_DISCOVERY_URL


@dataclass(slots=True, frozen=True)
class PendingAuthFlow:
    flow_id: str
    created_at: str
    verifier: str
    state: str
    auth_endpoint: str
    token_endpoint: str
    client_id: str
    redirect_uri: str
    scope: str


def _manifest_definition() -> dict[str, Any]:
    for manifest_path in MANIFEST_PATH_CANDIDATES:
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
    searched = ", ".join(str(path) for path in MANIFEST_PATH_CANDIDATES)
    raise FileNotFoundError(f"Penny plugin manifest.json not found. Looked in: {searched}")


def _resolve_optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value.expanduser().resolve()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        return Path(raw).expanduser().resolve()
    raise TypeError(f"expected path-like value, got {type(value).__name__}")


def _string_option(options: Mapping[str, Any], key: str, default: str) -> str:
    return str(options.get(key, default))


def _int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    return int(options.get(key, default))


def _bool_option(options: Mapping[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _option_present(options: Mapping[str, Any], key: str) -> bool:
    return key in options and options.get(key) is not None


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _expires_at_from_now(expires_in_seconds: int | None) -> str | None:
    if expires_in_seconds is None:
        return None
    return (datetime.now(tz=UTC) + timedelta(seconds=max(expires_in_seconds, 0))).isoformat()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _decode_jwt_claims(token: str | None) -> Mapping[str, Any] | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    parts = raw.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        claims = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return claims if isinstance(claims, Mapping) else None


def _profile_from_oauth(oauth: OauthSession) -> dict[str, Any]:
    for token in (oauth.access_token, oauth.id_token):
        claims = _decode_jwt_claims(token)
        if not isinstance(claims, Mapping):
            continue
        subject = str(claims.get("sub") or "").strip()
        if not subject:
            continue
        return {
            "sub": subject,
            "email": str(claims.get("email") or "").strip() or None,
            "first_name": str(claims.get("given_name") or "").strip() or None,
            "last_name": str(claims.get("family_name") or "").strip() or None,
            "issuer": str(claims.get("iss") or "").strip() or None,
        }
    return {}


def _parse_redirect(url: str) -> tuple[str | None, str | None, str | None]:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    code = query.get("code", [None])[0]
    state = query.get("state", [None])[0]
    error = query.get("error", [None])[0]
    return code, state, error


def _state_file_for_context(storage_root: Path, options: Mapping[str, Any]) -> Path:
    explicit = _resolve_optional_path(options.get("state_file"))
    if explicit is not None:
        return explicit
    return (storage_root / "penny_state.json").resolve()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PennyPluginError(f"expected JSON object at {path}", code="contract_violation")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(dict(payload), indent=2, sort_keys=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(serialized)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _validate_storage_state_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    cookies = normalized.get("cookies")
    if not isinstance(cookies, list) or len(cookies) == 0:
        raise PennyPluginError(
            "Penny browser session import did not contain any cookies",
            code="auth_required",
        )
    origins = normalized.get("origins")
    if origins is None:
        normalized["origins"] = []
    elif not isinstance(origins, list):
        raise PennyPluginError(
            "Penny browser session import contains invalid origins data",
            code="auth_required",
        )
    return normalized


def _load_storage_state_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PennyPluginError(
            f"Penny browser session import file is not valid JSON: {path}",
            code="auth_required",
        ) from exc
    if not isinstance(payload, dict):
        raise PennyPluginError(
            f"Penny browser session import file must contain a JSON object: {path}",
            code="auth_required",
        )
    return _validate_storage_state_payload(payload)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": STATE_SCHEMA_VERSION}
    payload = _load_json(path)
    if int(payload.get("schema_version") or 0) != STATE_SCHEMA_VERSION:
        raise PennyPluginError(
            f"Penny plugin state schema mismatch at {path}",
            code="contract_violation",
        )
    return payload


def _persist_state(path: Path, payload: Mapping[str, Any]) -> None:
    normalized = dict(payload)
    normalized["schema_version"] = STATE_SCHEMA_VERSION
    normalized["updated_at"] = _iso_now()
    _write_json(path, normalized)


def _fixture_file_from_options(options: Mapping[str, Any]) -> Path | None:
    return _resolve_optional_path(options.get("fixture_file"))


def _storage_state_to_httpx_cookies(storage_state: Mapping[str, Any]) -> httpx.Cookies:
    jar = httpx.Cookies()
    for cookie in storage_state.get("cookies", []):
        if not isinstance(cookie, Mapping):
            continue
        name = str(cookie.get("name") or "").strip()
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").strip() or None
        path = str(cookie.get("path") or "/")
        if not name:
            continue
        jar.set(name, value, domain=domain, path=path)
    return jar


def _storage_state_with_httpx_cookies(storage_state: Mapping[str, Any], cookie_jar: Any) -> dict[str, Any]:
    updated = dict(storage_state)
    cookies_payload: list[dict[str, Any]] = []
    for cookie in cookie_jar.jar:
        domain = cookie.domain or ""
        if not _chrome_cookie_matches_penny_domain(domain):
            continue
        cookies_payload.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": domain,
                "path": cookie.path or "/",
                "expires": int(cookie.expires) if cookie.expires else -1,
                "httpOnly": "HttpOnly" in getattr(cookie, "_rest", {}),
                "secure": bool(cookie.secure),
            }
        )
    updated["cookies"] = cookies_payload
    if "origins" not in updated or not isinstance(updated.get("origins"), list):
        updated["origins"] = []
    return _validate_storage_state_payload(updated)


def _load_fixture_records(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path)
    records = payload.get("records")
    if not isinstance(records, list):
        raise PennyPluginError(f"Penny fixture file {path} must contain a records list", code="contract_violation")
    return [dict(record) for record in records]


def _merchant_label(options: Mapping[str, Any]) -> str:
    label = str(options.get("merchant_label") or "").strip()
    return label or DEFAULT_MERCHANT_NAME


def _candidate_home_directories() -> tuple[Path, ...]:
    candidates: list[Path] = []
    seen: set[str] = set()
    if os.name != "nt":
        with suppress(Exception):
            import pwd

            home = Path(pwd.getpwuid(os.getuid()).pw_dir).expanduser().resolve()
            marker = str(home)
            if marker not in seen:
                seen.add(marker)
                candidates.append(home)
    for env_key in ("HOME", "USERPROFILE"):
        raw = os.environ.get(env_key, "").strip()
        if not raw:
            continue
        home = Path(raw).expanduser().resolve()
        marker = str(home)
        if marker in seen:
            continue
        seen.add(marker)
        candidates.append(home)
    return tuple(candidates)


def _default_chrome_user_data_dir() -> Path | None:
    if sys.platform == "darwin":
        for home in _candidate_home_directories():
            candidate = (home / "Library" / "Application Support" / "Google" / "Chrome").resolve()
            if candidate.exists():
                return candidate
        return None
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            candidate = (Path(local_app_data) / "Google" / "Chrome" / "User Data").resolve()
            if candidate.exists():
                return candidate
        return None
    for home in _candidate_home_directories():
        candidate = (home / ".config" / "google-chrome").resolve()
        if candidate.exists():
            return candidate
        chromium_candidate = (home / ".config" / "chromium").resolve()
        if chromium_candidate.exists():
            return chromium_candidate
    return None


def _chrome_user_data_dir_for_options(options: Mapping[str, Any]) -> Path:
    explicit = _resolve_optional_path(options.get("chrome_user_data_dir"))
    if explicit is not None:
        return explicit
    detected = _default_chrome_user_data_dir()
    if detected is None:
        raise PennyPluginError(
            "Penny Chrome-session import requires chrome_user_data_dir to be configured on this host.",
            code="auth_required",
        )
    return detected


def _chrome_cookie_db_path(source_user_data_dir: Path, profile_name: str) -> Path:
    candidates = (
        source_user_data_dir / profile_name / "Cookies",
        source_user_data_dir / profile_name / "Network" / "Cookies",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise PennyPluginError(
        f"Penny Chrome-session import could not find the Chrome cookie database. Looked in: {searched}",
        code="auth_required",
    )


def _chrome_safe_storage_password() -> str:
    if sys.platform == "darwin":
        with suppress(Exception):
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-w",
                    "-s",
                    _CHROME_SAFE_STORAGE_SERVICE,
                    "-a",
                    _CHROME_SAFE_STORAGE_ACCOUNT,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            password = result.stdout.strip()
            if password:
                return password
    raise PennyPluginError(
        "Penny Chrome-session import could not read the Chrome Safe Storage secret on this host.",
        code="auth_required",
    )


def _chrome_cookie_encryption_key() -> bytes:
    password = _chrome_safe_storage_password().encode("utf-8")
    return hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, dklen=16)


def _chrome_user_agent() -> str:
    if sys.platform == "darwin" and _DEFAULT_CHROME_EXECUTABLE.exists():
        with suppress(Exception):
            version = subprocess.check_output([str(_DEFAULT_CHROME_EXECUTABLE), "--version"], text=True).strip()
            chrome_version = version.split()[-1]
            if chrome_version:
                return (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    f"Chrome/{chrome_version} Safari/537.36"
                )
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )


def _chrome_cookie_db_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("select value from meta where key = 'version'").fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _decrypt_chrome_cookie_value(
    *,
    encrypted_value: bytes,
    host_key: str,
    key: bytes,
    cookie_db_version: int,
) -> str:
    if not encrypted_value:
        return ""
    if not encrypted_value.startswith(b"v10"):
        return encrypted_value.decode("utf-8")
    cipher = Cipher(algorithms.AES(key), modes.CBC(b" " * 16))
    decryptor = cipher.decryptor()
    padded = decryptor.update(encrypted_value[3:]) + decryptor.finalize()
    if not padded:
        return ""
    pad_length = padded[-1]
    if pad_length <= 0 or pad_length > 16:
        raise PennyPluginError(
            "Penny Chrome-session import read an invalid encrypted cookie payload.",
            code="auth_required",
        )
    plaintext = padded[:-pad_length]
    host_digest = hashlib.sha256(host_key.encode("utf-8")).digest()
    if cookie_db_version >= 24 and plaintext.startswith(host_digest):
        plaintext = plaintext[len(host_digest) :]
    return plaintext.decode("utf-8")


def _chrome_cookie_matches_penny_domain(host_key: str) -> bool:
    normalized = host_key.lstrip(".").lower()
    return normalized == "penny.de" or normalized.endswith(".penny.de")


def _chrome_cookie_expires_unix_seconds(expires_utc: int) -> int:
    if expires_utc <= 0:
        return -1
    return max(int((expires_utc / 1_000_000) - _CHROME_COOKIE_EPOCH_OFFSET_SECONDS), -1)


def _playwright_cookie_same_site(raw_value: object) -> str | None:
    mapping = {
        -1: None,
        0: "None",
        1: "Lax",
        2: "Strict",
    }
    try:
        normalized = int(raw_value)
    except (TypeError, ValueError):
        return None
    return mapping.get(normalized)


def _penny_cookie_rows_to_storage_state(
    rows: list[sqlite3.Row],
    *,
    decryption_key: bytes,
    cookie_db_version: int,
) -> dict[str, Any]:
    cookies: list[dict[str, Any]] = []
    for row in rows:
        host_key = str(row["host_key"] or "")
        if not _chrome_cookie_matches_penny_domain(host_key):
            continue
        name = str(row["name"] or "")
        if not name:
            continue
        raw_value = row["value"]
        if isinstance(raw_value, bytes):
            value = raw_value.decode("utf-8")
        else:
            value = str(raw_value or "")
        if not value:
            encrypted_value = row["encrypted_value"]
            if not isinstance(encrypted_value, bytes):
                encrypted_value = bytes(encrypted_value or b"")
            value = _decrypt_chrome_cookie_value(
                encrypted_value=encrypted_value,
                host_key=host_key,
                key=decryption_key,
                cookie_db_version=cookie_db_version,
            )
        if not value:
            continue
        cookie_payload: dict[str, Any] = {
            "name": name,
            "value": value,
            "domain": host_key,
            "path": str(row["path"] or "/"),
            "httpOnly": bool(row["is_httponly"]),
            "secure": bool(row["is_secure"]),
            "expires": _chrome_cookie_expires_unix_seconds(int(row["expires_utc"] or 0)),
        }
        same_site = _playwright_cookie_same_site(row["samesite"])
        if same_site is not None:
            cookie_payload["sameSite"] = same_site
        cookies.append(cookie_payload)
    return _validate_storage_state_payload({"cookies": cookies, "origins": [], "user_agent": _chrome_user_agent()})


def _verify_penny_storage_state(*, storage_state: Mapping[str, Any], start_url: str) -> dict[str, Any]:
    try:
        with httpx.Client(
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=True,
            cookies=_storage_state_to_httpx_cookies(storage_state),
            headers={"User-Agent": str(storage_state.get("user_agent") or _chrome_user_agent())},
        ) as client:
            response = client.get(start_url)
            final_url = str(response.url)
            if response.status_code in {401, 403}:
                raise PennyPluginError(
                    "Penny imported browser session is not authenticated against the account site.",
                    code="auth_required",
                )
            if "/protocol/openid-connect/auth" in final_url:
                raise PennyPluginError(
                    "Penny imported browser session redirected back to login.",
                    code="auth_required",
                )
            if "account-ui" not in final_url and "/realms/penny/account" not in final_url:
                raise PennyPluginError(
                    f"Penny imported browser session landed on an unexpected page: {final_url}",
                    code="auth_required",
                )
            return _storage_state_with_httpx_cookies(storage_state, client.cookies)
    except PennyPluginError:
        raise
    except Exception as exc:
        raise PennyPluginError(
            f"Failed to validate imported Penny browser session: {exc}",
            code="auth_required",
        ) from exc


def _capture_storage_state_from_running_chrome_session(
    *,
    source_user_data_dir: Path,
    profile_name: str,
    start_url: str,
) -> dict[str, Any]:
    cookie_db_path = _chrome_cookie_db_path(source_user_data_dir, profile_name)
    decryption_key = _chrome_cookie_encryption_key()
    with TemporaryDirectory(prefix="penny-chrome-cookies-") as temp_dir:
        temp_cookie_db = Path(temp_dir) / "Cookies"
        shutil.copy2(cookie_db_path, temp_cookie_db)
        connection = sqlite3.connect(temp_cookie_db)
        connection.row_factory = sqlite3.Row
        try:
            cookie_db_version = _chrome_cookie_db_version(connection)
            rows = list(
                connection.execute(
                    """
                    select host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite
                    from cookies
                    where host_key like '%penny.de%'
                    order by host_key, name
                    """
                )
            )
        finally:
            connection.close()
    storage_state = _penny_cookie_rows_to_storage_state(
        rows,
        decryption_key=decryption_key,
        cookie_db_version=cookie_db_version,
    )
    return _verify_penny_storage_state(storage_state=storage_state, start_url=start_url)


def _money_to_cents(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    normalized = str(value).strip().replace("EUR", "").replace("eur", "").replace(" ", "").replace("€", "")
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    try:
        amount = Decimal(normalized)
    except Exception:
        return 0
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz=UTC)
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.now(tz=UTC)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _format_quantity(value: Any) -> str:
    try:
        numeric = Decimal(str(value))
    except Exception:
        return "1"
    if numeric == numeric.to_integral():
        return str(int(numeric))
    return format(numeric.normalize(), "f")


def _format_address(address: Mapping[str, Any] | None) -> str | None:
    if not isinstance(address, Mapping):
        return None
    parts = [
        str(address.get("street") or "").strip(),
        " ".join(
            part
            for part in [
                str(address.get("postalCode") or "").strip(),
                str(address.get("city") or "").strip(),
            ]
            if part
        ),
        str(address.get("countryCode") or "").strip(),
    ]
    normalized = [part for part in parts if part]
    if not normalized:
        return None
    return ", ".join(normalized)


def _looks_like_deposit(name: str, raw_item: Mapping[str, Any]) -> bool:
    if isinstance(raw_item.get("isDeposit"), bool):
        return bool(raw_item.get("isDeposit"))
    lowered = name.lower()
    return "pfand" in lowered or "deposit" in lowered


def _cents_to_amount_text(value: int) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(int(value))
    euros, cents = divmod(absolute, 100)
    return f"{sign}{euros}.{cents:02d}"


def _clean_pdf_line(value: Any) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def _parse_vat_rate_text(value: str) -> str:
    normalized = value.replace(",", ".")
    try:
        numeric = Decimal(normalized)
    except Exception:
        return f"{value}%"
    if numeric == numeric.to_integral():
        return f"{int(numeric)}%"
    return f"{format(numeric.normalize(), 'f')}%"


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        raise PennyPluginError("Penny eBon PDF payload was empty", code="upstream_error")
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise PennyPluginError(
            "Penny live eBon parsing requires pypdf in the desktop Python environment.",
            code="upstream_error",
        ) from exc
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        extracted = "\n".join((page.extract_text() or "").strip() for page in reader.pages)
    except Exception as exc:
        raise PennyPluginError(
            f"Failed to read Penny eBon PDF text: {exc}",
            code="upstream_error",
            retryable=True,
        ) from exc
    normalized = extracted.strip()
    if not normalized:
        raise PennyPluginError(
            "Penny eBon PDF did not contain readable text.",
            code="upstream_error",
        )
    return normalized


def _parse_penny_ebon_pdf_text(
    text: str,
    *,
    fallback_timestamp: str | None = None,
    merchant_label: str = DEFAULT_MERCHANT_NAME,
) -> dict[str, Any]:
    lines = [_clean_pdf_line(line) for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise PennyPluginError("Penny eBon PDF text was empty", code="contract_violation")

    header_lines: list[str] = []
    saw_banner = False
    vat_rates = dict(_PENNY_DEFAULT_VAT_RATES)
    total_gross_cents = 0
    discount_total_cents = 0
    transaction_discount_rows: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    current_item: dict[str, Any] | None = None
    receipt_number: str | None = None
    market_id: str | None = None
    purchased_at = fallback_timestamp
    purchased_date: str | None = None
    purchased_time: str | None = None
    payment_method: str | None = None
    payment_amount_cents = 0
    savings_cents = 0

    for line in lines:
        if "P E N N Y" in line:
            saw_banner = True
            continue
        if saw_banner and line == "EUR":
            continue
        if saw_banner and line.startswith("UID Nr."):
            saw_banner = False
            continue
        if saw_banner:
            header_lines.append(line)

        vat_match = _PENNY_VAT_RATE_RE.match(line)
        if vat_match:
            vat_rates[vat_match.group("code")] = _parse_vat_rate_text(vat_match.group("rate"))
            continue

        date_match = _PENNY_DATE_LINE_RE.match(line)
        if date_match:
            purchased_date = date_match.group("value")
            continue
        time_match = _PENNY_TIME_LINE_RE.match(line)
        if time_match:
            purchased_time = time_match.group("value")
            continue

        receipt_match = _PENNY_RECEIPT_NUMBER_RE.match(line)
        if receipt_match:
            receipt_number = receipt_match.group("value")
            continue
        market_match = _PENNY_MARKET_ID_RE.match(line)
        if market_match:
            market_id = market_match.group("value")
            continue

        payment_match = _PENNY_PAYMENT_LINE_RE.match(line)
        if payment_match:
            payment_method = payment_match.group("method").strip().lower()
            payment_amount_cents = _money_to_cents(payment_match.group("amount"))
            continue

        savings_match = _PENNY_SAVINGS_LINE_RE.match(line)
        if savings_match:
            savings_cents = _money_to_cents(savings_match.group("amount"))
            continue

        sum_match = _PENNY_SUM_LINE_RE.match(line)
        if sum_match:
            total_gross_cents = _money_to_cents(sum_match.group("amount"))
            continue

        item_match = _PENNY_ITEM_LINE_RE.match(line)
        if not item_match:
            continue
        name = item_match.group("name").strip()
        amount_cents = _money_to_cents(item_match.group("amount"))
        vat_rate = vat_rates.get(item_match.group("vat"))
        if amount_cents < 0:
            discount_payload = {
                "id": f"discount-{len(items)}-{len((current_item or {}).get('discounts') or []) + 1}",
                "label": name,
                "amount": _cents_to_amount_text(abs(amount_cents)),
                "subkind": "promotion",
                "funded_by": "merchant",
            }
            if current_item is not None:
                current_item.setdefault("discounts", []).append(discount_payload)
            else:
                transaction_discount_rows.append(discount_payload)
            discount_total_cents += abs(amount_cents)
            continue

        current_item = {
            "id": f"line-{len(items) + 1}",
            "name": name,
            "quantity": "1",
            "unit": "pcs",
            "unitPrice": _cents_to_amount_text(amount_cents),
            "lineTotal": _cents_to_amount_text(amount_cents),
            "vatRate": vat_rate,
            "discounts": [],
        }
        if _looks_like_deposit(name, current_item):
            current_item["isDeposit"] = True
        items.append(current_item)

    if purchased_at is None and purchased_date and purchased_time:
        try:
            purchased_at = datetime.strptime(
                f"{purchased_date} {purchased_time}",
                "%d.%m.%Y %H:%M:%S",
            ).replace(tzinfo=UTC).isoformat()
        except ValueError:
            purchased_at = None

    if total_gross_cents <= 0:
        fallback_sum = payment_amount_cents or sum(_money_to_cents(item.get("lineTotal")) for item in items)
        total_gross_cents = fallback_sum
    if discount_total_cents <= 0 and savings_cents > 0:
        discount_total_cents = savings_cents

    street = None
    postal_code = None
    city = None
    if header_lines:
        street = header_lines[0]
    if len(header_lines) > 1:
        postal_match = _PENNY_POSTAL_CITY_RE.match(header_lines[1])
        if postal_match:
            postal_code = postal_match.group("postal")
            city = postal_match.group("city")

    store_name = merchant_label
    if market_id:
        store_name = f"{merchant_label} Markt {market_id}"

    payments = []
    if payment_method and payment_amount_cents > 0:
        payments.append(
            {
                "method": payment_method,
                "amount": _cents_to_amount_text(payment_amount_cents),
            }
        )

    return {
        "purchasedAt": purchased_at,
        "receiptNumber": receipt_number,
        "store": {
            "id": market_id or store_name,
            "name": store_name,
            "address": {
                "street": street,
                "postalCode": postal_code,
                "city": city,
                "countryCode": "DE",
            },
        },
        "totals": {
            "gross": _cents_to_amount_text(total_gross_cents),
            "discount": _cents_to_amount_text(discount_total_cents),
            "currency": "EUR",
        },
        "payments": payments,
        "discounts": transaction_discount_rows,
        "items": items,
    }


class PennyEbonApiClient:
    def __init__(
        self,
        *,
        access_token: str,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        api_base_url: str = DEFAULT_EBON_API_BASE_URL,
        user_agent: str | None = None,
    ) -> None:
        self._access_token = access_token
        self._timeout_seconds = timeout_seconds
        self._api_base_url = api_base_url.rstrip("/")
        self._user_agent = user_agent or _chrome_user_agent()

    def list_ebons(self, rewe_id: str, *, page: int, page_size: int) -> Mapping[str, Any]:
        url = f"{self._customer_base_url(rewe_id)}/ebons"
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True) as client:
                response = client.get(
                    url,
                    params={"objectsPerPage": page_size, "page": page},
                    headers=self._headers(accept="application/json, text/plain, */*"),
                )
        except Exception as exc:
            raise PennyPluginError(
                f"Failed to list Penny eBons: {exc}",
                code="upstream_error",
                retryable=True,
            ) from exc
        return self._decode_json_response(response, operation="list Penny eBons")

    def fetch_pdf(self, rewe_id: str, record_ref: str) -> bytes:
        url = self.pdf_url(rewe_id, record_ref)
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True) as client:
                response = client.get(
                    url,
                    headers=self._headers(accept="application/pdf,application/octet-stream;q=0.9,*/*;q=0.8"),
                )
        except Exception as exc:
            raise PennyPluginError(
                f"Failed to fetch Penny eBon PDF: {exc}",
                code="upstream_error",
                retryable=True,
            ) from exc
        if response.status_code in {401, 403}:
            raise PennyPluginError(
                "Penny rejected the eBon PDF request. Re-run start_auth to refresh the stored OAuth session.",
                code="auth_required",
            )
        if response.status_code >= 400:
            raise PennyPluginError(
                f"Penny eBon PDF request failed with HTTP {response.status_code}.",
                code="upstream_error",
                retryable=response.status_code >= 500,
            )
        return response.content

    def pdf_url(self, rewe_id: str, record_ref: str) -> str:
        return f"{self._customer_base_url(rewe_id)}/ebons/{urllib.parse.quote(record_ref, safe='')}/pdf"

    def _customer_base_url(self, rewe_id: str) -> str:
        return f"{self._api_base_url}/api/tenants/penny/customers/{urllib.parse.quote(rewe_id, safe='')}"

    def _headers(self, *, accept: str) -> dict[str, str]:
        return {
            "Accept": accept,
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": self._user_agent,
            "correlation-id": secrets.token_hex(16),
        }

    @staticmethod
    def _decode_json_response(response: httpx.Response, *, operation: str) -> Mapping[str, Any]:
        if response.status_code in {401, 403}:
            raise PennyPluginError(
                f"Penny rejected the request to {operation}. Re-run start_auth to refresh the stored OAuth session.",
                code="auth_required",
            )
        if response.status_code >= 400:
            raise PennyPluginError(
                f"Penny {operation} failed with HTTP {response.status_code}.",
                code="upstream_error",
                retryable=response.status_code >= 500,
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise PennyPluginError(
                f"Penny {operation} did not return valid JSON: {exc}",
                code="contract_violation",
            ) from exc
        if not isinstance(payload, Mapping):
            raise PennyPluginError(
                f"Penny {operation} response was not a JSON object.",
                code="contract_violation",
            )
        return payload


class PennyOidcClient:
    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        discovery_url: str = DEFAULT_DISCOVERY_URL,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._discovery_url = discovery_url

    def load_metadata(self) -> Mapping[str, Any]:
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True) as client:
                response = client.get(self._discovery_url)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise PennyPluginError(
                f"Failed to load Penny OIDC metadata from {self._discovery_url}: {exc}",
                code="upstream_error",
                retryable=True,
            ) from exc
        if not isinstance(payload, Mapping):
            raise PennyPluginError(
                "Penny OIDC discovery payload is not a JSON object",
                code="contract_violation",
            )
        return payload

    def resolve_endpoints(self) -> tuple[str, str]:
        metadata = self.load_metadata()
        auth_endpoint = str(metadata.get("authorization_endpoint") or DEFAULT_AUTH_ENDPOINT).strip()
        token_endpoint = str(metadata.get("token_endpoint") or DEFAULT_TOKEN_ENDPOINT).strip()
        if not auth_endpoint or not token_endpoint:
            raise PennyPluginError(
                "Penny OIDC metadata did not include both authorization and token endpoints",
                code="contract_violation",
            )
        return auth_endpoint, token_endpoint

    def exchange_code(self, code: str, *, pending: PendingAuthFlow) -> OauthSession:
        payload = self._post_token(
            pending.token_endpoint,
            {
                "grant_type": "authorization_code",
                "client_id": pending.client_id,
                "code": code,
                "redirect_uri": pending.redirect_uri,
                "code_verifier": pending.verifier,
            },
        )
        return OauthSession(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or ""),
            expires_at=_expires_at_from_now(self._coerce_expires_in(payload.get("expires_in"))),
            scope=str(payload.get("scope") or pending.scope or "").strip() or None,
            token_type=str(payload.get("token_type") or "").strip() or None,
            id_token=str(payload.get("id_token") or "").strip() or None,
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            auth_endpoint=pending.auth_endpoint,
            token_endpoint=pending.token_endpoint,
            discovery_url=self._discovery_url,
        )

    def refresh(self, oauth: OauthSession) -> OauthSession:
        if not oauth.refresh_token:
            raise PennyPluginError("Penny session is missing a refresh token", code="auth_required")
        payload = self._post_token(
            oauth.token_endpoint,
            {
                "grant_type": "refresh_token",
                "client_id": oauth.client_id,
                "refresh_token": oauth.refresh_token,
            },
        )
        return OauthSession(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or oauth.refresh_token),
            expires_at=_expires_at_from_now(self._coerce_expires_in(payload.get("expires_in"))),
            scope=str(payload.get("scope") or oauth.scope or "").strip() or None,
            token_type=str(payload.get("token_type") or oauth.token_type or "").strip() or None,
            id_token=str(payload.get("id_token") or oauth.id_token or "").strip() or None,
            client_id=oauth.client_id,
            redirect_uri=oauth.redirect_uri,
            auth_endpoint=oauth.auth_endpoint,
            token_endpoint=oauth.token_endpoint,
            discovery_url=oauth.discovery_url,
        )

    def _post_token(self, endpoint: str, form: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=True) as client:
                response = client.post(
                    endpoint,
                    data=dict(form),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise PennyPluginError(
                f"Penny token exchange failed against {endpoint}: {exc}",
                code="auth_required",
                retryable=True,
            ) from exc
        if not isinstance(payload, Mapping):
            raise PennyPluginError("Penny token response is not a JSON object", code="contract_violation")
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise PennyPluginError("Penny token response did not include an access_token", code="auth_required")
        return payload

    @staticmethod
    def _coerce_expires_in(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None


class PennyReceiptPlugin(ReceiptConnector):
    def __init__(self) -> None:
        self._manifest = ConnectorManifest.model_validate(_manifest_definition())

    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        validated = validate_receipt_action_request(request)
        handler = getattr(self, f"_handle_{validated.action}")
        try:
            return handler(validated)
        except PennyPluginError as exc:
            return self._error(validated.action, code=exc.code, message=str(exc), retryable=exc.retryable)

    def _handle_get_manifest(self, request: ReceiptActionRequest) -> dict[str, Any]:
        return self._ok(
            request.action,
            GetManifestOutput(manifest=self._manifest).model_dump(mode="python"),
        )

    def _handle_healthcheck(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        diagnostics = self._diagnostics_payload(context)
        if fixture_file is not None:
            fixture_records = _load_fixture_records(fixture_file)
            return self._ok(
                request.action,
                HealthcheckOutput(
                    healthy=True,
                    detail="Penny fixture mode is ready for offline connector validation.",
                    sample_size=len(fixture_records),
                    diagnostics=diagnostics,
                ).model_dump(mode="python"),
            )
        state_path = self._state_file(context)
        session = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        healthy = (session is not None and not self._session_expired(session)) or browser_session is not None
        detail = (
            "Penny auth state is stored and the direct eBon backend is ready for one-time receipt sync."
            if healthy
            else "Penny requires authentication before live eBon discovery can run."
        )
        return self._ok(
            request.action,
            HealthcheckOutput(
                healthy=healthy,
                detail=detail,
                diagnostics=diagnostics,
            ).model_dump(mode="python"),
        )

    def _handle_get_auth_status(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            output = GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=("start_auth",),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Fixture mode bypasses live Penny auth for offline connector validation.",
                metadata={
                    "fixture_mode": True,
                    "fixture_file": str(fixture_file),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))

        state_path = self._state_file(context)
        state = _load_state(state_path)
        pending = state.get("pending_auth")
        oauth = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        if oauth is not None and self._session_expired(oauth):
            output = GetAuthStatusOutput(
                status="expired",
                is_authenticated=False,
                available_actions=("start_auth",),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Stored Penny auth exists but the access token is expired.",
                metadata={
                    "state_file": str(state_path),
                    "expires_at": oauth.expires_at,
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        if oauth is not None:
            output = GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=("start_auth",),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Penny OIDC state is stored in plugin-local runtime storage.",
                metadata={
                    "state_file": str(state_path),
                    "expires_at": oauth.expires_at,
                    "subject": state.get("profile", {}).get("sub"),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        if browser_session is not None:
            output = GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=("start_auth",),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Penny browser session was imported from normal Chrome and stored in plugin-local runtime storage.",
                metadata={
                    "state_file": str(state_path),
                    "bootstrap_source": browser_session.get("bootstrap_source"),
                    "authenticated_at": browser_session.get("authenticated_at"),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        if isinstance(pending, Mapping):
            output = GetAuthStatusOutput(
                status="pending",
                is_authenticated=False,
                available_actions=("cancel_auth", "confirm_auth"),
                implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
                compatibility_actions=("start_auth", "cancel_auth"),
                reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
                detail="Shared browser auth is waiting for the Penny OAuth callback.",
                metadata={
                    "state_file": str(state_path),
                    "flow_id": str(pending.get("flow_id") or ""),
                },
            )
            return self._ok(request.action, output.model_dump(mode="python"))
        output = GetAuthStatusOutput(
            status="requires_auth",
            is_authenticated=False,
            available_actions=("start_auth",),
            implemented_actions=("start_auth", "cancel_auth", "confirm_auth"),
            compatibility_actions=("start_auth", "cancel_auth"),
            reserved_actions=("start_auth", "cancel_auth", "confirm_auth"),
            detail="No Penny auth state is stored yet.",
            metadata={"state_file": str(state_path)},
        )
        return self._ok(request.action, output.model_dump(mode="python"))

    def _handle_start_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="Fixture mode bypasses live Penny auth.",
                    metadata={"fixture_mode": True, "fixture_file": str(fixture_file)},
                ).model_dump(mode="python"),
            )

        state_path = self._state_file(context)
        state = _load_state(state_path)
        force_reauth = _bool_option(options, "force_reauth", False)
        existing = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        if force_reauth:
            state.pop("oauth", None)
            state.pop("browser_session", None)
            state.pop("pending_auth", None)
            _persist_state(state_path, state)
        if existing is not None and not self._session_expired(existing) and not force_reauth:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="Penny is already authenticated. Set force_reauth=true to replace the stored session.",
                    metadata={"state_file": str(state_path), "expires_at": existing.expires_at},
                ).model_dump(mode="python"),
            )
        if browser_session is not None and not force_reauth:
            try:
                refreshed = _verify_penny_storage_state(
                    storage_state=browser_session.get("storage_state") or {},
                    start_url=DEFAULT_ACCOUNT_URL,
                )
            except PennyPluginError:
                state.pop("browser_session", None)
                _persist_state(state_path, state)
            else:
                browser_session["storage_state"] = refreshed
                state["browser_session"] = browser_session
                _persist_state(state_path, state)
                return self._ok(
                    request.action,
                    AuthLifecycleOutput(
                        status="no_op",
                        detail="Penny normal-Chrome browser session is still valid. Set force_reauth=true to replace it.",
                        metadata={
                            "state_file": str(state_path),
                            "bootstrap_source": browser_session.get("bootstrap_source"),
                        },
                    ).model_dump(mode="python"),
                )
        import_storage_state = _resolve_optional_path(options.get("import_storage_state_file"))
        if import_storage_state is not None:
            imported_state = _verify_penny_storage_state(
                storage_state=_load_storage_state_file(import_storage_state),
                start_url=DEFAULT_ACCOUNT_URL,
            )
            state["browser_session"] = {
                "storage_state": imported_state,
                "authenticated_at": _iso_now(),
                "bootstrap_source": "import_storage_state_file",
                "import_storage_state_file": str(import_storage_state),
            }
            state.pop("pending_auth", None)
            _persist_state(state_path, state)
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="confirmed",
                    detail="Penny browser session was imported from an existing storage-state file.",
                    metadata={
                        "state_file": str(state_path),
                        "import_storage_state_file": str(import_storage_state),
                        "bootstrap_source": "import_storage_state_file",
                    },
                ).model_dump(mode="python"),
            )
        chrome_cookie_export_requested = (
            _bool_option(options, "chrome_cookie_export", True)
            if not _option_present(options, "chrome_cookie_export")
            else _bool_option(options, "chrome_cookie_export", False)
        )
        chrome_cookie_export_error: str | None = None
        if chrome_cookie_export_requested:
            try:
                source_user_data_dir = _chrome_user_data_dir_for_options(options)
                profile_name = _string_option(options, "chrome_profile_name", "Default")
                imported_state = _capture_storage_state_from_running_chrome_session(
                    source_user_data_dir=source_user_data_dir,
                    profile_name=profile_name,
                    start_url=DEFAULT_ACCOUNT_URL,
                )
            except PennyPluginError as exc:
                chrome_cookie_export_error = str(exc)
            else:
                state["browser_session"] = {
                    "storage_state": imported_state,
                    "authenticated_at": _iso_now(),
                    "bootstrap_source": "chrome_cookie_export",
                    "chrome_user_data_dir": str(source_user_data_dir),
                    "chrome_profile_name": profile_name,
                }
                state.pop("pending_auth", None)
                _persist_state(state_path, state)
                return self._ok(
                    request.action,
                    AuthLifecycleOutput(
                        status="confirmed",
                        detail=(
                            "Penny browser session was imported from the running normal Chrome session. "
                            "No separate login window was opened."
                        ),
                        metadata={
                            "state_file": str(state_path),
                            "chrome_user_data_dir": str(source_user_data_dir),
                            "chrome_profile_name": profile_name,
                            "bootstrap_source": "chrome_cookie_export",
                        },
                    ).model_dump(mode="python"),
                )
        if isinstance(state.get("pending_auth"), Mapping) and not force_reauth:
            pending_flow_id = str(state["pending_auth"].get("flow_id") or "")
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="pending",
                    flow_id=pending_flow_id or None,
                    next_poll_after_seconds=2,
                    detail="A Penny auth flow is already pending. Cancel it first if you want to restart.",
                ).model_dump(mode="python"),
            )

        timeout_seconds = _int_option(options, "auth_timeout_seconds", DEFAULT_AUTH_TIMEOUT_SECONDS)
        oidc = PennyOidcClient(timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        auth_endpoint = DEFAULT_AUTH_ENDPOINT
        token_endpoint = DEFAULT_TOKEN_ENDPOINT
        discovery_warning = None
        try:
            auth_endpoint, token_endpoint = oidc.resolve_endpoints()
        except PennyPluginError as exc:
            discovery_warning = str(exc)

        verifier, challenge = _pkce_pair()
        state_value = secrets.token_urlsafe(24)
        flow_id = secrets.token_hex(12)
        pending = PendingAuthFlow(
            flow_id=flow_id,
            created_at=_iso_now(),
            verifier=verifier,
            state=state_value,
            auth_endpoint=auth_endpoint,
            token_endpoint=token_endpoint,
            client_id=DEFAULT_CLIENT_ID,
            redirect_uri=DEFAULT_REDIRECT_URI,
            scope=DEFAULT_SCOPE,
        )
        start_url = (
            auth_endpoint
            + "?"
            + urllib.parse.urlencode(
                {
                    "client_id": pending.client_id,
                    "redirect_uri": pending.redirect_uri,
                    "response_type": "code",
                    "scope": pending.scope,
                    "state": pending.state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "app_container": "android",
                }
            )
        )
        state["pending_auth"] = asdict(pending)
        _persist_state(state_path, state)
        plan = AuthBrowserPlan(
            start_url=start_url,
            callback_url_prefixes=(pending.redirect_uri,),
            expected_callback_state=pending.state,
            timeout_seconds=timeout_seconds,
            wait_until="domcontentloaded",
            interactive=True,
            capture_storage_state=False,
        )
        metadata = build_auth_browser_metadata(flow_id=flow_id, plan=plan)
        if discovery_warning is not None:
            metadata["warnings"] = [discovery_warning]
        if chrome_cookie_export_error is not None:
            metadata.setdefault("warnings", []).append(chrome_cookie_export_error)
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="started",
                flow_id=flow_id,
                detail=(
                    "Penny could not reuse a normal Chrome session automatically, so the shared-browser PKCE fallback started. "
                    "The account login uses Cloudflare Turnstile and redirects back to the app callback URL."
                ),
                metadata=metadata,
            ).model_dump(mode="python"),
        )

    def _handle_cancel_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="Fixture mode does not keep a pending Penny auth flow.",
                    metadata={"fixture_mode": True},
                ).model_dump(mode="python"),
            )

        state_path = self._state_file(context)
        state = _load_state(state_path)
        if "pending_auth" not in state:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="No pending Penny auth flow exists.",
                ).model_dump(mode="python"),
            )
        state.pop("pending_auth", None)
        _persist_state(state_path, state)
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="canceled",
                detail="Pending Penny auth flow was canceled.",
            ).model_dump(mode="python"),
        )

    def _handle_confirm_auth(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="confirmed",
                    detail="Fixture mode bypasses live Penny auth confirmation.",
                    metadata={"fixture_mode": True, "fixture_file": str(fixture_file)},
                ).model_dump(mode="python"),
            )

        state_path = self._state_file(context)
        state = _load_state(state_path)
        pending_payload = state.get("pending_auth")
        if not isinstance(pending_payload, Mapping):
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="no_op",
                    detail="No pending Penny auth flow exists.",
                ).model_dump(mode="python"),
            )
        pending = PendingAuthFlow(**dict(pending_payload))
        browser_result = parse_auth_browser_runtime_context(context.runtime_context)
        if browser_result is None:
            return self._ok(
                request.action,
                AuthLifecycleOutput(
                    status="pending",
                    flow_id=pending.flow_id,
                    next_poll_after_seconds=2,
                    detail="Waiting for the Penny OAuth callback from the shared browser.",
                ).model_dump(mode="python"),
            )
        if browser_result.flow_id != pending.flow_id:
            return self._error(
                request.action,
                code="contract_violation",
                message="Browser callback flow_id did not match the pending Penny auth flow.",
            )

        code, state_value, error = _parse_redirect(browser_result.callback_url or browser_result.final_url)
        if error:
            return self._error(
                request.action,
                code="auth_required",
                message=f"Penny auth returned an OAuth error: {error}",
            )
        if state_value != pending.state:
            return self._error(
                request.action,
                code="auth_required",
                message="Penny auth callback state did not match the pending auth flow.",
            )
        if not code:
            return self._error(
                request.action,
                code="auth_required",
                message="Penny auth callback did not include an authorization code.",
            )

        timeout_seconds = _int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        oidc = PennyOidcClient(timeout_seconds=timeout_seconds)
        oauth = oidc.exchange_code(code, pending=pending)
        profile = _profile_from_oauth(oauth)
        state["oauth"] = asdict(oauth)
        state["profile"] = profile
        state["authenticated_at"] = _iso_now()
        state["last_callback_url"] = browser_result.callback_url
        if browser_result.storage_state is not None:
            state["last_browser_storage_state"] = browser_result.storage_state
        state.pop("pending_auth", None)
        _persist_state(state_path, state)
        return self._ok(
            request.action,
            AuthLifecycleOutput(
                status="confirmed",
                flow_id=browser_result.flow_id,
                detail="Stored Penny OAuth state for direct Penny eBon backend access.",
                metadata={
                    "state_file": str(state_path),
                    "subject": profile.get("sub"),
                    "email": profile.get("email"),
                    "account_url": DEFAULT_ACCOUNT_URL,
                },
            ).model_dump(mode="python"),
        )

    def _handle_discover_records(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            records = _load_fixture_records(fixture_file)
            limit = request.input.limit or DEFAULT_DISCOVERY_LIMIT
            discovered = []
            for record in records[:limit]:
                purchased_at = _parse_datetime(record.get("purchasedAt"))
                discovered.append(
                    RecordReference(
                        record_ref=str(record.get("id") or ""),
                        discovered_at=purchased_at,
                        metadata={"fixture": True},
                    )
                )
            return self._ok(
                request.action,
                DiscoverRecordsOutput(records=discovered, next_cursor=None).model_dump(mode="python"),
            )

        state_path = self._state_file(context)
        oauth = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        if oauth is None and browser_session is None:
            return self._error(
                request.action,
                code="auth_required",
                message="Run start_auth and confirm_auth before discovering Penny records.",
            )
        if oauth is None:
            return self._error(
                request.action,
                code="auth_required",
                message=(
                    "Penny direct eBon sync requires stored OAuth tokens. "
                    "Re-run start_auth with force_reauth=true and complete the shared-browser callback flow."
                ),
            )
        try:
            output = self._discover_live_records(request, context, oauth, state_path)
        except PennyPluginError as exc:
            return self._error(request.action, code=exc.code, message=str(exc), retryable=exc.retryable)
        return self._ok(request.action, output.model_dump(mode="python"))

    def _handle_fetch_record(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        if fixture_file is not None:
            for record in _load_fixture_records(fixture_file):
                if str(record.get("id") or "") == request.input.record_ref:
                    return self._ok(
                        request.action,
                        FetchRecordOutput(record_ref=request.input.record_ref, record=record).model_dump(mode="python"),
                    )
            return self._error(
                request.action,
                code="invalid_request",
                message=f"Penny fixture record {request.input.record_ref!r} was not found.",
            )

        state_path = self._state_file(context)
        oauth = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        if oauth is None and browser_session is None:
            return self._error(
                request.action,
                code="auth_required",
                message="Run start_auth and confirm_auth before fetching Penny records.",
            )
        if oauth is None:
            return self._error(
                request.action,
                code="auth_required",
                message=(
                    "Penny direct eBon sync requires stored OAuth tokens. "
                    "Re-run start_auth with force_reauth=true and complete the shared-browser callback flow."
                ),
            )
        try:
            output = self._fetch_live_record(request, context, oauth, state_path)
        except PennyPluginError as exc:
            return self._error(request.action, code=exc.code, message=str(exc), retryable=exc.retryable)
        return self._ok(request.action, output.model_dump(mode="python"))

    def _handle_normalize_record(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        normalized = self._normalize_record(dict(request.input.record), context.connector_options)
        return self._ok(
            request.action,
            NormalizeRecordOutput(normalized_record=normalized).model_dump(mode="python"),
        )

    def _handle_extract_discounts(self, request: ReceiptActionRequest) -> dict[str, Any]:
        discounts = self._extract_discounts(dict(request.input.record))
        return self._ok(
            request.action,
            ExtractDiscountsOutput(discounts=discounts).model_dump(mode="python"),
        )

    def _handle_get_diagnostics(self, request: ReceiptActionRequest) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        return self._ok(
            request.action,
            DiagnosticsOutput(diagnostics=self._diagnostics_payload(context)).model_dump(mode="python"),
        )

    def _normalize_record(
        self,
        record: dict[str, Any],
        options: Mapping[str, Any],
    ) -> NormalizedReceiptRecord:
        record_id = str(record.get("id") or "").strip()
        if not record_id:
            raise PennyPluginError("Penny record did not include an id", code="contract_violation")
        purchased_at = _parse_datetime(record.get("purchasedAt"))
        store = record.get("store")
        if not isinstance(store, Mapping):
            store = {}
        totals = record.get("totals")
        if not isinstance(totals, Mapping):
            totals = {}
        item_rows = record.get("items")
        if not isinstance(item_rows, list) or not item_rows:
            raise PennyPluginError("Penny record did not include any items", code="contract_violation")

        normalized_items: list[NormalizedReceiptItem] = []
        for index, raw_item in enumerate(item_rows, start=1):
            item = dict(raw_item) if isinstance(raw_item, Mapping) else {}
            name = str(item.get("name") or f"Item {index}").strip()
            normalized_items.append(
                NormalizedReceiptItem(
                    line_no=index,
                    name=name,
                    qty=_format_quantity(item.get("quantity")),
                    unit=str(item.get("unit") or "").strip() or None,
                    unit_price_cents=_money_to_cents(item.get("unitPrice")),
                    line_total_cents=_money_to_cents(item.get("lineTotal")),
                    is_deposit=_looks_like_deposit(name, item),
                    vat_rate=str(item.get("vatRate") or "").strip() or None,
                    source_item_id=str(item.get("id") or "").strip() or None,
                    discounts=list(item.get("discounts") or []),
                )
            )

        total_gross_cents = _money_to_cents(totals.get("gross"))
        discount_total_cents = _money_to_cents(totals.get("discount"))
        store_name = str(store.get("name") or _merchant_label(options)).strip() or _merchant_label(options)
        fingerprint = compute_fingerprint(
            purchased_at=purchased_at.isoformat(),
            total_cents=total_gross_cents,
            item_names=[item.name for item in normalized_items],
        )
        return NormalizedReceiptRecord(
            id=record_id,
            purchased_at=purchased_at,
            store_id=str(store.get("id") or store_name).strip() or store_name,
            store_name=store_name,
            store_address=_format_address(store.get("address")) if isinstance(store, Mapping) else None,
            total_gross_cents=total_gross_cents,
            currency=str(totals.get("currency") or "EUR"),
            discount_total_cents=discount_total_cents,
            fingerprint=fingerprint,
            items=normalized_items,
            raw_json=record,
        )

    def _extract_discounts(self, record: dict[str, Any]) -> list[NormalizedDiscountRow]:
        discounts: list[NormalizedDiscountRow] = []
        for row in record.get("discounts") or []:
            if not isinstance(row, Mapping):
                continue
            amount_cents = abs(_money_to_cents(row.get("amount")))
            if amount_cents <= 0:
                continue
            discounts.append(
                NormalizedDiscountRow(
                    line_no=None,
                    type="promotion",
                    promotion_id=str(row.get("id") or "").strip() or None,
                    amount_cents=amount_cents,
                    label=str(row.get("label") or "PENNY discount"),
                    scope="transaction",
                    subkind=str(row.get("subkind") or "").strip() or None,
                    funded_by=str(row.get("funded_by") or "").strip() or None,
                )
            )

        for index, raw_item in enumerate(record.get("items") or [], start=1):
            if not isinstance(raw_item, Mapping):
                continue
            for item_discount in raw_item.get("discounts") or []:
                if not isinstance(item_discount, Mapping):
                    continue
                amount_cents = abs(_money_to_cents(item_discount.get("amount")))
                if amount_cents <= 0:
                    continue
                discounts.append(
                    NormalizedDiscountRow(
                        line_no=index,
                        type="promotion",
                        promotion_id=str(item_discount.get("id") or "").strip() or None,
                        amount_cents=amount_cents,
                        label=str(item_discount.get("label") or "PENNY item discount"),
                        scope="item",
                        subkind=str(item_discount.get("subkind") or "").strip() or None,
                        funded_by=str(item_discount.get("funded_by") or "").strip() or None,
                    )
                )

        if discounts:
            return discounts
        fallback_cents = abs(_money_to_cents(((record.get("totals") or {}) if isinstance(record.get("totals"), Mapping) else {}).get("discount")))
        if fallback_cents > 0:
            return [
                NormalizedDiscountRow(
                    line_no=None,
                    type="promotion",
                    amount_cents=fallback_cents,
                    label="PENNY discount",
                    scope="transaction",
                    subkind="promotion",
                )
            ]
        return []

    def _diagnostics_payload(self, context: Any) -> dict[str, Any]:
        options = context.connector_options
        fixture_file = _fixture_file_from_options(options)
        state_path = self._state_file(context)
        state = _load_state(state_path)
        oauth = self._oauth_session_from_state(state_path)
        browser_session = self._browser_session_from_state(state_path)
        pending = state.get("pending_auth") if isinstance(state.get("pending_auth"), Mapping) else None
        return {
            "fixture_mode": fixture_file is not None,
            "fixture_file": str(fixture_file) if fixture_file is not None else None,
            "state_file": str(state_path),
            "auth": {
                "discovery_url": DEFAULT_DISCOVERY_URL,
                "authorization_endpoint": (pending or {}).get("auth_endpoint") or DEFAULT_AUTH_ENDPOINT,
                "token_endpoint": (pending or {}).get("token_endpoint") or getattr(oauth, "token_endpoint", DEFAULT_TOKEN_ENDPOINT),
                "client_id": DEFAULT_CLIENT_ID,
                "redirect_uri": DEFAULT_REDIRECT_URI,
                "account_url": DEFAULT_ACCOUNT_URL,
                "account_ui_url": DEFAULT_ACCOUNT_UI_URL,
            },
            "profile": state.get("profile") or {},
            "authenticated_at": state.get("authenticated_at"),
            "oauth_expires_at": oauth.expires_at if oauth is not None else None,
            "browser_bootstrap_source": browser_session.get("bootstrap_source") if browser_session is not None else None,
            "browser_authenticated_at": browser_session.get("authenticated_at") if browser_session is not None else None,
            "browser_storage_state_present": browser_session is not None,
            "pending_flow_id": (pending or {}).get("flow_id"),
            "proven_facts": [
                "Android app package is de.penny.app.",
                "Login uses account.penny.de Keycloak/OIDC with client_id pennyandroid.",
                "App bridges tokens into account-ui through cookie-setter?redirect=account-ui.",
                "Direct Penny eBon endpoints are live at api.penny.de for subscriptions, eBon lists, and PDF fetches.",
                "The OAuth access token contains the rewe_id required by the eBon backend.",
            ],
            "blockers": [
                "Cloudflare Turnstile protects the login form.",
                "Penny only exposes a PDF/text-layer eBon, not a richer structured line-item API.",
                "Future Penny PDF format changes could require parser updates.",
            ],
        }

    def _state_file(self, context: Any) -> Path:
        return _state_file_for_context(context.storage.data_dir, context.connector_options)

    def _oauth_session_from_state(self, state_path: Path) -> OauthSession | None:
        state = _load_state(state_path)
        payload = state.get("oauth")
        if not isinstance(payload, Mapping):
            return None
        return OauthSession(**dict(payload))

    def _browser_session_from_state(self, state_path: Path) -> dict[str, Any] | None:
        state = _load_state(state_path)
        payload = state.get("browser_session")
        if not isinstance(payload, Mapping):
            return None
        storage_state = payload.get("storage_state")
        if not isinstance(storage_state, Mapping):
            return None
        return {
            "storage_state": dict(storage_state),
            "authenticated_at": payload.get("authenticated_at"),
            "bootstrap_source": payload.get("bootstrap_source"),
            "chrome_user_data_dir": payload.get("chrome_user_data_dir"),
            "chrome_profile_name": payload.get("chrome_profile_name"),
            "import_storage_state_file": payload.get("import_storage_state_file"),
        }

    def _session_expired(self, oauth: OauthSession) -> bool:
        expires_at = _parse_iso_datetime(oauth.expires_at)
        if expires_at is None:
            return False
        return expires_at <= datetime.now(tz=UTC)

    def _live_oauth_session(self, state_path: Path, options: Mapping[str, Any], oauth: OauthSession) -> OauthSession:
        needs_refresh = self._session_expired(oauth) or not str(oauth.access_token or "").strip()
        if not needs_refresh:
            return oauth
        refreshed = PennyOidcClient(
            timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            discovery_url=oauth.discovery_url,
        ).refresh(oauth)
        state = _load_state(state_path)
        state["oauth"] = asdict(refreshed)
        state["profile"] = _profile_from_oauth(refreshed) or state.get("profile") or {}
        _persist_state(state_path, state)
        return refreshed

    def _rewe_id_from_oauth(self, oauth: OauthSession) -> str:
        for token in (oauth.access_token, oauth.id_token):
            claims = _decode_jwt_claims(token)
            if not isinstance(claims, Mapping):
                continue
            rewe_id = str(claims.get("rewe_id") or "").strip()
            if rewe_id:
                return rewe_id
        raise PennyPluginError(
            "Penny OAuth token did not contain the rewe_id claim required by the eBon backend.",
            code="auth_required",
        )

    def _ebon_api_client(self, oauth: OauthSession, options: Mapping[str, Any]) -> PennyEbonApiClient:
        return PennyEbonApiClient(
            access_token=oauth.access_token,
            timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            api_base_url=_string_option(options, "ebon_api_base_url", DEFAULT_EBON_API_BASE_URL),
        )

    def _discover_live_records(
        self,
        request: ReceiptActionRequest,
        context: Any,
        oauth: OauthSession,
        state_path: Path,
    ) -> DiscoverRecordsOutput:
        options = context.connector_options
        live_oauth = self._live_oauth_session(state_path, options, oauth)
        rewe_id = self._rewe_id_from_oauth(live_oauth)
        client = self._ebon_api_client(live_oauth, options)

        start_index = int(str(request.input.cursor or "0"))
        limit = int(request.input.limit or DEFAULT_DISCOVERY_LIMIT)
        page_size = max(1, min(int(options.get("ebon_page_size", DEFAULT_EBON_PAGE_SIZE)), max(limit, DEFAULT_EBON_PAGE_SIZE)))

        filtered_items: list[Mapping[str, Any]] = []
        has_more_pages = True
        page = 1
        while len(filtered_items) < start_index + limit and has_more_pages:
            payload = client.list_ebons(rewe_id, page=page, page_size=page_size)
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                break
            for raw_item in items:
                if not isinstance(raw_item, Mapping):
                    continue
                purchased_at = _parse_datetime(raw_item.get("timestamp"))
                if request.input.window_start and purchased_at < request.input.window_start:
                    continue
                if request.input.window_end and purchased_at > request.input.window_end:
                    continue
                filtered_items.append(dict(raw_item))
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), Mapping) else {}
            current_page = int(pagination.get("currentPage") or page)
            page_count = int(pagination.get("pageCount") or current_page)
            has_more_pages = current_page < page_count
            page += 1

        page_items = filtered_items[start_index : start_index + limit]
        next_cursor = None
        if start_index + limit < len(filtered_items) or has_more_pages:
            next_cursor = str(start_index + limit)
        records = [
            RecordReference(
                record_ref=str(item.get("id") or ""),
                discovered_at=_parse_datetime(item.get("timestamp")),
                metadata={
                    "cancelled": bool(item.get("cancelled")),
                    "total_price_cents": item.get("totalPrice"),
                    "currency": "EUR",
                    "surface": "penny_ebon_api",
                },
            )
            for item in page_items
            if str(item.get("id") or "").strip()
        ]
        return DiscoverRecordsOutput(records=records, next_cursor=next_cursor)

    def _fetch_live_record(
        self,
        request: ReceiptActionRequest,
        context: Any,
        oauth: OauthSession,
        state_path: Path,
    ) -> FetchRecordOutput:
        options = context.connector_options
        live_oauth = self._live_oauth_session(state_path, options, oauth)
        rewe_id = self._rewe_id_from_oauth(live_oauth)
        client = self._ebon_api_client(live_oauth, options)
        record_ref = str(request.input.record_ref or "").strip()
        if not record_ref:
            raise PennyPluginError("Penny fetch_record requires a record_ref.", code="invalid_request")

        lookup_limit = _int_option(options, "lookup_limit", DEFAULT_DISCOVERY_LIMIT)
        summary: Mapping[str, Any] | None = None
        page = 1
        page_size = max(DEFAULT_EBON_PAGE_SIZE, min(lookup_limit, 100))
        scanned = 0
        while scanned < lookup_limit:
            payload = client.list_ebons(rewe_id, page=page, page_size=page_size)
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                break
            for raw_item in items:
                scanned += 1
                if isinstance(raw_item, Mapping) and str(raw_item.get("id") or "").strip() == record_ref:
                    summary = dict(raw_item)
                    break
            if summary is not None or len(items) < page_size:
                break
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), Mapping) else {}
            current_page = int(pagination.get("currentPage") or page)
            page_count = int(pagination.get("pageCount") or current_page)
            if current_page >= page_count:
                break
            page += 1
        if summary is None:
            raise PennyPluginError(f"unknown Penny record_ref: {record_ref}", code="invalid_request")

        pdf_bytes = client.fetch_pdf(rewe_id, record_ref)
        pdf_text = _extract_text_from_pdf_bytes(pdf_bytes)
        parsed = _parse_penny_ebon_pdf_text(
            pdf_text,
            fallback_timestamp=str(summary.get("timestamp") or "").strip() or None,
            merchant_label=_merchant_label(options),
        )
        parsed["id"] = record_ref
        if not parsed.get("purchasedAt"):
            parsed["purchasedAt"] = str(summary.get("timestamp") or "")
        totals = parsed.get("totals")
        if isinstance(totals, Mapping) and (not totals.get("gross")) and summary.get("totalPrice") is not None:
            parsed["totals"] = {
                **dict(totals),
                "gross": _cents_to_amount_text(_money_to_cents(summary.get("totalPrice"))),
            }
        parsed["attachments"] = [{"kind": "pdf", "url": client.pdf_url(rewe_id, record_ref)}]
        parsed["source"] = {
            "fixture": False,
            "surface": "penny_ebon_api",
            "summary": dict(summary),
        }
        return FetchRecordOutput(record_ref=record_ref, record=parsed)

    @staticmethod
    def _ok(action: str, output: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "plugin_family": "receipt",
            "contract_version": "1",
            "action": action,
            "ok": True,
            "output": dict(output),
        }

    @staticmethod
    def _error(action: str, *, code: str, message: str, retryable: bool = False) -> dict[str, Any]:
        return {
            "plugin_family": "receipt",
            "contract_version": "1",
            "action": action,
            "ok": False,
            "error": ConnectorError(code=code, message=message, retryable=retryable).model_dump(mode="python"),
        }
