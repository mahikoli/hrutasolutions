"""Add an explicit author/employee account type to users.

Revision ID: 20261114_0004
Revises: 20261114_0003
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "20261114_0004"
down_revision = "20261114_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("account_type", sa.String(length=20), server_default="employee", nullable=False),
    )
    op.execute(sa.text("""
        UPDATE users
        SET account_type = 'author'
        WHERE id IN (
            SELECT user_roles.user_id
            FROM user_roles
            JOIN roles ON roles.id = user_roles.role_id
            WHERE roles.name IN ('Super Admin', 'Management')
        )
    """))


def downgrade() -> None:
    op.drop_column("users", "account_type")
