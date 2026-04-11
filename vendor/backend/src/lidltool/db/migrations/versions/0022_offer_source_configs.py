"""add user managed offer source configs

Revision ID: 0022_offer_source_configs
Revises: 0021_mobile_push_devices
Create Date: 2026-04-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_offer_source_configs"
down_revision = "0021_mobile_push_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_source_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("merchant_name", sa.String(), nullable=False),
        sa.Column("merchant_url", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id"),
    )
    op.create_index(
        op.f("ix_offer_source_configs_active"),
        "offer_source_configs",
        ["active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_source_configs_merchant_name"),
        "offer_source_configs",
        ["merchant_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_source_configs_source_id"),
        "offer_source_configs",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_offer_source_configs_user_id"),
        "offer_source_configs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_offer_source_configs_user_id"), table_name="offer_source_configs")
    op.drop_index(op.f("ix_offer_source_configs_source_id"), table_name="offer_source_configs")
    op.drop_index(op.f("ix_offer_source_configs_merchant_name"), table_name="offer_source_configs")
    op.drop_index(op.f("ix_offer_source_configs_active"), table_name="offer_source_configs")
    op.drop_table("offer_source_configs")
