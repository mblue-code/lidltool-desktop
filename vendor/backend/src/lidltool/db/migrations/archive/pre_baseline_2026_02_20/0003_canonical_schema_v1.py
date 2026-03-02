"""add canonical schema v1 tables (non-destructive)

Revision ID: 0003_canonical_schema_v1
Revises: 0002_item_discounts
Create Date: 2026-02-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_canonical_schema_v1"
down_revision = "0002_item_discounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "source_accounts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("account_ref", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_accounts_source_id", "source_accounts", ["source_id"])

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column(
            "source_account_id",
            sa.String(),
            sa.ForeignKey("source_accounts.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingestion_jobs_source_id", "ingestion_jobs", ["source_id"])
    op.create_index("ix_ingestion_jobs_source_account_id", "ingestion_jobs", ["source_account_id"])
    op.create_index("ix_ingestion_jobs_idempotency_key", "ingestion_jobs", ["idempotency_key"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column(
            "source_account_id",
            sa.String(),
            sa.ForeignKey("source_accounts.id"),
            nullable=True,
        ),
        sa.Column("source_transaction_id", sa.String(), nullable=False),
        sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("total_gross_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("discount_total_cents", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transactions_source_id", "transactions", ["source_id"])
    op.create_index("ix_transactions_source_account_id", "transactions", ["source_account_id"])
    op.create_index(
        "ix_transactions_source_transaction_id", "transactions", ["source_transaction_id"]
    )
    op.create_index("ix_transactions_purchased_at", "transactions", ["purchased_at"])
    op.create_index("ix_transactions_fingerprint", "transactions", ["fingerprint"])

    op.create_table(
        "transaction_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("transaction_id", sa.String(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column("source_item_id", sa.String(), nullable=True),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("unit_price_cents", sa.Integer(), nullable=True),
        sa.Column("line_total_cents", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_transaction_items_transaction_id", "transaction_items", ["transaction_id"])

    op.create_table(
        "discount_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("transaction_id", sa.String(), sa.ForeignKey("transactions.id"), nullable=False),
        sa.Column(
            "transaction_item_id",
            sa.String(),
            sa.ForeignKey("transaction_items.id"),
            nullable=True,
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_discount_code", sa.String(), nullable=True),
        sa.Column("source_label", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subkind", sa.String(), nullable=True),
        sa.Column("funded_by", sa.String(), nullable=False),
        sa.Column("is_loyalty_program", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_discount_events_transaction_id", "discount_events", ["transaction_id"])
    op.create_index(
        "ix_discount_events_transaction_item_id", "discount_events", ["transaction_item_id"]
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("transaction_id", sa.String(), sa.ForeignKey("transactions.id"), nullable=True),
        sa.Column("source_id", sa.String(), sa.ForeignKey("sources.id"), nullable=True),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_transaction_id", "documents", ["transaction_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])

    op.create_table(
        "merchant_aliases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("alias", sa.String(), nullable=False),
        sa.Column("canonical_name", sa.String(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_merchant_aliases_alias", "merchant_aliases", ["alias"])

    op.create_table(
        "normalization_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("rule_type", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("replacement", sa.String(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=True),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("normalization_rules")
    op.drop_index("ix_merchant_aliases_alias", table_name="merchant_aliases")
    op.drop_table("merchant_aliases")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_transaction_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_discount_events_transaction_item_id", table_name="discount_events")
    op.drop_index("ix_discount_events_transaction_id", table_name="discount_events")
    op.drop_table("discount_events")
    op.drop_index("ix_transaction_items_transaction_id", table_name="transaction_items")
    op.drop_table("transaction_items")
    op.drop_index("ix_transactions_fingerprint", table_name="transactions")
    op.drop_index("ix_transactions_purchased_at", table_name="transactions")
    op.drop_index("ix_transactions_source_transaction_id", table_name="transactions")
    op.drop_index("ix_transactions_source_account_id", table_name="transactions")
    op.drop_index("ix_transactions_source_id", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_ingestion_jobs_idempotency_key", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_source_account_id", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_jobs_source_id", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("ix_source_accounts_source_id", table_name="source_accounts")
    op.drop_table("source_accounts")
    op.drop_table("sources")
