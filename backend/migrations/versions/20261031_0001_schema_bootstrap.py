"""Bootstrap the current ORM schema.

Revision ID: 20261031_0001
Revises:
Create Date: 2026-10-31

This first revision adopts databases that were previously initialized with
SQLAlchemy create_all and creates missing tables on fresh installations. Keep
this revision immutable; subsequent schema changes belong in new revisions.
"""
from alembic import op

from app import models  # noqa: F401 - register all ORM tables on Base.metadata
from app.database import Base

revision = "20261031_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The baseline is intentionally additive and safe for existing databases.
    # Later revisions should use explicit Alembic operations and remain static.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # A baseline downgrade could drop user data; preserve tables and records.
    pass
