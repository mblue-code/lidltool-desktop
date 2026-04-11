"""seed fish category into canonical taxonomy

Revision ID: 0023_add_fish_category
Revises: 0022_offer_source_configs
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_add_fish_category"
down_revision = "0022_offer_source_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    categories = sa.table(
        "categories",
        sa.column("category_id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("parent_category_id", sa.String()),
    )
    parent_id = conn.execute(
        sa.select(categories.c.category_id).where(categories.c.name == "groceries").limit(1)
    ).scalar_one_or_none()
    if parent_id is None:
        return
    existing = conn.execute(
        sa.select(categories.c.category_id).where(categories.c.name == "groceries:fish").limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return
    op.bulk_insert(
        categories,
        [
            {
                "category_id": "groceries:fish",
                "name": "groceries:fish",
                "parent_category_id": parent_id,
            }
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM categories WHERE category_id = :category_id"),
        {"category_id": "groceries:fish"},
    )
