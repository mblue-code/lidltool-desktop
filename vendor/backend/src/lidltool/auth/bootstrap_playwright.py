from __future__ import annotations

import base64
import hashlib
import secrets
import select
import sys
import urllib.parse
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import sync_playwright

_CLIENT_ID = "LidlPlusNativeClient"
_AUTH_ENDPOINT = "https://accounts.lidl.com/connect/authorize"
_TOKEN_ENDPOINT = "https://accounts.lidl.com/connect/token"
_REDIRECT_URI = "com.lidlplus.app://callback"
_SCOPES = "openid profile offline_access lpprofile lpapis"


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) for PKCE S256."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_auth_url(code_challenge: str, country: str = "DE", language: str = "de") -> str:
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
    return f"{_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def _exchange_code(code: str, verifier: str) -> str:
    """Exchange PKCE authorization code for a refresh_token."""
    secret = base64.b64encode(f"{_CLIENT_ID}:secret".encode()).decode()
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _REDIRECT_URI,
            "code_verifier": verifier,
        }
    )
    resp = httpx.post(
        _TOKEN_ENDPOINT,
        headers={
            "Authorization": f"Basic {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        content=body.encode(),
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    rt = payload.get("refresh_token")
    if not rt:
        raise RuntimeError(f"No refresh_token in token response: {list(payload.keys())}")
    return str(rt)


def _extract_code_from_url(url: str) -> str | None:
    if not url.startswith(_REDIRECT_URI):
        return None
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    codes = qs.get("code", [])
    return codes[0] if codes else None


def run_headful_bootstrap(
    har_output: Path, country: str = "DE", language: str = "de"
) -> str | None:
    """
    Open a headful browser at the Lidl Plus OAuth endpoint.
    Intercepts the com.lidlplus.app://callback redirect automatically,
    exchanges the authorization code for a refresh_token, and returns it.
    Returns None if the code could not be captured (caller should prompt).
    """
    har_output.parent.mkdir(parents=True, exist_ok=True)
    verifier, challenge = _pkce_pair()
    auth_url = _build_auth_url(challenge, country=country, language=language)
    captured: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            record_har_path=str(har_output),
            record_har_mode="full",
        )
        page = context.new_page()

        # Strategy 1: intercept the 302 Location header on the OAuth callback response
        def on_response(response: Any) -> None:
            if captured:
                return
            try:
                location = response.headers.get("location", "")
                code = _extract_code_from_url(location)
                if code:
                    captured.append(code)
                    return
            except Exception:
                pass

        # Strategy 2: catch the custom-scheme navigation event
        def on_nav(frame: Any) -> None:
            if captured:
                return
            code = _extract_code_from_url(frame.url)
            if code:
                captured.append(code)

        # Strategy 3: catch it as a plain request event
        def on_request(request: Any) -> None:
            if captured:
                return
            code = _extract_code_from_url(request.url)
            if code:
                captured.append(code)

        page.on("response", on_response)
        page.on("framenavigated", on_nav)
        page.on("request", on_request)

        page.goto(auth_url, wait_until="domcontentloaded")
        print("Browser open: log in to Lidl Plus (complete CAPTCHA / MFA if shown).")
        print("The refresh token will be captured automatically after login.")

        has_tty = sys.stdin.isatty()
        if has_tty:
            print("Press Enter to stop waiting (you will be prompted to paste the token manually).")

        # Poll every 500 ms so Playwright can dispatch events; break on Enter or capture.
        # When there is no TTY (server-spawned process), skip the stdin check entirely so
        # DEVNULL / pipe stdin does not cause an immediate EOF break.
        max_wait_no_tty = 600  # 10 minutes
        elapsed_ticks = 0
        while not captured:
            if has_tty:
                rlist, _, _ = select.select([sys.stdin], [], [], 0)
                if rlist:
                    sys.stdin.readline()
                    break
            else:
                elapsed_ticks += 1
                if elapsed_ticks > max_wait_no_tty * 2:  # 500 ms ticks
                    print("Timed out waiting for login; aborting.")
                    break
            try:
                page.wait_for_timeout(500)
            except Exception:
                break

        context.close()
        browser.close()

    # Strategy 4: HAR fallback – scan redirect URLs recorded in the HAR
    if not captured:
        try:
            import json

            data = json.load(open(str(har_output), encoding="utf-8"))
            for entry in data.get("log", {}).get("entries", []):
                candidates = [
                    entry.get("response", {}).get("redirectURL", ""),
                    *(
                        h.get("value", "")
                        for h in entry.get("response", {}).get("headers", [])
                        if h.get("name", "").lower() == "location"
                    ),
                ]
                for val in candidates:
                    code = _extract_code_from_url(val)
                    if code:
                        captured.append(code)
                        break
                if captured:
                    break
        except Exception:
            pass

    if not captured:
        return None

    try:
        refresh_token = _exchange_code(captured[0], verifier)
        print("Refresh token captured and exchanged automatically.")
        return refresh_token
    except Exception as exc:
        print(f"Token exchange failed: {exc}")
        return None
