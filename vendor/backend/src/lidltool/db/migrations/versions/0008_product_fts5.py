"""add product FTS5 indexes and AI clustering columns

Revision ID: 0008_product_fts5
Revises: 0006
Create Date: 2026-02-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_product_fts5"
down_revision = "0006"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _column_exists(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    if not _table_exists(inspector, table_name):
        return False
    return any(column.get("name") == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _table_exists(inspector, "products") and not _column_exists(
        inspector, "products", "is_ai_generated"
    ):
        op.add_column(
            "products",
            sa.Column(
                "is_ai_generated",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    inspector = sa.inspect(bind)
    if _table_exists(inspector, "products") and not _column_exists(
        inspector, "products", "cluster_confidence"
    ):
        op.add_column("products", sa.Column("cluster_confidence", sa.Float(), nullable=True))

    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
        USING fts5(
            product_id UNINDEXED,
            canonical_name,
            brand,
            content='products',
            content_rowid='rowid'
        )
        """
    )
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS product_aliases_fts
        USING fts5(
            product_id UNINDEXED,
            raw_name,
            content='product_aliases',
            content_rowid='rowid'
        )
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_fts_ai
        AFTER INSERT ON products
        BEGIN
          INSERT INTO products_fts(rowid, product_id, canonical_name, brand)
          VALUES (new.rowid, new.product_id, new.canonical_name, coalesce(new.brand, ''));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_fts_au
        AFTER UPDATE ON products
        BEGIN
          INSERT INTO products_fts(products_fts, rowid, product_id, canonical_name, brand)
          VALUES ('delete', old.rowid, old.product_id, old.canonical_name, coalesce(old.brand, ''));
          INSERT INTO products_fts(rowid, product_id, canonical_name, brand)
          VALUES (new.rowid, new.product_id, new.canonical_name, coalesce(new.brand, ''));
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS products_fts_ad
        AFTER DELETE ON products
        BEGIN
          INSERT INTO products_fts(products_fts, rowid, product_id, canonical_name, brand)
          VALUES ('delete', old.rowid, old.product_id, old.canonical_name, coalesce(old.brand, ''));
        END
        """
    )

    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS product_aliases_fts_ai
        AFTER INSERT ON product_aliases
        BEGIN
          INSERT INTO product_aliases_fts(rowid, product_id, raw_name)
          VALUES (new.rowid, new.product_id, new.raw_name);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS product_aliases_fts_au
        AFTER UPDATE ON product_aliases
        BEGIN
          INSERT INTO product_aliases_fts(product_aliases_fts, rowid, product_id, raw_name)
          VALUES ('delete', old.rowid, old.product_id, old.raw_name);
          INSERT INTO product_aliases_fts(rowid, product_id, raw_name)
          VALUES (new.rowid, new.product_id, new.raw_name);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS product_aliases_fts_ad
        AFTER DELETE ON product_aliases
        BEGIN
          INSERT INTO product_aliases_fts(product_aliases_fts, rowid, product_id, raw_name)
          VALUES ('delete', old.rowid, old.product_id, old.raw_name);
        END
        """
    )

    op.execute("INSERT INTO products_fts(products_fts) VALUES ('rebuild')")
    op.execute("INSERT INTO product_aliases_fts(product_aliases_fts) VALUES ('rebuild')")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS product_aliases_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS product_aliases_fts_au")
    op.execute("DROP TRIGGER IF EXISTS product_aliases_fts_ai")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ad")
    op.execute("DROP TRIGGER IF EXISTS products_fts_au")
    op.execute("DROP TRIGGER IF EXISTS products_fts_ai")

    op.execute("DROP TABLE IF EXISTS product_aliases_fts")
    op.execute("DROP TABLE IF EXISTS products_fts")

    with op.batch_alter_table("products") as batch_op:
        batch_op.drop_column("cluster_confidence")
        batch_op.drop_column("is_ai_generated")
