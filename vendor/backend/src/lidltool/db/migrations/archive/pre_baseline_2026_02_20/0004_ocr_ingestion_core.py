"""add OCR ingestion fields for documents and confidence

Revision ID: 0004_ocr_ingestion_core
Revises: 0003_canonical_schema_v1
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_ocr_ingestion_core"
down_revision = "0003_canonical_schema_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.create_index("ix_transactions_confidence", "transactions", ["confidence"])

    op.add_column("transaction_items", sa.Column("confidence", sa.Numeric(4, 3), nullable=True))
    op.create_index("ix_transaction_items_confidence", "transaction_items", ["confidence"])

    op.add_column("documents", sa.Column("file_name", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("ocr_status", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("ocr_provider", sa.String(), nullable=True))
    op.add_column("documents", sa.Column("ocr_latency_ms", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("ocr_confidence", sa.Numeric(4, 3), nullable=True))
    op.add_column("documents", sa.Column("ocr_fallback_used", sa.Boolean(), nullable=True))
    op.add_column("documents", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column(
        "documents", sa.Column("ocr_processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_documents_ocr_status", "documents", ["ocr_status"])


def downgrade() -> None:
    op.drop_index("ix_documents_ocr_status", table_name="documents")
    op.drop_column("documents", "ocr_processed_at")
    op.drop_column("documents", "ocr_text")
    op.drop_column("documents", "ocr_fallback_used")
    op.drop_column("documents", "ocr_confidence")
    op.drop_column("documents", "ocr_latency_ms")
    op.drop_column("documents", "ocr_provider")
    op.drop_column("documents", "ocr_status")
    op.drop_column("documents", "file_name")

    op.drop_index("ix_transaction_items_confidence", table_name="transaction_items")
    op.drop_column("transaction_items", "confidence")

    op.drop_index("ix_transactions_confidence", table_name="transactions")
    op.drop_column("transactions", "confidence")
