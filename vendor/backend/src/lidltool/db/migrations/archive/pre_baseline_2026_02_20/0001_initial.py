"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-02-18 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
    )

    op.create_table(
        "receipts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("store_id", sa.String(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("store_name", sa.String(), nullable=True),
        sa.Column("store_address", sa.String(), nullable=True),
        sa.Column("total_gross", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("discount_total", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_receipts_purchased_at", "receipts", ["purchased_at"])
    op.create_index("ix_receipts_store_id", "receipts", ["store_id"])
    op.create_index("ix_receipts_fingerprint", "receipts", ["fingerprint"])

    op.create_table(
        "receipt_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("receipt_id", sa.String(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("unit_price", sa.Integer(), nullable=True),
        sa.Column("line_total", sa.Integer(), nullable=False),
        sa.Column("vat_rate", sa.Numeric(6, 3), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])
    op.create_index("ix_receipt_items_name", "receipt_items", ["name"])
    op.create_index("ix_receipt_items_category", "receipt_items", ["category"])
    op.create_index(
        "ux_receipt_items_receipt_line",
        "receipt_items",
        ["receipt_id", "line_no"],
        unique=True,
    )

    op.create_table(
        "sync_state",
        sa.Column("source", sa.String(), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_receipt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_receipt_id", sa.String(), nullable=True),
    )

    op.create_table(
        "category_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
    )


def downgrade() -> None:
    op.drop_table("category_rules")
    op.drop_table("sync_state")
    op.drop_index("ux_receipt_items_receipt_line", table_name="receipt_items")
    op.drop_index("ix_receipt_items_category", table_name="receipt_items")
    op.drop_index("ix_receipt_items_name", table_name="receipt_items")
    op.drop_index("ix_receipt_items_receipt_id", table_name="receipt_items")
    op.drop_table("receipt_items")
    op.drop_index("ix_receipts_fingerprint", table_name="receipts")
    op.drop_index("ix_receipts_store_id", table_name="receipts")
    op.drop_index("ix_receipts_purchased_at", table_name="receipts")
    op.drop_table("receipts")
    op.drop_table("stores")
