"""add monthly budget and cashflow tables

Revision ID: 0018_monthly_budget_cashflow
Revises: 0017_transaction_item_categorization
Create Date: 2026-03-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_monthly_budget_cashflow"
down_revision = "0017_transaction_item_categorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("budget_rules", sa.Column("user_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_budget_rules_user_id"), "budget_rules", ["user_id"], unique=False)
    op.create_index(
        "ix_budget_rules_user_active",
        "budget_rules",
        ["user_id", "active"],
        unique=False,
    )

    op.create_table(
        "budget_months",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("planned_income_cents", sa.Integer(), nullable=True),
        sa.Column("target_savings_cents", sa.Integer(), nullable=True),
        sa.Column("opening_balance_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budget_months_user_id"), "budget_months", ["user_id"], unique=False)
    op.create_index(op.f("ix_budget_months_year"), "budget_months", ["year"], unique=False)
    op.create_index(op.f("ix_budget_months_month"), "budget_months", ["month"], unique=False)
    op.create_index(
        "ux_budget_months_user_period",
        "budget_months",
        ["user_id", "year", "month"],
        unique=True,
    )

    op.create_table(
        "cashflow_entries",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("linked_transaction_id", sa.String(), nullable=True),
        sa.Column("linked_recurring_occurrence_id", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["linked_recurring_occurrence_id"], ["recurring_bill_occurrences.id"]),
        sa.ForeignKeyConstraint(["linked_transaction_id"], ["transactions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cashflow_entries_user_id"), "cashflow_entries", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_cashflow_entries_effective_date"),
        "cashflow_entries",
        ["effective_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_entries_direction"),
        "cashflow_entries",
        ["direction"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_entries_linked_transaction_id"),
        "cashflow_entries",
        ["linked_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cashflow_entries_linked_recurring_occurrence_id"),
        "cashflow_entries",
        ["linked_recurring_occurrence_id"],
        unique=False,
    )
    op.create_index(
        "ix_cashflow_entries_user_date",
        "cashflow_entries",
        ["user_id", "effective_date"],
        unique=False,
    )
    op.create_index(
        "ix_cashflow_entries_user_direction",
        "cashflow_entries",
        ["user_id", "direction"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cashflow_entries_user_direction", table_name="cashflow_entries")
    op.drop_index("ix_cashflow_entries_user_date", table_name="cashflow_entries")
    op.drop_index(
        op.f("ix_cashflow_entries_linked_recurring_occurrence_id"),
        table_name="cashflow_entries",
    )
    op.drop_index(op.f("ix_cashflow_entries_linked_transaction_id"), table_name="cashflow_entries")
    op.drop_index(op.f("ix_cashflow_entries_direction"), table_name="cashflow_entries")
    op.drop_index(op.f("ix_cashflow_entries_effective_date"), table_name="cashflow_entries")
    op.drop_index(op.f("ix_cashflow_entries_user_id"), table_name="cashflow_entries")
    op.drop_table("cashflow_entries")

    op.drop_index("ux_budget_months_user_period", table_name="budget_months")
    op.drop_index(op.f("ix_budget_months_month"), table_name="budget_months")
    op.drop_index(op.f("ix_budget_months_year"), table_name="budget_months")
    op.drop_index(op.f("ix_budget_months_user_id"), table_name="budget_months")
    op.drop_table("budget_months")

    op.drop_index("ix_budget_rules_user_active", table_name="budget_rules")
    op.drop_index(op.f("ix_budget_rules_user_id"), table_name="budget_rules")
    op.drop_column("budget_rules", "user_id")
