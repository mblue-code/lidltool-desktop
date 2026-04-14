from __future__ import annotations

from pathlib import Path

from lidltool.amazon.auth_state import classify_amazon_auth_state
from lidltool.amazon.profiles import get_country_profile
from lidltool.amazon.session import ensure_state_parent
from lidltool.connectors.auth.browser_session_bootstrap import (
    SessionValidationProbeResult,
    run_headful_browser_session_bootstrap,
)


def run_amazon_headful_bootstrap(
    state_file: Path,
    *,
    source_id: str = "amazon_de",
    domain: str | None = None,
    debug_html_dir: Path | None = None,
) -> bool:
    """
    Open Amazon login in a headful browser and persist Playwright storage state.

    Returns True when login/session validation succeeds and state was saved.
    """
    profile = get_country_profile(source_id=source_id, domain=domain)
    login_url = profile.sign_in_url()
    account_url = profile.order_history_url()
    return run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=ensure_state_parent,
        login_url=login_url,
        validation_url=account_url,
        instructions="Browser open: sign in to Amazon and complete MFA or CAPTCHA if shown.",
        blocked_url_patterns=profile.auth_rules.blocked_url_patterns(),
        blocked_html_markers=profile.auth_rules.blocked_html_markers(),
        probe_validator=lambda url, html: _amazon_bootstrap_probe_validator(
            url=url,
            html=html,
            source_id=source_id,
            domain=profile.domain,
        ),
        debug_html_dir=debug_html_dir,
    )


def _amazon_bootstrap_probe_validator(
    *,
    url: str,
    html: str,
    source_id: str,
    domain: str,
) -> SessionValidationProbeResult:
    profile = get_country_profile(source_id=source_id, domain=domain)
    classification = classify_amazon_auth_state(
        url=url,
        html=html,
        profile=profile,
        expect_authenticated_session=False,
    )
    detail = None if classification.authenticated else (classification.detail or "Amazon authentication is incomplete.")
    return SessionValidationProbeResult(
        authenticated=classification.authenticated,
        url=url,
        html=html,
        state=classification.state.value,
        detail=detail,
    )
