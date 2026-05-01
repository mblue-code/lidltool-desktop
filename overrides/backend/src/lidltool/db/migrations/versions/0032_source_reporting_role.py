"""add source reporting role

Revision ID: 0032_source_reporting_role
Revises: 0031_finance_category_taxonomy_refinements
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_source_reporting_role"
down_revision = "0031_finance_category_taxonomy_refinements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sources")}
    if "reporting_role" not in columns:
        op.add_column(
            "sources",
            sa.Column(
                "reporting_role",
                sa.String(),
                nullable=False,
                server_default="spending_and_cashflow",
            ),
        )
    sources = sa.table(
        "sources",
        sa.column("id", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("reporting_role", sa.String()),
    )
    op.get_bind().execute(
        sources.update()
        .where(sa.func.coalesce(sources.c.reporting_role, "") == "")
        .values(reporting_role="spending_and_cashflow")
    )
    op.get_bind().execute(
        sources.update()
        .where(
            sa.or_(
                sources.c.kind.in_(["connector", "ocr"]),
                sources.c.id.like("amazon_%"),
                sources.c.id.like("lidl_plus_%"),
                sources.c.id.like("rewe_%"),
                sources.c.id.like("penny_%"),
                sources.c.id.like("dm_%"),
                sources.c.id.like("kaufland_%"),
            )
        )
        .where(sources.c.reporting_role == "spending_and_cashflow")
        .values(reporting_role="spending_only")
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("sources")}
    if "reporting_role" in columns:
        op.drop_column("sources", "reporting_role")
