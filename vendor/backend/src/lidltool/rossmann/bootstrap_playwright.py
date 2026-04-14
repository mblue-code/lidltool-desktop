from __future__ import annotations

from pathlib import Path

from lidltool.connectors.auth.browser_session_bootstrap import (
    run_headful_browser_session_bootstrap,
)
from lidltool.rossmann.session import ensure_state_parent


def run_rossmann_headful_bootstrap(
    state_file: Path,
    *,
    domain: str = "www.rossmann.de",
) -> bool:
    normalized_domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
    login_url = f"https://{normalized_domain}/de/account/login"
    orders_url = f"https://{normalized_domain}/de/account/orders"
    return run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=ensure_state_parent,
        login_url=login_url,
        validation_url=orders_url,
        instructions="Browser open: sign in to Rossmann and complete MFA or CAPTCHA if shown.",
        blocked_url_patterns=("/login", "/anmeldung"),
    )
