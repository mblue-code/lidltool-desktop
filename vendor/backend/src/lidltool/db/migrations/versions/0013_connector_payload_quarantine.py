"""add connector payload quarantine table

Revision ID: 0013_connector_payload_quarantine
Revises: 0012_user_locale_preference
Create Date: 2026-03-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_connector_payload_quarantine"
down_revision = "0012_user_locale_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_payload_quarantine",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_account_id", sa.String(), nullable=True),
        sa.Column("ingestion_job_id", sa.String(), nullable=True),
        sa.Column("plugin_id", sa.String(), nullable=True),
        sa.Column("manifest_version", sa.String(), nullable=True),
        sa.Column("connector_api_version", sa.String(), nullable=True),
        sa.Column("runtime_kind", sa.String(), nullable=True),
        sa.Column("action_name", sa.String(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("review_status", sa.String(), nullable=False),
        sa.Column("source_record_ref", sa.String(), nullable=True),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("runtime_diagnostics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_job_id"], ["ingestion_jobs.id"]),
        sa.ForeignKeyConstraint(["source_account_id"], ["source_accounts.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_action_name"),
        "connector_payload_quarantine",
        ["action_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_created_at"),
        "connector_payload_quarantine",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_ingestion_job_id"),
        "connector_payload_quarantine",
        ["ingestion_job_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_outcome"),
        "connector_payload_quarantine",
        ["outcome"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_plugin_id"),
        "connector_payload_quarantine",
        ["plugin_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_review_status"),
        "connector_payload_quarantine",
        ["review_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_source_account_id"),
        "connector_payload_quarantine",
        ["source_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_source_id"),
        "connector_payload_quarantine",
        ["source_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_payload_quarantine_source_record_ref"),
        "connector_payload_quarantine",
        ["source_record_ref"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_connector_payload_quarantine_source_record_ref"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_source_id"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_source_account_id"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_review_status"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_plugin_id"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_outcome"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_ingestion_job_id"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_created_at"),
        table_name="connector_payload_quarantine",
    )
    op.drop_index(
        op.f("ix_connector_payload_quarantine_action_name"),
        table_name="connector_payload_quarantine",
    )
    op.drop_table("connector_payload_quarantine")
