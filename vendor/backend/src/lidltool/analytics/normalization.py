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
    "household": "household",
    "haushalt": "household",
    "reinigung": "household",
    "personal care": "personal_care",
    "personal_care": "personal_care",
    "pflege": "personal_care",
    "hygiene": "personal_care",
    "drogerie": "personal_care",
    "electronics": "electronics",
    "elektronik": "electronics",
    "gaming": "gaming_media",
    "gaming_media": "gaming_media",
    "media": "gaming_media",
    "shipping": "shipping_fees",
    "shipping_fees": "shipping_fees",
    "delivery": "shipping_fees",
    "shipping fee": "shipping_fees",
    "shipping fees": "shipping_fees",
    "versand": "shipping_fees",
    "versandkosten": "shipping_fees",
    "fees": "other",
    "fee": "other",
    "deposit": "deposit",
    "pfand": "deposit",
    "other": "other",
}
_CATEGORY_PATTERN_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(pfand|deposit|leergut)\b", re.IGNORECASE), "deposit"),
    (re.compile(r"\b(shipping|delivery|versand|liefer|porto)\b", re.IGNORECASE), "shipping_fees"),
    (re.compile(r"\b(service fee|service charge|gebuhr|gebühr|fee|fees)\b", re.IGNORECASE), "other"),
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
