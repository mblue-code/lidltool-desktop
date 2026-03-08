"""add user locale preference

Revision ID: 0012_user_locale_preference
Revises: 0011_recurring_bills
Create Date: 2026-03-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_user_locale_preference"
down_revision = "0011_recurring_bills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_locale", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "preferred_locale")
