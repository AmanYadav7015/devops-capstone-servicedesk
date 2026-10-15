"""seed the default service desk categories

Revision ID: 0002_seed
Revises: 0001_schema
Create Date: 2026-10-15 16:58:02.114903

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_seed"
down_revision: str | None = "0001_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_CATEGORIES = [
    ("Hardware", "Laptops, docking stations, peripherals and on-site equipment"),
    ("Network", "VPN, Wi-Fi, firewall rules and connectivity incidents"),
    ("Access", "Account provisioning, password resets and permission requests"),
    ("Software", "Application installs, licence keys and upgrade requests"),
]

categories = sa.table(
    "categories",
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
)


def upgrade() -> None:
    op.bulk_insert(
        categories,
        [{"name": name, "description": description} for name, description in DEFAULT_CATEGORIES],
    )


def downgrade() -> None:
    names = tuple(name for name, _ in DEFAULT_CATEGORIES)
    op.execute(
        sa.delete(categories).where(sa.column("name", sa.String).in_(names))
    )
