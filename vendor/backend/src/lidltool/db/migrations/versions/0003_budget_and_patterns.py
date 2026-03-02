"""budget rules foundation for analytics modules

Revision ID: 0003_budget_and_patterns
Revises: 0002_analytics_product_layer
Create Date: 2026-02-20 19:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_budget_and_patterns"
down_revision = "0002_analytics_product_layer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if "budget_rules" not in table_names:
        op.create_table(
            "budget_rules",
            sa.Column("rule_id", sa.String(), nullable=False),
            sa.Column("scope_type", sa.String(), nullable=False),
            sa.Column("scope_value", sa.String(), nullable=False),
            sa.Column("period", sa.String(), nullable=False),
            sa.Column("amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(length=8), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("rule_id"),
        )
        inspector = sa.inspect(bind)
    index_names = {index.get("name") for index in inspector.get_indexes("budget_rules")}
    scope_type_index = op.f("ix_budget_rules_scope_type")
    scope_value_index = op.f("ix_budget_rules_scope_value")
    if scope_type_index not in index_names:
        op.create_index(scope_type_index, "budget_rules", ["scope_type"], unique=False)
    if scope_value_index not in index_names:
        op.create_index(scope_value_index, "budget_rules", ["scope_value"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_budget_rules_scope_value"), table_name="budget_rules")
    op.drop_index(op.f("ix_budget_rules_scope_type"), table_name="budget_rules")
    op.drop_table("budget_rules")
