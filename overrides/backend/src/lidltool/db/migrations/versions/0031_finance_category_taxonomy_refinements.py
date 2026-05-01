"""refine finance category taxonomy and merchant seeds

Revision ID: 0031_finance_category_taxonomy_refinements
Revises: 0030_finance_category_rules
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_finance_category_taxonomy_refinements"
down_revision = "0030_finance_category_rules"
branch_labels = None
depends_on = None


_CATEGORIES: tuple[tuple[str, str | None], ...] = (
    ("shopping:online_retail", "shopping"),
    ("shopping:convenience", "shopping"),
    ("shopping:other", "shopping"),
    ("personal_care:drugstore", "personal_care"),
    ("personal_care:other", "personal_care"),
    ("education:publications", "education"),
    ("education:courses", "education"),
    ("education:books", "education"),
    ("education:other", "education"),
)

_RULES: tuple[dict[str, object], ...] = (
    {
        "id": "seed-amazon-online-retail",
        "pattern": "Amazon",
        "normalized_pattern": "amazon",
        "category_id": "shopping:online_retail",
        "direction": "outflow",
        "metadata_json": {"reason": "known online retail merchant"},
    },
    {
        "id": "seed-amazon-marketplace-online-retail",
        "pattern": "Amazon Marketplace",
        "normalized_pattern": "amazon marketplace",
        "category_id": "shopping:online_retail",
        "direction": "outflow",
        "metadata_json": {"reason": "known online retail merchant"},
    },
    {
        "id": "seed-substack-publications",
        "pattern": "Substack",
        "normalized_pattern": "substack",
        "category_id": "education:publications",
        "direction": "outflow",
        "metadata_json": {"reason": "known publication and knowledge platform"},
    },
    {
        "id": "seed-catapult-news",
        "pattern": "Catapult",
        "normalized_pattern": "catapult",
        "category_id": "subscriptions:news",
        "direction": "outflow",
        "metadata_json": {"reason": "known magazine subscription"},
    },
    {
        "id": "seed-catapult-magazine-news",
        "pattern": "Catapult Magazine",
        "normalized_pattern": "catapult magazine",
        "category_id": "subscriptions:news",
        "direction": "outflow",
        "metadata_json": {"reason": "known magazine subscription"},
    },
    {
        "id": "seed-swift-fitness",
        "pattern": "Swift",
        "normalized_pattern": "swift",
        "category_id": "subscriptions:fitness",
        "direction": "outflow",
        "metadata_json": {"reason": "known fitness subscription merchant"},
    },
    {
        "id": "seed-dm-drugstore",
        "pattern": "DM",
        "normalized_pattern": "dm",
        "category_id": "personal_care:drugstore",
        "direction": "outflow",
        "metadata_json": {"reason": "known drugstore merchant"},
    },
    {
        "id": "seed-dm-drogerie-markt-drugstore",
        "pattern": "dm-drogerie markt",
        "normalized_pattern": "dm-drogerie markt",
        "category_id": "personal_care:drugstore",
        "direction": "outflow",
        "metadata_json": {"reason": "known drugstore merchant"},
    },
    {
        "id": "seed-rossmann-drugstore",
        "pattern": "Rossmann",
        "normalized_pattern": "rossmann",
        "category_id": "personal_care:drugstore",
        "direction": "outflow",
        "metadata_json": {"reason": "known drugstore merchant"},
    },
    {
        "id": "seed-kiosk-convenience",
        "pattern": "Kiosk",
        "normalized_pattern": "kiosk",
        "category_id": "shopping:convenience",
        "direction": "outflow",
        "metadata_json": {"reason": "known convenience store merchant"},
    },
)


def upgrade() -> None:
    categories = sa.table(
        "categories",
        sa.column("category_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("parent_category_id", sa.String()),
    )
    conn = op.get_bind()
    existing_categories = {row[0] for row in conn.execute(sa.select(categories.c.category_id)).all()}
    category_rows = [
        {"category_id": category_id, "name": category_id, "parent_category_id": parent_id}
        for category_id, parent_id in _CATEGORIES
        if category_id not in existing_categories
    ]
    if category_rows:
        op.bulk_insert(categories, category_rows)

    if "finance_category_rules" not in sa.inspect(conn).get_table_names():
        return
    rules = sa.table(
        "finance_category_rules",
        sa.column("id", sa.String()),
        sa.column("rule_type", sa.String()),
        sa.column("pattern", sa.String()),
        sa.column("normalized_pattern", sa.String()),
        sa.column("category_id", sa.String()),
        sa.column("direction", sa.String()),
        sa.column("source", sa.String()),
        sa.column("confidence", sa.Numeric()),
        sa.column("hit_count", sa.Integer()),
        sa.column("enabled", sa.Boolean()),
        sa.column("metadata_json", sa.JSON()),
    )
    existing_rules = {
        row[0]: row[1]
        for row in conn.execute(sa.select(rules.c.normalized_pattern, rules.c.source)).all()
    }
    for row in _RULES:
        if row["normalized_pattern"] in existing_rules and existing_rules[row["normalized_pattern"]] != "manual":
            conn.execute(
                rules.update()
                .where(rules.c.normalized_pattern == row["normalized_pattern"])
                .where(rules.c.source != "manual")
                .values(
                    category_id=row["category_id"],
                    direction=row["direction"],
                    source="seed",
                    confidence=1,
                    enabled=True,
                    metadata_json=row["metadata_json"],
                )
            )
    rule_rows = [
        {
            "rule_type": "merchant",
            "source": "seed",
            "confidence": 1,
            "hit_count": 0,
            "enabled": True,
            **row,
        }
        for row in _RULES
        if row["normalized_pattern"] not in existing_rules
    ]
    if rule_rows:
        op.bulk_insert(rules, rule_rows)


def downgrade() -> None:
    if "finance_category_rules" in sa.inspect(op.get_bind()).get_table_names():
        rules = sa.table("finance_category_rules", sa.column("id", sa.String()))
        op.get_bind().execute(
            rules.delete().where(rules.c.id.in_([str(row["id"]) for row in _RULES]))
        )
