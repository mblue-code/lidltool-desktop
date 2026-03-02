"""0006 deposit tracking

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005_multi_user_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transaction_items",
        sa.Column("is_deposit", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Flag existing Pfand items
    op.execute(
        "UPDATE transaction_items SET is_deposit = 1 WHERE LOWER(name) LIKE '%pfand%'"
    )
    # Recalculate transaction totals excluding deposits
    op.execute(
        """
        UPDATE transactions
        SET total_gross_cents = (
            SELECT COALESCE(SUM(ti.line_total_cents), 0)
            FROM transaction_items ti
            WHERE ti.transaction_id = transactions.id
              AND ti.is_deposit = 0
        )
        """
    )


def downgrade() -> None:
    op.drop_column("transaction_items", "is_deposit")
