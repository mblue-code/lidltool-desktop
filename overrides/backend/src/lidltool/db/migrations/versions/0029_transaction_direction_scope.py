"""add transaction direction and ingestion policy metadata

Revision ID: 0029_transaction_direction_scope
Revises: 0028_ingestion_agent
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_transaction_direction_scope"
down_revision = "0028_ingestion_agent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("direction", sa.String(length=16), nullable=False, server_default="outflow"))
        batch.add_column(sa.Column("ledger_scope", sa.String(length=32), nullable=False, server_default="household"))
        batch.add_column(sa.Column("dashboard_include", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index(op.f("ix_transactions_direction"), "transactions", ["direction"], unique=False)
    op.create_index(op.f("ix_transactions_ledger_scope"), "transactions", ["ledger_scope"], unique=False)
    op.create_index(op.f("ix_transactions_dashboard_include"), "transactions", ["dashboard_include"], unique=False)
    with op.batch_alter_table("ingestion_agent_settings") as batch:
        batch.add_column(sa.Column("personal_system_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ingestion_agent_settings") as batch:
        batch.drop_column("personal_system_prompt")
    op.drop_index(op.f("ix_transactions_dashboard_include"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_ledger_scope"), table_name="transactions")
    op.drop_index(op.f("ix_transactions_direction"), table_name="transactions")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("dashboard_include")
        batch.drop_column("ledger_scope")
        batch.drop_column("direction")
