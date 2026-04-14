from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from lidltool.db.models import MerchantAlias, NormalizationRule

_CATEGORY_ALIASES: dict[str, str] = {
    "groceries": "groceries",
    "grocery": "groceries",
    "food": "groceries",
    "lebensmittel": "groceries",
    "dairy": "groceries:dairy",
    "fresh_dairy": "groceries:dairy",
    "milchprodukte": "groceries:dairy",
    "molkerei": "groceries:dairy",
    "joghurt": "groceries:dairy",
    "jogurt": "groceries:dairy",
    "yogurt": "groceries:dairy",
    "yoghurt": "groceries:dairy",
    "baking": "groceries:baking",
    "backzutaten": "groceries:baking",
    "beverages": "groceries:beverages",
    "drinks": "groceries:beverages",
    "drink": "groceries:beverages",
    "getraenke": "groceries:beverages",
    "getränke": "groceries:beverages",
    "getraenk": "groceries:beverages",
    "getränk": "groceries:beverages",
    "produce": "groceries:produce",
    "fruit": "groceries:produce",
    "vegetables": "groceries:produce",
    "obst": "groceries:produce",
    "gemuese": "groceries:produce",
    "gemüse": "groceries:produce",
    "bakery": "groceries:bakery",
    "bread": "groceries:bakery",
    "backwaren": "groceries:bakery",
    "fish": "groceries:fish",
    "fisch": "groceries:fish",
    "seafood": "groceries:fish",
    "meeresfruechte": "groceries:fish",
    "meeresfrüchte": "groceries:fish",
    "meat": "groceries:meat",
    "fleisch": "groceries:meat",
    "frozen": "groceries:frozen",
    "tiefkuehl": "groceries:frozen",
    "tiefkühl": "groceries:frozen",
    "snacks": "groceries:snacks",
    "snack": "groceries:snacks",
    "suessigkeiten": "groceries:snacks",
    "süßigkeiten": "groceries:snacks",
    "pantry": "groceries:pantry",
    "trockenwaren": "groceries:pantry",
    "vorrat": "groceries:pantry",
    "dining": "dining",
    "dining:restaurant": "dining:restaurant",
    "restaurant": "dining:restaurant",
    "restaurants": "dining:restaurant",
    "gastronomy": "dining:restaurant",
    "gastronomie": "dining:restaurant",
    "essen gehen": "dining:restaurant",
    "dining:takeaway_delivery": "dining:takeaway_delivery",
    "takeaway_delivery": "dining:takeaway_delivery",
    "delivery and takeaway": "dining:takeaway_delivery",
    "lieferservice": "dining:takeaway_delivery",
    "take away": "dining:takeaway_delivery",
    "takeaway": "dining:takeaway_delivery",
    "dining:coffee_snacks": "dining:coffee_snacks",
    "coffee_snacks": "dining:coffee_snacks",
    "coffee and snacks": "dining:coffee_snacks",
    "kaffee und snacks": "dining:coffee_snacks",
    "household": "household",
    "haushalt": "household",
    "household:cleaning": "household:cleaning",
    "cleaning": "household:cleaning",
    "cleaning supplies": "household:cleaning",
    "reinigung": "household:cleaning",
    "putzmittel": "household:cleaning",
    "reiniger": "household:cleaning",
    "detergent": "household:cleaning",
    "waschmittel": "household:cleaning",
    "household:paper_goods": "household:paper_goods",
    "paper goods": "household:paper_goods",
    "paper_goods": "household:paper_goods",
    "papierwaren": "household:paper_goods",
    "toilettenpapier": "household:paper_goods",
    "kuechenrolle": "household:paper_goods",
    "küchenrolle": "household:paper_goods",
    "taschentuecher": "household:paper_goods",
    "taschentücher": "household:paper_goods",
    "household:home_misc": "household:home_misc",
    "home_misc": "household:home_misc",
    "home misc": "household:home_misc",
    "haushaltswaren": "household:home_misc",
    "personal care": "personal_care",
    "personal_care": "personal_care",
    "pflege": "personal_care",
    "drogerie": "personal_care",
    "personal_care:cosmetics": "personal_care:cosmetics",
    "cosmetics": "personal_care:cosmetics",
    "cosmetic": "personal_care:cosmetics",
    "beauty": "personal_care:cosmetics",
    "makeup": "personal_care:cosmetics",
    "make up": "personal_care:cosmetics",
    "kosmetik": "personal_care:cosmetics",
    "hautpflege": "personal_care:cosmetics",
    "skin care": "personal_care:cosmetics",
    "skincare": "personal_care:cosmetics",
    "personal_care:hygiene": "personal_care:hygiene",
    "hygiene": "personal_care:hygiene",
    "hygiene products": "personal_care:hygiene",
    "koerperpflege": "personal_care:hygiene",
    "körperpflege": "personal_care:hygiene",
    "toiletries": "personal_care:hygiene",
    "personal_care:baby": "personal_care:baby",
    "baby": "personal_care:baby",
    "baby care": "personal_care:baby",
    "babycare": "personal_care:baby",
    "babystuff": "personal_care:baby",
    "baby stuff": "personal_care:baby",
    "windeln": "personal_care:baby",
    "diapers": "personal_care:baby",
    "health": "health",
    "health:pharmacy": "health:pharmacy",
    "pharmacy": "health:pharmacy",
    "apotheke": "health:pharmacy",
    "apotheke drogerie": "health:pharmacy",
    "drugstore": "health:pharmacy",
    "health:medical": "health:medical",
    "medical": "health:medical",
    "arzt": "health:medical",
    "doctor": "health:medical",
    "medizin": "health:medical",
    "transport": "transport",
    "transport:fuel": "transport:fuel",
    "fuel": "transport:fuel",
    "gas": "transport:fuel",
    "gasoline": "transport:fuel",
    "petrol": "transport:fuel",
    "benzin": "transport:fuel",
    "diesel": "transport:fuel",
    "tanken": "transport:fuel",
    "transport:public_transit": "transport:public_transit",
    "public_transit": "transport:public_transit",
    "public transit": "transport:public_transit",
    "oepnv": "transport:public_transit",
    "öpnv": "transport:public_transit",
    "bahn": "transport:public_transit",
    "transport:taxi_rideshare": "transport:taxi_rideshare",
    "taxi_rideshare": "transport:taxi_rideshare",
    "taxi": "transport:taxi_rideshare",
    "rideshare": "transport:taxi_rideshare",
    "fahrdienst": "transport:taxi_rideshare",
    "transport:parking_tolls": "transport:parking_tolls",
    "parking_tolls": "transport:parking_tolls",
    "parking": "transport:parking_tolls",
    "parken": "transport:parking_tolls",
    "tolls": "transport:parking_tolls",
    "maut": "transport:parking_tolls",
    "shopping": "shopping",
    "shopping:clothing": "shopping:clothing",
    "clothing": "shopping:clothing",
    "fashion": "shopping:clothing",
    "kleidung": "shopping:clothing",
    "shopping:electronics": "shopping:electronics",
    "electronics": "shopping:electronics",
    "elektronik": "shopping:electronics",
    "shopping:general": "shopping:general",
    "general shopping": "shopping:general",
    "allgemeiner einkauf": "shopping:general",
    "shopping general": "shopping:general",
    "entertainment": "entertainment",
    "entertainment:streaming": "entertainment:streaming",
    "streaming": "entertainment:streaming",
    "entertainment:games_hobbies": "entertainment:games_hobbies",
    "games_hobbies": "entertainment:games_hobbies",
    "gaming": "entertainment:games_hobbies",
    "gaming_media": "entertainment:games_hobbies",
    "media": "entertainment:games_hobbies",
    "hobbies": "entertainment:games_hobbies",
    "entertainment:events_leisure": "entertainment:events_leisure",
    "events_leisure": "entertainment:events_leisure",
    "events": "entertainment:events_leisure",
    "leisure": "entertainment:events_leisure",
    "freizeit": "entertainment:events_leisure",
    "travel": "travel",
    "travel:transport": "travel:transport",
    "travel transport": "travel:transport",
    "reise transport": "travel:transport",
    "travel:lodging": "travel:lodging",
    "lodging": "travel:lodging",
    "unterkunft": "travel:lodging",
    "fees": "fees",
    "fees:shipping": "fees:shipping",
    "shipping": "fees:shipping",
    "shipping_fees": "fees:shipping",
    "delivery": "fees:shipping",
    "shipping fee": "fees:shipping",
    "shipping fees": "fees:shipping",
    "versand": "fees:shipping",
    "versandkosten": "fees:shipping",
    "fees:service": "fees:service",
    "service fee": "fees:service",
    "service fees": "fees:service",
    "service charge": "fees:service",
    "gebuehr": "fees:service",
    "gebühr": "fees:service",
    "fee": "fees:service",
    "deposit": "deposit",
    "pfand": "deposit",
    "other": "other",
}
_CATEGORY_PATTERN_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(pfand|deposit|leergut)\b", re.IGNORECASE), "deposit"),
    (re.compile(r"\b(shipping|delivery|versand|liefer|porto)\b", re.IGNORECASE), "fees:shipping"),
    (
        re.compile(
            r"\b(restaurant|pizzeria|pizza|burger|sushi|d[oö]ner|doener|imbiss|bistro|gastst[aä]tte|gasthaus)\b",
            re.IGNORECASE,
        ),
        "dining:restaurant",
    ),
    (
        re.compile(
            r"\b(lieferando|uber\s*eats|ubereats|doordash|wolt|takeaway|take\s*away|lieferservice)\b",
            re.IGNORECASE,
        ),
        "dining:takeaway_delivery",
    ),
    (
        re.compile(
            r"\b(caf[eé]|coffee\s*shop|kaffee|espresso|cappuccino|latte|croissant)\b",
            re.IGNORECASE,
        ),
        "dining:coffee_snacks",
    ),
    (
        re.compile(
            r"\b(baby|windel|windeln|diaper|diapers|feuchttuch|feuchttuecher|feuchttücher|wipes)\b",
            re.IGNORECASE,
        ),
        "personal_care:baby",
    ),
    (
        re.compile(
            r"\b(kosmetik|cosmetic|cosmetics|beauty|makeup|skin\s*care|skincare)\b",
            re.IGNORECASE,
        ),
        "personal_care:cosmetics",
    ),
    (
        re.compile(r"\b(shampoo|seife|zahnpasta|deo|duschgel|toiletries|hygiene)\b", re.IGNORECASE),
        "personal_care:hygiene",
    ),
    (
        re.compile(
            r"\b(reinigung|cleaning|detergent|detergents|putz|reiniger|waschmittel|spuel|spül)\b",
            re.IGNORECASE,
        ),
        "household:cleaning",
    ),
    (
        re.compile(
            r"\b(paper\s*goods|papierwaren|toilettenpapier|kuechenrolle|küchenrolle|taschentuecher|taschentücher|tissues?)\b",
            re.IGNORECASE,
        ),
        "household:paper_goods",
    ),
    (
        re.compile(
            r"\b(apotheke|pharmacy|ibuprofen|paracetamol|vitamin|supplement|nasenspray)\b",
            re.IGNORECASE,
        ),
        "health:pharmacy",
    ),
    (
        re.compile(
            r"\b(arzt|doctor|clinic|klinik|hospital|krankenhaus|physio|physiotherapie|medical)\b",
            re.IGNORECASE,
        ),
        "health:medical",
    ),
    (
        re.compile(
            r"\b(benzin|diesel|super\s*e10|fuel|tankstelle|gasoline|petrol)\b",
            re.IGNORECASE,
        ),
        "transport:fuel",
    ),
    (
        re.compile(
            r"\b(deutschlandticket|bahn|train|bus|tram|u-?bahn|s-?bahn|oepnv|öpnv|verkehrsbetriebe)\b",
            re.IGNORECASE,
        ),
        "transport:public_transit",
    ),
    (
        re.compile(r"\b(taxi|uber|bolt|rideshare|fahrdienst)\b", re.IGNORECASE),
        "transport:taxi_rideshare",
    ),
    (
        re.compile(r"\b(parking|parkhaus|parken|maut|toll)\b", re.IGNORECASE),
        "transport:parking_tolls",
    ),
    (
        re.compile(
            r"\b(kleidung|shirt|jeans|socken|jacke|jacket|hose|dress|schuh|schuhe|fashion)\b",
            re.IGNORECASE,
        ),
        "shopping:clothing",
    ),
    (
        re.compile(
            r"\b(elektronik|electronics|charger|kabel|cable|headphones|kopfh[oö]rer|usb)\b",
            re.IGNORECASE,
        ),
        "shopping:electronics",
    ),
    (
        re.compile(
            r"\b(netflix|spotify|disney|prime\s*video|youtube\s*premium|streaming)\b",
            re.IGNORECASE,
        ),
        "entertainment:streaming",
    ),
    (
        re.compile(
            r"\b(steam|nintendo|playstation|xbox|book|buch|lego|hobby|game|gaming)\b",
            re.IGNORECASE,
        ),
        "entertainment:games_hobbies",
    ),
    (
        re.compile(
            r"\b(cinema|kino|concert|konzert|museum|theater|event|festival|freizeitpark)\b",
            re.IGNORECASE,
        ),
        "entertainment:events_leisure",
    ),
    (
        re.compile(r"\b(flight|airline|flug|boarding|rail\s*pass|fernverkehr)\b", re.IGNORECASE),
        "travel:transport",
    ),
    (
        re.compile(r"\b(hotel|hostel|airbnb|booking\.com|unterkunft|lodging)\b", re.IGNORECASE),
        "travel:lodging",
    ),
    (re.compile(r"\b(service fee|service charge|gebuhr|gebühr|fee|fees)\b", re.IGNORECASE), "fees:service"),
]


@dataclass(slots=True)
class CompiledNormalizationRule:
    rule_type: str
    pattern: re.Pattern[str]
    replacement: str | None
    priority: int


@dataclass(slots=True)
class NormalizationBundle:
    source: str
    merchant_aliases: dict[str, str]
    rules: list[CompiledNormalizationRule]


@dataclass(slots=True)
class CategoryNormalizationMatch:
    rule_type: str
    replacement: str
    priority: int


def canonicalize_category_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().replace("-", "_").split())
    if not normalized:
        return None
    if normalized in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[normalized]
    direct = normalized.replace(" ", "_")
    if direct in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[direct]
    direct = direct.replace("__", "_")
    if direct in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[direct]
    if normalized.startswith("groceries:"):
        return normalized.replace(" ", "_")
    for pattern, category_name in _CATEGORY_PATTERN_ALIASES:
        if pattern.search(normalized):
            return category_name
    return None


def _compile_rule(model: NormalizationRule) -> CompiledNormalizationRule | None:
    try:
        compiled = re.compile(model.pattern, re.IGNORECASE)
    except re.error:
        return None
    return CompiledNormalizationRule(
        rule_type=model.rule_type,
        pattern=compiled,
        replacement=model.replacement,
        priority=model.priority,
    )


def load_normalization_bundle(session: Session, *, source: str) -> NormalizationBundle:
    alias_rows = session.execute(
        select(MerchantAlias)
        .where(or_(MerchantAlias.source.is_(None), MerchantAlias.source == source))
        .order_by(MerchantAlias.source.is_(None), MerchantAlias.created_at.asc())
    ).scalars()
    aliases: dict[str, str] = {}
    for row in alias_rows:
        key = row.alias.strip().lower()
        if not key:
            continue
        aliases[key] = row.canonical_name

    rule_rows = session.execute(
        select(NormalizationRule)
        .where(
            NormalizationRule.enabled.is_(True),
            or_(NormalizationRule.source.is_(None), NormalizationRule.source == source),
        )
        .order_by(NormalizationRule.priority.asc(), NormalizationRule.created_at.asc())
    ).scalars()
    rules: list[CompiledNormalizationRule] = []
    for rule_row in rule_rows:
        compiled = _compile_rule(rule_row)
        if compiled is not None:
            rules.append(compiled)

    return NormalizationBundle(source=source, merchant_aliases=aliases, rules=rules)


def normalize_merchant_name(name: str | None, bundle: NormalizationBundle) -> str | None:
    if name is None:
        return None
    value = name.strip()
    if not value:
        return None
    alias = bundle.merchant_aliases.get(value.lower())
    if alias:
        return alias
    for rule in bundle.rules:
        if rule.rule_type != "merchant_regex":
            continue
        if not rule.pattern.search(value):
            continue
        if rule.replacement:
            return rule.pattern.sub(rule.replacement, value)
    return value


def normalize_item_category(
    *,
    item_name: str,
    current_category: str | None,
    bundle: NormalizationBundle,
) -> str | None:
    category_value = current_category.strip() if current_category is not None else ""
    value_match = find_category_value_normalization(
        current_category=current_category,
        bundle=bundle,
    )
    if value_match is not None:
        return canonicalize_category_name(value_match.replacement) or value_match.replacement
    name_match = find_category_name_normalization(item_name=item_name, bundle=bundle)
    if name_match is not None:
        return canonicalize_category_name(name_match.replacement) or name_match.replacement
    if category_value:
        return canonicalize_category_name(category_value) or current_category
    return None


def find_category_name_normalization(
    *,
    item_name: str,
    bundle: NormalizationBundle,
) -> CategoryNormalizationMatch | None:
    name_value = item_name.strip()
    for rule in bundle.rules:
        if rule.rule_type != "category_name_regex":
            continue
        if not rule.pattern.search(name_value) or not rule.replacement:
            continue
        return CategoryNormalizationMatch(
            rule_type=rule.rule_type,
            replacement=rule.replacement,
            priority=rule.priority,
        )
    return None


def find_category_value_normalization(
    *,
    current_category: str | None,
    bundle: NormalizationBundle,
) -> CategoryNormalizationMatch | None:
    category_value = current_category.strip() if current_category is not None else ""
    for rule in bundle.rules:
        if rule.rule_type != "category_value_regex":
            continue
        if not category_value or not rule.pattern.search(category_value) or not rule.replacement:
            continue
        return CategoryNormalizationMatch(
            rule_type=rule.rule_type,
            replacement=rule.replacement,
            priority=rule.priority,
        )
    return None
