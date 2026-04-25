"""add local mobile pairing and capture sync tables

Revision ID: 0027_mobile_pairing_sync
Revises: 0026_workspace_ownership
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_mobile_pairing_sync"
down_revision = "0026_workspace_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mobile_pairing_sessions",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("desktop_id", sa.String(length=128), nullable=False),
        sa.Column("desktop_name", sa.String(), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("pairing_token_hash", sa.String(length=64), nullable=False),
        sa.Column("public_key_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("paired_device_id", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("pairing_token_hash"),
    )
    op.create_index(op.f("ix_mobile_pairing_sessions_desktop_id"), "mobile_pairing_sessions", ["desktop_id"], unique=False)
    op.create_index(op.f("ix_mobile_pairing_sessions_created_by_user_id"), "mobile_pairing_sessions", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_mobile_pairing_sessions_expires_at"), "mobile_pairing_sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_mobile_pairing_sessions_status"), "mobile_pairing_sessions", ["status"], unique=False)

    op.create_table(
        "mobile_paired_devices",
        sa.Column("paired_device_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("desktop_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("device_name", sa.String(), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("sync_token_hash", sa.String(length=64), nullable=False),
        sa.Column("public_key_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("protocol_version", sa.Integer(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paired_device_id"),
        sa.UniqueConstraint("sync_token_hash"),
    )
    op.create_index(op.f("ix_mobile_paired_devices_desktop_id"), "mobile_paired_devices", ["desktop_id"], unique=False)
    op.create_index(op.f("ix_mobile_paired_devices_device_id"), "mobile_paired_devices", ["device_id"], unique=False)
    op.create_index(op.f("ix_mobile_paired_devices_platform"), "mobile_paired_devices", ["platform"], unique=False)
    op.create_index(op.f("ix_mobile_paired_devices_revoked_at"), "mobile_paired_devices", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_mobile_paired_devices_user_id"), "mobile_paired_devices", ["user_id"], unique=False)
    op.create_index("ux_mobile_paired_devices_desktop_device", "mobile_paired_devices", ["desktop_id", "device_id"], unique=True)

    op.create_table(
        "mobile_captures",
        sa.Column("capture_id", sa.String(), nullable=False),
        sa.Column("paired_device_id", sa.String(), nullable=False),
        sa.Column("mobile_capture_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["ingestion_jobs.id"]),
        sa.ForeignKeyConstraint(["paired_device_id"], ["mobile_paired_devices.paired_device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("capture_id"),
    )
    op.create_index(op.f("ix_mobile_captures_document_id"), "mobile_captures", ["document_id"], unique=False)
    op.create_index(op.f("ix_mobile_captures_job_id"), "mobile_captures", ["job_id"], unique=False)
    op.create_index(op.f("ix_mobile_captures_mobile_capture_id"), "mobile_captures", ["mobile_capture_id"], unique=False)
    op.create_index(op.f("ix_mobile_captures_paired_device_id"), "mobile_captures", ["paired_device_id"], unique=False)
    op.create_index(op.f("ix_mobile_captures_sha256"), "mobile_captures", ["sha256"], unique=False)
    op.create_index(op.f("ix_mobile_captures_status"), "mobile_captures", ["status"], unique=False)
    op.create_index("ux_mobile_captures_device_capture", "mobile_captures", ["paired_device_id", "mobile_capture_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ux_mobile_captures_device_capture", table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_status"), table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_sha256"), table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_paired_device_id"), table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_mobile_capture_id"), table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_job_id"), table_name="mobile_captures")
    op.drop_index(op.f("ix_mobile_captures_document_id"), table_name="mobile_captures")
    op.drop_table("mobile_captures")
    op.drop_index("ux_mobile_paired_devices_desktop_device", table_name="mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_paired_devices_user_id"), table_name="mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_paired_devices_revoked_at"), table_name="mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_paired_devices_platform"), table_name="mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_paired_devices_device_id"), table_name="mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_paired_devices_desktop_id"), table_name="mobile_paired_devices")
    op.drop_table("mobile_paired_devices")
    op.drop_index(op.f("ix_mobile_pairing_sessions_status"), table_name="mobile_pairing_sessions")
    op.drop_index(op.f("ix_mobile_pairing_sessions_expires_at"), table_name="mobile_pairing_sessions")
    op.drop_index(op.f("ix_mobile_pairing_sessions_created_by_user_id"), table_name="mobile_pairing_sessions")
    op.drop_index(op.f("ix_mobile_pairing_sessions_desktop_id"), table_name="mobile_pairing_sessions")
    op.drop_table("mobile_pairing_sessions")
