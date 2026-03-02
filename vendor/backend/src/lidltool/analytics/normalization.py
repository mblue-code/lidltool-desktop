from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from lidltool.db.models import MerchantAlias, NormalizationRule


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
    name_value = item_name.strip()
    category_value = current_category.strip() if current_category is not None else ""
    for rule in bundle.rules:
        if rule.rule_type == "category_name_regex":
            if rule.pattern.search(name_value) and rule.replacement:
                return rule.replacement
        elif rule.rule_type == "category_value_regex":
            if category_value and rule.pattern.search(category_value) and rule.replacement:
                return rule.replacement
    return current_category
