from __future__ import annotations

from pathlib import Path

import pytest

from lidltool.amazon.auth_state import AmazonAuthState, classify_amazon_auth_state
from lidltool.amazon.profiles import get_country_profile


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "amazon" / "auth"


@pytest.mark.parametrize(
    ("fixture_name", "url", "source_id", "expect_authenticated_session", "expected_state"),
    [
        ("authenticated_de.html", "https://www.amazon.de/gp/your-account/order-history", "amazon_de", True, AmazonAuthState.AUTHENTICATED),
        ("login_de.html", "https://www.amazon.de/ap/signin", "amazon_de", False, AmazonAuthState.LOGIN_REQUIRED),
        ("login_de.html", "https://www.amazon.de/ap/signin", "amazon_de", True, AmazonAuthState.EXPIRED_SESSION),
        ("mfa_de.html", "https://www.amazon.de/ap/cvf/verify", "amazon_de", True, AmazonAuthState.MFA_REQUIRED),
        ("captcha_de.html", "https://www.amazon.de/errors/validateCaptcha", "amazon_de", True, AmazonAuthState.CAPTCHA_REQUIRED),
        ("claim_de.html", "https://www.amazon.de/ap/claimfixup", "amazon_de", True, AmazonAuthState.CLAIM_REQUIRED),
        ("intent_de.html", "https://www.amazon.de/ap/intent", "amazon_de", True, AmazonAuthState.INTENT_REQUIRED),
        ("bot_de.html", "https://www.amazon.de/errors/validateCaptcha", "amazon_de", True, AmazonAuthState.BOT_CHALLENGE),
        ("authenticated_fr.html", "https://www.amazon.fr/gp/your-account/order-history", "amazon_fr", True, AmazonAuthState.AUTHENTICATED),
        ("authenticated_gb.html", "https://www.amazon.co.uk/gp/your-account/order-history", "amazon_gb", True, AmazonAuthState.AUTHENTICATED),
        ("login_gb.html", "https://www.amazon.co.uk/ap/signin", "amazon_gb", False, AmazonAuthState.LOGIN_REQUIRED),
        ("mfa_gb.html", "https://www.amazon.co.uk/ap/cvf/verify", "amazon_gb", True, AmazonAuthState.MFA_REQUIRED),
        ("captcha_gb.html", "https://www.amazon.co.uk/errors/validateCaptcha", "amazon_gb", True, AmazonAuthState.CAPTCHA_REQUIRED),
    ],
)
def test_classify_amazon_auth_state_from_fixtures(
    fixture_name: str,
    url: str,
    source_id: str,
    expect_authenticated_session: bool,
    expected_state: AmazonAuthState,
) -> None:
    html = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    classification = classify_amazon_auth_state(
        url=url,
        html=html,
        profile=get_country_profile(source_id=source_id),
        expect_authenticated_session=expect_authenticated_session,
    )
    assert classification.state == expected_state


def test_classify_amazon_auth_state_prefers_authenticated_orders_page_over_generic_auth_words() -> None:
    html = (FIXTURE_DIR / "authenticated_de.html").read_text(encoding="utf-8")
    noisy_html = html + " bestaetigungscode mfa weiter einkaufen anmelden "
    classification = classify_amazon_auth_state(
        url="https://www.amazon.de/gp/your-account/order-history",
        html=noisy_html,
        profile=get_country_profile(source_id="amazon_de"),
        expect_authenticated_session=True,
    )
    assert classification.state == AmazonAuthState.AUTHENTICATED


def test_classify_amazon_auth_state_does_not_trust_order_history_url_without_authenticated_content() -> None:
    classification = classify_amazon_auth_state(
        url="https://www.amazon.de/gp/your-account/order-history",
        html="<html><head><title>Amazon</title></head><body>Loading...</body></html>",
        profile=get_country_profile(source_id="amazon_de"),
        expect_authenticated_session=False,
    )
    assert classification.state == AmazonAuthState.UNKNOWN_AUTH_BLOCK


def test_classify_amazon_auth_state_does_not_default_blank_pages_to_authenticated() -> None:
    classification = classify_amazon_auth_state(
        url="https://www.amazon.de/gp/your-account/order-history",
        html="",
        profile=get_country_profile(source_id="amazon_de"),
        expect_authenticated_session=True,
    )
    assert classification.state == AmazonAuthState.UNKNOWN_AUTH_BLOCK
