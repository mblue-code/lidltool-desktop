from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


def _normalize_domain(domain: str) -> str:
    return domain.removeprefix("https://").removeprefix("http://").strip("/")


@dataclass(frozen=True, slots=True)
class AmazonAuthRuleSet:
    sign_in_url_patterns: tuple[str, ...]
    sign_in_html_markers: tuple[str, ...]
    sign_in_text_markers: tuple[str, ...]
    mfa_url_patterns: tuple[str, ...]
    mfa_text_markers: tuple[str, ...]
    captcha_url_patterns: tuple[str, ...]
    captcha_text_markers: tuple[str, ...]
    claim_url_patterns: tuple[str, ...]
    claim_text_markers: tuple[str, ...]
    intent_url_patterns: tuple[str, ...]
    intent_text_markers: tuple[str, ...]
    bot_challenge_url_patterns: tuple[str, ...]
    bot_challenge_text_markers: tuple[str, ...]
    authenticated_text_markers: tuple[str, ...]

    def blocked_url_patterns(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                self.sign_in_url_patterns
                + self.mfa_url_patterns
                + self.captcha_url_patterns
                + self.claim_url_patterns
                + self.intent_url_patterns
                + self.bot_challenge_url_patterns
            )
        )

    def blocked_html_markers(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                self.sign_in_html_markers
                + self.mfa_text_markers
                + self.captcha_text_markers
                + self.claim_text_markers
                + self.intent_text_markers
                + self.bot_challenge_text_markers
            )
        )


@dataclass(frozen=True, slots=True)
class AmazonCountryProfile:
    country_code: str
    source_id: str
    domain: str
    currency: str
    languages: tuple[str, ...]
    auth_rules: AmazonAuthRuleSet
    default_order_history_path: str = "/gp/your-account/order-history"
    default_sign_in_path: str = "/ap/signin"

    def normalized_domain(self) -> str:
        return _normalize_domain(self.domain)

    def sign_in_url(self) -> str:
        return f"https://www.{self.normalized_domain()}{self.default_sign_in_path}"

    def order_history_url(self, *, year: int | None = None, start_index: int = 0) -> str:
        url = f"https://www.{self.normalized_domain()}{self.default_order_history_path}"
        query: list[str] = []
        if year is not None:
            query.append(f"timeFilter=year-{year}")
        if start_index > 0:
            query.append(f"startIndex={start_index}")
        if not query:
            return url
        return f"{url}?{'&'.join(query)}"

    def item_url(self, asin: str) -> str:
        asin = str(asin or "").strip().upper()
        if not asin:
            return ""
        return f"https://www.{self.normalized_domain()}/dp/{asin}"


def _amazon_auth_rules(
    *,
    sign_in_text: tuple[str, ...],
    mfa_text: tuple[str, ...],
    captcha_text: tuple[str, ...],
    claim_text: tuple[str, ...],
    intent_text: tuple[str, ...],
    bot_text: tuple[str, ...],
    authenticated_text: tuple[str, ...],
) -> AmazonAuthRuleSet:
    return AmazonAuthRuleSet(
        sign_in_url_patterns=("/ap/signin", "authportal"),
        sign_in_html_markers=(
            'id="auth-login-form"',
            'name="signIn"',
            'id="auth-email"',
            'id="ap_email"',
        ),
        sign_in_text_markers=sign_in_text,
        mfa_url_patterns=("/ap/cvf", "/ap/mfa"),
        mfa_text_markers=("verification code", "two-step verification") + mfa_text,
        captcha_url_patterns=("validatecaptcha", "/errors/validatecaptcha"),
        captcha_text_markers=("captcha", "enter the characters") + captcha_text,
        claim_url_patterns=("/ap/claim", "/hz/claim"),
        claim_text_markers=claim_text,
        intent_url_patterns=("/ap/intent", "openid.return_to"),
        intent_text_markers=intent_text,
        bot_challenge_url_patterns=("robotcheck", "challenge"),
        bot_challenge_text_markers=("robot check", "automated access") + bot_text,
        authenticated_text_markers=authenticated_text,
    )


GERMANY_PROFILE = AmazonCountryProfile(
    country_code="DE",
    source_id="amazon_de",
    domain="amazon.de",
    currency="EUR",
    languages=("de-DE", "en-GB"),
    auth_rules=_amazon_auth_rules(
        sign_in_text=("anmelden", "einloggen", "sign in", "passwort"),
        mfa_text=("bestätigungscode", "mfa", "zweistufige verifizierung", "one-time password"),
        captcha_text=("zeichen eingeben", "captcha", "bild angezeigten zeichen"),
        claim_text=("anspruch", "claim code", "geschenkgutschein anwenden"),
        intent_text=("weiter einkaufen", "fortfahren", "continue shopping"),
        bot_text=("automatisierte zugriffe", "robot check"),
        authenticated_text=("bestellungen", "order history", "ihre bestellungen"),
    ),
)

FRANCE_PROFILE = AmazonCountryProfile(
    country_code="FR",
    source_id="amazon_fr",
    domain="amazon.fr",
    currency="EUR",
    languages=("fr-FR", "en-GB"),
    auth_rules=_amazon_auth_rules(
        sign_in_text=("s'identifier", "se connecter", "mot de passe", "sign in"),
        mfa_text=("code de vérification", "authentification", "mot de passe à usage unique"),
        captcha_text=("saisissez les caractères", "captcha", "robot"),
        claim_text=("carte cadeau", "code promotionnel", "utiliser un code"),
        intent_text=("continuer vos achats", "continuer", "continue shopping"),
        bot_text=("accès automatisé", "robot check"),
        authenticated_text=("vos commandes", "historique des commandes", "order history"),
    ),
)

UNITED_KINGDOM_PROFILE = AmazonCountryProfile(
    country_code="GB",
    source_id="amazon_gb",
    domain="amazon.co.uk",
    currency="GBP",
    languages=("en-GB",),
    auth_rules=_amazon_auth_rules(
        sign_in_text=("sign in", "password", "email or mobile phone number"),
        mfa_text=("enter verification code", "two-step verification", "one-time password"),
        captcha_text=("enter the characters", "captcha", "type the characters you see in this image"),
        claim_text=("gift card", "claim code", "apply a gift card"),
        intent_text=("continue shopping", "continue", "confirm your identity"),
        bot_text=("robot check", "automated access"),
        authenticated_text=("your orders", "order history"),
    ),
)

_PROFILES_BY_SOURCE_ID: dict[str, AmazonCountryProfile] = {
    profile.source_id: profile
    for profile in (GERMANY_PROFILE, FRANCE_PROFILE, UNITED_KINGDOM_PROFILE)
}
_PROFILES_BY_DOMAIN: dict[str, AmazonCountryProfile] = {
    profile.normalized_domain(): profile
    for profile in (GERMANY_PROFILE, FRANCE_PROFILE, UNITED_KINGDOM_PROFILE)
}


def list_country_profiles() -> tuple[AmazonCountryProfile, ...]:
    return tuple(_PROFILES_BY_SOURCE_ID.values())


def is_amazon_source_id(source_id: str) -> bool:
    return source_id in _PROFILES_BY_SOURCE_ID


def get_country_profile(*, source_id: str | None = None, domain: str | None = None) -> AmazonCountryProfile:
    if source_id is not None:
        profile = _PROFILES_BY_SOURCE_ID.get(source_id)
        if profile is not None:
            return profile
    if domain is not None:
        profile = _PROFILES_BY_DOMAIN.get(_normalize_domain(domain))
        if profile is not None:
            return profile
    if source_id is not None:
        raise KeyError(f"unknown Amazon source id: {source_id}")
    if domain is not None:
        raise KeyError(f"unknown Amazon domain: {domain}")
    raise KeyError("expected source_id or domain")


def default_amazon_state_file_name(*, source_id: str = "amazon_de") -> str:
    return "amazon_storage_state.json" if source_id == "amazon_de" else f"{source_id}_storage_state.json"


def default_amazon_profile_dir_name(*, source_id: str = "amazon_de") -> str:
    return "amazon_browser_profile" if source_id == "amazon_de" else f"{source_id}_browser_profile"
