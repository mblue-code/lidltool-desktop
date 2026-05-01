"""add transaction-level finance categorization

Revision ID: 0029_finance_transaction_categories
Revises: 0029_transaction_direction_scope
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_finance_transaction_categories"
down_revision = "0029_transaction_direction_scope"
branch_labels = None
depends_on = None


_FINANCE_CATEGORIES: list[tuple[str, str | None]] = [
    ("groceries", None), ("dining", None), ("housing", None), ("insurance", None),
    ("credit", None), ("mobility", None), ("car", None), ("investment", None),
    ("health", None), ("personal_care", None), ("subscriptions", None),
    ("communication", None), ("shopping", None), ("entertainment", None),
    ("travel", None), ("education", None), ("fees", None), ("tax", None),
    ("income", None), ("transfer", None), ("other", None), ("uncategorized", None),
    ("housing:rent", "housing"), ("housing:electricity", "housing"),
    ("housing:heating", "housing"), ("housing:water", "housing"),
    ("housing:utilities", "housing"), ("housing:internet", "housing"),
    ("housing:repairs", "housing"), ("housing:tradespeople", "housing"),
    ("housing:furniture", "housing"), ("housing:appliances", "housing"),
    ("housing:other", "housing"), ("insurance:health", "insurance"),
    ("insurance:liability", "insurance"), ("insurance:household", "insurance"),
    ("insurance:legal", "insurance"), ("insurance:car", "insurance"),
    ("insurance:travel", "insurance"), ("insurance:life", "insurance"),
    ("insurance:other", "insurance"), ("credit:repayment", "credit"),
    ("credit:interest", "credit"), ("credit:fees", "credit"),
    ("credit:other", "credit"), ("mobility:public_transit", "mobility"),
    ("mobility:train", "mobility"), ("mobility:taxi_rideshare", "mobility"),
    ("mobility:bike", "mobility"), ("mobility:parking_tolls", "mobility"),
    ("mobility:other", "mobility"), ("car:fuel", "car"),
    ("car:charging", "car"), ("car:maintenance", "car"), ("car:repairs", "car"),
    ("car:parking", "car"), ("car:tax", "car"), ("car:wash", "car"),
    ("car:other", "car"), ("investment:broker_transfer", "investment"),
    ("investment:savings_transfer", "investment"), ("investment:pension", "investment"),
    ("investment:crypto", "investment"), ("investment:other", "investment"),
    ("income:salary", "income"), ("income:refund", "income"),
    ("income:reimbursement", "income"), ("income:interest", "income"),
    ("income:gift", "income"), ("income:other", "income"),
    ("subscriptions:software", "subscriptions"), ("subscriptions:streaming", "subscriptions"),
    ("subscriptions:fitness", "subscriptions"), ("subscriptions:news", "subscriptions"),
    ("subscriptions:cloud", "subscriptions"), ("subscriptions:other", "subscriptions"),
    ("shopping:online_retail", "shopping"), ("shopping:convenience", "shopping"),
    ("shopping:other", "shopping"), ("personal_care:drugstore", "personal_care"),
    ("personal_care:other", "personal_care"), ("education:publications", "education"),
    ("education:courses", "education"), ("education:books", "education"),
    ("education:other", "education"),
    ("fees:bank", "fees"), ("fees:service", "fees"), ("fees:shipping", "fees"),
    ("fees:late_payment", "fees"), ("tax:income_tax", "tax"),
    ("tax:vehicle_tax", "tax"), ("tax:property_tax", "tax"), ("tax:other", "tax"),
]


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _seed_categories() -> None:
    categories = sa.table(
        "categories",
        sa.column("category_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("parent_category_id", sa.String()),
    )
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.select(categories.c.category_id)).all()}
    rows = [
        {"category_id": category_id, "name": category_id, "parent_category_id": parent_id}
        for category_id, parent_id in _FINANCE_CATEGORIES
        if category_id not in existing
    ]
    if rows:
        op.bulk_insert(categories, rows)


def _seed_finance_rules() -> None:
    if "finance_category_rules" not in sa.inspect(op.get_bind()).get_table_names():
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
    missing = {
        column
        for column in {
            "direction",
            "finance_category_id",
            "finance_category_method",
            "finance_category_confidence",
            "finance_category_source_value",
            "finance_category_version",
            "finance_tags_json",
        }
        if column not in _columns("transactions")
    }
    if missing:
        with op.batch_alter_table("transactions", recreate="always") as batch_op:
            if "direction" in missing:
                batch_op.add_column(sa.Column("direction", sa.String(), nullable=False, server_default="outflow"))
            if "finance_category_id" in missing:
                batch_op.add_column(sa.Column("finance_category_id", sa.String(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_transactions_finance_category_id_categories",
                    "categories",
                    ["finance_category_id"],
                    ["category_id"],
                )
            if "finance_category_method" in missing:
                batch_op.add_column(sa.Column("finance_category_method", sa.String(), nullable=True))
            if "finance_category_confidence" in missing:
                batch_op.add_column(sa.Column("finance_category_confidence", sa.Numeric(4, 3), nullable=True))
            if "finance_category_source_value" in missing:
                batch_op.add_column(sa.Column("finance_category_source_value", sa.String(), nullable=True))
            if "finance_category_version" in missing:
                batch_op.add_column(sa.Column("finance_category_version", sa.String(), nullable=True))
            if "finance_tags_json" in missing:
                batch_op.add_column(sa.Column("finance_tags_json", sa.JSON(), nullable=True))
    if "ix_transactions_direction" not in _indexes("transactions"):
        op.create_index("ix_transactions_direction", "transactions", ["direction"])
    if "ix_transactions_finance_category_id" not in _indexes("transactions"):
        op.create_index("ix_transactions_finance_category_id", "transactions", ["finance_category_id"])
    _seed_categories()
    if "finance_category_rules" not in sa.inspect(op.get_bind()).get_table_names():
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
        op.create_index("ix_finance_category_rules_pattern", "finance_category_rules", ["pattern"])
        op.create_index("ix_finance_category_rules_normalized_pattern", "finance_category_rules", ["normalized_pattern"])
        op.create_index("ix_finance_category_rules_category_id", "finance_category_rules", ["category_id"])
        op.create_index("ix_finance_category_rules_direction", "finance_category_rules", ["direction"])
        op.create_index("ix_finance_category_rules_enabled", "finance_category_rules", ["enabled"])
    _seed_finance_rules()


def downgrade() -> None:
    if "finance_category_rules" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_index("ix_finance_category_rules_enabled", table_name="finance_category_rules")
        op.drop_index("ix_finance_category_rules_direction", table_name="finance_category_rules")
        op.drop_index("ix_finance_category_rules_category_id", table_name="finance_category_rules")
        op.drop_index("ix_finance_category_rules_normalized_pattern", table_name="finance_category_rules")
        op.drop_index("ix_finance_category_rules_pattern", table_name="finance_category_rules")
        op.drop_table("finance_category_rules")
    if "ix_transactions_finance_category_id" in _indexes("transactions"):
        op.drop_index("ix_transactions_finance_category_id", table_name="transactions")
    if "ix_transactions_direction" in _indexes("transactions"):
        op.drop_index("ix_transactions_direction", table_name="transactions")
    columns = _columns("transactions")
    with op.batch_alter_table("transactions", recreate="always") as batch_op:
        for column in (
            "finance_tags_json",
            "finance_category_version",
            "finance_category_source_value",
            "finance_category_confidence",
            "finance_category_method",
            "finance_category_id",
            "direction",
        ):
            if column in columns:
                batch_op.drop_column(column)
