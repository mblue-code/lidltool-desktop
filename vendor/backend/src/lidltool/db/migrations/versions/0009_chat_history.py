"""add chat history persistence tables

Revision ID: 0009_chat_history
Revises: 0008_product_fts5
Create Date: 2026-02-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_chat_history"
down_revision = "0008_product_fts5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column(
            "stream_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'idle'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("thread_id"),
    )
    op.create_index(op.f("ix_chat_threads_user_id"), "chat_threads", ["user_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("tool_call_id", sa.String(), nullable=True),
        sa.Column("usage_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.thread_id"]),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(op.f("ix_chat_messages_thread_id"), "chat_messages", ["thread_id"], unique=False)
    op.create_index(
        "ix_chat_messages_thread_created",
        "chat_messages",
        ["thread_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_chat_messages_thread_message",
        "chat_messages",
        ["thread_id", "message_id"],
        unique=False,
    )

    op.create_table(
        "chat_runs",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.message_id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.thread_id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_chat_runs_thread_id"), "chat_runs", ["thread_id"], unique=False)
    op.create_index(op.f("ix_chat_runs_message_id"), "chat_runs", ["message_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_runs_message_id"), table_name="chat_runs")
    op.drop_index(op.f("ix_chat_runs_thread_id"), table_name="chat_runs")
    op.drop_table("chat_runs")

    op.drop_index("ix_chat_messages_thread_message", table_name="chat_messages")
    op.drop_index("ix_chat_messages_thread_created", table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_thread_id"), table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index(op.f("ix_chat_threads_user_id"), table_name="chat_threads")
    op.drop_table("chat_threads")
