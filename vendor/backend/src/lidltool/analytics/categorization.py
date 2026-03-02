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
    for rule in rules:
        if rule.pattern.search(name):
            return rule.category
    return None
