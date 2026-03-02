"""analytics product layer and query workbench foundations

Revision ID: 0002_analytics_product_layer
Revises: 0001_baseline_schema
Create Date: 2026-02-20 18:45:00.000000
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0002_analytics_product_layer"
down_revision = "0001_baseline_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _refresh() -> None:
        nonlocal inspector
        inspector = sa.inspect(bind)

    def _has_table(name: str) -> bool:
        return name in set(inspector.get_table_names())

    def _has_column(table_name: str, column_name: str) -> bool:
        if not _has_table(table_name):
            return False
        return any(column.get("name") == column_name for column in inspector.get_columns(table_name))

    def _has_index(table_name: str, index_name: str) -> bool:
        if not _has_table(table_name):
            return False
        return any(index.get("name") == index_name for index in inspector.get_indexes(table_name))

    def _ensure_index(table_name: str, index_name: str, columns: list[str]) -> None:
        if _has_index(table_name, index_name):
            return
        op.create_index(index_name, table_name, columns, unique=False)
        _refresh()

    if not _has_table("categories"):
        op.create_table(
            "categories",
            sa.Column("category_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("parent_category_id", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["parent_category_id"], ["categories.category_id"]),
            sa.PrimaryKeyConstraint("category_id"),
        )
        _refresh()
    _ensure_index("categories", op.f("ix_categories_name"), ["name"])
    _ensure_index("categories", op.f("ix_categories_parent_category_id"), ["parent_category_id"])

    if not _has_table("products"):
        op.create_table(
            "products",
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("canonical_name", sa.Text(), nullable=False),
            sa.Column("brand", sa.String(), nullable=True),
            sa.Column("default_unit", sa.String(), nullable=True),
            sa.Column("category_id", sa.String(), nullable=True),
            sa.Column("gtin_ean", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"]),
            sa.PrimaryKeyConstraint("product_id"),
        )
        _refresh()
    _ensure_index("products", op.f("ix_products_category_id"), ["category_id"])
    _ensure_index("products", op.f("ix_products_gtin_ean"), ["gtin_ean"])

    if _has_table("transaction_items") and not _has_column("transaction_items", "product_id"):
        op.add_column("transaction_items", sa.Column("product_id", sa.String(), nullable=True))
        _refresh()
    _ensure_index(
        "transaction_items",
        op.f("ix_transaction_items_product_id"),
        ["product_id"],
    )

    if not _has_table("product_aliases"):
        op.create_table(
            "product_aliases",
            sa.Column("alias_id", sa.String(), nullable=False),
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("source_kind", sa.String(), nullable=True),
            sa.Column("raw_name", sa.Text(), nullable=False),
            sa.Column("raw_sku", sa.String(), nullable=True),
            sa.Column("match_confidence", sa.Numeric(4, 3), nullable=False),
            sa.Column("match_method", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
            sa.PrimaryKeyConstraint("alias_id"),
        )
        _refresh()
    _ensure_index("product_aliases", op.f("ix_product_aliases_product_id"), ["product_id"])
    _ensure_index("product_aliases", "idx_product_aliases_raw", ["source_kind", "raw_name"])

    if not _has_table("comparison_groups"):
        op.create_table(
            "comparison_groups",
            sa.Column("group_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("unit_standard", sa.String(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("group_id"),
        )
        _refresh()

    if not _has_table("comparison_group_members"):
        op.create_table(
            "comparison_group_members",
            sa.Column("group_id", sa.String(), nullable=False),
            sa.Column("product_id", sa.String(), nullable=False),
            sa.Column("weight", sa.Numeric(10, 3), nullable=False),
            sa.ForeignKeyConstraint(["group_id"], ["comparison_groups.group_id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
            sa.PrimaryKeyConstraint("group_id", "product_id"),
        )
        _refresh()

    if not _has_table("saved_queries"):
        op.create_table(
            "saved_queries",
            sa.Column("query_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("query_json", sa.JSON(), nullable=False),
            sa.Column("is_preset", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("query_id"),
        )
        _refresh()

    if not _has_table("item_observations"):
        op.create_table(
            "item_observations",
            sa.Column("observation_id", sa.String(), nullable=False),
            sa.Column("transaction_id", sa.String(), nullable=False),
            sa.Column("date", sa.String(), nullable=False),
            sa.Column("source_id", sa.String(), nullable=False),
            sa.Column("source_kind", sa.String(), nullable=False),
            sa.Column("product_id", sa.String(), nullable=True),
            sa.Column("raw_item_name", sa.Text(), nullable=False),
            sa.Column("quantity_value", sa.Numeric(12, 3), nullable=False),
            sa.Column("quantity_unit", sa.String(), nullable=False),
            sa.Column("unit_price_gross_cents", sa.Integer(), nullable=False),
            sa.Column("unit_price_net_cents", sa.Integer(), nullable=False),
            sa.Column("line_total_gross_cents", sa.Integer(), nullable=False),
            sa.Column("line_total_net_cents", sa.Integer(), nullable=False),
            sa.Column("basket_discount_alloc_cents", sa.Integer(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("category_id", sa.String(), nullable=True),
            sa.Column("merchant_name", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["category_id"], ["categories.category_id"]),
            sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
            sa.PrimaryKeyConstraint("observation_id"),
        )
        _refresh()
    _ensure_index(
        "item_observations",
        op.f("ix_item_observations_transaction_id"),
        ["transaction_id"],
    )
    _ensure_index("item_observations", op.f("ix_item_observations_date"), ["date"])
    _ensure_index("item_observations", op.f("ix_item_observations_source_id"), ["source_id"])
    _ensure_index("item_observations", op.f("ix_item_observations_source_kind"), ["source_kind"])
    _ensure_index("item_observations", op.f("ix_item_observations_product_id"), ["product_id"])
    _ensure_index("item_observations", op.f("ix_item_observations_category_id"), ["category_id"])
    _ensure_index("item_observations", "idx_obs_product_date", ["product_id", "date"])
    _ensure_index("item_observations", "idx_obs_category_date", ["category_id", "date"])
    _ensure_index("item_observations", "idx_obs_source_date", ["source_kind", "date"])
    _ensure_index("item_observations", "idx_obs_date", ["date"])

    if not _has_table("analytics_metadata"):
        op.create_table(
            "analytics_metadata",
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )
        _refresh()

    _ensure_index(
        "transactions",
        "idx_transactions_purchased_source",
        ["purchased_at", "source_id"],
    )
    _ensure_index(
        "discount_events",
        "idx_discount_events_kind",
        ["kind", "transaction_id"],
    )

    saved_queries = sa.table(
        "saved_queries",
        sa.column("query_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("query_json", sa.JSON()),
        sa.column("is_preset", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    preset_rows = [
            {
                "query_id": "preset-total-spend-all-time",
                "name": "Total spend all time",
                "description": "Monthly net spend across all available data.",
                "query_json": {
                    "metrics": ["net_total"],
                    "dimensions": ["month"],
                    "filters": {},
                    "time_grain": "month",
                    "sort_by": "month",
                    "sort_dir": "asc",
                },
                "is_preset": True,
                "created_at": datetime.now(tz=UTC),
            },
            {
                "query_id": "preset-groceries-last-90d-by-source",
                "name": "Groceries last 90 days by source",
                "description": "Net spend by source over the last 90 days.",
                "query_json": {
                    "metrics": ["net_total"],
                    "dimensions": ["source_kind"],
                    "filters": {"date_preset": "last90d"},
                    "sort_by": "net_total",
                    "sort_dir": "desc",
                },
                "is_preset": True,
                "created_at": datetime.now(tz=UTC),
            },
            {
                "query_id": "preset-top-20-items-ytd",
                "name": "Top 20 items by spend this year",
                "description": "Top products by net spend year-to-date.",
                "query_json": {
                    "metrics": ["net_total"],
                    "dimensions": ["product"],
                    "filters": {"date_preset": "ytd"},
                    "sort_by": "net_total",
                    "sort_dir": "desc",
                    "limit": 20,
                },
                "is_preset": True,
                "created_at": datetime.now(tz=UTC),
            },
            {
                "query_id": "preset-discount-attribution-ytd",
                "name": "Discount attribution this year",
                "description": "Total discounts year-to-date by source.",
                "query_json": {
                    "metrics": ["discount_total"],
                    "dimensions": ["source_kind"],
                    "filters": {"date_preset": "ytd"},
                    "sort_by": "discount_total",
                    "sort_dir": "desc",
                },
                "is_preset": True,
                "created_at": datetime.now(tz=UTC),
            },
            {
                "query_id": "preset-monthly-basket-count-by-source",
                "name": "Monthly basket count by source",
                "description": "Receipt count trend by source.",
                "query_json": {
                    "metrics": ["purchase_count"],
                    "dimensions": ["month", "source_kind"],
                    "filters": {},
                    "sort_by": "month",
                    "sort_dir": "asc",
                },
                "is_preset": True,
                "created_at": datetime.now(tz=UTC),
            },
        ]
    existing_query_ids: set[str] = set()
    if _has_table("saved_queries"):
        rows = bind.execute(sa.text("SELECT query_id FROM saved_queries")).all()
        existing_query_ids = {str(row[0]) for row in rows}
    missing_rows = [row for row in preset_rows if row["query_id"] not in existing_query_ids]
    if missing_rows:
        op.bulk_insert(saved_queries, missing_rows)


def downgrade() -> None:
    op.drop_index("idx_discount_events_kind", table_name="discount_events")
    op.drop_index("idx_transactions_purchased_source", table_name="transactions")

    op.drop_table("analytics_metadata")

    op.drop_index("idx_obs_date", table_name="item_observations")
    op.drop_index("idx_obs_source_date", table_name="item_observations")
    op.drop_index("idx_obs_category_date", table_name="item_observations")
    op.drop_index("idx_obs_product_date", table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_category_id"), table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_product_id"), table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_source_kind"), table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_source_id"), table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_date"), table_name="item_observations")
    op.drop_index(op.f("ix_item_observations_transaction_id"), table_name="item_observations")
    op.drop_table("item_observations")

    op.drop_table("saved_queries")
    op.drop_table("comparison_group_members")
    op.drop_table("comparison_groups")

    op.drop_index("idx_product_aliases_raw", table_name="product_aliases")
    op.drop_index(op.f("ix_product_aliases_product_id"), table_name="product_aliases")
    op.drop_table("product_aliases")

    op.drop_index(op.f("ix_transaction_items_product_id"), table_name="transaction_items")
    op.drop_column("transaction_items", "product_id")

    op.drop_index(op.f("ix_products_gtin_ean"), table_name="products")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_table("products")

    op.drop_index(op.f("ix_categories_parent_category_id"), table_name="categories")
    op.drop_index(op.f("ix_categories_name"), table_name="categories")
    op.drop_table("categories")
