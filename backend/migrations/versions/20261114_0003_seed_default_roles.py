"""Seed the default application roles during deployment.

Revision ID: 20261114_0003
Revises: 20261109_0002
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20261114_0003"
down_revision = "20261109_0002"
branch_labels = None
depends_on = None

DEFAULT_ROLES = [
    "Super Admin", "Management", "Sales / Business Development",
    "Internship Coordinator", "Training Coordinator", "Finance / Accounts",
    "Marketing Executive", "Project / Team Manager", "Employee / Intern", "Trainer / Teacher",
]


def upgrade() -> None:
    bind = op.get_bind()
    roles = sa.table("roles", sa.column("name", sa.String(length=60)))
    existing_roles = set(bind.execute(sa.select(roles.c.name)).scalars())
    missing_roles = [name for name in DEFAULT_ROLES if name not in existing_roles]
    if missing_roles:
        op.bulk_insert(roles, [{"name": name} for name in missing_roles])


def downgrade() -> None:
    # Roles may already be assigned to users; preserve them on downgrade.
    pass
