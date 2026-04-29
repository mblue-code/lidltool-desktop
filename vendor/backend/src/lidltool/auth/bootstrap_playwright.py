from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
import os
import secrets
import urllib.parse
from pathlib import Path

import httpx

_CLIENT_ID = "LidlPlusNativeClient"
_AUTH_ENDPOINT = "https://accounts.lidl.com/connect/authorize"
_TOKEN_ENDPOINT = "https://accounts.lidl.com/connect/token"
_REDIRECT_URI = "com.lidlplus.app://callback"
_SCOPES = "openid profile offline_access lpprofile lpapis"


@dataclass(frozen=True, slots=True)
class PreparedLidlBootstrap:
    auth_url: str
    verifier: str
    callback_url_prefixes: tuple[str, ...] = (_REDIRECT_URI,)


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_auth_url(
    code_challenge: str,
    country: str = "DE",
    language: str = "de",
    *,
    state: str | None = None,
) -> str:
    params = {
        "client_id": _CLIENT_ID,
        "response_type": "code",
        "scope": _SCOPES,
        "redirect_uri": _REDIRECT_URI,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "country_code": country.upper(),
        "ui_locales": f"{language.lower()}-{country.upper()}",
    }
    if state:
        params["state"] = state
    return f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _exchange_code(code: str, verifier: str) -> str:
    """Exchange PKCE authorization code for a refresh_token."""
    secret = base64.b64encode(f"{_CLIENT_ID}:secret".encode()).decode()
    base_params = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": _REDIRECT_URI,
        "code_verifier": verifier,
    }
    attempts = (
        ("basic_auth", base_params, True),
        ("basic_auth_with_client_id", {**base_params, "client_id": _CLIENT_ID}, True),
        ("body_client_id_only", {**base_params, "client_id": _CLIENT_ID}, False),
    )
    failures: list[str] = []
    for label, params, include_basic_auth in attempts:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if include_basic_auth:
            headers["Authorization"] = f"Basic {secret}"
        resp = httpx.post(
            _TOKEN_ENDPOINT,
            headers=headers,
            content=urllib.parse.urlencode(params).encode(),
            timeout=20,
        )
        if resp.is_success:
            payload = resp.json()
            rt = payload.get("refresh_token")
            if not rt:
                raise RuntimeError(f"No refresh_token in token response: {list(payload.keys())}")
            return str(rt)
        snippet = " ".join(resp.text.strip().split())
        failures.append(f"{label}: HTTP {resp.status_code} {snippet[:240]}")
        if resp.status_code not in {400, 401, 403}:
            resp.raise_for_status()
    raise RuntimeError("Token exchange failed. " + " | ".join(failures))


def _extract_code_from_url(url: str) -> str | None:
    if not url.startswith(_REDIRECT_URI):
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    codes = qs.get("code", [])
    return codes[0] if codes else None


def prepare_lidl_manual_bootstrap(
    country: str = "DE",
    language: str = "de",
) -> PreparedLidlBootstrap:
    verifier, challenge = _pkce_pair()
    return PreparedLidlBootstrap(
        auth_url=_build_auth_url(
            challenge,
            country=country,
            language=language,
        ),
        verifier=verifier,
    )


def exchange_lidl_callback_url(callback_url: str, verifier: str) -> str:
    code = _extract_code_from_url(callback_url)
    if not code:
        raise RuntimeError("authorization code missing from Lidl callback URL")
    return _exchange_code(code, verifier)


def _run_browser_auth(auth_url: str, expected_state: str | None) -> object:
    from lidltool.connectors.auth.browser_runtime import AuthBrowserRuntimeService
    from lidltool.connectors.sdk.runtime import AuthBrowserPlan, AuthBrowserStartRequest

    return AuthBrowserRuntimeService().run(
        AuthBrowserStartRequest(
            flow_id=secrets.token_hex(12),
            plan=AuthBrowserPlan(
                start_url=auth_url,
                callback_url_prefixes=(_REDIRECT_URI,),
                expected_callback_state=expected_state,
                timeout_seconds=900,
                wait_until="domcontentloaded",
                interactive=True,
                capture_storage_state=False,
            ),
        ),
        environment={
            **os.environ,
            # Lidl emits the authorization code in an intermediate custom-scheme
            # redirect header after MFA. Chrome history/tab polling misses that
            # hop, so use the real Chrome CDP handoff and capture the Location
            # header before Chrome lands on Lidl's generic error page.
            "LIDLTOOL_AUTH_BROWSER_PREFER_SYSTEM_PROFILE": "false",
            "LIDLTOOL_AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM": "true",
        },
    )


def run_headful_bootstrap(
    har_output: Path, country: str = "DE", language: str = "de"
) -> str | None:
    """
    Open a browser at the Lidl Plus OAuth endpoint, capture the PKCE callback,
    exchange the authorization code for a refresh_token, and return it.

    On desktop hosts this uses the shared auth-browser runtime with the real
    installed Chromium executable and CDP capture. That avoids Playwright's
    bundled Chrome-for-Testing risk signal while still seeing the intermediate
    custom-scheme redirect header that contains the authorization code.
    """
    har_output.parent.mkdir(parents=True, exist_ok=True)
    prepared = prepare_lidl_manual_bootstrap(
        country=country,
        language=language,
    )

    try:
        browser_result = _run_browser_auth(prepared.auth_url, None)
    except Exception as exc:
        print(f"Lidl browser auth failed: {exc}")
        return None

    code = _extract_code_from_url(str(getattr(browser_result, "callback_url", "")))
    if not code:
        return None

    try:
        refresh_token = _exchange_code(code, prepared.verifier)
        print("Refresh token captured and exchanged automatically.")
        return refresh_token
    except Exception as exc:
        print(f"Token exchange failed: {exc}")
        return None
