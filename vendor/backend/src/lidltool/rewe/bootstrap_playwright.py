from __future__ import annotations

from pathlib import Path

from lidltool.connectors.auth.browser_session_bootstrap import (
    run_headful_browser_session_bootstrap,
)
from lidltool.rewe.session import ensure_state_parent


def run_rewe_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "shop.rewe.de",
) -> bool:
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    login_url = f"https://{normalized_domain}/auth/login"
    account_url = f"https://{normalized_domain}/account/orders"
    return run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=ensure_state_parent,
        login_url=login_url,
        validation_url=account_url,
        instructions="Browser open: sign in to REWE and complete MFA or CAPTCHA if shown.",
        blocked_url_patterns=("/auth/login", "/login"),
    )
