from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lidltool.amazon.profiles import AmazonCountryProfile


class AmazonAuthState(StrEnum):
    AUTHENTICATED = "authenticated"
    LOGIN_REQUIRED = "login_required"
    MFA_REQUIRED = "mfa_required"
    CAPTCHA_REQUIRED = "captcha_required"
    CLAIM_REQUIRED = "claim_required"
    INTENT_REQUIRED = "intent_required"
    BOT_CHALLENGE = "bot_challenge"
    EXPIRED_SESSION = "expired_session"
    UNKNOWN_AUTH_BLOCK = "unknown_auth_block"


@dataclass(frozen=True, slots=True)
class AmazonAuthClassification:
    state: AmazonAuthState
    matched_on: str | None = None
    detail: str | None = None

    @property
    def authenticated(self) -> bool:
        return self.state == AmazonAuthState.AUTHENTICATED


def classify_amazon_auth_state(
    *,
    url: str,
    html: str,
    profile: AmazonCountryProfile,
    expect_authenticated_session: bool = False,
) -> AmazonAuthClassification:
    normalized_url = url.strip().lower()
    normalized_html = html.lower()
    text = _html_to_text(html)
    rules = profile.auth_rules

    if _matches_any(normalized_url, rules.bot_challenge_url_patterns) or _matches_any(
        normalized_html,
        rules.bot_challenge_text_markers,
    ):
        return AmazonAuthClassification(
            state=AmazonAuthState.BOT_CHALLENGE,
            matched_on="bot_challenge",
            detail="Amazon blocked the session with a bot or JavaScript challenge.",
        )

    if _matches_any(normalized_url, rules.captcha_url_patterns) or _matches_any(
        normalized_html,
        rules.captcha_text_markers,
    ):
        return AmazonAuthClassification(
            state=AmazonAuthState.CAPTCHA_REQUIRED,
            matched_on="captcha",
            detail="Amazon is requesting a CAPTCHA before the session can continue.",
        )

    if _matches_any(normalized_url, rules.mfa_url_patterns) or _matches_any(
        normalized_html,
        rules.mfa_text_markers,
    ):
        return AmazonAuthClassification(
            state=AmazonAuthState.MFA_REQUIRED,
            matched_on="mfa",
            detail="Amazon is requesting MFA or an extra verification code.",
        )

    if _matches_any(normalized_url, rules.claim_url_patterns) or _matches_any(
        normalized_html,
        rules.claim_text_markers,
    ):
        return AmazonAuthClassification(
            state=AmazonAuthState.CLAIM_REQUIRED,
            matched_on="claim",
            detail="Amazon is blocking progress behind a claim or code confirmation step.",
        )

    if _matches_any(normalized_url, rules.intent_url_patterns) or _matches_any(
        normalized_html,
        rules.intent_text_markers,
    ):
        return AmazonAuthClassification(
            state=AmazonAuthState.INTENT_REQUIRED,
            matched_on="intent",
            detail="Amazon is waiting for an account-intent confirmation before showing orders.",
        )

    if (
        _matches_any(normalized_url, rules.sign_in_url_patterns)
        or _matches_any(normalized_html, rules.sign_in_html_markers)
        or _matches_any(text, rules.sign_in_text_markers)
    ):
        return AmazonAuthClassification(
            state=(
                AmazonAuthState.EXPIRED_SESSION
                if expect_authenticated_session
                else AmazonAuthState.LOGIN_REQUIRED
            ),
            matched_on="sign_in",
            detail=(
                "Amazon redirected the saved browser session back to sign-in."
                if expect_authenticated_session
                else "Amazon still requires sign-in before orders are accessible."
            ),
        )

    if any(marker in text for marker in rules.authenticated_text_markers):
        return AmazonAuthClassification(
            state=AmazonAuthState.AUTHENTICATED,
            matched_on="authenticated_marker",
            detail=None,
        )

    if "ap/" in normalized_url or "auth" in normalized_url:
        return AmazonAuthClassification(
            state=AmazonAuthState.UNKNOWN_AUTH_BLOCK,
            matched_on="auth_url",
            detail="Amazon is showing an unrecognized authentication or account-gating page.",
        )

    return AmazonAuthClassification(
        state=AmazonAuthState.AUTHENTICATED,
        matched_on="no_auth_markers",
        detail=None,
    )


def describe_auth_failure(
    *,
    source_id: str,
    classification: AmazonAuthClassification,
) -> str:
    source_hint = f"Run 'lidltool connectors auth bootstrap --source-id {source_id}' again."
    prefix = "Amazon session check failed."
    if classification.state == AmazonAuthState.CAPTCHA_REQUIRED:
        return f"{prefix} CAPTCHA is required. {source_hint}"
    if classification.state == AmazonAuthState.MFA_REQUIRED:
        return f"{prefix} MFA verification is required. {source_hint}"
    if classification.state == AmazonAuthState.CLAIM_REQUIRED:
        return f"{prefix} claim or code confirmation is required. {source_hint}"
    if classification.state == AmazonAuthState.INTENT_REQUIRED:
        return f"{prefix} account intent confirmation is required. {source_hint}"
    if classification.state == AmazonAuthState.BOT_CHALLENGE:
        return f"{prefix} Amazon presented a bot or JavaScript challenge. {source_hint}"
    if classification.state == AmazonAuthState.EXPIRED_SESSION:
        return f"{prefix} saved browser session expired or is no longer valid. {source_hint}"
    if classification.state == AmazonAuthState.LOGIN_REQUIRED:
        return f"{prefix} sign-in is still required. {source_hint}"
    if classification.state == AmazonAuthState.UNKNOWN_AUTH_BLOCK:
        return f"{prefix} Amazon presented an unknown auth block. {source_hint}"
    return f"{prefix} authentication status is unknown. {source_hint}"


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern.strip().lower() in value for pattern in patterns if pattern.strip())


def _html_to_text(html: str) -> str:
    text = html.lower()
    for marker in ("<", ">", "\n", "\r", "\t"):
        text = text.replace(marker, " ")
    return " ".join(text.split())
