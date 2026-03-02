"""add dashboard analytics indexes

Revision ID: 0007_dashboard_analytics_indexes
Revises: 0006_training_hints
Create Date: 2026-02-19
"""

from __future__ import annotations

from alembic import op

revision = "0007_dashboard_analytics_indexes"
down_revision = "0006_training_hints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_purchased_at_source_id",
        "transactions",
        ["purchased_at", "source_id"],
    )
    op.create_index(
        "ix_discount_events_kind_transaction_id",
        "discount_events",
        ["kind", "transaction_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_discount_events_kind_transaction_id", table_name="discount_events")
    op.drop_index("ix_transactions_purchased_at_source_id", table_name="transactions")
