"""add shared-group ownership columns across workspace-scoped domains

Revision ID: 0026_workspace_ownership
Revises: 0025_shared_groups
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_workspace_ownership"
down_revision = "0025_shared_groups"
branch_labels = None
depends_on = None


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def _add_shared_group_column(table_name: str, *, ondelete: str | None = None) -> None:
    op.add_column(table_name, sa.Column("shared_group_id", sa.String(), nullable=True))
    if not _is_sqlite():
        if ondelete is None:
            op.create_foreign_key(
                f"fk_{table_name}_shared_group_id",
                table_name,
                "shared_groups",
                ["shared_group_id"],
                ["group_id"],
            )
        else:
            op.create_foreign_key(
                f"fk_{table_name}_shared_group_id",
                table_name,
                "shared_groups",
                ["shared_group_id"],
                ["group_id"],
                ondelete=ondelete,
            )
    op.create_index(op.f(f"ix_{table_name}_shared_group_id"), table_name, ["shared_group_id"], unique=False)


def upgrade() -> None:
    _add_shared_group_column("chat_threads")
    _add_shared_group_column("sources")
    _add_shared_group_column("transactions")
    _add_shared_group_column("transaction_items")
    _add_shared_group_column("recurring_bills")
    _add_shared_group_column("documents")
    _add_shared_group_column("offer_source_configs", ondelete="SET NULL")
    _add_shared_group_column("product_watchlists")
    _add_shared_group_column("offer_matches")
    _add_shared_group_column("alert_events")
    _add_shared_group_column("offer_refresh_runs")
    op.add_column("saved_queries", sa.Column("user_id", sa.String(), nullable=True))
    if not _is_sqlite():
        op.create_foreign_key(
            "fk_saved_queries_user_id",
            "saved_queries",
            "users",
            ["user_id"],
            ["user_id"],
        )
    op.create_index(op.f("ix_saved_queries_user_id"), "saved_queries", ["user_id"], unique=False)
    _add_shared_group_column("saved_queries")
    _add_shared_group_column("budget_rules")
    _add_shared_group_column("budget_months")
    _add_shared_group_column("cashflow_entries")
    _add_shared_group_column("goals", ondelete="SET NULL")
    _add_shared_group_column("notifications", ondelete="SET NULL")

    op.create_index("ix_recurring_bills_group_active", "recurring_bills", ["shared_group_id", "active"], unique=False)
    op.create_index("ix_budget_rules_group_active", "budget_rules", ["shared_group_id", "active"], unique=False)
    op.create_index("ux_budget_months_group_period", "budget_months", ["shared_group_id", "year", "month"], unique=True)
    op.create_index("ix_cashflow_entries_group_date", "cashflow_entries", ["shared_group_id", "effective_date"], unique=False)
    op.create_index(
        "ix_cashflow_entries_group_direction",
        "cashflow_entries",
        ["shared_group_id", "direction"],
        unique=False,
    )
    op.create_index("ix_goals_group_active", "goals", ["shared_group_id", "active"], unique=False)
    op.create_index("ix_goals_group_type", "goals", ["shared_group_id", "goal_type"], unique=False)
    op.create_index("ix_notifications_group_unread", "notifications", ["shared_group_id", "unread"], unique=False)
    op.create_index(
        "ix_notifications_group_occurred",
        "notifications",
        ["shared_group_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ux_notifications_group_fingerprint",
        "notifications",
        ["shared_group_id", "fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_notifications_group_fingerprint", table_name="notifications")
    op.drop_index("ix_notifications_group_occurred", table_name="notifications")
    op.drop_index("ix_notifications_group_unread", table_name="notifications")
    op.drop_index("ix_goals_group_type", table_name="goals")
    op.drop_index("ix_goals_group_active", table_name="goals")
    op.drop_index("ix_cashflow_entries_group_direction", table_name="cashflow_entries")
    op.drop_index("ix_cashflow_entries_group_date", table_name="cashflow_entries")
    op.drop_index("ux_budget_months_group_period", table_name="budget_months")
    op.drop_index("ix_budget_rules_group_active", table_name="budget_rules")
    op.drop_index("ix_recurring_bills_group_active", table_name="recurring_bills")
    for table_name in (
        "notifications",
        "goals",
        "cashflow_entries",
        "budget_months",
        "budget_rules",
        "saved_queries",
        "offer_refresh_runs",
        "alert_events",
        "offer_matches",
        "product_watchlists",
        "offer_source_configs",
        "documents",
        "recurring_bills",
        "transaction_items",
        "transactions",
        "sources",
        "chat_threads",
    ):
        op.drop_index(op.f(f"ix_{table_name}_shared_group_id"), table_name=table_name)
        if not _is_sqlite():
            op.drop_constraint(f"fk_{table_name}_shared_group_id", table_name, type_="foreignkey")
        op.drop_column(table_name, "shared_group_id")

    op.drop_index(op.f("ix_saved_queries_user_id"), table_name="saved_queries")
    if not _is_sqlite():
        op.drop_constraint("fk_saved_queries_user_id", "saved_queries", type_="foreignkey")
    op.drop_column("saved_queries", "user_id")
