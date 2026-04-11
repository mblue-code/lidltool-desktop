"""add offer refresh run tracking

Revision ID: 0015_offer_refresh_runs
Revises: 0014_offer_platform_foundation
Create Date: 2026-03-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_offer_refresh_runs"
down_revision = "0014_offer_platform_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_refresh_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("rule_id", sa.String(), nullable=True),
        sa.Column("trigger_kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["automation_rules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_offer_refresh_runs_created_at"),
        "offer_refresh_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_refresh_runs_rule_id"),
        "offer_refresh_runs",
        ["rule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_refresh_runs_status"),
        "offer_refresh_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_refresh_runs_user_id"),
        "offer_refresh_runs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_refresh_runs_user_id"), table_name="offer_refresh_runs")
    op.drop_index(op.f("ix_offer_refresh_runs_status"), table_name="offer_refresh_runs")
    op.drop_index(op.f("ix_offer_refresh_runs_rule_id"), table_name="offer_refresh_runs")
    op.drop_index(op.f("ix_offer_refresh_runs_created_at"), table_name="offer_refresh_runs")
    op.drop_table("offer_refresh_runs")
