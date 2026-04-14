from __future__ import annotations

from pathlib import Path

from lidltool.connectors.auth.browser_session_bootstrap import (
    run_headful_browser_session_bootstrap,
)
from lidltool.kaufland.session import ensure_state_parent


def run_kaufland_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "www.kaufland.de",
) -> bool:
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    login_url = f"https://{normalized_domain}/user/login"
    orders_url = f"https://{normalized_domain}/order-history"
    return run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=ensure_state_parent,
        login_url=login_url,
        validation_url=orders_url,
        instructions="Browser open: sign in to Kaufland and complete MFA or CAPTCHA if shown.",
        blocked_url_patterns=("/login", "/signin"),
    )
