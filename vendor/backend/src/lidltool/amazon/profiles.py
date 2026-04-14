from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from lidltool.amazon.selectors import AmazonSelectorBundle, DEFAULT_AMAZON_SELECTOR_BUNDLE


def _normalize_domain(domain: str) -> str:
    return domain.removeprefix("https://").removeprefix("http://").strip("/")


def _parse_euro_amount(text: str) -> float:
    return _parse_decimal_amount(
        text,
        currency_markers=("EUR", "€"),
        decimal_comma=True,
    )


def _parse_pound_amount(text: str) -> float:
    return _parse_decimal_amount(
        text,
        currency_markers=("GBP", "£"),
        decimal_comma=False,
    )


def _parse_decimal_amount(
    text: str,
    *,
    currency_markers: tuple[str, ...],
    decimal_comma: bool,
) -> float:
    normalized = (
        text.replace("\xa0", " ")
        .replace(" ", "")
        .replace("'", "")
    )
    for marker in currency_markers:
        normalized = normalized.replace(marker, " ")
    if decimal_comma:
        normalized = re.sub(r"(\d)[.\s](\d{3})(?=[,.\s]|$)", r"\1\2", normalized)
        normalized = normalized.replace(",", ".")
    else:
        normalized = re.sub(r"(\d)[,\s](\d{3})(?=[.\s]|$)", r"\1\2", normalized)
    match = re.search(r"(-?\d+(?:\.\d+)?)", normalized)
    if not match:
        return 0.0
    try:
        return float(match.group(1))
    except ValueError:
        return 0.0


def _parse_month_name_date(
    text: str,
    *,
    month_map: dict[str, int],
    day_month_year_patterns: tuple[re.Pattern[str], ...],
    english_month_year_pattern: re.Pattern[str],
) -> datetime | None:
    numeric_match = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
    if numeric_match:
        try:
            return datetime(
                int(numeric_match.group(3)),
                int(numeric_match.group(2)),
                int(numeric_match.group(1)),
                tzinfo=UTC,
            )
        except ValueError:
            pass

    for pattern in day_month_year_patterns:
        month_match = pattern.search(text)
        if not month_match:
            continue
        month = month_map.get(month_match.group(2).lower().rstrip("."))
        if month is None:
            continue
        try:
            return datetime(
                int(month_match.group(3)),
                month,
                int(month_match.group(1)),
                tzinfo=UTC,
            )
        except ValueError:
            return None

    english_match = english_month_year_pattern.search(text)
    if not english_match:
        return None
    month = month_map.get(english_match.group(1).lower().rstrip("."))
    if month is None:
        return None
    try:
        return datetime(
            int(english_match.group(3)),
            month,
            int(english_match.group(2)),
            tzinfo=UTC,
        )
    except ValueError:
        return None


_DE_MONTH_MAP: dict[str, int] = {
    "januar": 1,
    "jan": 1,
    "january": 1,
    "februar": 2,
    "feb": 2,
    "february": 2,
    "märz": 3,
    "mär": 3,
    "maerz": 3,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "may": 5,
    "juni": 6,
    "jun": 6,
    "june": 6,
    "juli": 7,
    "jul": 7,
    "july": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
    "december": 12,
    "dec": 12,
}

_FR_MONTH_MAP: dict[str, int] = {
    "janvier": 1,
    "janv": 1,
    "jan": 1,
    "january": 1,
    "fevrier": 2,
    "février": 2,
    "fevr": 2,
    "févr": 2,
    "february": 2,
    "feb": 2,
    "mars": 3,
    "march": 3,
    "mar": 3,
    "avril": 4,
    "avr": 4,
    "april": 4,
    "mai": 5,
    "may": 5,
    "juin": 6,
    "jun": 6,
    "june": 6,
    "juillet": 7,
    "juil": 7,
    "jul": 7,
    "july": 7,
    "aout": 8,
    "août": 8,
    "august": 8,
    "aug": 8,
    "septembre": 9,
    "sept": 9,
    "sep": 9,
    "octobre": 10,
    "oct": 10,
    "october": 10,
    "novembre": 11,
    "nov": 11,
    "decembre": 12,
    "décembre": 12,
    "dec": 12,
    "december": 12,
}

_EN_MONTH_MAP: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _parse_german_date(text: str) -> datetime | None:
    return _parse_month_name_date(
        text,
        month_map=_DE_MONTH_MAP,
        day_month_year_patterns=(
            re.compile(r"(\d{1,2})\.\s*([A-Za-zäöüÄÖÜß]+\.?)\s+(\d{4})"),
            re.compile(r"(\d{1,2})\s+([A-Za-zäöüÄÖÜß]+\.?)\s+(\d{4})"),
        ),
        english_month_year_pattern=re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"),
    )


def _parse_french_date(text: str) -> datetime | None:
    return _parse_month_name_date(
        text,
        month_map=_FR_MONTH_MAP,
        day_month_year_patterns=(
            re.compile(r"(\d{1,2})\s+([A-Za-zéèêëàâîïôöùûüç]+\.?)\s+(\d{4})", re.IGNORECASE),
            re.compile(r"(\d{1,2})\.\s*([A-Za-zéèêëàâîïôöùûüç]+\.?)\s+(\d{4})", re.IGNORECASE),
        ),
        english_month_year_pattern=re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"),
    )


def _parse_english_date(text: str) -> datetime | None:
    return _parse_month_name_date(
        text,
        month_map=_EN_MONTH_MAP,
        day_month_year_patterns=(
            re.compile(r"(\d{1,2})\s+([A-Za-z]+\.?)\s+(\d{4})"),
            re.compile(r"(\d{1,2})[./](\d{1,2})[./](\d{4})"),
        ),
        english_month_year_pattern=re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"),
    )


@dataclass(frozen=True, slots=True)
class AmazonUnsupportedOrderRule:
    reason: str
    markers: tuple[str, ...]


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
    selector_bundle: AmazonSelectorBundle
    date_parser: Callable[[str], datetime | None]
    amount_parser: Callable[[str], float]
    list_date_patterns: tuple[re.Pattern[str], ...]
    list_status_patterns: tuple[re.Pattern[str], ...]
    order_total_label_patterns: tuple[re.Pattern[str], ...]
    subtotal_label_map: tuple[tuple[str, str], ...]
    promotion_keywords: tuple[str, ...]
    shipping_line_name: str
    gift_wrap_line_name: str
    auth_rules: AmazonAuthRuleSet
    unsupported_order_rules: tuple[AmazonUnsupportedOrderRule, ...]
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
        if not asin:
            return ""
        return f"https://www.{self.normalized_domain()}/dp/{asin}"


def _amazon_auth_rules(*, sign_in_text: tuple[str, ...], mfa_text: tuple[str, ...], captcha_text: tuple[str, ...], claim_text: tuple[str, ...], intent_text: tuple[str, ...], bot_text: tuple[str, ...], authenticated_text: tuple[str, ...]) -> AmazonAuthRuleSet:
    return AmazonAuthRuleSet(
        sign_in_url_patterns=("/ap/signin", "authportal"),
        sign_in_html_markers=DEFAULT_AMAZON_SELECTOR_BUNDLE.auth.sign_in_markers,
        sign_in_text_markers=sign_in_text,
        mfa_url_patterns=("/ap/cvf", "/ap/mfa"),
        mfa_text_markers=DEFAULT_AMAZON_SELECTOR_BUNDLE.auth.mfa_markers + mfa_text,
        captcha_url_patterns=("validatecaptcha", "/errors/validatecaptcha"),
        captcha_text_markers=DEFAULT_AMAZON_SELECTOR_BUNDLE.auth.captcha_markers + captcha_text,
        claim_url_patterns=("/ap/claim", "/hz/claim"),
        claim_text_markers=claim_text,
        intent_url_patterns=("/ap/intent", "openid.return_to"),
        intent_text_markers=intent_text,
        bot_challenge_url_patterns=("robotcheck", "challenge"),
        bot_challenge_text_markers=DEFAULT_AMAZON_SELECTOR_BUNDLE.auth.bot_challenge_markers + bot_text,
        authenticated_text_markers=authenticated_text,
    )


GERMANY_PROFILE = AmazonCountryProfile(
    country_code="DE",
    source_id="amazon_de",
    domain="amazon.de",
    currency="EUR",
    languages=("de-DE", "en-GB"),
    selector_bundle=DEFAULT_AMAZON_SELECTOR_BUNDLE,
    date_parser=_parse_german_date,
    amount_parser=_parse_euro_amount,
    list_date_patterns=(
        re.compile(r"(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\s*[A-Za-zäöüÄÖÜß]+\.?\s+\d{4})", re.IGNORECASE),
        re.compile(r"(?:Bestellt am|Bestellung aufgegeben am)\s+(\d{1,2}\.\d{1,2}\.\d{4})", re.IGNORECASE),
        re.compile(r"(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE),
    ),
    list_status_patterns=(
        re.compile(r"(?:Zugestellt|Geliefert)\s*(?:am)?\s*[\d.\s\wäöüÄÖÜß-]*", re.IGNORECASE),
        re.compile(r"(?:Unterwegs|Versandt|Versendet)\s*[\w\s,\däöüÄÖÜß-]*", re.IGNORECASE),
        re.compile(r"(?:Delivered|Arriving|Shipped)\s*[\w\s,\d-]*", re.IGNORECASE),
        re.compile(r"(?:Storniert|Cancelled|Returned|Refunded)", re.IGNORECASE),
    ),
    order_total_label_patterns=(
        re.compile(r"(?:Bestellsumme|Gesamt(?:betrag|summe)?|Summe)\D{0,12}([€EUR0-9.,\s-]+)", re.IGNORECASE),
        re.compile(r"(?:Order total|Total)\D{0,12}([€EUR0-9.,\s-]+)", re.IGNORECASE),
    ),
    subtotal_label_map=(
        ("gratisversand", "free_shipping"),
        ("kostenloser versand", "free_shipping"),
        ("versand", "shipping"),
        ("lieferung", "shipping"),
        ("geschenkverpackung", "gift_wrap"),
        ("geschenkoption", "gift_wrap"),
        ("spar-abo", "subscribe_and_save"),
        ("subscribe", "subscribe_and_save"),
        ("coupon", "coupon"),
        ("gutschein", "coupon"),
        ("mehrfachkauf", "multibuy_discount"),
        ("amazon-rabatt", "amazon_discount"),
        ("amazon rabatt", "amazon_discount"),
        ("rabatt", "promotion"),
        ("nachlass", "promotion"),
        ("ersparnis", "promotion"),
        ("geschenkgutschein", "gift_card"),
        ("geschenkkarte", "gift_card"),
        ("punkte", "reward_points"),
    ),
    promotion_keywords=("rabatt", "nachlass", "ersparnis", "savings", "discount", "coupon", "gutschein"),
    shipping_line_name="Versandkosten",
    gift_wrap_line_name="Geschenkverpackung",
    auth_rules=_amazon_auth_rules(
        sign_in_text=("anmelden", "einloggen", "sign in", "passwort"),
        mfa_text=("bestätigungscode", "mfa", "zweistufige verifizierung", "one-time password"),
        captcha_text=("zeichen eingeben", "captcha", "bild angezeigten zeichen"),
        claim_text=("anspruch", "claim code", "geschenkgutschein anwenden"),
        intent_text=("weiter einkaufen", "fortfahren", "continue shopping"),
        bot_text=("automatisierte zugriffe", "robot check"),
        authenticated_text=("bestellungen", "order history", "ihre bestellungen"),
    ),
    unsupported_order_rules=(
        AmazonUnsupportedOrderRule("digital_order", ("prime video", "amazon music", "kindle", "digital order")),
        AmazonUnsupportedOrderRule("grocery_order", ("amazon fresh", "pantry", "lebensmittel", "lebensmittelbestellung")),
        AmazonUnsupportedOrderRule("store_purchase", ("im laden gekauft", "store purchase", "abholung im geschäft")),
        AmazonUnsupportedOrderRule("canceled_only", ("storniert", "annulliert")),
        AmazonUnsupportedOrderRule("return_heavy", ("rücksendung", "erstattet", "refund")),
    ),
)


FRANCE_PROFILE = AmazonCountryProfile(
    country_code="FR",
    source_id="amazon_fr",
    domain="amazon.fr",
    currency="EUR",
    languages=("fr-FR", "en-GB"),
    selector_bundle=DEFAULT_AMAZON_SELECTOR_BUNDLE,
    date_parser=_parse_french_date,
    amount_parser=_parse_euro_amount,
    list_date_patterns=(
        re.compile(r"(?:Commandé le|Commande effectuée le)\s+(\d{1,2}\s+[A-Za-zéèêëàâîïôöùûüç]+\.?\s+\d{4})", re.IGNORECASE),
        re.compile(r"(?:Commandé le|Commande effectuée le)\s+(\d{1,2}[./]\d{1,2}[./]\d{4})", re.IGNORECASE),
        re.compile(r"(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE),
    ),
    list_status_patterns=(
        re.compile(r"(?:Livré|Livrée)\s*(?:le)?\s*[\d.\s\wéèêëàâîïôöùûüç-]*", re.IGNORECASE),
        re.compile(r"(?:En cours de livraison|Expédié|Expédiée)\s*[\w\s,\déèêëàâîïôöùûüç-]*", re.IGNORECASE),
        re.compile(r"(?:Delivered|Arriving|Shipped)\s*[\w\s,\d-]*", re.IGNORECASE),
        re.compile(r"(?:Annulé|Annulée|Returned|Refunded|Remboursé)", re.IGNORECASE),
    ),
    order_total_label_patterns=(
        re.compile(r"(?:Total de la commande|Montant total|Total)\D{0,12}([€EUR0-9.,\s-]+)", re.IGNORECASE),
        re.compile(r"(?:Order total|Total)\D{0,12}([€EUR0-9.,\s-]+)", re.IGNORECASE),
    ),
    subtotal_label_map=(
        ("livraison gratuite", "free_shipping"),
        ("expédition gratuite", "free_shipping"),
        ("frais de livraison", "shipping"),
        ("livraison", "shipping"),
        ("emballage cadeau", "gift_wrap"),
        ("abonnez-vous", "subscribe_and_save"),
        ("coupon", "coupon"),
        ("bon de réduction", "coupon"),
        ("réduction amazon", "amazon_discount"),
        ("reduction amazon", "amazon_discount"),
        ("offre groupée", "multibuy_discount"),
        ("remise", "promotion"),
        ("réduction", "promotion"),
        ("reduction", "promotion"),
        ("économie", "promotion"),
        ("economie", "promotion"),
        ("carte cadeau", "gift_card"),
        ("points", "reward_points"),
    ),
    promotion_keywords=("réduction", "reduction", "remise", "coupon", "économie", "economie", "discount"),
    shipping_line_name="Frais de livraison",
    gift_wrap_line_name="Emballage cadeau",
    auth_rules=_amazon_auth_rules(
        sign_in_text=("s'identifier", "se connecter", "mot de passe", "sign in"),
        mfa_text=("code de vérification", "authentification", "mot de passe à usage unique"),
        captcha_text=("saisissez les caractères", "captcha", "robot"),
        claim_text=("carte cadeau", "code promotionnel", "utiliser un code"),
        intent_text=("continuer vos achats", "continuer", "continue shopping"),
        bot_text=("accès automatisé", "robot check"),
        authenticated_text=("vos commandes", "historique des commandes", "order history"),
    ),
    unsupported_order_rules=(
        AmazonUnsupportedOrderRule("digital_order", ("prime video", "amazon music", "kindle", "commande numérique")),
        AmazonUnsupportedOrderRule("grocery_order", ("amazon fresh", "épicerie", "epicerie", "pantry")),
        AmazonUnsupportedOrderRule("store_purchase", ("achat en magasin", "store purchase")),
        AmazonUnsupportedOrderRule("canceled_only", ("annulé", "annulee")),
        AmazonUnsupportedOrderRule("return_heavy", ("retour", "remboursé", "rembourse")),
    ),
)


UNITED_KINGDOM_PROFILE = AmazonCountryProfile(
    country_code="GB",
    source_id="amazon_gb",
    domain="amazon.co.uk",
    currency="GBP",
    languages=("en-GB",),
    selector_bundle=DEFAULT_AMAZON_SELECTOR_BUNDLE,
    date_parser=_parse_english_date,
    amount_parser=_parse_pound_amount,
    list_date_patterns=(
        re.compile(r"(?:Order placed|Ordered on)\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})", re.IGNORECASE),
        re.compile(r"(?:Order placed|Ordered on)\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})", re.IGNORECASE),
        re.compile(r"(?:Order placed|Ordered on)\s+(\d{1,2}[./]\d{1,2}[./]\d{4})", re.IGNORECASE),
    ),
    list_status_patterns=(
        re.compile(r"(?:Delivered|Arriving|Shipped)\s*[\w\s,\d-]*", re.IGNORECASE),
        re.compile(r"(?:Dispatched|On the way|Out for delivery)\s*[\w\s,\d-]*", re.IGNORECASE),
        re.compile(r"(?:Cancelled|Returned|Refunded)", re.IGNORECASE),
    ),
    order_total_label_patterns=(
        re.compile(r"(?:Order total|Total)\D{0,12}([£GBP0-9.,\s-]+)", re.IGNORECASE),
    ),
    subtotal_label_map=(
        ("free delivery", "free_shipping"),
        ("free shipping", "free_shipping"),
        ("delivery", "shipping"),
        ("shipping", "shipping"),
        ("gift wrap", "gift_wrap"),
        ("subscribe & save", "subscribe_and_save"),
        ("subscribe and save", "subscribe_and_save"),
        ("coupon", "coupon"),
        ("voucher", "coupon"),
        ("multibuy", "multibuy_discount"),
        ("amazon discount", "amazon_discount"),
        ("discount", "promotion"),
        ("savings", "promotion"),
        ("gift card", "gift_card"),
        ("reward points", "reward_points"),
        ("points", "reward_points"),
    ),
    promotion_keywords=("discount", "savings", "coupon", "voucher"),
    shipping_line_name="Delivery",
    gift_wrap_line_name="Gift wrap",
    auth_rules=_amazon_auth_rules(
        sign_in_text=("sign in", "password", "email or mobile phone number"),
        mfa_text=("enter verification code", "two-step verification", "one-time password"),
        captcha_text=("enter the characters", "captcha", "type the characters you see in this image"),
        claim_text=("gift card", "claim code", "apply a gift card"),
        intent_text=("continue shopping", "continue", "confirm your identity"),
        bot_text=("robot check", "automated access"),
        authenticated_text=("your orders", "order history"),
    ),
    unsupported_order_rules=(
        AmazonUnsupportedOrderRule("digital_order", ("prime video", "amazon music", "kindle", "digital order")),
        AmazonUnsupportedOrderRule("grocery_order", ("amazon fresh", "pantry", "grocery order")),
        AmazonUnsupportedOrderRule("store_purchase", ("store purchase", "collected in store")),
        AmazonUnsupportedOrderRule("canceled_only", ("cancelled", "canceled")),
        AmazonUnsupportedOrderRule("return_heavy", ("returned", "refunded", "refund")),
    ),
)


_PROFILES_BY_SOURCE_ID: dict[str, AmazonCountryProfile] = {
    GERMANY_PROFILE.source_id: GERMANY_PROFILE,
    FRANCE_PROFILE.source_id: FRANCE_PROFILE,
    UNITED_KINGDOM_PROFILE.source_id: UNITED_KINGDOM_PROFILE,
}
_PROFILES_BY_DOMAIN: dict[str, AmazonCountryProfile] = {
    GERMANY_PROFILE.normalized_domain(): GERMANY_PROFILE,
    FRANCE_PROFILE.normalized_domain(): FRANCE_PROFILE,
    UNITED_KINGDOM_PROFILE.normalized_domain(): UNITED_KINGDOM_PROFILE,
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
        normalized_domain = _normalize_domain(domain)
        profile = _PROFILES_BY_DOMAIN.get(normalized_domain)
        if profile is not None:
            return profile
    if source_id is not None:
        raise KeyError(f"unknown Amazon source id: {source_id}")
    if domain is not None:
        raise KeyError(f"unknown Amazon domain: {domain}")
    raise KeyError("expected source_id or domain")
