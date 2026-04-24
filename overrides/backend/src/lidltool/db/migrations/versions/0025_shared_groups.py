"""add shared groups and memberships

Revision ID: 0025_shared_groups
Revises: 0024_goals_and_notifications
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_shared_groups"
down_revision = "0024_goals_and_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shared_groups",
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("group_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("group_id"),
    )
    op.create_index(op.f("ix_shared_groups_group_type"), "shared_groups", ["group_type"], unique=False)
    op.create_index(op.f("ix_shared_groups_status"), "shared_groups", ["status"], unique=False)
    op.create_index(
        op.f("ix_shared_groups_created_by_user_id"),
        "shared_groups",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_shared_groups_type_status",
        "shared_groups",
        ["group_type", "status"],
        unique=False,
    )
    op.create_index(
        "ix_shared_groups_creator",
        "shared_groups",
        ["created_by_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "shared_group_members",
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default=sa.text("'member'")),
        sa.Column(
            "membership_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["shared_groups.group_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )
    op.create_index(op.f("ix_shared_group_members_role"), "shared_group_members", ["role"], unique=False)
    op.create_index(
        op.f("ix_shared_group_members_membership_status"),
        "shared_group_members",
        ["membership_status"],
        unique=False,
    )
    op.create_index(
        "ix_shared_group_members_user_status",
        "shared_group_members",
        ["user_id", "membership_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_shared_group_members_user_status", table_name="shared_group_members")
    op.drop_index(op.f("ix_shared_group_members_membership_status"), table_name="shared_group_members")
    op.drop_index(op.f("ix_shared_group_members_role"), table_name="shared_group_members")
    op.drop_table("shared_group_members")

    op.drop_index("ix_shared_groups_creator", table_name="shared_groups")
    op.drop_index("ix_shared_groups_type_status", table_name="shared_groups")
    op.drop_index(op.f("ix_shared_groups_created_by_user_id"), table_name="shared_groups")
    op.drop_index(op.f("ix_shared_groups_status"), table_name="shared_groups")
    op.drop_index(op.f("ix_shared_groups_group_type"), table_name="shared_groups")
    op.drop_table("shared_groups")
