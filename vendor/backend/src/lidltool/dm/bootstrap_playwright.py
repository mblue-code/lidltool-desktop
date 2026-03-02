from __future__ import annotations

import select
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from lidltool.dm.session import ensure_state_parent


def run_dm_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "www.dm.de",
) -> bool:
    ensure_state_parent(state_file)
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    if normalized_domain.endswith("dm.de"):
        login_url = "https://www.dm.de/"
        account_url = "https://account.dm.de/purchases"
    else:
        login_url = f"https://{normalized_domain}/"
        account_url = "https://account.dm.de/purchases"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")

        print("Browser open: sign in to dm and complete MFA/CAPTCHA if shown.")
        print("If prompted, accept privacy/cookie notices before continuing.")
        print("Open 'Mein Konto' -> 'Meine Einkaeufe' once before pressing Enter.")
        print("When done, press Enter in this terminal.")

        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
            if ready:
                sys.stdin.readline()
                break
            try:
                page.wait_for_timeout(500)
            except Exception:  # noqa: BLE001
                break

        page.goto(account_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3500)
        current_url = page.url.lower()
        login_url_ok = all(
            marker not in current_url
            for marker in (
                "signin.dm.de",
                "/authentication/web-login",
                "/login",
                "/anmeldung",
                "/auth",
            )
        )
        auth_state = page.evaluate(
            """
            () => {
              const text = ((document.body && document.body.innerText) || "").toLowerCase();
              const hasPurchasesPath = /account\\.dm\\.de\\/purchases/.test(window.location.href || "");
              const links = Array.from(document.querySelectorAll("a[href]"));
              const hasPurchaseLinks = links.some((a) => /\\/ebons\\/[0-9a-fA-F-]{8,}/.test(String(a.getAttribute("href") || "")));
              const hasAccountLinks = links.some((a) => /(\\/purchases|\\/profile|\\/orders|\\/myaccount)/i.test(String(a.getAttribute("href") || "")));
              const interactive = Array.from(document.querySelectorAll("a,button"));
              const hasLogout = interactive.some((el) => {
                const blob = `${el.textContent || ""} ${el.getAttribute("aria-label") || ""}`.toLowerCase();
                return /(abmelden|logout|sign out)/i.test(blob);
              });
              const hasLoginIframe = Boolean(document.querySelector("iframe#___loginIframe___"));
              const hasError404Meta = Boolean(document.querySelector("meta[name='render:status_code'][content='404']"));
              const hasErrorText = /entschuldigung|seite existiert leider nicht/.test(text);
              return { hasPurchasesPath, hasPurchaseLinks, hasAccountLinks, hasLogout, hasLoginIframe, hasError404Meta, hasErrorText };
            }
            """
        )
        looks_authenticated = False
        if isinstance(auth_state, dict):
            has_positive_auth = (
                bool(auth_state.get("hasPurchasesPath"))
                or bool(auth_state.get("hasPurchaseLinks"))
                or bool(auth_state.get("hasAccountLinks"))
                or bool(auth_state.get("hasLogout"))
            )
            has_negative_auth = any(
                bool(auth_state.get(key))
                for key in ("hasLoginIframe", "hasError404Meta", "hasErrorText")
            )
            looks_authenticated = has_positive_auth and not has_negative_auth
        looks_logged_in = login_url_ok and looks_authenticated
        if looks_logged_in:
            context.storage_state(path=str(state_file))
        context.close()
        browser.close()
        return looks_logged_in
