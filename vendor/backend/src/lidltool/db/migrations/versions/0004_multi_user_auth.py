"""Add users and user_api_keys tables for multi-user auth

Revision ID: 0004_multi_user_auth
Revises: 0003_budget_and_patterns
Create Date: 2026-02-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_multi_user_auth"
down_revision = "0003_budget_and_patterns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {row[0] for row in conn.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("username", sa.String(), nullable=False),
            sa.Column("display_name", sa.String(), nullable=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("user_id"),
            sa.UniqueConstraint("username"),
        )

    if "user_api_keys" not in existing:
        op.create_table(
            "user_api_keys",
            sa.Column("key_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("label", sa.String(), nullable=False),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("key_hash", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("key_id"),
            sa.UniqueConstraint("key_hash"),
        )
        op.create_index("idx_user_api_keys_active", "user_api_keys", ["is_active"], unique=False)
        op.create_index("idx_user_api_keys_user_id", "user_api_keys", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_user_api_keys_user_id", table_name="user_api_keys")
    op.drop_index("idx_user_api_keys_active", table_name="user_api_keys")
    op.drop_table("user_api_keys")
    op.drop_table("users")
