"""add idempotency key to chat messages

Revision ID: 0010_chat_message_idempotency
Revises: 0009_chat_history
Create Date: 2026-02-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_chat_message_idempotency"
down_revision = "0009_chat_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("idempotency_key", sa.String(), nullable=True))
    op.create_index(
        "ux_chat_messages_thread_idempotency",
        "chat_messages",
        ["thread_id", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_chat_messages_thread_idempotency", table_name="chat_messages")
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_column("idempotency_key")
