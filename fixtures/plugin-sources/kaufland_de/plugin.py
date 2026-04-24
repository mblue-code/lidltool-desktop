from __future__ import annotations

import base64
import hashlib
import json
import secrets
import urllib.parse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import httpx

from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.receipt import (
    AuthLifecycleOutput,
    CancelAuthResponse,
    ConfirmAuthResponse,
    ConnectorError,
    DiagnosticsOutput,
    DiscoverRecordsOutput,
    DiscoverRecordsResponse,
    ExtractDiscountsOutput,
    ExtractDiscountsResponse,
    FetchRecordOutput,
    FetchRecordResponse,
    GetAuthStatusOutput,
    GetAuthStatusResponse,
    GetDiagnosticsResponse,
    GetManifestOutput,
    GetManifestResponse,
    HealthcheckOutput,
    HealthcheckResponse,
    NormalizeRecordOutput,
    NormalizeRecordResponse,
    ReceiptActionRequest,
    ReceiptActionResponse,
    RecordReference,
    StartAuthResponse,
    validate_receipt_action_request,
)
from lidltool.connectors.sdk.runtime import (
    AuthBrowserPlan,
    build_auth_browser_metadata,
    load_plugin_runtime_context,
    parse_auth_browser_runtime_context,
)
from lidltool.ingest.normalizer import normalize_receipt

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH_CANDIDATES = (
    ROOT / "manifest.json",
    ROOT.parent / "manifest.json",
)

STATE_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_AUTH_TIMEOUT_SECONDS = 900
DEFAULT_DISCOVERY_LIMIT = 100
DEFAULT_LOOKUP_LIMIT = 250
DEFAULT_COUNTRY_CODE = "DE"
DEFAULT_UI_LOCALES = "de"
DEFAULT_VIEW_TYPE = ""
DEFAULT_APP_PLATFORM = "Android"
DEFAULT_APP_VERSION = "6.2.0"
DEFAULT_CIDAAS_VERSION = "1.5.22"
DEFAULT_CIDAAS_BASE_URL = "https://account.kaufland.com"
DEFAULT_CIDAAS_AUTH_ENDPOINT = DEFAULT_CIDAAS_BASE_URL + "/authz-srv/authz"
DEFAULT_CIDAAS_TOKEN_ENDPOINT = DEFAULT_CIDAAS_BASE_URL + "/token-srv/token"
DEFAULT_CIDAAS_CLIENT_ID = "fb1b425b-ab2f-4140-aef9-20263b6cfa49"
DEFAULT_REDIRECT_URI = "com.kaufland.kaufland://oauth/callback"
DEFAULT_USERINFO_BASE_URL = "https://app.kaufland.net"
DEFAULT_LOYALTY_BASE_URL = "https://p.crm-dynamics.schwarz"
DEFAULT_LOYALTY_CLIENT_ID = "88207bfc-780b-400d-92ee-893ae72dab40"


class KauflandPluginError(RuntimeError):
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
    client_id: str = DEFAULT_CIDAAS_CLIENT_ID
    redirect_uri: str = DEFAULT_REDIRECT_URI
    auth_endpoint: str = DEFAULT_CIDAAS_AUTH_ENDPOINT
    token_endpoint: str = DEFAULT_CIDAAS_TOKEN_ENDPOINT


@dataclass(slots=True, frozen=True)
class UserProfile:
    sub: str
    provider: str | None = None
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None


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
    ui_locales: str
    preferred_store_id: str | None
    view_type: str


def _manifest_definition() -> dict[str, Any]:
    for manifest_path in MANIFEST_PATH_CANDIDATES:
        if manifest_path.exists():
            return json.loads(manifest_path.read_text(encoding="utf-8"))
    searched = ", ".join(str(path) for path in MANIFEST_PATH_CANDIDATES)
    raise FileNotFoundError(f"Kaufland plugin manifest.json not found. Looked in: {searched}")


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
    value = options.get(key, default)
    return str(value)


def _int_option(options: Mapping[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    return int(value)


def _bool_option(options: Mapping[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


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


def _provider_from_claims(claims: Mapping[str, Any]) -> str | None:
    issuer = str(claims.get("iss") or "").strip().lower()
    if not issuer:
        return None
    if "account.kaufland.com" in issuer:
        return "cidaas"
    return issuer


def _user_from_oauth_claims(oauth: OauthSession) -> UserProfile | None:
    for token in (oauth.access_token, oauth.id_token):
        claims = _decode_jwt_claims(token)
        if not isinstance(claims, Mapping):
            continue
        sub = str(claims.get("sub") or "").strip()
        if not sub:
            continue
        return UserProfile(
            sub=sub,
            provider=_provider_from_claims(claims),
            email=str(claims.get("email")) if claims.get("email") else None,
            first_name=str(claims.get("given_name")) if claims.get("given_name") else None,
            last_name=str(claims.get("family_name")) if claims.get("family_name") else None,
        )
    return None


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
    return (storage_root / "kaufland_state.json").resolve()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(serialized)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _oauth_from_mapping(payload: Mapping[str, Any]) -> OauthSession | None:
    raw = payload.get("oauth")
    if not isinstance(raw, Mapping):
        return None
    access_token = str(raw.get("access_token") or "").strip()
    refresh_token = str(raw.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        return None
    return OauthSession(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=str(raw.get("expires_at")) if raw.get("expires_at") else None,
        scope=str(raw.get("scope")) if raw.get("scope") else None,
        token_type=str(raw.get("token_type")) if raw.get("token_type") else None,
        id_token=str(raw.get("id_token")) if raw.get("id_token") else None,
        client_id=str(raw.get("client_id") or DEFAULT_CIDAAS_CLIENT_ID),
        redirect_uri=str(raw.get("redirect_uri") or DEFAULT_REDIRECT_URI),
        auth_endpoint=str(raw.get("auth_endpoint") or DEFAULT_CIDAAS_AUTH_ENDPOINT),
        token_endpoint=str(raw.get("token_endpoint") or DEFAULT_CIDAAS_TOKEN_ENDPOINT),
    )


def _user_from_mapping(payload: Mapping[str, Any]) -> UserProfile | None:
    raw = payload.get("user")
    if not isinstance(raw, Mapping):
        return None
    sub = str(raw.get("sub") or "").strip()
    if not sub:
        return None
    return UserProfile(
        sub=sub,
        provider=str(raw.get("provider")) if raw.get("provider") else None,
        email=str(raw.get("email")) if raw.get("email") else None,
        first_name=str(raw.get("first_name")) if raw.get("first_name") else None,
        last_name=str(raw.get("last_name")) if raw.get("last_name") else None,
    )


def _pending_auth_from_mapping(payload: Mapping[str, Any]) -> PendingAuthFlow | None:
    raw = payload.get("pending_auth")
    if not isinstance(raw, Mapping):
        return None
    flow_id = str(raw.get("flow_id") or "").strip()
    verifier = str(raw.get("verifier") or "").strip()
    state = str(raw.get("state") or "").strip()
    if not flow_id or not verifier or not state:
        return None
    preferred_store = raw.get("preferred_store_id")
    return PendingAuthFlow(
        flow_id=flow_id,
        created_at=str(raw.get("created_at") or _iso_now()),
        verifier=verifier,
        state=state,
        auth_endpoint=str(raw.get("auth_endpoint") or DEFAULT_CIDAAS_AUTH_ENDPOINT),
        token_endpoint=str(raw.get("token_endpoint") or DEFAULT_CIDAAS_TOKEN_ENDPOINT),
        client_id=str(raw.get("client_id") or DEFAULT_CIDAAS_CLIENT_ID),
        redirect_uri=str(raw.get("redirect_uri") or DEFAULT_REDIRECT_URI),
        ui_locales=str(raw.get("ui_locales") or DEFAULT_UI_LOCALES),
        preferred_store_id=str(preferred_store) if preferred_store not in {None, ""} else None,
        view_type=str(raw.get("view_type") or DEFAULT_VIEW_TYPE),
    )


def _is_token_stale(oauth: OauthSession, *, skew_seconds: int = 300) -> bool:
    expires_at = _parse_iso_datetime(oauth.expires_at)
    if expires_at is None:
        return False
    return expires_at <= datetime.now(tz=UTC) + timedelta(seconds=skew_seconds)


def _to_cents(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value * 100))
    text = str(value).strip()
    if not text:
        return 0
    normalized = text.replace("EUR", "").replace("€", "").replace(" ", "").strip()
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif "," in normalized:
        normalized = normalized.replace(",", ".")
    try:
        return int(round(float(normalized) * 100))
    except ValueError:
        return 0


def _map_quantity_unit(value: Any) -> str:
    quantity_unit = str(value or "").strip().upper()
    if quantity_unit == "KG":
        return "kg"
    if quantity_unit == "G":
        return "g"
    if quantity_unit == "L":
        return "l"
    if quantity_unit == "ML":
        return "ml"
    return "pcs"


def _infer_position_mapping(position: Mapping[str, Any]) -> dict[str, Any]:
    total_cents = _to_cents(position.get("total"))
    quantity_raw = position.get("quantity") if position.get("quantity") is not None else 1
    try:
        quantity_value = float(quantity_raw)
    except (TypeError, ValueError):
        quantity_value = 1.0
    if quantity_value <= 0:
        quantity_value = 1.0
    explicit_unit_price_cents = _to_cents(position.get("unitPrice"))
    unit = _map_quantity_unit(position.get("quantityUnit"))
    discounts: list[dict[str, Any]] = []

    if explicit_unit_price_cents > 0:
        expected_total = int(round(explicit_unit_price_cents * quantity_value))
        if unit in {"kg", "g", "l", "ml"} and quantity_value == 1.0 and total_cents > 0:
            inferred_quantity = round(total_cents / explicit_unit_price_cents, 3)
            inferred_expected_total = int(round(explicit_unit_price_cents * inferred_quantity))
            if inferred_quantity > 0 and abs(inferred_expected_total - total_cents) <= 2:
                quantity_value = inferred_quantity
                expected_total = inferred_expected_total
        if abs(expected_total - total_cents) <= 2:
            unit_price_cents = explicit_unit_price_cents
        elif expected_total > total_cents:
            unit_price_cents = explicit_unit_price_cents
            discount_cents = expected_total - total_cents
            discounts.append(
                {
                    "type": "promotion",
                    "label": "Kaufland item discount",
                    "amount_cents": discount_cents,
                    "scope": "item",
                    "subkind": "promotion",
                    "funded_by": "retailer",
                }
            )
        else:
            if unit in {"kg", "g", "l", "ml"} and quantity_value == 1.0:
                unit = "pcs"
            unit_price_cents = int(round(total_cents / quantity_value)) if quantity_value else total_cents
    else:
        unit_price_cents = int(round(total_cents / quantity_value)) if quantity_value else total_cents

    return {
        "quantity_value": quantity_value,
        "unit": unit,
        "unit_price_cents": unit_price_cents,
        "line_total_cents": total_cents,
        "discounts": discounts,
    }


class KauflandPkceBootstrapper:
    def __init__(
        self,
        *,
        auth_endpoint: str,
        token_endpoint: str,
        client_id: str,
        redirect_uri: str,
        ui_locales: str,
        preferred_store_id: str | None,
        view_type: str,
    ) -> None:
        self._auth_endpoint = auth_endpoint
        self._token_endpoint = token_endpoint
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._ui_locales = ui_locales
        self._preferred_store_id = preferred_store_id
        self._view_type = view_type

    def build_pending_flow(self, *, timeout_seconds: int) -> tuple[PendingAuthFlow, AuthBrowserPlan]:
        verifier, challenge = _pkce_pair()
        flow_id = secrets.token_hex(16)
        state = secrets.token_urlsafe(24)
        auth_url = self._build_auth_url(challenge=challenge, state=state)
        pending = PendingAuthFlow(
            flow_id=flow_id,
            created_at=_iso_now(),
            verifier=verifier,
            state=state,
            auth_endpoint=self._auth_endpoint,
            token_endpoint=self._token_endpoint,
            client_id=self._client_id,
            redirect_uri=self._redirect_uri,
            ui_locales=self._ui_locales,
            preferred_store_id=self._preferred_store_id,
            view_type=self._view_type,
        )
        plan = AuthBrowserPlan(
            start_url=auth_url,
            callback_url_prefixes=(self._redirect_uri,),
            expected_callback_state=state,
            timeout_seconds=max(timeout_seconds, 30),
        )
        return pending, plan

    def _build_auth_url(self, *, challenge: str, state: str) -> str:
        params = [
            ("client_id", self._client_id),
            ("response_type", "code"),
            ("redirect_uri", self._redirect_uri),
            ("ui_locales", self._ui_locales),
            ("v", DEFAULT_CIDAAS_VERSION),
            ("view_type", self._view_type),
            ("preferredStore", self._preferred_store_id or ""),
            ("code_challenge", challenge),
            ("code_challenge_method", "S256"),
            ("state", state),
        ]
        return f"{self._auth_endpoint}?{urllib.parse.urlencode(params)}"


class KauflandOidcClient:
    def exchange_code(self, code: str, *, pending: PendingAuthFlow) -> OauthSession:
        data = {
            "code": code,
            "client_id": pending.client_id,
            "redirect_uri": pending.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": pending.verifier,
            "v": DEFAULT_CIDAAS_VERSION,
            "preferredStore": pending.preferred_store_id or "",
        }
        response = httpx.post(
            pending.token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=data,
            timeout=30.0,
            follow_redirects=True,
        )
        return self._parse_token_response(
            response,
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            auth_endpoint=pending.auth_endpoint,
            token_endpoint=pending.token_endpoint,
        )

    def refresh(self, oauth: OauthSession, *, preferred_store_id: str | None) -> OauthSession:
        response = httpx.post(
            oauth.token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "refresh_token": oauth.refresh_token,
                "grant_type": "refresh_token",
                "client_id": oauth.client_id,
                "v": DEFAULT_CIDAAS_VERSION,
                "preferredStore": preferred_store_id or "",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        return self._parse_token_response(
            response,
            client_id=oauth.client_id,
            redirect_uri=oauth.redirect_uri,
            auth_endpoint=oauth.auth_endpoint,
            token_endpoint=oauth.token_endpoint,
            previous_refresh_token=oauth.refresh_token,
        )

    def _parse_token_response(
        self,
        response: httpx.Response,
        *,
        client_id: str,
        redirect_uri: str,
        auth_endpoint: str,
        token_endpoint: str,
        previous_refresh_token: str | None = None,
    ) -> OauthSession:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if response.status_code in {400, 401} else "upstream_error"
            raise KauflandPluginError(
                f"Kaufland token exchange failed with HTTP {response.status_code}: {response.text[:300]}",
                code=code,
            ) from exc
        payload = response.json()
        access_token = str(payload.get("access_token") or "").strip()
        refresh_token = str(payload.get("refresh_token") or previous_refresh_token or "").strip()
        if not access_token or not refresh_token:
            raise KauflandPluginError(
                "Kaufland token response did not include access/refresh token",
                code="auth_required",
            )
        expires_in_raw = payload.get("expires_in")
        expires_in = int(expires_in_raw) if isinstance(expires_in_raw, int) else None
        return OauthSession(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=_expires_at_from_now(expires_in),
            scope=str(payload.get("scope")) if payload.get("scope") else None,
            token_type=str(payload.get("token_type")) if payload.get("token_type") else None,
            id_token=str(payload.get("id_token")) if payload.get("id_token") else None,
            client_id=client_id,
            redirect_uri=redirect_uri,
            auth_endpoint=auth_endpoint,
            token_endpoint=token_endpoint,
        )


class KauflandUserInfoClient:
    def __init__(self, *, base_url: str = DEFAULT_USERINFO_BASE_URL, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_user_info(self, access_token: str) -> UserProfile:
        response = httpx.get(
            self._base_url + "/users-srv/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=self._timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if response.status_code in {401, 403} else "upstream_error"
            raise KauflandPluginError(
                f"Kaufland userinfo failed with HTTP {response.status_code}: {response.text[:300]}",
                code=code,
            ) from exc
        payload = response.json()
        sub = str(payload.get("sub") or "").strip()
        if not sub:
            raise KauflandPluginError("Kaufland userinfo response did not include sub", code="auth_required")
        return UserProfile(
            sub=sub,
            provider=str(payload.get("provider")) if payload.get("provider") else None,
            email=str(payload.get("email")) if payload.get("email") else None,
            first_name=str(payload.get("given_name")) if payload.get("given_name") else None,
            last_name=str(payload.get("family_name")) if payload.get("family_name") else None,
        )


class KauflandTransactionsClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_LOYALTY_BASE_URL,
        loyalty_client_id: str = DEFAULT_LOYALTY_CLIENT_ID,
        app_platform: str = DEFAULT_APP_PLATFORM,
        app_version: str = DEFAULT_APP_VERSION,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._loyalty_client_id = loyalty_client_id
        self._app_platform = app_platform
        self._app_version = app_version
        self._timeout_seconds = timeout_seconds

    def list_transactions(self, *, access_token: str, user_id: str, country_code: str, start: int, limit: int) -> list[dict[str, Any]]:
        response = httpx.get(
            self._base_url + f"/api/v2/customers/{urllib.parse.quote(user_id, safe='')}/transactions",
            params={
                "start": start,
                "limit": limit,
                "country": country_code,
                "version": 2,
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "client-id": self._loyalty_client_id,
                "app-platform": self._app_platform,
                "app-version": self._app_version,
            },
            timeout=self._timeout_seconds,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            code = "auth_required" if response.status_code in {401, 403} else "upstream_error"
            raise KauflandPluginError(
                f"Kaufland transaction API failed with HTTP {response.status_code}: {response.text[:300]}",
                code=code,
                retryable=response.status_code >= 500,
            ) from exc
        payload = response.json()
        if not isinstance(payload, list):
            raise KauflandPluginError("Kaufland transaction API returned a non-list payload", code="upstream_error")
        return [item for item in payload if isinstance(item, dict)]


class KauflandFixtureClient:
    def __init__(self, fixture_file: Path) -> None:
        self._fixture_file = fixture_file

    def list_transactions(self, *, access_token: str, user_id: str, country_code: str, start: int, limit: int) -> list[dict[str, Any]]:
        del access_token, user_id, country_code
        payload = _load_json(self._fixture_file)
        if isinstance(payload, list):
            transactions = payload
        else:
            raw = payload.get("transactions", [])
            transactions = raw if isinstance(raw, list) else []
        return [item for item in transactions[start : start + limit] if isinstance(item, dict)]


class KauflandReceiptPlugin:
    def __init__(self) -> None:
        self._manifest = ConnectorManifest.model_validate(_manifest_definition())
        self._list_cache: dict[str, dict[str, Any]] = {}

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
            if validated.action == "healthcheck":
                return HealthcheckResponse(output=self._healthcheck())
            if validated.action == "discover_records":
                return DiscoverRecordsResponse(output=self._discover_records(validated.input.limit))
            if validated.action == "fetch_record":
                record = self._fetch_record(validated.input.record_ref)
                return FetchRecordResponse(
                    output=FetchRecordOutput(record_ref=validated.input.record_ref, record=record)
                )
            if validated.action == "normalize_record":
                return NormalizeRecordResponse(
                    output=NormalizeRecordOutput(normalized_record=self._normalize_record(validated.input.record))
                )
            if validated.action == "extract_discounts":
                return ExtractDiscountsResponse(
                    output=ExtractDiscountsOutput(discounts=self._extract_discounts(validated.input.record))
                )
            if validated.action == "get_diagnostics":
                return GetDiagnosticsResponse(output=DiagnosticsOutput(diagnostics=self._diagnostics()))
        except KauflandPluginError as exc:
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
        raise AssertionError(f"unsupported action {validated.action!r}")

    def _start_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        if _resolve_optional_path(options.get("fixture_file")) is not None:
            return AuthLifecycleOutput(status="not_supported", detail="Fixture mode does not support live auth bootstrap.")
        state_file = _state_file_for_context(context.storage.data_dir, options)
        existing_payload = _load_json(state_file) if state_file.exists() else {}
        if not _bool_option(options, "force_reauth", False):
            oauth = _oauth_from_mapping(existing_payload)
            user = _user_from_mapping(existing_payload)
            if oauth is not None and user is not None:
                return AuthLifecycleOutput(
                    status="no_op",
                    detail="Kaufland auth state already exists; set force_reauth=true to replace it.",
                )
        bootstrapper = KauflandPkceBootstrapper(
            auth_endpoint=_string_option(options, "cidaas_auth_endpoint", DEFAULT_CIDAAS_AUTH_ENDPOINT),
            token_endpoint=_string_option(options, "cidaas_token_endpoint", DEFAULT_CIDAAS_TOKEN_ENDPOINT),
            client_id=_string_option(options, "cidaas_client_id", DEFAULT_CIDAAS_CLIENT_ID),
            redirect_uri=_string_option(options, "redirect_uri", DEFAULT_REDIRECT_URI),
            ui_locales=_string_option(options, "ui_locales", DEFAULT_UI_LOCALES),
            preferred_store_id=str(options.get("preferred_store_id")) if options.get("preferred_store_id") else None,
            view_type=_string_option(options, "view_type", DEFAULT_VIEW_TYPE),
        )
        pending, browser_plan = bootstrapper.build_pending_flow(
            timeout_seconds=_int_option(options, "auth_timeout_seconds", DEFAULT_AUTH_TIMEOUT_SECONDS)
        )
        payload = dict(existing_payload)
        payload["schema_version"] = STATE_SCHEMA_VERSION
        payload["tracking_source_id"] = context.tracking_source_id
        payload["import_source"] = "auth_browser_plan"
        payload["pending_auth"] = asdict(pending)
        _write_json(state_file, payload)
        return AuthLifecycleOutput(
            status="started",
            flow_id=pending.flow_id,
            next_poll_after_seconds=2,
            detail="Kaufland browser login started through the public auth-browser runtime contract.",
            metadata=build_auth_browser_metadata(flow_id=pending.flow_id, plan=browser_plan),
        )

    def _cancel_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        if _resolve_optional_path(options.get("fixture_file")) is not None:
            return AuthLifecycleOutput(status="not_supported", detail="Fixture mode does not support live auth bootstrap.")
        state_file = _state_file_for_context(context.storage.data_dir, options)
        if not state_file.exists():
            return AuthLifecycleOutput(status="no_op", detail="No pending Kaufland auth flow exists.")
        payload = _load_json(state_file)
        if "pending_auth" not in payload:
            return AuthLifecycleOutput(status="no_op", detail="No pending Kaufland auth flow exists.")
        payload.pop("pending_auth", None)
        _write_json(state_file, payload)
        return AuthLifecycleOutput(status="canceled", detail="Pending Kaufland browser auth flow cleared.")

    def _confirm_auth(self) -> AuthLifecycleOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        if _resolve_optional_path(options.get("fixture_file")) is not None:
            return AuthLifecycleOutput(status="not_supported", detail="Fixture mode does not support live auth bootstrap.")
        state_file = _state_file_for_context(context.storage.data_dir, options)
        if not state_file.exists():
            raise KauflandPluginError(
                "Kaufland auth confirmation requires a pending browser auth flow",
                code="auth_required",
            )
        payload = _load_json(state_file)
        pending = _pending_auth_from_mapping(payload)
        if pending is None:
            raise KauflandPluginError(
                "Kaufland auth confirmation requires a pending browser auth flow",
                code="auth_required",
            )
        browser_result = parse_auth_browser_runtime_context(context.runtime_context)
        if browser_result is None:
            raise KauflandPluginError("Kaufland auth confirmation is missing browser callback context", code="auth_required")
        if browser_result.flow_id != pending.flow_id:
            raise KauflandPluginError("Kaufland auth confirmation flow_id mismatch", code="auth_required")
        code, returned_state, error = _parse_redirect(browser_result.callback_url)
        if returned_state != pending.state:
            raise KauflandPluginError("state mismatch on Kaufland OAuth redirect", code="auth_required")
        if error:
            raise KauflandPluginError(f"Kaufland OAuth redirect returned error={error}", code="auth_required")
        if not code:
            raise KauflandPluginError(
                "Kaufland OAuth redirect did not include an authorization code",
                code="auth_required",
            )
        oidc = KauflandOidcClient().exchange_code(code, pending=pending)
        user = _user_from_oauth_claims(oidc)
        if user is None:
            user = KauflandUserInfoClient(
                base_url=_string_option(options, "userinfo_base_url", DEFAULT_USERINFO_BASE_URL),
                timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            ).get_user_info(oidc.access_token)
        payload["schema_version"] = STATE_SCHEMA_VERSION
        payload["oauth"] = asdict(oidc)
        payload["user"] = asdict(user)
        payload["settings"] = {
            "country_code": _string_option(options, "country_code", DEFAULT_COUNTRY_CODE),
            "preferred_store_id": pending.preferred_store_id,
            "ui_locales": pending.ui_locales,
            "app_version": _string_option(options, "app_version", DEFAULT_APP_VERSION),
            "app_platform": _string_option(options, "app_platform", DEFAULT_APP_PLATFORM),
            "loyalty_client_id": _string_option(options, "loyalty_client_id", DEFAULT_LOYALTY_CLIENT_ID),
        }
        payload["import_source"] = "auth_browser_plan"
        payload["last_auth_at"] = _iso_now()
        payload.pop("pending_auth", None)
        _write_json(state_file, payload)
        return AuthLifecycleOutput(
            status="confirmed",
            flow_id=pending.flow_id,
            detail="Kaufland browser login completed and receipt API credentials were stored.",
            metadata={
                "browser_mode": browser_result.mode,
                "callback_url": browser_result.callback_url,
                "user_sub": user.sub,
            },
        )

    def _get_auth_status(self) -> GetAuthStatusOutput:
        context = load_plugin_runtime_context()
        options = context.connector_options
        fixture_file = _resolve_optional_path(options.get("fixture_file"))
        state_file = _state_file_for_context(context.storage.data_dir, options)
        if fixture_file is not None:
            return GetAuthStatusOutput(
                status="authenticated",
                is_authenticated=True,
                available_actions=self._manifest.auth.available_actions() if self._manifest.auth else (),
                implemented_actions=self._manifest.auth.implemented_actions if self._manifest.auth else (),
                compatibility_actions=self._manifest.auth.compatibility_actions if self._manifest.auth else (),
                reserved_actions=self._manifest.auth.reserved_actions if self._manifest.auth else (),
                detail="Kaufland plugin is running in fixture mode.",
                metadata={
                    "fixture_mode": True,
                    "fixture_file": str(fixture_file),
                    "supports_auth_browser_plan": True,
                    "supports_headless_refresh": False,
                },
            )
        if not state_file.exists():
            return GetAuthStatusOutput(
                status="requires_auth",
                is_authenticated=False,
                available_actions=self._manifest.auth.available_actions() if self._manifest.auth else (),
                implemented_actions=self._manifest.auth.implemented_actions if self._manifest.auth else (),
                compatibility_actions=self._manifest.auth.compatibility_actions if self._manifest.auth else (),
                reserved_actions=self._manifest.auth.reserved_actions if self._manifest.auth else (),
                detail="Kaufland requires authentication. Run start_auth for browser bootstrap.",
                metadata={
                    "supports_auth_browser_plan": True,
                    "supports_headless_refresh": True,
                    "state_file": str(state_file),
                },
            )
        payload = _load_json(state_file)
        pending = _pending_auth_from_mapping(payload)
        oauth = _oauth_from_mapping(payload)
        user = _user_from_mapping(payload)
        if pending is not None and oauth is None:
            return GetAuthStatusOutput(
                status="pending",
                is_authenticated=False,
                available_actions=self._manifest.auth.available_actions() if self._manifest.auth else (),
                implemented_actions=self._manifest.auth.implemented_actions if self._manifest.auth else (),
                compatibility_actions=self._manifest.auth.compatibility_actions if self._manifest.auth else (),
                reserved_actions=self._manifest.auth.reserved_actions if self._manifest.auth else (),
                detail="Kaufland browser login is prepared but not finished.",
                metadata={
                    "state_file": str(state_file),
                    "pending_auth_flow_id": pending.flow_id,
                    "supports_auth_browser_plan": True,
                    "supports_headless_refresh": True,
                },
            )
        if oauth is None or user is None:
            return GetAuthStatusOutput(
                status="requires_auth",
                is_authenticated=False,
                available_actions=self._manifest.auth.available_actions() if self._manifest.auth else (),
                implemented_actions=self._manifest.auth.implemented_actions if self._manifest.auth else (),
                compatibility_actions=self._manifest.auth.compatibility_actions if self._manifest.auth else (),
                reserved_actions=self._manifest.auth.reserved_actions if self._manifest.auth else (),
                detail="Kaufland state exists but is missing OAuth or user-info material.",
                metadata={
                    "state_file": str(state_file),
                    "supports_auth_browser_plan": True,
                    "supports_headless_refresh": True,
                },
            )
        return GetAuthStatusOutput(
            status="authenticated",
            is_authenticated=True,
            available_actions=self._manifest.auth.available_actions() if self._manifest.auth else (),
            implemented_actions=self._manifest.auth.implemented_actions if self._manifest.auth else (),
            compatibility_actions=self._manifest.auth.compatibility_actions if self._manifest.auth else (),
            reserved_actions=self._manifest.auth.reserved_actions if self._manifest.auth else (),
            detail="Kaufland receipt session is configured.",
            metadata={
                "supports_auth_browser_plan": True,
                "supports_headless_refresh": True,
                "state_file": str(state_file),
                "user_sub": user.sub,
                "expires_at": oauth.expires_at,
                "country_code": self._country_code(payload, options),
                "preferred_store_id": self._preferred_store_id(payload, options),
                "pending_auth_flow_id": pending.flow_id if pending is not None else None,
                "last_success_at": payload.get("last_success_at"),
                "last_failure_at": payload.get("last_failure_at"),
            },
        )

    def _healthcheck(self) -> HealthcheckOutput:
        context = load_plugin_runtime_context()
        try:
            transactions, diagnostics = self._list_transactions(context, start=0, limit=1)
        except KauflandPluginError as exc:
            self._mark_state_failure(context, str(exc))
            return HealthcheckOutput(healthy=False, detail=str(exc), diagnostics={})
        self._mark_state_success(context, sample_size=len(transactions))
        return HealthcheckOutput(healthy=True, sample_size=len(transactions), diagnostics=diagnostics)

    def _discover_records(self, limit: int | None) -> DiscoverRecordsOutput:
        context = load_plugin_runtime_context()
        requested_limit = limit or _int_option(context.connector_options, "discovery_limit", DEFAULT_DISCOVERY_LIMIT)
        transactions, _diagnostics = self._list_transactions(context, start=0, limit=requested_limit)
        self._list_cache = {
            str(transaction.get("id")): transaction
            for transaction in transactions
            if str(transaction.get("id") or "").strip()
        }
        self._mark_state_success(context, sample_size=len(transactions))
        return DiscoverRecordsOutput(
            records=[
                RecordReference(
                    record_ref=str(transaction["id"]),
                    metadata={
                        "timestamp": transaction.get("timestamp"),
                        "store_name": (transaction.get("store") or {}).get("name")
                        if isinstance(transaction.get("store"), Mapping)
                        else None,
                        "sum": transaction.get("sum"),
                        "currency": transaction.get("currency"),
                    },
                )
                for transaction in transactions
                if transaction.get("id") is not None
            ],
            next_cursor=None,
        )

    def _fetch_record(self, record_ref: str) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        transaction = self._list_cache.get(record_ref)
        if transaction is None:
            lookup_limit = _int_option(context.connector_options, "lookup_limit", DEFAULT_LOOKUP_LIMIT)
            transactions, _diagnostics = self._list_transactions(context, start=0, limit=lookup_limit)
            for item in transactions:
                if str(item.get("id") or "") == record_ref:
                    transaction = item
                    break
        if transaction is None:
            raise KauflandPluginError(f"Kaufland receipt {record_ref} was not found", code="invalid_request")
        self._mark_state_success(context, sample_size=1)
        return {
            "id": str(record_ref),
            "source": "kaufland_de",
            "transaction": transaction,
            "fetched_at": _iso_now(),
        }

    def _normalize_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        transaction = record.get("transaction") if isinstance(record.get("transaction"), Mapping) else record
        if not isinstance(transaction, Mapping):
            raise KauflandPluginError("Kaufland fetch_record payload is missing transaction detail", code="contract_violation")
        store = transaction.get("store") if isinstance(transaction.get("store"), Mapping) else {}
        positions = transaction.get("positions") if isinstance(transaction.get("positions"), list) else []
        refund_positions = (
            transaction.get("refundPositions") if isinstance(transaction.get("refundPositions"), list) else []
        )
        mapped_items: list[dict[str, Any]] = []
        for position in positions:
            if not isinstance(position, Mapping):
                continue
            mapped = _infer_position_mapping(position)
            mapped_items.append(
                {
                    "id": position.get("id"),
                    "name": position.get("name") or position.get("itemno") or "article",
                    "qty": mapped["quantity_value"],
                    "unit": mapped["unit"],
                    "unitPrice": mapped["unit_price_cents"],
                    "lineTotal": mapped["line_total_cents"],
                    "category": position.get("materialGroup"),
                    "discounts": mapped["discounts"],
                }
            )
        for position in refund_positions:
            if not isinstance(position, Mapping):
                continue
            total_cents = -abs(_to_cents(position.get("total")))
            quantity = position.get("quantity") if position.get("quantity") is not None else 1
            try:
                quantity_value = float(quantity)
            except (TypeError, ValueError):
                quantity_value = 1.0
            mapped_items.append(
                {
                    "id": position.get("id"),
                    "name": f"{position.get('name') or position.get('itemno') or 'refund'} (refund)",
                    "qty": quantity_value,
                    "unit": "pcs",
                    "unitPrice": int(round(total_cents / quantity_value)) if quantity_value else total_cents,
                    "lineTotal": total_cents,
                    "category": position.get("materialGroup"),
                }
            )
        if not mapped_items:
            raise KauflandPluginError("Kaufland transaction payload did not contain any positions", code="contract_violation")
        store_address_parts = [str(store.get("street") or "").strip(), str(store.get("city") or "").strip()]
        payload = {
            "id": transaction.get("id") or record.get("id"),
            "purchasedAt": transaction.get("timestamp"),
            "store": {
                "id": store.get("id"),
                "name": store.get("name") or _string_option(options, "store_name", "Kaufland"),
                "address": ", ".join(part for part in store_address_parts if part),
            },
            "totalGross": transaction.get("sum"),
            "discountTotal": transaction.get("saving"),
            "currency": transaction.get("currency") or "EUR",
            "items": mapped_items,
        }
        normalized = normalize_receipt(payload)
        items: list[dict[str, Any]] = []
        for item in normalized.items:
            is_deposit = "pfand" in item.name.lower()
            items.append(
                {
                    "line_no": item.line_no,
                    "source_item_id": mapped_items[item.line_no - 1].get("id") or f"{normalized.id}:{item.line_no}",
                    "name": item.name,
                    "qty": str(item.qty),
                    "unit": item.unit,
                    "unit_price_cents": item.unit_price,
                    "line_total_cents": item.line_total,
                    "is_deposit": is_deposit,
                    "vat_rate": str(item.vat_rate) if item.vat_rate is not None else None,
                    "category": item.category,
                    "discounts": item.discounts,
                }
            )
        return {
            "id": normalized.id,
            "purchased_at": normalized.purchased_at.isoformat(),
            "store_id": normalized.store_id or "kaufland_de",
            "store_name": normalized.store_name or _string_option(options, "store_name", "Kaufland"),
            "store_address": normalized.store_address,
            "total_gross_cents": normalized.total_gross,
            "currency": normalized.currency,
            "discount_total_cents": normalized.discount_total or 0,
            "fingerprint": normalized.fingerprint,
            "items": items,
            "raw_json": {
                "transaction": dict(transaction),
            },
        }

    def _extract_discounts(self, record: Mapping[str, Any]) -> list[dict[str, Any]]:
        transaction = record.get("transaction") if isinstance(record.get("transaction"), Mapping) else record
        positions = transaction.get("positions") if isinstance(transaction.get("positions"), list) else []
        promotions = transaction.get("promotions") if isinstance(transaction.get("promotions"), list) else []
        rows: list[dict[str, Any]] = []
        inferred_item_discount_total = 0
        for index, position in enumerate(positions, start=1):
            if not isinstance(position, Mapping):
                continue
            mapped = _infer_position_mapping(position)
            for discount in mapped["discounts"]:
                amount_cents = abs(_to_cents(discount.get("amount_cents")))
                if amount_cents <= 0:
                    continue
                inferred_item_discount_total += amount_cents
                rows.append(
                    {
                        "line_no": index,
                        "type": "promotion",
                        "promotion_id": str(position.get("id")) if position.get("id") else None,
                        "amount_cents": amount_cents,
                        "label": str(discount.get("label") or position.get("name") or "Kaufland item discount"),
                        "scope": "item",
                        "subkind": "promotion",
                        "funded_by": "retailer",
                    }
                )
        for promotion in promotions:
            if not isinstance(promotion, Mapping):
                continue
            amount_cents = abs(_to_cents(promotion.get("saving")))
            if amount_cents <= 0:
                continue
            rows.append(
                {
                    "line_no": None,
                    "type": "promotion",
                    "promotion_id": str(promotion.get("id")) if promotion.get("id") else None,
                    "amount_cents": amount_cents,
                    "label": str(promotion.get("desc") or "Kaufland promotion"),
                    "scope": "transaction",
                    "subkind": "promotion",
                    "funded_by": "retailer",
                }
            )
        if rows and all(abs(_to_cents(promotion.get("saving"))) <= 0 for promotion in promotions if isinstance(promotion, Mapping)):
            saving_cents = abs(_to_cents(transaction.get("saving")))
            if saving_cents <= inferred_item_discount_total:
                return rows
        if rows:
            return rows
        saving_cents = abs(_to_cents(transaction.get("saving")))
        if saving_cents <= 0:
            return rows
        labels = [
            str(promotion.get("desc") or "").strip()
            for promotion in promotions
            if isinstance(promotion, Mapping) and str(promotion.get("desc") or "").strip()
        ]
        label = " / ".join(dict.fromkeys(labels)) if labels else "Kaufland discount"
        rows.append(
            {
                "line_no": None,
                "type": "promotion",
                "promotion_id": None,
                "amount_cents": saving_cents,
                "label": label,
                "scope": "transaction",
                "subkind": "promotion",
                "funded_by": "retailer",
            }
        )
        return rows

    def _diagnostics(self) -> dict[str, Any]:
        context = load_plugin_runtime_context()
        options = context.connector_options
        state_file = _state_file_for_context(context.storage.data_dir, options)
        fixture_file = _resolve_optional_path(options.get("fixture_file"))
        payload: dict[str, Any] = {
            "plugin_type": "external_receipt_plugin",
            "supports_auth_browser_plan": True,
            "supports_headless_refresh": True,
            "fixture_mode": fixture_file is not None,
            "fixture_file": str(fixture_file) if fixture_file is not None else None,
            "state_file": str(state_file),
            "country_code": _string_option(options, "country_code", DEFAULT_COUNTRY_CODE),
            "preferred_store_id": str(options.get("preferred_store_id")) if options.get("preferred_store_id") else None,
            "cidaas_client_id": _string_option(options, "cidaas_client_id", DEFAULT_CIDAAS_CLIENT_ID),
            "loyalty_client_id": _string_option(options, "loyalty_client_id", DEFAULT_LOYALTY_CLIENT_ID),
            "app_version": _string_option(options, "app_version", DEFAULT_APP_VERSION),
        }
        if state_file.exists():
            state_payload = _load_json(state_file)
            payload["last_success_at"] = state_payload.get("last_success_at")
            payload["last_failure_at"] = state_payload.get("last_failure_at")
            payload["last_auth_at"] = state_payload.get("last_auth_at")
            payload["import_source"] = state_payload.get("import_source")
            user = _user_from_mapping(state_payload)
            if user is not None:
                payload["user_sub"] = user.sub
            oauth = _oauth_from_mapping(state_payload)
            if oauth is not None:
                payload["expires_at"] = oauth.expires_at
        return payload

    def _country_code(self, payload: Mapping[str, Any], options: Mapping[str, Any]) -> str:
        settings = payload.get("settings")
        if isinstance(settings, Mapping) and settings.get("country_code"):
            return str(settings.get("country_code"))
        return _string_option(options, "country_code", DEFAULT_COUNTRY_CODE)

    def _preferred_store_id(self, payload: Mapping[str, Any], options: Mapping[str, Any]) -> str | None:
        settings = payload.get("settings")
        if isinstance(settings, Mapping) and settings.get("preferred_store_id"):
            return str(settings.get("preferred_store_id"))
        if options.get("preferred_store_id"):
            return str(options.get("preferred_store_id"))
        pending = _pending_auth_from_mapping(payload)
        return pending.preferred_store_id if pending is not None else None

    def _mark_state_success(self, context: Any, *, sample_size: int) -> None:
        options = context.connector_options
        if _resolve_optional_path(options.get("fixture_file")) is not None:
            return
        state_file = _state_file_for_context(context.storage.data_dir, options)
        if not state_file.exists():
            return
        payload = _load_json(state_file)
        payload["last_success_at"] = _iso_now()
        payload["last_sample_size"] = sample_size
        payload.pop("last_failure_at", None)
        payload.pop("last_failure_message", None)
        _write_json(state_file, payload)

    def _mark_state_failure(self, context: Any, message: str) -> None:
        options = context.connector_options
        if _resolve_optional_path(options.get("fixture_file")) is not None:
            return
        state_file = _state_file_for_context(context.storage.data_dir, options)
        payload = _load_json(state_file) if state_file.exists() else {"schema_version": STATE_SCHEMA_VERSION}
        payload["last_failure_at"] = _iso_now()
        payload["last_failure_message"] = message
        _write_json(state_file, payload)

    def _ensure_live_state(
        self,
        context: Any,
    ) -> tuple[Path, dict[str, Any], OauthSession, UserProfile, str, str | None]:
        options = context.connector_options
        state_file = _state_file_for_context(context.storage.data_dir, options)
        if not state_file.exists():
            raise KauflandPluginError("Kaufland requires authentication before syncing receipts", code="auth_required")
        payload = _load_json(state_file)
        oauth = _oauth_from_mapping(payload)
        if oauth is None:
            raise KauflandPluginError("Kaufland state is missing OAuth tokens", code="auth_required")
        preferred_store_id = self._preferred_store_id(payload, options)
        if _is_token_stale(oauth):
            oauth = KauflandOidcClient().refresh(oauth, preferred_store_id=preferred_store_id)
            payload["oauth"] = asdict(oauth)
            payload["last_auth_refresh_at"] = _iso_now()
            _write_json(state_file, payload)
        user = _user_from_mapping(payload)
        if user is None:
            user = _user_from_oauth_claims(oauth)
        if user is None:
            user = KauflandUserInfoClient(
                base_url=_string_option(options, "userinfo_base_url", DEFAULT_USERINFO_BASE_URL),
                timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            ).get_user_info(oauth.access_token)
            payload["user"] = asdict(user)
            _write_json(state_file, payload)
        elif payload.get("user") is None:
            payload["user"] = asdict(user)
            _write_json(state_file, payload)
        return state_file, payload, oauth, user, self._country_code(payload, options), preferred_store_id

    def _list_transactions(self, context: Any, *, start: int, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        options = context.connector_options
        fixture_file = _resolve_optional_path(options.get("fixture_file"))
        diagnostics: dict[str, Any]
        if fixture_file is not None:
            client = KauflandFixtureClient(fixture_file)
            transactions = client.list_transactions(
                access_token="fixture",
                user_id="fixture-user",
                country_code=_string_option(options, "country_code", DEFAULT_COUNTRY_CODE),
                start=start,
                limit=limit,
            )
            diagnostics = {"fixture_mode": True, "fixture_file": str(fixture_file)}
            return transactions, diagnostics
        state_file, payload, oauth, user, country_code, preferred_store_id = self._ensure_live_state(context)
        client = KauflandTransactionsClient(
            base_url=_string_option(options, "loyalty_base_url", DEFAULT_LOYALTY_BASE_URL),
            loyalty_client_id=_string_option(options, "loyalty_client_id", DEFAULT_LOYALTY_CLIENT_ID),
            app_platform=_string_option(options, "app_platform", DEFAULT_APP_PLATFORM),
            app_version=_string_option(options, "app_version", DEFAULT_APP_VERSION),
            timeout_seconds=_int_option(options, "timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        )
        diagnostics = {
            "fixture_mode": False,
            "state_file": str(state_file),
            "user_sub": user.sub,
            "country_code": country_code,
            "preferred_store_id": preferred_store_id,
        }
        try:
            transactions = client.list_transactions(
                access_token=oauth.access_token,
                user_id=user.sub,
                country_code=country_code,
                start=start,
                limit=limit,
            )
        except KauflandPluginError as exc:
            if exc.code != "auth_required":
                raise
            oauth = KauflandOidcClient().refresh(oauth, preferred_store_id=preferred_store_id)
            payload["oauth"] = asdict(oauth)
            payload["last_auth_refresh_at"] = _iso_now()
            _write_json(state_file, payload)
            diagnostics["refreshed_after_auth_error"] = True
            transactions = client.list_transactions(
                access_token=oauth.access_token,
                user_id=user.sub,
                country_code=country_code,
                start=start,
                limit=limit,
            )
        return transactions, diagnostics
