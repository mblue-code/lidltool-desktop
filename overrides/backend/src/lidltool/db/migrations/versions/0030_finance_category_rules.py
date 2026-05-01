"""add learned finance category rules

Revision ID: 0030_finance_category_rules
Revises: 0029_finance_transaction_categories
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_finance_category_rules"
down_revision = "0029_finance_transaction_categories"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _seed_rules() -> None:
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
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.select(rules.c.normalized_pattern)).all()}
    rows = [
        {
            "id": "seed-getsafe-digital-gmbh",
            "rule_type": "merchant",
            "pattern": "Getsafe Digital GmbH",
            "normalized_pattern": "getsafe digital gmbh",
            "category_id": "insurance:liability",
            "direction": "outflow",
            "source": "seed",
            "confidence": 1,
            "hit_count": 0,
            "enabled": True,
            "metadata_json": {"reason": "known recurring insurance merchant"},
        }
    ]
    rows = [row for row in rows if row["normalized_pattern"] not in existing]
    if rows:
        op.bulk_insert(rules, rows)


def upgrade() -> None:
    if "finance_category_rules" not in _table_names():
        op.create_table(
            "finance_category_rules",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("rule_type", sa.String(), nullable=False, server_default="merchant"),
            sa.Column("pattern", sa.String(), nullable=False),
            sa.Column("normalized_pattern", sa.String(), nullable=False),
            sa.Column("category_id", sa.String(), nullable=False),
            sa.Column("direction", sa.String(length=16), nullable=False, server_default="outflow"),
            sa.Column("source", sa.String(), nullable=False, server_default="learned"),
            sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    indexes = _index_names("finance_category_rules")
    for name, columns in {
        "ix_finance_category_rules_pattern": ["pattern"],
        "ix_finance_category_rules_normalized_pattern": ["normalized_pattern"],
        "ix_finance_category_rules_category_id": ["category_id"],
        "ix_finance_category_rules_direction": ["direction"],
        "ix_finance_category_rules_enabled": ["enabled"],
    }.items():
        if name not in indexes:
            op.create_index(name, "finance_category_rules", columns)
    _seed_rules()


def downgrade() -> None:
    if "finance_category_rules" not in _table_names():
        return
    for name in (
        "ix_finance_category_rules_enabled",
        "ix_finance_category_rules_direction",
        "ix_finance_category_rules_category_id",
        "ix_finance_category_rules_normalized_pattern",
        "ix_finance_category_rules_pattern",
    ):
        if name in _index_names("finance_category_rules"):
            op.drop_index(name, table_name="finance_category_rules")
    op.drop_table("finance_category_rules")
