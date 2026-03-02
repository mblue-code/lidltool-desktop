"""add review workflow status to documents

Revision ID: 0005_review_queue_state
Revises: 0004_ocr_ingestion_core
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_review_queue_state"
down_revision = "0004_ocr_ingestion_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("review_status", sa.String(), nullable=True))
    op.create_index("ix_documents_review_status", "documents", ["review_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_review_status", table_name="documents")
    op.drop_column("documents", "review_status")
