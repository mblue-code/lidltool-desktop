from __future__ import annotations

from pathlib import Path

from lidltool.amazon.auth_state import classify_amazon_auth_state
from lidltool.amazon.client_playwright import AmazonClientError, AmazonPlaywrightClient
from lidltool.amazon.profiles import get_country_profile
from lidltool.amazon.session import default_amazon_profile_dir, ensure_state_parent
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
    profile_dir: Path | None = None,
) -> bool:
    """
    Open Amazon login in a headful browser and persist Playwright storage state.

    Returns True when login/session validation succeeds and state was saved.
    """
    profile = get_country_profile(source_id=source_id, domain=domain)
    account_url = profile.order_history_url()
    browser_profile_dir = profile_dir or default_amazon_profile_dir(source_id=source_id)
    if browser_profile_dir.exists():
        try:
            AmazonPlaywrightClient(
                state_file=state_file,
                profile_dir=browser_profile_dir,
                source_id=source_id,
                domain=profile.domain,
                headless=True,
            ).validate_session()
        except AmazonClientError:
            pass
        else:
            return True
    return run_headful_browser_session_bootstrap(
        state_file,
        ensure_state_parent=ensure_state_parent,
        # Amazon's bare /ap/signin URL currently 404s on amazon.de. Opening the
        # authenticated order-history target lets Amazon redirect into the
        # current, market-specific sign-in flow instead.
        login_url=account_url,
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
        user_data_dir=browser_profile_dir,
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
