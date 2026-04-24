from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from playwright.sync_api import sync_playwright

from lidltool.connectors._sdk_compat import coerce_receipt_connector
from lidltool.connectors.auth.browser_runtime import launch_playwright_chromium_persistent_context
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    CancelAuthResponse,
    ConfirmAuthResponse,
    ConnectorError,
    DiagnosticsOutput,
    GetAuthStatusOutput,
    GetAuthStatusResponse,
    GetDiagnosticsResponse,
    GetManifestOutput,
    GetManifestResponse,
    ReceiptActionRequest,
    ReceiptActionResponse,
    StartAuthResponse,
    validate_receipt_action_request,
)
from lidltool.connectors.sdk.runtime import (
    AuthBrowserPlan,
    build_auth_browser_metadata,
    load_plugin_runtime_context,
    parse_auth_browser_runtime_context,
)

ROOT = Path(__file__).resolve().parent
_REWE_COOKIE_DOMAIN = "rewe.de"
_CHROME_SAFE_STORAGE_SERVICE = "Chrome Safe Storage"
_CHROME_SAFE_STORAGE_ACCOUNT = "Chrome"
_CHROME_COOKIE_EPOCH_OFFSET_SECONDS = 11_644_473_600
_DEFAULT_CHROME_EXECUTABLE = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _load_local_module(module_name: str, file_name: str) -> Any:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, ROOT / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load local REWE module {file_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_rewe_client_module = _load_local_module("rewe_client", "rewe_client.py")
_rewe_adapter_module = _load_local_module("rewe_adapter", "rewe_adapter.py")

REWE_ACCOUNT_ROOT_URL = _rewe_client_module.REWE_ACCOUNT_ROOT_URL
REWE_MARKET_PURCHASES_URL = _rewe_client_module.REWE_MARKET_PURCHASES_URL
REWE_ONLINE_PURCHASES_URL = _rewe_client_module.REWE_ONLINE_PURCHASES_URL
REWE_PURCHASES_URL = _rewe_client_module.REWE_PURCHASES_URL
ReweChromeLiveTabClient = _rewe_client_module.ReweChromeLiveTabClient
RewePlaywrightClient = _rewe_client_module.RewePlaywrightClient
ReweConnectorAdapter = _rewe_adapter_module.ReweConnectorAdapter
looks_like_rewe_bot_challenge = _rewe_client_module.looks_like_rewe_bot_challenge
probe_rewe_live_chrome_session = _rewe_client_module.probe_rewe_live_chrome_session
verify_and_refresh_rewe_http_storage_state = _rewe_client_module.verify_and_refresh_rewe_http_storage_state
ReweClientError = _rewe_client_module.ReweClientError
ReweReauthRequiredError = _rewe_client_module.ReweReauthRequiredError


def _manifest_definition() -> dict[str, Any]:
    manifest_candidates = (
        ROOT / "manifest.json",
        ROOT.parent / "manifest.json",
    )
    for manifest_path in manifest_candidates:
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
    searched = ", ".join(str(path) for path in manifest_candidates)
    raise FileNotFoundError(f"REWE plugin manifest.json not found. Looked in: {searched}")


class RewePluginError(RuntimeError):
    def __init__(self, message: str, *, code: str = "internal_error", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


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


def _use_live_chrome_tab(options: Mapping[str, Any]) -> bool:
    return _bool_option(options, "chrome_live_tab", False)


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _state_file_for_context() -> Path:
    context = load_plugin_runtime_context()
    options = context.connector_options
    resolved = _resolve_optional_path(options.get("state_file"))
    if resolved is not None:
        return resolved
    return (context.storage.data_dir / "rewe_storage_state.json").expanduser().resolve()


def _pending_auth_file(state_file: Path) -> Path:
    return state_file.with_name(f"{state_file.stem}_pending_auth.json")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RewePluginError(f"invalid REWE plugin state payload at {path}", code="contract_violation")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _ensure_parent(path)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _trace_rewe(event: str, **fields: object) -> None:
    parts = [f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={str(value).replace(chr(10), ' ').strip()}")
    print(f"rewe.trace {' '.join(parts)}", flush=True)


def _validate_storage_state_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    cookies = normalized.get("cookies")
    if not isinstance(cookies, list) or len(cookies) == 0:
        raise RewePluginError(
            "REWE browser session import did not contain any cookies",
            code="auth_required",
        )
    origins = normalized.get("origins")
    if origins is None:
        normalized["origins"] = []
    elif not isinstance(origins, list):
        raise RewePluginError(
            "REWE browser session import contains invalid origins data",
            code="auth_required",
        )
    return normalized


def _load_storage_state_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RewePluginError(
            f"REWE browser session import file is not valid JSON: {path}",
            code="auth_required",
        ) from exc
    if not isinstance(payload, dict):
        raise RewePluginError(
            f"REWE browser session import file must contain a JSON object: {path}",
            code="auth_required",
        )
    return _validate_storage_state_payload(payload)


def _read_saved_storage_state(path: Path) -> dict[str, Any]:
    return _load_storage_state_file(path)


def _validate_saved_storage_state(
    *,
    path: Path,
    headless: bool,
) -> dict[str, Any]:
    validated = _verify_rewe_storage_state(
        storage_state=_read_saved_storage_state(path),
        start_url=REWE_MARKET_PURCHASES_URL,
        headless=headless,
    )
    _write_json(path, validated)
    return validated


def _option_present(options: Mapping[str, Any], key: str) -> bool:
    return key in options and options.get(key) is not None


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
        for home in _candidate_home_directories():
            candidate = (home / "AppData" / "Local" / "Google" / "Chrome" / "User Data").resolve()
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
        raise RewePluginError(
            "REWE Chrome-profile import requires chrome_user_data_dir to be configured on this host.",
            code="auth_required",
        )
    return detected


def _copytree_if_present(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(
            source,
            target,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "Cache",
                "Code Cache",
                "GPUCache",
                "ShaderCache",
                "GrShaderCache",
                "Crashpad",
                "Singleton*",
                "LOCK",
                "*.lock",
                "*.log",
            ),
        )
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _chrome_profile_dir(source_user_data_dir: Path, profile_name: str) -> Path:
    return source_user_data_dir / profile_name


def _chrome_cookie_db_path(source_user_data_dir: Path, profile_name: str) -> Path:
    profile_dir = _chrome_profile_dir(source_user_data_dir, profile_name)
    candidates = (
        profile_dir / "Cookies",
        profile_dir / "Network" / "Cookies",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise RewePluginError(
        f"REWE running-Chrome session import could not find the Chrome cookie database. Looked in: {searched}",
        code="auth_required",
    )


def _chrome_safe_storage_password() -> str:
    with suppress(Exception):
        import keyring

        password = keyring.get_password(_CHROME_SAFE_STORAGE_SERVICE, _CHROME_SAFE_STORAGE_ACCOUNT)
        if password:
            return password
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
    raise RewePluginError(
        "REWE running-Chrome session import could not read the Chrome Safe Storage secret on this host.",
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
        raise RewePluginError(
            "REWE running-Chrome session import read an invalid encrypted cookie payload.",
            code="auth_required",
        )
    plaintext = padded[:-pad_length]
    host_digest = hashlib.sha256(host_key.encode("utf-8")).digest()
    if cookie_db_version >= 24 and plaintext.startswith(host_digest):
        plaintext = plaintext[len(host_digest) :]
    return plaintext.decode("utf-8")


def _chrome_cookie_matches_rewe_domain(host_key: str) -> bool:
    normalized = host_key.lstrip(".").lower()
    return normalized == _REWE_COOKIE_DOMAIN or normalized.endswith(f".{_REWE_COOKIE_DOMAIN}")


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


def _rewe_cookie_rows_to_storage_state(
    rows: list[sqlite3.Row],
    *,
    decryption_key: bytes,
    cookie_db_version: int,
) -> dict[str, Any]:
    cookies: list[dict[str, Any]] = []
    for row in rows:
        host_key = str(row["host_key"] or "")
        if not _chrome_cookie_matches_rewe_domain(host_key):
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
    return _validate_storage_state_payload(
        {
            "cookies": cookies,
            "origins": [],
            "user_agent": _chrome_user_agent(),
        }
    )


def _verify_rewe_storage_state(
    *,
    storage_state: Mapping[str, Any],
    start_url: str,
    headless: bool,
)-> dict[str, Any]:
    del headless
    try:
        return verify_and_refresh_rewe_http_storage_state(
            dict(storage_state),
            start_url=start_url,
        )
    except ReweReauthRequiredError as exc:
        raise RewePluginError(
            f"{exc} Re-open REWE in normal Chrome and run bootstrap again.",
            code="auth_required",
        ) from exc
    except ReweClientError as exc:
        raise RewePluginError(
            str(exc),
            code="auth_required",
        ) from exc


def _capture_storage_state_from_running_chrome_session(
    *,
    source_user_data_dir: Path,
    profile_name: str,
    start_url: str,
    headless: bool,
) -> dict[str, Any]:
    cookie_db_path = _chrome_cookie_db_path(source_user_data_dir, profile_name)
    decryption_key = _chrome_cookie_encryption_key()
    with TemporaryDirectory(prefix="rewe-chrome-cookies-") as temp_dir:
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
                    where host_key like '%rewe.de%'
                    order by host_key, name
                    """
                )
            )
        finally:
            connection.close()
    storage_state = _rewe_cookie_rows_to_storage_state(
        rows,
        decryption_key=decryption_key,
        cookie_db_version=cookie_db_version,
    )
    storage_state = _verify_rewe_storage_state(
        storage_state=storage_state,
        start_url=start_url,
        headless=headless,
    )
    return storage_state


def _capture_storage_state_from_chrome_profile(
    *,
    source_user_data_dir: Path,
    profile_name: str,
    start_url: str,
    headless: bool,
) -> dict[str, Any]:
    profile_source = source_user_data_dir / profile_name
    if not profile_source.exists():
        raise RewePluginError(
            f"REWE Chrome-profile import could not find profile directory: {profile_source}",
            code="auth_required",
        )
    with TemporaryDirectory(prefix="rewe-chrome-import-") as temp_dir:
        temp_root = Path(temp_dir) / "chrome-user-data"
        temp_root.mkdir(parents=True, exist_ok=True)
        _copytree_if_present(source_user_data_dir / "Local State", temp_root / "Local State")
        _copytree_if_present(profile_source, temp_root / profile_name)
        with suppress(Exception):
            _copytree_if_present(
                source_user_data_dir / profile_name / "Network",
                temp_root / profile_name / "Network",
            )
        with sync_playwright() as playwright:
            context = launch_playwright_chromium_persistent_context(
                playwright=playwright,
                user_data_dir=temp_root,
                headless=headless,
                args=[f"--profile-directory={profile_name}"],
            )
            try:
                storage_state = context.storage_state()
            finally:
                context.close()
    if not isinstance(storage_state, dict):
        raise RewePluginError(
            "REWE Chrome-profile import did not yield browser storage state.",
            code="auth_required",
        )
    validated = _validate_storage_state_payload(storage_state)
    return _verify_rewe_storage_state(
        storage_state=validated,
        start_url=start_url,
        headless=headless,
    )


class ReweReceiptPlugin:
    def __init__(self) -> None:
        self._manifest = ConnectorManifest.model_validate(_manifest_definition())

    def invoke_action(
        self,
        request: ReceiptActionRequest | Mapping[str, Any],
    ) -> ReceiptActionResponse | Mapping[str, Any]:
        validated = validate_receipt_action_request(request)
        try:
            if validated.action == "get_manifest":
                return GetManifestResponse(output=GetManifestOutput(manifest=self._manifest))
            if validated.action == "get_auth_status":
                return GetAuthStatusResponse(output=self._get_auth_status())
            if validated.action == "start_auth":
                return StartAuthResponse(output=self._start_auth())
            if validated.action == "cancel_auth":
                return CancelAuthResponse(output=self._cancel_auth())
            if validated.action == "confirm_auth":
                return ConfirmAuthResponse(output=self._confirm_auth())
            if validated.action == "get_diagnostics":
                return GetDiagnosticsResponse(output=DiagnosticsOutput(diagnostics=self._diagnostics()))
            connector = self._build_connector()
            return coerce_receipt_connector(connector, manifest=self._manifest).invoke_action(validated)
        except RewePluginError as exc:
            return {
                "contract_version": validated.contract_version,
                "plugin_family": validated.plugin_family,
                "action": validated.action,
                "ok": False,
                "warnings": (),
                "error": ConnectorError(
                    code=exc.code,  # type: ignore[arg-type]
                    message=str(exc),
                    retryable=exc.retryable,
                ).model_dump(mode="python"),
                "output": None,
            }

    def _start_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        if _use_live_chrome_tab(options):
            try:
                probe = probe_rewe_live_chrome_session()
            except Exception as exc:
                raise RewePluginError(
                    "REWE live Chrome mode requires a logged-in normal Chrome tab on REWE and Chrome setting "
                    "'Darstellung > Entwickler > JavaScript von Apple Events erlauben'. "
                    f"Probe failed: {exc}",
                    code="auth_required",
                ) from exc
            return AuthLifecycleOutput(
                status="confirmed",
                detail="REWE live Chrome session is ready in the already-authenticated normal Chrome tab.",
                metadata={
                    "bootstrap_source": "chrome_live_tab",
                    "chrome_tab_url": probe.get("href"),
                    "chrome_tab_title": probe.get("title"),
                },
            )
        state_file = _state_file_for_context()
        pending_file = _pending_auth_file(state_file)
        force_reauth = _bool_option(options, "force_reauth", False)
        stale_state_detail: str | None = None
        if state_file.exists():
            if force_reauth:
                state_file.unlink(missing_ok=True)
                pending_file.unlink(missing_ok=True)
            else:
                try:
                    _validate_saved_storage_state(
                        path=state_file,
                        headless=_bool_option(options, "headless", True),
                    )
                except RewePluginError as exc:
                    stale_state_detail = str(exc)
                    state_file.unlink(missing_ok=True)
                    pending_file.unlink(missing_ok=True)
                else:
                    return AuthLifecycleOutput(
                        status="no_op",
                        detail="REWE browser session is still valid. Run start_auth with force_reauth=true to replace it.",
                        metadata={"state_file": str(state_file)},
                    )
        import_storage_state = _resolve_optional_path(options.get("import_storage_state_file"))
        if import_storage_state is not None:
            imported_state = _load_storage_state_file(import_storage_state)
            _ensure_parent(state_file)
            state_file.write_text(
                json.dumps(imported_state, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            pending_file.unlink(missing_ok=True)
            return AuthLifecycleOutput(
                status="confirmed",
                detail="REWE browser session was imported from an existing storage-state file.",
                metadata={
                    "state_file": str(state_file),
                    "import_storage_state_file": str(import_storage_state),
                    "replaced_stale_session": stale_state_detail is not None or force_reauth,
                },
            )
        chrome_cookie_export_requested = (
            _bool_option(options, "chrome_cookie_export", True)
            if not _option_present(options, "chrome_cookie_export")
            else _bool_option(options, "chrome_cookie_export", False)
        )
        chrome_cookie_export_error: str | None = None
        source_user_data_dir: Path | None = None
        profile_name = _string_option(options, "chrome_profile_name", "Default")
        if chrome_cookie_export_requested:
            try:
                source_user_data_dir = _chrome_user_data_dir_for_options(options)
                imported_state = _capture_storage_state_from_running_chrome_session(
                    source_user_data_dir=source_user_data_dir,
                    profile_name=profile_name,
                    start_url=REWE_MARKET_PURCHASES_URL,
                    headless=_bool_option(options, "chrome_cookie_export_headless", True),
                )
            except RewePluginError as exc:
                chrome_cookie_export_error = str(exc)
            else:
                _ensure_parent(state_file)
                state_file.write_text(
                    json.dumps(imported_state, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                pending_file.unlink(missing_ok=True)
                _trace_rewe(
                    "start_auth.chrome_cookie_export_confirmed",
                    state_file=state_file,
                    chrome_user_data_dir=source_user_data_dir,
                    chrome_profile_name=profile_name,
                )
                return AuthLifecycleOutput(
                    status="confirmed",
                    detail=(
                        "REWE browser session was imported from the running normal Chrome session. Future syncs reuse this saved "
                        "session until REWE requires reauthentication."
                    ),
                    metadata={
                        "state_file": str(state_file),
                        "chrome_user_data_dir": str(source_user_data_dir),
                        "chrome_profile_name": profile_name,
                        "bootstrap_source": "chrome_cookie_export",
                        "replaced_stale_session": stale_state_detail is not None or force_reauth,
                    },
                )
        chrome_profile_import_requested = (
            _bool_option(options, "chrome_profile_import", True)
            if not _option_present(options, "chrome_profile_import")
            else _bool_option(options, "chrome_profile_import", False)
        )
        chrome_profile_import_error: str | None = None
        if chrome_profile_import_requested:
            try:
                if source_user_data_dir is None:
                    source_user_data_dir = _chrome_user_data_dir_for_options(options)
                imported_state = _capture_storage_state_from_chrome_profile(
                    source_user_data_dir=source_user_data_dir,
                    profile_name=profile_name,
                    start_url=REWE_MARKET_PURCHASES_URL,
                    headless=_bool_option(options, "chrome_profile_import_headless", True),
                )
            except RewePluginError as exc:
                chrome_profile_import_error = str(exc)
            else:
                _ensure_parent(state_file)
                state_file.write_text(
                    json.dumps(imported_state, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                pending_file.unlink(missing_ok=True)
                _trace_rewe(
                    "start_auth.chrome_profile_import_confirmed",
                    state_file=state_file,
                    chrome_user_data_dir=source_user_data_dir,
                    chrome_profile_name=profile_name,
                )
                return AuthLifecycleOutput(
                    status="confirmed",
                    detail=(
                        "REWE browser session was imported from a logged-in normal Chrome profile. No separate login window was "
                        "opened."
                    ),
                    metadata={
                        "state_file": str(state_file),
                        "chrome_user_data_dir": str(source_user_data_dir),
                        "chrome_profile_name": profile_name,
                        "replaced_stale_session": stale_state_detail is not None or force_reauth,
                    },
                )
        flow_id = secrets.token_hex(16)
        _write_json(
            pending_file,
            {
                "flow_id": flow_id,
                "created_at": _iso_now(),
                "tracking_source_id": context.tracking_source_id,
                "state_file": str(state_file),
                "start_url": REWE_MARKET_PURCHASES_URL,
                "chrome_cookie_export_error": chrome_cookie_export_error,
                "chrome_profile_import_error": chrome_profile_import_error,
            },
        )
        if chrome_cookie_export_error is None and chrome_profile_import_error is None:
            detail = (
                "REWE could not reuse a logged-in normal Chrome session, so browser login started in the shared host auth session. "
                "If you want the easier path, open Chrome, sign into REWE there, leave the tab open, and rerun setup."
            )
        elif chrome_profile_import_error is None:
            detail = (
                "REWE could not reuse the currently running Chrome session, so browser login started in the shared host auth session. "
                "Open Chrome, sign into REWE there, leave the tab open, and retry if you want to avoid the fallback browser."
            )
        elif chrome_cookie_export_error is None:
            detail = (
                "REWE could not import the normal Chrome profile, so browser login started in the shared host auth session. "
                "Open Chrome, sign into REWE there, leave the tab open, and retry if needed."
            )
        else:
            detail = (
                "REWE could not reuse the normal Chrome session automatically, so browser login started in the shared host auth "
                "session. Open Chrome, sign into REWE there, leave the tab open, and retry setup if the fallback login does not work."
            )
        if stale_state_detail is not None:
            detail = f"{stale_state_detail} {detail}"
        _trace_rewe(
            "start_auth.shared_browser_fallback",
            state_file=state_file,
            chrome_cookie_export_error=chrome_cookie_export_error,
            chrome_profile_import_error=chrome_profile_import_error,
            flow_id=flow_id,
        )
        return AuthLifecycleOutput(
            status="started",
            flow_id=flow_id,
            next_poll_after_seconds=2,
            detail=detail,
            metadata=build_auth_browser_metadata(
                flow_id=flow_id,
                plan=AuthBrowserPlan(
                    start_url=REWE_MARKET_PURCHASES_URL,
                    callback_url_prefixes=(
                        REWE_MARKET_PURCHASES_URL,
                        REWE_ONLINE_PURCHASES_URL,
                        REWE_PURCHASES_URL,
                        REWE_ACCOUNT_ROOT_URL,
                    ),
                    require_navigation_away_before_completion=True,
                    timeout_seconds=_int_option(options, "auth_timeout_seconds", 900),
                    capture_storage_state=True,
                ),
            ),
        )

    def _cancel_auth(self) -> AuthLifecycleOutput:
        options = load_plugin_runtime_context().connector_options
        if _use_live_chrome_tab(options):
            return AuthLifecycleOutput(status="no_op", detail="REWE live Chrome mode has no pending auth flow to cancel.")
        state_file = _state_file_for_context()
        pending_file = _pending_auth_file(state_file)
        if not pending_file.exists():
            return AuthLifecycleOutput(status="no_op", detail="No pending REWE auth flow exists.")
        pending_file.unlink()
        return AuthLifecycleOutput(status="canceled", detail="Pending REWE browser auth flow cleared.")

    def _confirm_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        if _use_live_chrome_tab(context.connector_options):
            try:
                probe = probe_rewe_live_chrome_session()
            except Exception as exc:
                raise RewePluginError(
                    "REWE live Chrome mode is not ready. Open a logged-in REWE tab in normal Chrome and enable "
                    "'Darstellung > Entwickler > JavaScript von Apple Events erlauben'. "
                    f"Probe failed: {exc}",
                    code="auth_required",
                ) from exc
            return AuthLifecycleOutput(
                status="confirmed",
                detail="REWE live Chrome session is ready in the already-authenticated normal Chrome tab.",
                metadata={
                    "bootstrap_source": "chrome_live_tab",
                    "chrome_tab_url": probe.get("href"),
                    "chrome_tab_title": probe.get("title"),
                },
            )
        state_file = _state_file_for_context()
        pending_file = _pending_auth_file(state_file)
        if not pending_file.exists():
            return AuthLifecycleOutput(status="no_op", detail="No pending REWE auth flow exists.")
        pending_payload = _read_json(pending_file)
        expected_flow_id = str(pending_payload.get("flow_id") or "").strip()
        browser_result = parse_auth_browser_runtime_context(context.runtime_context)
        if browser_result is None:
            return AuthLifecycleOutput(
                status="pending",
                flow_id=expected_flow_id or None,
                detail="REWE browser auth is still waiting for shared-browser completion.",
            )
        if browser_result.flow_id != expected_flow_id:
            raise RewePluginError("REWE auth confirmation flow_id mismatch", code="auth_required")
        if not browser_result.callback_url.startswith(REWE_ACCOUNT_ROOT_URL):
            raise RewePluginError(
                "REWE browser auth did not finish on the authenticated account pages",
                code="auth_required",
            )
        if browser_result.storage_state is None:
            raise RewePluginError(
                "REWE auth confirmation did not receive browser storage state",
                code="auth_required",
            )
        cookies = browser_result.storage_state.get("cookies")
        if not isinstance(cookies, list) or len(cookies) == 0:
            raise RewePluginError(
                "REWE auth confirmation did not capture an authenticated browser session",
                code="auth_required",
            )
        _ensure_parent(state_file)
        state_file.write_text(
            json.dumps(browser_result.storage_state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pending_file.unlink(missing_ok=True)
        _trace_rewe(
            "confirm_auth.captured_storage_state",
            flow_id=expected_flow_id or browser_result.flow_id,
            browser_mode=browser_result.mode,
            callback_url=browser_result.callback_url,
            cookie_count=len(cookies),
            origin_count=len(browser_result.storage_state.get("origins") or []),
            state_file=state_file,
        )
        return AuthLifecycleOutput(
            status="confirmed",
            flow_id=expected_flow_id or browser_result.flow_id,
            detail="REWE browser login completed and session storage was captured.",
            metadata={
                "state_file": str(state_file),
                "browser_mode": browser_result.mode,
            },
        )

    def _get_auth_status(self) -> GetAuthStatusOutput:
        options = load_plugin_runtime_context().connector_options
        if _use_live_chrome_tab(options):
            available_actions = self._manifest.auth.available_actions() if self._manifest.auth else ()
            implemented_actions = self._manifest.auth.implemented_actions if self._manifest.auth else ()
            compatibility_actions = self._manifest.auth.compatibility_actions if self._manifest.auth else ()
            reserved_actions = self._manifest.auth.reserved_actions if self._manifest.auth else ()
            try:
                probe = probe_rewe_live_chrome_session()
            except Exception as exc:
                return GetAuthStatusOutput(
                    status="requires_auth",
                    is_authenticated=False,
                    available_actions=available_actions,
                    implemented_actions=implemented_actions,
                    compatibility_actions=compatibility_actions,
                    reserved_actions=reserved_actions,
                    detail=(
                        "REWE live Chrome mode requires a logged-in normal Chrome tab on REWE and Chrome setting "
                        "'Darstellung > Entwickler > JavaScript von Apple Events erlauben'. "
                        f"Probe failed: {exc}"
                    ),
                    metadata={
                        "bootstrap_source": "chrome_live_tab",
                        "supports_external_auth_hosting": False,
                        "supports_headless_refresh": False,
                    },
                )
            return GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=compatibility_actions,
                reserved_actions=reserved_actions,
                detail="REWE live Chrome session is available via the already-authenticated normal Chrome tab.",
                metadata={
                    "bootstrap_source": "chrome_live_tab",
                    "chrome_tab_url": probe.get("href"),
                    "chrome_tab_title": probe.get("title"),
                    "supports_external_auth_hosting": False,
                    "supports_headless_refresh": False,
                },
            )
        state_file = _state_file_for_context()
        pending_file = _pending_auth_file(state_file)
        available_actions = self._manifest.auth.available_actions() if self._manifest.auth else ()
        implemented_actions = self._manifest.auth.implemented_actions if self._manifest.auth else ()
        compatibility_actions = self._manifest.auth.compatibility_actions if self._manifest.auth else ()
        reserved_actions = self._manifest.auth.reserved_actions if self._manifest.auth else ()
        metadata = {
            "state_file": str(state_file),
            "pending_auth_file": str(pending_file),
            "supports_external_auth_hosting": True,
            "supports_headless_refresh": False,
        }
        if pending_file.exists():
            pending_payload = _read_json(pending_file)
            metadata["pending_flow_id"] = pending_payload.get("flow_id")
            metadata["chrome_cookie_export_error"] = pending_payload.get("chrome_cookie_export_error")
            metadata["chrome_profile_import_error"] = pending_payload.get("chrome_profile_import_error")
            return GetAuthStatusOutput(
                status="pending",
                is_authenticated=False,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=compatibility_actions,
                reserved_actions=reserved_actions,
                detail="REWE browser auth is waiting for confirmation.",
                metadata=metadata,
            )
        if not state_file.exists():
            return GetAuthStatusOutput(
                status="requires_auth",
                is_authenticated=False,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=compatibility_actions,
                reserved_actions=reserved_actions,
                detail=(
                    "REWE requires authentication. Open normal Chrome, sign into REWE there, leave the logged-in tab open, and run "
                    "start_auth again."
                ),
                metadata=metadata,
            )
        try:
            parsed = _read_saved_storage_state(state_file)
        except RewePluginError:
            return GetAuthStatusOutput(
                status="requires_auth",
                is_authenticated=False,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=compatibility_actions,
                reserved_actions=reserved_actions,
                detail=(
                    "REWE browser session state is invalid. Open normal Chrome, sign into REWE again, leave the tab open, and run "
                    "start_auth again."
                ),
                metadata=metadata,
            )
        cookies = parsed.get("cookies")
        origins = parsed.get("origins")
        metadata["cookie_count"] = len(cookies) if isinstance(cookies, list) else 0
        metadata["origin_count"] = len(origins) if isinstance(origins, list) else 0
        try:
            refreshed = _validate_saved_storage_state(
                path=state_file,
                headless=_bool_option(options, "headless", True),
            )
        except RewePluginError as exc:
            metadata["reauth_required"] = True
            return GetAuthStatusOutput(
                status="expired",
                is_authenticated=False,
                available_actions=available_actions,
                implemented_actions=implemented_actions,
                compatibility_actions=compatibility_actions,
                reserved_actions=reserved_actions,
                detail=str(exc),
                metadata=metadata,
            )
        refreshed_cookies = refreshed.get("cookies")
        refreshed_origins = refreshed.get("origins")
        metadata["cookie_count"] = len(refreshed_cookies) if isinstance(refreshed_cookies, list) else 0
        metadata["origin_count"] = len(refreshed_origins) if isinstance(refreshed_origins, list) else 0
        _trace_rewe(
            "get_auth_status.valid",
            state_file=state_file,
            cookie_count=metadata["cookie_count"],
            origin_count=metadata["origin_count"],
        )
        return GetAuthStatusOutput(
            status="authenticated",
            is_authenticated=True,
            available_actions=available_actions,
            implemented_actions=implemented_actions,
            compatibility_actions=compatibility_actions,
            reserved_actions=reserved_actions,
            detail="REWE browser session is stored locally and still reaches the authenticated account area.",
            metadata=metadata,
        )

    def _diagnostics(self) -> dict[str, Any]:
        options = load_plugin_runtime_context().connector_options
        if _use_live_chrome_tab(options):
            diagnostics: dict[str, Any] = {
                "plugin_id": self._manifest.plugin_id,
                "source_id": self._manifest.source_id,
                "runtime_kind": self._manifest.runtime_kind,
                "uses_plugin_owned_rewe_runtime": True,
                "bootstrap_source": "chrome_live_tab",
                "verified_surfaces": {
                    "account_root": REWE_ACCOUNT_ROOT_URL,
                    "purchases": REWE_PURCHASES_URL,
                    "market": REWE_MARKET_PURCHASES_URL,
                    "online": REWE_ONLINE_PURCHASES_URL,
                },
            }
            with suppress(Exception):
                diagnostics["chrome_live_tab_probe"] = probe_rewe_live_chrome_session()
            return diagnostics
        state_file = _state_file_for_context()
        pending_file = _pending_auth_file(state_file)
        return {
            "plugin_id": self._manifest.plugin_id,
            "source_id": self._manifest.source_id,
            "runtime_kind": self._manifest.runtime_kind,
            "state_file": str(state_file),
            "state_file_present": state_file.exists(),
            "pending_auth_file": str(pending_file),
            "pending_auth_present": pending_file.exists(),
            "uses_plugin_owned_rewe_runtime": True,
            "verified_surfaces": {
                "account_root": REWE_ACCOUNT_ROOT_URL,
                "purchases": REWE_PURCHASES_URL,
                "market": REWE_MARKET_PURCHASES_URL,
                "online": REWE_ONLINE_PURCHASES_URL,
            },
        }

    def _build_connector(self) -> ReweConnectorAdapter:
        context = load_plugin_runtime_context()
        options = context.connector_options
        if _use_live_chrome_tab(options):
            client = ReweChromeLiveTabClient(
                max_records=_int_option(options, "max_records", 250),
                detail_fetch_limit=_int_option(options, "detail_fetch_limit", 25),
            )
        else:
            state_file = _state_file_for_context()
            dump_html = _resolve_optional_path(options.get("dump_html"))
            client = RewePlaywrightClient(
                state_file=state_file,
                headless=_bool_option(options, "headless", True),
                max_records=_int_option(options, "max_records", 250),
                detail_fetch_limit=_int_option(options, "detail_fetch_limit", 25),
                http_timeout_seconds=_int_option(options, "http_timeout_seconds", 30),
                persist_state_on_success=_bool_option(options, "persist_state", True),
                dump_html_dir=dump_html,
            )
        return ReweConnectorAdapter(
            client=client,
            source=context.tracking_source_id or self._manifest.source_id,
            store_name=_string_option(options, "store_name", "REWE"),
        )
