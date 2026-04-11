"""add mobile device registration for push notifications

Revision ID: 0021_mobile_push_devices
Revises: 0020_connector_lifecycle_install_origin
Create Date: 2026-03-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_mobile_push_devices"
down_revision = "0020_connector_lifecycle_install_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_devices",
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("installation_id", sa.String(length=128), nullable=False),
        sa.Column("client_platform", sa.String(length=32), nullable=False),
        sa.Column("push_provider", sa.String(length=32), nullable=False),
        sa.Column("push_token", sa.Text(), nullable=False),
        sa.Column("device_label", sa.String(), nullable=True),
        sa.Column("client_name", sa.String(), nullable=True),
        sa.Column("app_version", sa.String(length=64), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=True),
        sa.Column("notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_push_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_push_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_push_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.session_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("device_id"),
    )
    op.create_index(op.f("ix_mobile_devices_client_platform"), "mobile_devices", ["client_platform"], unique=False)
    op.create_index(op.f("ix_mobile_devices_notifications_enabled"), "mobile_devices", ["notifications_enabled"], unique=False)
    op.create_index(op.f("ix_mobile_devices_push_provider"), "mobile_devices", ["push_provider"], unique=False)
    op.create_index(op.f("ix_mobile_devices_session_id"), "mobile_devices", ["session_id"], unique=False)
    op.create_index(op.f("ix_mobile_devices_user_id"), "mobile_devices", ["user_id"], unique=False)
    op.create_index(
        "ux_mobile_devices_user_installation",
        "mobile_devices",
        ["user_id", "installation_id"],
        unique=True,
    )
    op.create_index(
        "ix_mobile_devices_provider_token",
        "mobile_devices",
        ["push_provider", "push_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mobile_devices_provider_token", table_name="mobile_devices")
    op.drop_index("ux_mobile_devices_user_installation", table_name="mobile_devices")
    op.drop_index(op.f("ix_mobile_devices_user_id"), table_name="mobile_devices")
    op.drop_index(op.f("ix_mobile_devices_session_id"), table_name="mobile_devices")
    op.drop_index(op.f("ix_mobile_devices_push_provider"), table_name="mobile_devices")
    op.drop_index(op.f("ix_mobile_devices_notifications_enabled"), table_name="mobile_devices")
    op.drop_index(op.f("ix_mobile_devices_client_platform"), table_name="mobile_devices")
    op.drop_table("mobile_devices")
