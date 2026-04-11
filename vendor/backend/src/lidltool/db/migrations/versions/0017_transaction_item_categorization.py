"""add canonical item categorization schema and seed taxonomy

Revision ID: 0017_transaction_item_categorization
Revises: 0016_user_sessions
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_transaction_item_categorization"
down_revision = "0016_user_sessions"
branch_labels = None
depends_on = None

_CATEGORY_TAXONOMY: list[tuple[str, str | None]] = [
    ("groceries", None),
    ("household", None),
    ("personal_care", None),
    ("electronics", None),
    ("gaming_media", None),
    ("shipping_fees", None),
    ("deposit", None),
    ("other", None),
    ("groceries:dairy", "groceries"),
    ("groceries:baking", "groceries"),
    ("groceries:beverages", "groceries"),
    ("groceries:produce", "groceries"),
    ("groceries:bakery", "groceries"),
    ("groceries:fish", "groceries"),
    ("groceries:meat", "groceries"),
    ("groceries:frozen", "groceries"),
    ("groceries:snacks", "groceries"),
    ("groceries:pantry", "groceries"),
]


def _get_columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _get_indexes(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _seed_taxonomy(conn: sa.Connection) -> None:
    categories = sa.table(
        "categories",
        sa.column("category_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("parent_category_id", sa.String()),
    )
    existing_rows = conn.execute(
        sa.select(categories.c.category_id, categories.c.name)
        .where(categories.c.name.in_([name for name, _ in _CATEGORY_TAXONOMY]))
        .order_by(categories.c.name.asc(), categories.c.category_id.asc())
    ).all()
    name_to_id: dict[str, str] = {}
    for category_id, name in existing_rows:
        normalized_name = str(name).strip()
        if normalized_name and normalized_name not in name_to_id:
            name_to_id[normalized_name] = str(category_id)

    rows_to_insert: list[dict[str, str | None]] = []
    for name, parent_name in _CATEGORY_TAXONOMY:
        if name in name_to_id:
            continue
        parent_id = name_to_id.get(parent_name) if parent_name is not None else None
        if parent_name is not None and parent_id is None:
            raise RuntimeError(f"taxonomy parent not seeded yet: {parent_name}")
        rows_to_insert.append(
            {
                "category_id": name,
                "name": name,
                "parent_category_id": parent_id,
            }
        )
        name_to_id[name] = name

    if rows_to_insert:
        op.bulk_insert(categories, rows_to_insert)


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    transaction_item_columns = _get_columns(inspector, "transaction_items")
    missing_columns = {
        column_name
        for column_name in {
            "category_id",
            "category_method",
            "category_confidence",
            "category_source_value",
            "category_version",
        }
        if column_name not in transaction_item_columns
    }

    if missing_columns:
        if conn.dialect.name == "sqlite":
            with op.batch_alter_table("transaction_items", recreate="always") as batch_op:
                if "category_id" in missing_columns:
                    batch_op.add_column(
                        sa.Column("category_id", sa.String(), nullable=True)
                    )
                if "category_method" in missing_columns:
                    batch_op.add_column(
                        sa.Column("category_method", sa.String(), nullable=True)
                    )
                if "category_confidence" in missing_columns:
                    batch_op.add_column(
                        sa.Column("category_confidence", sa.Numeric(4, 3), nullable=True)
                    )
                if "category_source_value" in missing_columns:
                    batch_op.add_column(
                        sa.Column("category_source_value", sa.String(), nullable=True)
                    )
                if "category_version" in missing_columns:
                    batch_op.add_column(
                        sa.Column("category_version", sa.String(), nullable=True)
                    )
                if "category_id" in missing_columns:
                    batch_op.create_foreign_key(
                        "fk_transaction_items_category_id_categories",
                        "categories",
                        ["category_id"],
                        ["category_id"],
                    )
        else:
            if "category_id" in missing_columns:
                op.add_column("transaction_items", sa.Column("category_id", sa.String(), nullable=True))
                op.create_foreign_key(
                    "fk_transaction_items_category_id_categories",
                    "transaction_items",
                    "categories",
                    ["category_id"],
                    ["category_id"],
                )
            if "category_method" in missing_columns:
                op.add_column(
                    "transaction_items", sa.Column("category_method", sa.String(), nullable=True)
                )
            if "category_confidence" in missing_columns:
                op.add_column(
                    "transaction_items", sa.Column("category_confidence", sa.Numeric(4, 3), nullable=True)
                )
            if "category_source_value" in missing_columns:
                op.add_column(
                    "transaction_items",
                    sa.Column("category_source_value", sa.String(), nullable=True),
                )
            if "category_version" in missing_columns:
                op.add_column(
                    "transaction_items", sa.Column("category_version", sa.String(), nullable=True)
                )

    inspector = sa.inspect(conn)
    if "ix_transaction_items_category_id" not in _get_indexes(inspector, "transaction_items"):
        op.create_index(
            "ix_transaction_items_category_id",
            "transaction_items",
            ["category_id"],
            unique=False,
        )

    _seed_taxonomy(conn)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "ix_transaction_items_category_id" in _get_indexes(inspector, "transaction_items"):
        op.drop_index("ix_transaction_items_category_id", table_name="transaction_items")

    transaction_item_columns = _get_columns(inspector, "transaction_items")
    if {"category_id", "category_method", "category_confidence", "category_source_value", "category_version"} & transaction_item_columns:
        if conn.dialect.name == "sqlite":
            with op.batch_alter_table("transaction_items", recreate="always") as batch_op:
                if "category_id" in transaction_item_columns:
                    batch_op.drop_column("category_id")
                if "category_method" in transaction_item_columns:
                    batch_op.drop_column("category_method")
                if "category_confidence" in transaction_item_columns:
                    batch_op.drop_column("category_confidence")
                if "category_source_value" in transaction_item_columns:
                    batch_op.drop_column("category_source_value")
                if "category_version" in transaction_item_columns:
                    batch_op.drop_column("category_version")
        else:
            if "category_id" in transaction_item_columns:
                op.drop_constraint(
                    "fk_transaction_items_category_id_categories",
                    "transaction_items",
                    type_="foreignkey",
                )
                op.drop_column("transaction_items", "category_id")
            if "category_method" in transaction_item_columns:
                op.drop_column("transaction_items", "category_method")
            if "category_confidence" in transaction_item_columns:
                op.drop_column("transaction_items", "category_confidence")
            if "category_source_value" in transaction_item_columns:
                op.drop_column("transaction_items", "category_source_value")
            if "category_version" in transaction_item_columns:
                op.drop_column("transaction_items", "category_version")
