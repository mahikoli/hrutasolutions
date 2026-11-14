"""Promote the explicitly designated first Author account.

Revision ID: 20261114_0005
Revises: 20261114_0004
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20261114_0005"
down_revision = "20261114_0004"
branch_labels = None
depends_on = None

PRIMARY_AUTHOR_EMAIL = "kolip1356@gmail.com"


def upgrade() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("email", sa.String()),
        sa.column("account_type", sa.String()),
    )
    roles = sa.table(
        "roles",
        sa.column("id", sa.Integer()),
        sa.column("name", sa.String()),
    )
    user_roles = sa.table(
        "user_roles",
        sa.column("user_id", sa.Integer()),
        sa.column("role_id", sa.Integer()),
    )

    author_id = bind.execute(
        sa.select(users.c.id).where(sa.func.lower(users.c.email) == PRIMARY_AUTHOR_EMAIL)
    ).scalar_one_or_none()
    if author_id is None:
        return

    bind.execute(sa.update(users).where(users.c.id == author_id).values(account_type="author"))
    super_admin_id = bind.execute(
        sa.select(roles.c.id).where(roles.c.name == "Super Admin")
    ).scalar_one_or_none()
    if super_admin_id is None:
        op.bulk_insert(roles, [{"name": "Super Admin"}])
        super_admin_id = bind.execute(
            sa.select(roles.c.id).where(roles.c.name == "Super Admin")
        ).scalar_one()

    link_exists = bind.execute(
        sa.select(user_roles.c.user_id).where(
            user_roles.c.user_id == author_id,
            user_roles.c.role_id == super_admin_id,
        )
    ).first()
    if not link_exists:
        op.bulk_insert(user_roles, [{"user_id": author_id, "role_id": super_admin_id}])


def downgrade() -> None:
    # Preserve the primary administrator assignment if the application is rolled back.
    pass
