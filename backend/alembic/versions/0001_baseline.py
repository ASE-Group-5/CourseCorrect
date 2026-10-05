"""Baseline (empty) migration.

Creates no application tables. Running it creates Alembic's own
`alembic_version` table, which proves the migration pipeline is wired up.

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
