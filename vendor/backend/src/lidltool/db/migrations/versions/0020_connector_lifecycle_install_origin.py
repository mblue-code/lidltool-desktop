"""add connector lifecycle install origin

Revision ID: 0020_connector_lifecycle_install_origin
Revises: 0019_connector_lifecycle_state
Create Date: 2026-03-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_connector_lifecycle_install_origin"
down_revision = "0019_connector_lifecycle_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "connector_lifecycle_state",
        sa.Column("install_origin", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_connector_lifecycle_state_install_origin"),
        "connector_lifecycle_state",
        ["install_origin"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_connector_lifecycle_state_install_origin"),
        table_name="connector_lifecycle_state",
    )
    op.drop_column("connector_lifecycle_state", "install_origin")
