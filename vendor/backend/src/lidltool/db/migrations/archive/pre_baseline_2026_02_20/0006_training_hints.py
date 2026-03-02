"""add training hints table for OCR correction feedback

Revision ID: 0006_training_hints
Revises: 0005_review_queue_state
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_training_hints"
down_revision = "0005_review_queue_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_hints",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("transaction_id", sa.String(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column(
            "transaction_item_id",
            sa.String(),
            sa.ForeignKey("transaction_items.id"),
            nullable=True,
        ),
        sa.Column("hint_type", sa.String(), nullable=False),
        sa.Column("field_path", sa.String(), nullable=False),
        sa.Column("original_value", sa.Text(), nullable=True),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_training_hints_document_id", "training_hints", ["document_id"])
    op.create_index("ix_training_hints_transaction_id", "training_hints", ["transaction_id"])
    op.create_index(
        "ix_training_hints_transaction_item_id", "training_hints", ["transaction_item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_training_hints_transaction_item_id", table_name="training_hints")
    op.drop_index("ix_training_hints_transaction_id", table_name="training_hints")
    op.drop_index("ix_training_hints_document_id", table_name="training_hints")
    op.drop_table("training_hints")
