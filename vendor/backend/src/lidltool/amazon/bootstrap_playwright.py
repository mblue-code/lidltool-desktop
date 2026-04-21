from __future__ import annotations

import select
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from lidltool.amazon.auth_state import classify_amazon_auth_state, describe_auth_failure
from lidltool.amazon.client_playwright import AmazonClientError
from lidltool.amazon.profiles import (
    default_amazon_profile_dir_name,
    AmazonCountryProfile,
    get_country_profile,
)
from lidltool.amazon.session import ensure_state_parent
from lidltool.connectors.auth.browser_runtime import (
    launch_playwright_chromium,
    launch_playwright_chromium_persistent_context,
)


def run_amazon_headful_bootstrap(
    state_file: Path,
    *,
    source_id: str = "amazon_de",
    domain: str | None = None,
    debug_html_dir: Path | None = None,
    profile_dir: Path | None = None,
) -> bool:
    """
    Open Amazon login in a headful browser and persist Playwright storage state.

    Returns True when login/session validation succeeds and state was saved.
    """
    ensure_state_parent(state_file)
    profile = get_country_profile(source_id=source_id, domain=domain)
    account_url = profile.order_history_url()
    browser_profile_dir = profile_dir or (
        state_file.parent / default_amazon_profile_dir_name(source_id=profile.source_id)
    )
    browser_profile_dir = browser_profile_dir.expanduser().resolve()
    browser_profile_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            try:
                context = launch_playwright_chromium_persistent_context(
                    playwright=playwright,
                    user_data_dir=browser_profile_dir,
                    headless=False,
                )
            except Exception:
                browser = launch_playwright_chromium(playwright=playwright, headless=False)
                context = browser.new_context()

            page = context.new_page()
            page.goto(account_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            if _save_if_authenticated(
                context=context,
                page_url=page.url,
                page_html=page.content(),
                state_file=state_file,
                profile=profile,
            ):
                return True

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
            if _save_if_authenticated(
                context=context,
                page_url=page.url,
                page_html=page.content(),
                state_file=state_file,
                profile=profile,
            ):
                return True

            if debug_html_dir is not None:
                _write_debug_html(
                    debug_html_dir=debug_html_dir,
                    filename="amazon_bootstrap_failed.html",
                    html=page.content(),
                )
            return False
        finally:
            if context is not None:
                context.close()
            if browser is not None:
                browser.close()


def _save_if_authenticated(
    *,
    context: object,
    page_url: str,
    page_html: str,
    state_file: Path,
    profile: AmazonCountryProfile,
) -> bool:
    classification = classify_amazon_auth_state(
        url=page_url,
        html=page_html,
        profile=profile,
        expect_authenticated_session=False,
    )
    if not classification.authenticated:
        print(describe_auth_failure(source_id=profile.source_id, classification=classification))
        return False

    storage_state = getattr(context, "storage_state", None)
    if callable(storage_state):
        snapshot = storage_state()
        cookies = snapshot.get("cookies") if isinstance(snapshot, dict) else None
        origins = snapshot.get("origins") if isinstance(snapshot, dict) else None
        if not cookies and not origins:
            raise AmazonClientError("Amazon bootstrap storage-state capture was empty")
        storage_state(path=str(state_file))
    return True


def _write_debug_html(*, debug_html_dir: Path, filename: str, html: str) -> None:
    debug_html_dir.mkdir(parents=True, exist_ok=True)
    (debug_html_dir / filename).write_text(html, encoding="utf-8")
