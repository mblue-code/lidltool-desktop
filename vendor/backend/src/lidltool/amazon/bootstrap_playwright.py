from __future__ import annotations

import select
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from lidltool.amazon.session import ensure_state_parent


def run_amazon_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "amazon.de",
) -> bool:
    """
    Open Amazon login in a headful browser and persist Playwright storage state.

    Returns True when login/session validation succeeds and state was saved.
    """
    ensure_state_parent(state_file)
    login_url = f"https://www.{domain}/ap/signin"
    account_url = f"https://www.{domain}/gp/your-account/order-history"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url, wait_until="domcontentloaded")

        print("Browser open: sign in to Amazon and complete MFA/CAPTCHA if shown.")
        print("When done, press Enter in this terminal.")

        while True:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                sys.stdin.readline()
                break
            try:
                page.wait_for_timeout(500)
            except Exception:
                break

        page.goto(account_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        current_url = page.url
        looks_logged_in = "/ap/signin" not in current_url
        if looks_logged_in:
            context.storage_state(path=str(state_file))
        context.close()
        browser.close()
        return looks_logged_in
