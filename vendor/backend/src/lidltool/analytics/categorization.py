from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.db.models import CategoryRule


@dataclass(slots=True)
class CompiledRule:
    pattern: re.Pattern[str]
    category: str


def load_compiled_rules(session: Session) -> list[CompiledRule]:
    rows = (
        session.execute(select(CategoryRule).order_by(CategoryRule.priority.asc())).scalars().all()
    )
    rules: list[CompiledRule] = []
    for row in rows:
        try:
            rules.append(
                CompiledRule(pattern=re.compile(row.pattern, re.IGNORECASE), category=row.category)
            )
        except re.error:
            continue
    return rules


def categorize_name(name: str, rules: list[CompiledRule]) -> str | None:
    match = find_category_rule(item_name=name, rules=rules)
    return match.category if match is not None else None


def find_category_rule(
    *,
    item_name: str,
    rules: list[CompiledRule] | tuple[CompiledRule, ...],
) -> CompiledRule | None:
    for rule in rules:
        if rule.pattern.search(item_name):
            return rule
    return None
