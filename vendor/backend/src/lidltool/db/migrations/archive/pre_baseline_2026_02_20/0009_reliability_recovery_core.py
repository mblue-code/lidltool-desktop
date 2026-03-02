"""add reliability and recovery core tables

Revision ID: 0009_reliability_recovery_core
Revises: 0008_automations_mvp
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_reliability_recovery_core"
down_revision = "0008_automations_mvp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "endpoint_metrics",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("route", sa.String(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_endpoint_metrics_route", "endpoint_metrics", ["route"])
    op.create_index("ix_endpoint_metrics_method", "endpoint_metrics", ["method"])
    op.create_index("ix_endpoint_metrics_status_code", "endpoint_metrics", ["status_code"])
    op.create_index("ix_endpoint_metrics_source", "endpoint_metrics", ["source"])
    op.create_index("ix_endpoint_metrics_created_at", "endpoint_metrics", ["created_at"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("incident_key", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incident_events_incident_key", "incident_events", ["incident_key"])
    op.create_index("ix_incident_events_event_type", "incident_events", ["event_type"])
    op.create_index("ix_incident_events_source", "incident_events", ["source"])
    op.create_index("ix_incident_events_created_at", "incident_events", ["created_at"])

    op.create_table(
        "recovery_drill_evidence",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("drill_name", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("rto_target_ms", sa.Integer(), nullable=False),
        sa.Column("rpo_target_minutes", sa.Integer(), nullable=False),
        sa.Column("rto_target_met", sa.Boolean(), nullable=False),
        sa.Column("rpo_target_met", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_recovery_drill_evidence_drill_name",
        "recovery_drill_evidence",
        ["drill_name"],
    )
    op.create_index(
        "ix_recovery_drill_evidence_provider",
        "recovery_drill_evidence",
        ["provider"],
    )
    op.create_index(
        "ix_recovery_drill_evidence_created_at",
        "recovery_drill_evidence",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_recovery_drill_evidence_created_at", table_name="recovery_drill_evidence")
    op.drop_index("ix_recovery_drill_evidence_provider", table_name="recovery_drill_evidence")
    op.drop_index("ix_recovery_drill_evidence_drill_name", table_name="recovery_drill_evidence")
    op.drop_table("recovery_drill_evidence")

    op.drop_index("ix_incident_events_created_at", table_name="incident_events")
    op.drop_index("ix_incident_events_source", table_name="incident_events")
    op.drop_index("ix_incident_events_event_type", table_name="incident_events")
    op.drop_index("ix_incident_events_incident_key", table_name="incident_events")
    op.drop_table("incident_events")

    op.drop_index("ix_endpoint_metrics_created_at", table_name="endpoint_metrics")
    op.drop_index("ix_endpoint_metrics_source", table_name="endpoint_metrics")
    op.drop_index("ix_endpoint_metrics_status_code", table_name="endpoint_metrics")
    op.drop_index("ix_endpoint_metrics_method", table_name="endpoint_metrics")
    op.drop_index("ix_endpoint_metrics_route", table_name="endpoint_metrics")
    op.drop_table("endpoint_metrics")
