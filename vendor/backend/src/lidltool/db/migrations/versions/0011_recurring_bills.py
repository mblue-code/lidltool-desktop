"""add recurring bills domain tables

Revision ID: 0011_recurring_bills
Revises: 0010_chat_message_idempotency
Create Date: 2026-02-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_recurring_bills"
down_revision = "0010_chat_message_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recurring_bills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("merchant_canonical", sa.String(), nullable=True),
        sa.Column("merchant_alias_pattern", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("frequency", sa.String(), nullable=False),
        sa.Column(
            "interval_value",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("amount_cents", sa.Integer(), nullable=True),
        sa.Column(
            "amount_tolerance_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.1"),
        ),
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default=sa.text("'EUR'"),
        ),
        sa.Column("anchor_date", sa.String(length=10), nullable=False),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recurring_bills_user_id"), "recurring_bills", ["user_id"], unique=False)
    op.create_index(
        "ix_recurring_bills_user_active",
        "recurring_bills",
        ["user_id", "active"],
        unique=False,
    )

    op.create_table(
        "recurring_bill_occurrences",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("bill_id", sa.String(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expected_amount_cents", sa.Integer(), nullable=True),
        sa.Column("actual_amount_cents", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["recurring_bills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_bill_occurrences_bill_id"),
        "recurring_bill_occurrences",
        ["bill_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_bill_occurrences_due_date"),
        "recurring_bill_occurrences",
        ["due_date"],
        unique=False,
    )
    op.create_index(
        "ux_recurring_bill_occurrences_bill_due_date",
        "recurring_bill_occurrences",
        ["bill_id", "due_date"],
        unique=True,
    )

    op.create_table(
        "recurring_bill_matches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("occurrence_id", sa.String(), nullable=False),
        sa.Column("transaction_id", sa.String(), nullable=False),
        sa.Column(
            "match_confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.0"),
        ),
        sa.Column("match_method", sa.String(), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["recurring_bill_occurrences.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recurring_bill_matches_occurrence_id"),
        "recurring_bill_matches",
        ["occurrence_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recurring_bill_matches_transaction_id"),
        "recurring_bill_matches",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ux_recurring_bill_matches_occurrence_transaction",
        "recurring_bill_matches",
        ["occurrence_id", "transaction_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_recurring_bill_matches_occurrence_transaction",
        table_name="recurring_bill_matches",
    )
    op.drop_index(op.f("ix_recurring_bill_matches_transaction_id"), table_name="recurring_bill_matches")
    op.drop_index(op.f("ix_recurring_bill_matches_occurrence_id"), table_name="recurring_bill_matches")
    op.drop_table("recurring_bill_matches")

    op.drop_index(
        "ux_recurring_bill_occurrences_bill_due_date",
        table_name="recurring_bill_occurrences",
    )
    op.drop_index(op.f("ix_recurring_bill_occurrences_due_date"), table_name="recurring_bill_occurrences")
    op.drop_index(op.f("ix_recurring_bill_occurrences_bill_id"), table_name="recurring_bill_occurrences")
    op.drop_table("recurring_bill_occurrences")

    op.drop_index("ix_recurring_bills_user_active", table_name="recurring_bills")
    op.drop_index(op.f("ix_recurring_bills_user_id"), table_name="recurring_bills")
    op.drop_table("recurring_bills")
