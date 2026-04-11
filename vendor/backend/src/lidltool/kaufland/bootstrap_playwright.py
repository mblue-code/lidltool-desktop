from __future__ import annotations

import select
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from lidltool.kaufland.session import ensure_state_parent


def run_kaufland_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "www.kaufland.de",
) -> bool:
    ensure_state_parent(state_file)
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    login_url = f"https://{normalized_domain}/user/login"
    orders_url = f"https://{normalized_domain}/order-history"

    with sync_playwright() as playwright:
        from lidltool.connectors.auth.browser_runtime import launch_playwright_chromium

        browser = launch_playwright_chromium(playwright=playwright, headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")

        print("Browser open: sign in to Kaufland and complete MFA/CAPTCHA if shown.")
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
        looks_logged_in = "/login" not in current_url and "/signin" not in current_url
        if looks_logged_in:
            context.storage_state(path=str(state_file))
        context.close()
        browser.close()
        return looks_logged_in
