from __future__ import annotations

import select
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from lidltool.rossmann.session import ensure_state_parent


def run_rossmann_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "www.rossmann.de",
) -> bool:
    ensure_state_parent(state_file)
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    login_url = f"https://{normalized_domain}/de/account/login"
    orders_url = f"https://{normalized_domain}/de/account/orders"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")

        print("Browser open: sign in to Rossmann and complete MFA/CAPTCHA if shown.")
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

        page.goto(orders_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        current_url = page.url.lower()
        looks_logged_in = "/login" not in current_url and "/anmeldung" not in current_url
        if looks_logged_in:
            context.storage_state(path=str(state_file))
        context.close()
        browser.close()
        return looks_logged_in
