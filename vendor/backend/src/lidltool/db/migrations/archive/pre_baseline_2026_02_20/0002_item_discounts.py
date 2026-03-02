"""add discounts column to receipt_items

Revision ID: 0002_item_discounts
Revises: 0001_initial
Create Date: 2026-02-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_item_discounts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("receipt_items", sa.Column("discounts", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("receipt_items", "discounts")
