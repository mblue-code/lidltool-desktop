from __future__ import annotations

import base64
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

DESKTOP_ROOT = Path(__file__).resolve().parents[4]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.config import AppConfig
from lidltool.connectors.runtime.context import build_plugin_runtime_environment
from lidltool.connectors.sdk import ReceiptConnectorContractFixture, assert_receipt_connector_contract
from lidltool.connectors.sdk.manifest import ConnectorManifest
from lidltool.connectors.sdk.runtime import (
    AuthBrowserResult,
    PLUGIN_RUNTIME_CONTEXT_ENV,
    build_auth_browser_runtime_context,
    parse_auth_browser_start_request,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = PLUGIN_ROOT / "plugin.py"
FIXTURE_PATH = PLUGIN_ROOT / "fixtures" / "raw_records.json"
MANIFEST = ConnectorManifest.model_validate_json((PLUGIN_ROOT / "manifest.json").read_text(encoding="utf-8"))
SAMPLE_EBON_TEXT = """*** P E N N Y - M A R K T  GmbH ***
Hauptstraße 11
38550 Isenbüttel
UID Nr.: DE202748117
EUR
GL MILD&NUSSIG 1,89 B
App-Preis-Rabatt -0,12 B
MIREE KNOBLAUCH 1,11 B
App-Preis-Rabatt -0,12 B
PHILAD. NATUR 2,29 B
W&C Knoblauchsau 0,89 B
Knorr Scha.Sauce 1,69 B
Hela Gewürzketch 3,39 B
SUMME EUR 11,02
Geg. Mastercard EUR 11,02
Datum: 25.04.2026
Uhrzeit: 20:09:16 Uhr
Beleg-Nr. 0355
B= 7,0% 10,30 0,72 11,02
Markt:2687 Kasse:2 Bed.:181818
0,24 EUR gespart
"""


def _future_expiry() -> str:
    return (datetime.now(tz=UTC) + timedelta(hours=2)).isoformat()


def _load_plugin_module():
    module_name = "penny_receipt_plugin"
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    spec = importlib.util.spec_from_file_location(module_name, PLUGIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Penny plugin module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_env(
    tmp_path: Path,
    *,
    connector_options: dict[str, object] | None = None,
    runtime_context: dict[str, object] | None = None,
) -> dict[str, str]:
    config = AppConfig(
        db_path=tmp_path / "penny.sqlite",
        config_dir=tmp_path / "config",
        source=MANIFEST.source_id,
    )
    return build_plugin_runtime_environment(
        source_config=config,
        source_id=MANIFEST.source_id,
        tracking_source_id=MANIFEST.source_id,
        manifest=MANIFEST,
        working_directory=PLUGIN_ROOT,
        connector_options=connector_options or {},
        runtime_context=runtime_context,
    )


def _encode_jwt(payload: dict[str, object]) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def _segment(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{_segment(header)}.{_segment(payload)}."


def test_penny_contract_passes_in_fixture_mode(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    env = _runtime_env(tmp_path, connector_options={"fixture_file": str(FIXTURE_PATH)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", env["LIDLTOOL_CONFIG_DIR"])

    assert_receipt_connector_contract(
        plugin,
        manifest=MANIFEST,
        fixture=ReceiptConnectorContractFixture(expect_discounts=True),
    )


def test_penny_start_auth_reuses_normal_chrome_session(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    state_file = tmp_path / "penny-state.json"
    env = _runtime_env(tmp_path, connector_options={"state_file": str(state_file)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", env["LIDLTOOL_CONFIG_DIR"])
    monkeypatch.setattr(module, "_chrome_user_data_dir_for_options", lambda options: tmp_path / "Chrome")
    monkeypatch.setattr(
        module,
        "_capture_storage_state_from_running_chrome_session",
        lambda **kwargs: {
            "cookies": [
                {
                    "name": "KEYCLOAK_IDENTITY",
                    "value": "fixture-cookie",
                    "domain": ".account.penny.de",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "expires": -1,
                }
            ],
            "origins": [],
            "user_agent": "Mozilla/5.0",
        },
    )

    started = plugin.invoke_action({"action": "start_auth"})
    assert started["ok"] is True
    assert started["output"]["status"] == "confirmed"
    assert started["output"]["metadata"]["bootstrap_source"] == "chrome_cookie_export"

    status = plugin.invoke_action({"action": "get_auth_status"})
    assert status["ok"] is True
    assert status["output"]["status"] == "authenticated"
    assert status["output"]["metadata"]["bootstrap_source"] == "chrome_cookie_export"

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_payload["browser_session"]["bootstrap_source"] == "chrome_cookie_export"


def test_penny_shared_browser_auth_flow_persists_oauth_state(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    state_file = tmp_path / "penny-state.json"

    class _FakeOidcClient:
        def __init__(self, **kwargs: object) -> None:
            self._kwargs = kwargs

        def resolve_endpoints(self) -> tuple[str, str]:
            return (
                "https://account.penny.de/realms/penny/protocol/openid-connect/auth",
                "https://account.penny.de/realms/penny/protocol/openid-connect/token",
            )

        def exchange_code(self, code: str, *, pending: object) -> object:
            del pending
            assert code == "auth-code"
            return module.OauthSession(
                access_token=_encode_jwt(
                    {
                        "sub": "penny-user-1",
                        "email": "penny.contest956@passmail.com",
                        "given_name": "Penny",
                        "family_name": "Fixture",
                        "iss": "https://account.penny.de/realms/penny",
                    }
                ),
                refresh_token="refresh-token",
                expires_at=_future_expiry(),
            )

    monkeypatch.setattr(module, "PennyOidcClient", _FakeOidcClient)

    start_env = _runtime_env(tmp_path, connector_options={"state_file": str(state_file)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, start_env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", start_env["LIDLTOOL_CONFIG_DIR"])

    started = plugin.invoke_action({"action": "start_auth"})
    assert started["ok"] is True
    request = parse_auth_browser_start_request(started["output"]["metadata"])
    assert request is not None
    assert request.plan.start_url.startswith("https://account.penny.de/realms/penny/protocol/openid-connect/auth?")
    assert request.plan.callback_url_prefixes == ("https://www.penny.de/app/login",)
    assert request.plan.auto_launch_browser is False
    assert "client_id=pennyandroid" in request.plan.start_url
    assert "app_container=android" in request.plan.start_url

    pending_status = plugin.invoke_action({"action": "get_auth_status"})
    assert pending_status["ok"] is True
    assert pending_status["output"]["status"] == "pending"
    assert pending_status["output"]["metadata"]["auth_start_url"] == request.plan.start_url
    assert pending_status["output"]["metadata"]["manual_callback_supported"] is True

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    callback_url = (
        "https://www.penny.de/app/login?code=auth-code&state="
        + state_payload["pending_auth"]["state"]
    )
    browser_result = AuthBrowserResult(
        flow_id=state_payload["pending_auth"]["flow_id"],
        session_id="session-1",
        mode="remote_vnc",
        start_url=request.plan.start_url,
        final_url=callback_url,
        callback_url=callback_url,
        started_at="2026-04-23T18:00:00+00:00",
        completed_at="2026-04-23T18:01:00+00:00",
    )
    confirm_env = _runtime_env(
        tmp_path,
        connector_options={"state_file": str(state_file)},
        runtime_context=build_auth_browser_runtime_context(browser_result),
    )
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, confirm_env[PLUGIN_RUNTIME_CONTEXT_ENV])

    confirmed = plugin.invoke_action({"action": "confirm_auth"})
    assert confirmed["ok"] is True
    assert confirmed["output"]["status"] == "confirmed"

    status = plugin.invoke_action({"action": "get_auth_status"})
    assert status["ok"] is True
    assert status["output"]["status"] == "authenticated"

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_payload["oauth"]["refresh_token"] == "refresh-token"
    assert state_payload["profile"]["sub"] == "penny-user-1"
    assert "pending_auth" not in state_payload


def test_penny_confirm_auth_accepts_manual_callback_runtime_context(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    state_file = tmp_path / "penny-state.json"

    class _FakeOidcClient:
        def __init__(self, **kwargs: object) -> None:
            self._kwargs = kwargs

        def resolve_endpoints(self) -> tuple[str, str]:
            return (
                "https://account.penny.de/realms/penny/protocol/openid-connect/auth",
                "https://account.penny.de/realms/penny/protocol/openid-connect/token",
            )

        def exchange_code(self, code: str, *, pending: object) -> object:
            del pending
            assert code == "manual-code"
            return module.OauthSession(
                access_token=_encode_jwt({"sub": "penny-user-2"}),
                refresh_token="refresh-token-2",
                expires_at=_future_expiry(),
            )

    monkeypatch.setattr(module, "PennyOidcClient", _FakeOidcClient)

    start_env = _runtime_env(tmp_path, connector_options={"state_file": str(state_file)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, start_env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", start_env["LIDLTOOL_CONFIG_DIR"])

    started = plugin.invoke_action({"action": "start_auth"})
    request = parse_auth_browser_start_request(started["output"]["metadata"])
    assert request is not None

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    callback_url = (
        "https://www.penny.de/app/login?code=manual-code&state="
        + state_payload["pending_auth"]["state"]
    )
    manual_result = AuthBrowserResult(
        flow_id=state_payload["pending_auth"]["flow_id"],
        session_id="manual-session",
        mode="local_display",
        start_url=request.plan.start_url,
        final_url=callback_url,
        callback_url=callback_url,
        started_at="2026-04-27T10:00:00+00:00",
        completed_at="2026-04-27T10:01:00+00:00",
    )
    confirm_env = _runtime_env(
        tmp_path,
        connector_options={"state_file": str(state_file)},
        runtime_context=build_auth_browser_runtime_context(manual_result),
    )
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, confirm_env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", confirm_env["LIDLTOOL_CONFIG_DIR"])

    confirmed = plugin.invoke_action({"action": "confirm_auth"})

    assert confirmed["ok"] is True
    assert confirmed["output"]["status"] == "confirmed"
    assert confirmed["output"]["metadata"]["subject"] == "penny-user-2"


def test_penny_parses_ebon_pdf_text_into_receipt_shape() -> None:
    module = _load_plugin_module()
    parsed = module._parse_penny_ebon_pdf_text(
        SAMPLE_EBON_TEXT,
        fallback_timestamp="2026-04-25T18:09:25Z",
        merchant_label="PENNY",
    )
    assert parsed["purchasedAt"] == "2026-04-25T18:09:25Z"
    assert parsed["receiptNumber"] == "0355"
    assert parsed["store"]["id"] == "2687"
    assert parsed["store"]["address"]["street"] == "Hauptstraße 11"
    assert parsed["totals"]["gross"] == "11.02"
    assert parsed["totals"]["discount"] == "0.24"
    assert len(parsed["items"]) == 6
    assert parsed["items"][0]["name"] == "GL MILD&NUSSIG"
    assert parsed["items"][0]["discounts"][0]["amount"] == "0.12"
    assert parsed["payments"][0]["method"] == "mastercard"


def test_penny_live_discovery_and_fetch_use_ebon_api(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    state_file = tmp_path / "penny-state.json"
    record_ref = "receipt-1"

    class _FakeOidcClient:
        def __init__(self, **kwargs: object) -> None:
            self._kwargs = kwargs

        def refresh(self, oauth: object) -> object:
            del oauth
            return module.OauthSession(
                access_token=_encode_jwt(
                    {
                        "sub": "penny-user-1",
                        "iss": "https://account.penny.de/realms/penny",
                        "rewe_id": "rewe-customer-1",
                    }
                ),
                refresh_token="refresh-token-2",
                expires_at=_future_expiry(),
            )

    class _FakeEbonApiClient:
        def __init__(self, *, access_token: str, timeout_seconds: int = 30, api_base_url: str = "", user_agent: str | None = None) -> None:
            assert access_token
            self._api_base_url = api_base_url or module.DEFAULT_EBON_API_BASE_URL

        def list_ebons(self, rewe_id: str, *, page: int, page_size: int) -> dict[str, object]:
            assert rewe_id == "rewe-customer-1"
            assert page >= 1
            assert page_size >= 1
            return {
                "items": [
                    {
                        "id": record_ref,
                        "timestamp": "2026-04-25T18:09:25Z",
                        "totalPrice": 1102,
                        "cancelled": False,
                        "market": None,
                    }
                ],
                "pagination": {
                    "currentPage": 1,
                    "pageCount": 1,
                    "objectCount": 1,
                    "objectsPerPage": page_size,
                },
            }

        def fetch_pdf(self, rewe_id: str, fetched_record_ref: str) -> bytes:
            assert rewe_id == "rewe-customer-1"
            assert fetched_record_ref == record_ref
            return b"%PDF-1.7 fixture"

        def pdf_url(self, rewe_id: str, fetched_record_ref: str) -> str:
            return f"https://api.penny.de/api/tenants/penny/customers/{rewe_id}/ebons/{fetched_record_ref}/pdf"

    monkeypatch.setattr(module, "PennyOidcClient", _FakeOidcClient)
    monkeypatch.setattr(module, "PennyEbonApiClient", _FakeEbonApiClient)
    monkeypatch.setattr(module, "_extract_text_from_pdf_bytes", lambda payload: (SAMPLE_EBON_TEXT if payload else ""))

    state_file.write_text(
        json.dumps(
                {
                    "schema_version": module.STATE_SCHEMA_VERSION,
                    "oauth": {
                        "access_token": "",
                        "refresh_token": "refresh-token-1",
                    "expires_at": "2020-01-01T00:00:00+00:00",
                    "client_id": module.DEFAULT_CLIENT_ID,
                    "redirect_uri": module.DEFAULT_REDIRECT_URI,
                    "auth_endpoint": module.DEFAULT_AUTH_ENDPOINT,
                    "token_endpoint": module.DEFAULT_TOKEN_ENDPOINT,
                    "discovery_url": module.DEFAULT_DISCOVERY_URL,
                },
                "profile": {"sub": "penny-user-1"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    env = _runtime_env(tmp_path, connector_options={"state_file": str(state_file)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", env["LIDLTOOL_CONFIG_DIR"])

    discover = plugin.invoke_action({"action": "discover_records"})
    assert discover["ok"] is True
    assert discover["output"]["records"][0]["record_ref"] == record_ref
    assert discover["output"]["records"][0]["metadata"]["total_price_cents"] == 1102

    fetched = plugin.invoke_action({"action": "fetch_record", "input": {"record_ref": record_ref}})
    assert fetched["ok"] is True
    assert fetched["output"]["record"]["id"] == record_ref
    assert fetched["output"]["record"]["receiptNumber"] == "0355"
    assert fetched["output"]["record"]["totals"]["gross"] == "11.02"
    assert fetched["output"]["record"]["items"][0]["discounts"][0]["amount"] == "0.12"
    assert fetched["output"]["record"]["attachments"][0]["kind"] == "pdf"

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_payload["oauth"]["refresh_token"] == "refresh-token-2"


def test_penny_start_auth_falls_back_to_pkce_when_chrome_reuse_fails(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = module.PennyReceiptPlugin()
    state_file = tmp_path / "penny-state.json"

    class _FakeOidcClient:
        def __init__(self, **kwargs: object) -> None:
            self._kwargs = kwargs

        def resolve_endpoints(self) -> tuple[str, str]:
            return (module.DEFAULT_AUTH_ENDPOINT, module.DEFAULT_TOKEN_ENDPOINT)

    monkeypatch.setattr(module, "PennyOidcClient", _FakeOidcClient)
    monkeypatch.setattr(
        module,
        "_chrome_user_data_dir_for_options",
        lambda options: (_ for _ in ()).throw(module.PennyPluginError("chrome unavailable", code="auth_required")),
    )

    env = _runtime_env(tmp_path, connector_options={"state_file": str(state_file)})
    monkeypatch.setenv(PLUGIN_RUNTIME_CONTEXT_ENV, env[PLUGIN_RUNTIME_CONTEXT_ENV])
    monkeypatch.setenv("LIDLTOOL_CONFIG_DIR", env["LIDLTOOL_CONFIG_DIR"])

    started = plugin.invoke_action({"action": "start_auth"})
    assert started["ok"] is True
    assert started["output"]["status"] == "started"
    warnings = started["output"]["metadata"].get("warnings") or []
    assert any("chrome unavailable" in warning for warning in warnings)


def test_build_pack_script_emits_expected_receipt_pack_layout(tmp_path: Path) -> None:
    import zipfile

    sys.path.insert(0, str(PLUGIN_ROOT))
    import build_desktop_pack

    pack_path = build_desktop_pack.build_pack(tmp_path)
    assert pack_path.exists()

    with zipfile.ZipFile(pack_path) as archive:
        names = set(archive.namelist())

    assert "plugin-pack.json" in names
    assert "manifest.json" in names
    assert "integrity.json" in names
    assert "payload/plugin.py" in names
    assert "payload/fixtures/raw_records.json" in names
