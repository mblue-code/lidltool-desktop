"""add connector lifecycle and config state

Revision ID: 0019_connector_lifecycle_state
Revises: 0018_monthly_budget_cashflow
Create Date: 2026-03-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_connector_lifecycle_state"
down_revision = "0018_monthly_budget_cashflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_lifecycle_state",
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=True),
        sa.Column("installed", sa.Boolean(), nullable=False),
        sa.Column("desired_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(
        op.f("ix_connector_lifecycle_state_plugin_id"),
        "connector_lifecycle_state",
        ["plugin_id"],
        unique=False,
    )

    op.create_table(
        "connector_config_state",
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=True),
        sa.Column("public_config_json", sa.JSON(), nullable=True),
        sa.Column("secret_config_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )
    op.create_index(
        op.f("ix_connector_config_state_plugin_id"),
        "connector_config_state",
        ["plugin_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_connector_config_state_plugin_id"), table_name="connector_config_state")
    op.drop_table("connector_config_state")

    op.drop_index(op.f("ix_connector_lifecycle_state_plugin_id"), table_name="connector_lifecycle_state")
    op.drop_table("connector_lifecycle_state")
