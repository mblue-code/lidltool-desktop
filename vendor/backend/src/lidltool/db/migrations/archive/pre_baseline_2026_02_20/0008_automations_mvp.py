"""add automations mvp tables

Revision ID: 0008_automations_mvp
Revises: 0007_dashboard_analytics_indexes
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_automations_mvp"
down_revision = "0007_dashboard_analytics_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automation_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("trigger_config", sa.JSON(), nullable=True),
        sa.Column("action_config", sa.JSON(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_automation_rules_enabled_rule_type",
        "automation_rules",
        ["enabled", "rule_type"],
    )
    op.create_index(
        "ix_automation_rules_next_run_at",
        "automation_rules",
        ["next_run_at"],
    )

    op.create_table(
        "automation_executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("rule_id", sa.String(), sa.ForeignKey("automation_rules.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automation_executions_rule_id", "automation_executions", ["rule_id"])
    op.create_index(
        "ix_automation_executions_rule_id_triggered_at",
        "automation_executions",
        ["rule_id", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_executions_rule_id_triggered_at",
        table_name="automation_executions",
    )
    op.drop_index("ix_automation_executions_rule_id", table_name="automation_executions")
    op.drop_table("automation_executions")
    op.drop_index("ix_automation_rules_next_run_at", table_name="automation_rules")
    op.drop_index("ix_automation_rules_enabled_rule_type", table_name="automation_rules")
    op.drop_table("automation_rules")
