"""add ingestion agent proposal tables

Revision ID: 0028_ingestion_agent
Revises: 0027_mobile_pairing_sync
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_ingestion_agent"
down_revision = "0027_mobile_pairing_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("shared_group_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("input_kind", sa.String(), nullable=False),
        sa.Column("approval_mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shared_group_id"], ["shared_groups.group_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_sessions_created_at"), "ingestion_sessions", ["created_at"], unique=False)
    op.create_index(op.f("ix_ingestion_sessions_input_kind"), "ingestion_sessions", ["input_kind"], unique=False)
    op.create_index(op.f("ix_ingestion_sessions_shared_group_id"), "ingestion_sessions", ["shared_group_id"], unique=False)
    op.create_index(op.f("ix_ingestion_sessions_status"), "ingestion_sessions", ["status"], unique=False)
    op.create_index(op.f("ix_ingestion_sessions_user_id"), "ingestion_sessions", ["user_id"], unique=False)
    op.create_index("ix_ingestion_sessions_user_status", "ingestion_sessions", ["user_id", "status"], unique=False)

    op.create_table(
        "ingestion_agent_settings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("shared_group_id", sa.String(), nullable=True),
        sa.Column("approval_mode", sa.String(), nullable=False),
        sa.Column("auto_commit_confidence_threshold", sa.Float(), nullable=False),
        sa.Column("auto_link_confidence_threshold", sa.Float(), nullable=False),
        sa.Column("auto_ignore_confidence_threshold", sa.Float(), nullable=False),
        sa.Column("auto_create_recurring_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["shared_group_id"], ["shared_groups.group_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_agent_settings_shared_group_id"), "ingestion_agent_settings", ["shared_group_id"], unique=False)
    op.create_index(op.f("ix_ingestion_agent_settings_user_id"), "ingestion_agent_settings", ["user_id"], unique=False)
    op.create_index("ux_ingestion_agent_settings_scope", "ingestion_agent_settings", ["user_id", "shared_group_id"], unique=True)

    op.create_table(
        "ingestion_files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("file_name", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["ingestion_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_files_session_id"), "ingestion_files", ["session_id"], unique=False)
    op.create_index(op.f("ix_ingestion_files_sha256"), "ingestion_files", ["sha256"], unique=False)
    op.create_index("ix_ingestion_files_session_sha", "ingestion_files", ["session_id", "sha256"], unique=False)

    op.create_table(
        "statement_rows",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payee", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["ingestion_files.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["ingestion_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_statement_rows_amount_cents"), "statement_rows", ["amount_cents"], unique=False)
    op.create_index(op.f("ix_statement_rows_file_id"), "statement_rows", ["file_id"], unique=False)
    op.create_index(op.f("ix_statement_rows_occurred_at"), "statement_rows", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_statement_rows_row_hash"), "statement_rows", ["row_hash"], unique=False)
    op.create_index(op.f("ix_statement_rows_session_id"), "statement_rows", ["session_id"], unique=False)
    op.create_index(op.f("ix_statement_rows_status"), "statement_rows", ["status"], unique=False)
    op.create_index("ux_statement_rows_session_hash", "statement_rows", ["session_id", "row_hash"], unique=True)

    op.create_table(
        "ingestion_proposals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("statement_row_id", sa.String(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("model_metadata_json", sa.JSON(), nullable=True),
        sa.Column("commit_result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["ingestion_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["statement_row_id"], ["statement_rows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_proposals_created_at"), "ingestion_proposals", ["created_at"], unique=False)
    op.create_index(op.f("ix_ingestion_proposals_session_id"), "ingestion_proposals", ["session_id"], unique=False)
    op.create_index(op.f("ix_ingestion_proposals_statement_row_id"), "ingestion_proposals", ["statement_row_id"], unique=False)
    op.create_index(op.f("ix_ingestion_proposals_status"), "ingestion_proposals", ["status"], unique=False)
    op.create_index(op.f("ix_ingestion_proposals_type"), "ingestion_proposals", ["type"], unique=False)
    op.create_index("ix_ingestion_proposals_session_status", "ingestion_proposals", ["session_id", "status"], unique=False)
    op.create_index("ix_ingestion_proposals_session_type", "ingestion_proposals", ["session_id", "type"], unique=False)

    op.create_table(
        "ingestion_proposal_matches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("proposal_id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column("score", sa.Numeric(4, 3), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["ingestion_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingestion_proposal_matches_proposal_id"), "ingestion_proposal_matches", ["proposal_id"], unique=False)
    op.create_index(op.f("ix_ingestion_proposal_matches_transaction_id"), "ingestion_proposal_matches", ["transaction_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_proposal_matches_transaction_id"), table_name="ingestion_proposal_matches")
    op.drop_index(op.f("ix_ingestion_proposal_matches_proposal_id"), table_name="ingestion_proposal_matches")
    op.drop_table("ingestion_proposal_matches")
    op.drop_index("ix_ingestion_proposals_session_type", table_name="ingestion_proposals")
    op.drop_index("ix_ingestion_proposals_session_status", table_name="ingestion_proposals")
    op.drop_index(op.f("ix_ingestion_proposals_type"), table_name="ingestion_proposals")
    op.drop_index(op.f("ix_ingestion_proposals_status"), table_name="ingestion_proposals")
    op.drop_index(op.f("ix_ingestion_proposals_statement_row_id"), table_name="ingestion_proposals")
    op.drop_index(op.f("ix_ingestion_proposals_session_id"), table_name="ingestion_proposals")
    op.drop_index(op.f("ix_ingestion_proposals_created_at"), table_name="ingestion_proposals")
    op.drop_table("ingestion_proposals")
    op.drop_index("ux_statement_rows_session_hash", table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_status"), table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_session_id"), table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_row_hash"), table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_occurred_at"), table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_file_id"), table_name="statement_rows")
    op.drop_index(op.f("ix_statement_rows_amount_cents"), table_name="statement_rows")
    op.drop_table("statement_rows")
    op.drop_index("ix_ingestion_files_session_sha", table_name="ingestion_files")
    op.drop_index(op.f("ix_ingestion_files_sha256"), table_name="ingestion_files")
    op.drop_index(op.f("ix_ingestion_files_session_id"), table_name="ingestion_files")
    op.drop_table("ingestion_files")
    op.drop_index("ix_ingestion_sessions_user_status", table_name="ingestion_sessions")
    op.drop_index("ux_ingestion_agent_settings_scope", table_name="ingestion_agent_settings")
    op.drop_index(op.f("ix_ingestion_agent_settings_user_id"), table_name="ingestion_agent_settings")
    op.drop_index(op.f("ix_ingestion_agent_settings_shared_group_id"), table_name="ingestion_agent_settings")
    op.drop_table("ingestion_agent_settings")
    op.drop_index(op.f("ix_ingestion_sessions_user_id"), table_name="ingestion_sessions")
    op.drop_index(op.f("ix_ingestion_sessions_status"), table_name="ingestion_sessions")
    op.drop_index(op.f("ix_ingestion_sessions_shared_group_id"), table_name="ingestion_sessions")
    op.drop_index(op.f("ix_ingestion_sessions_input_kind"), table_name="ingestion_sessions")
    op.drop_index(op.f("ix_ingestion_sessions_created_at"), table_name="ingestion_sessions")
    op.drop_table("ingestion_sessions")
