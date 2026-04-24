"""Add multi-user ownership columns to existing tables

Revision ID: 0005_multi_user_columns
Revises: 0004_multi_user_auth
Create Date: 2026-02-21 00:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_multi_user_columns"
down_revision = "0004_multi_user_auth"
branch_labels = None
depends_on = None


def _has_column(conn: sa.engine.Connection, table: str, column: str) -> bool:
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    conn = op.get_bind()

    # sources: user_id (nullable FK)
    if not _has_column(conn, "sources", "user_id"):
        op.add_column("sources", sa.Column("user_id", sa.String(), nullable=True))
        op.create_index("idx_sources_user_id", "sources", ["user_id"], unique=False)

    # transactions: user_id (nullable FK)
    if not _has_column(conn, "transactions", "user_id"):
        op.add_column("transactions", sa.Column("user_id", sa.String(), nullable=True))
        op.create_index("idx_transactions_user_id", "transactions", ["user_id"], unique=False)


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN in older versions; skip for now
    pass
