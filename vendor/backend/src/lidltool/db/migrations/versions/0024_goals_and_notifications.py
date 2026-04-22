"""add goals and notifications tables

Revision ID: 0024_goals_and_notifications
Revises: 0023_add_fish_category
Create Date: 2026-04-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_goals_and_notifications"
down_revision = "0023_add_fish_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "goals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("goal_type", sa.String(), nullable=False),
        sa.Column("target_amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("recurring_bill_id", sa.String(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["recurring_bill_id"], ["recurring_bills.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_goals_user_id"), "goals", ["user_id"], unique=False)
    op.create_index(op.f("ix_goals_goal_type"), "goals", ["goal_type"], unique=False)
    op.create_index(op.f("ix_goals_category"), "goals", ["category"], unique=False)
    op.create_index(op.f("ix_goals_merchant_name"), "goals", ["merchant_name"], unique=False)
    op.create_index(op.f("ix_goals_recurring_bill_id"), "goals", ["recurring_bill_id"], unique=False)
    op.create_index(op.f("ix_goals_target_date"), "goals", ["target_date"], unique=False)
    op.create_index(op.f("ix_goals_active"), "goals", ["active"], unique=False)
    op.create_index("ix_goals_user_active", "goals", ["user_id", "active"], unique=False)
    op.create_index("ix_goals_user_type", "goals", ["user_id", "goal_type"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("href", sa.String(), nullable=True),
        sa.Column("fingerprint", sa.String(length=160), nullable=False),
        sa.Column("unread", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_notifications_user_id"), "notifications", ["user_id"], unique=False)
    op.create_index(op.f("ix_notifications_kind"), "notifications", ["kind"], unique=False)
    op.create_index(op.f("ix_notifications_severity"), "notifications", ["severity"], unique=False)
    op.create_index(op.f("ix_notifications_unread"), "notifications", ["unread"], unique=False)
    op.create_index("ix_notifications_user_unread", "notifications", ["user_id", "unread"], unique=False)
    op.create_index(
        "ix_notifications_user_occurred", "notifications", ["user_id", "occurred_at"], unique=False
    )
    op.create_index(
        "ux_notifications_user_fingerprint",
        "notifications",
        ["user_id", "fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_notifications_user_fingerprint", table_name="notifications")
    op.drop_index("ix_notifications_user_occurred", table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index(op.f("ix_notifications_unread"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_severity"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_kind"), table_name="notifications")
    op.drop_index(op.f("ix_notifications_user_id"), table_name="notifications")
    op.drop_table("notifications")

    op.drop_index("ix_goals_user_type", table_name="goals")
    op.drop_index("ix_goals_user_active", table_name="goals")
    op.drop_index(op.f("ix_goals_active"), table_name="goals")
    op.drop_index(op.f("ix_goals_target_date"), table_name="goals")
    op.drop_index(op.f("ix_goals_recurring_bill_id"), table_name="goals")
    op.drop_index(op.f("ix_goals_merchant_name"), table_name="goals")
    op.drop_index(op.f("ix_goals_category"), table_name="goals")
    op.drop_index(op.f("ix_goals_goal_type"), table_name="goals")
    op.drop_index(op.f("ix_goals_user_id"), table_name="goals")
    op.drop_table("goals")
