"""create categories and tickets tables

Revision ID: 0001_schema
Revises:
Create Date: 2026-10-15 16:51:38.778489

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="categories_pkey"),
        sa.UniqueConstraint("name", name="categories_name_key"),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requester", sa.String(length=120), nullable=False),
        sa.Column("assignee", sa.String(length=120), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name="tickets_category_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id", name="tickets_pkey"),
    )


def downgrade() -> None:
    op.drop_table("tickets")
    op.drop_table("categories")
