"""Add secure calendar OAuth state and event synchronization records.

Revision ID: 9f2e_calendar_oauth_sync
Revises: c4d9a1f07b23
"""

import sqlalchemy as sa
from alembic import op

revision = "9f2e_calendar_oauth_sync"
down_revision = "c4d9a1f07b23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(
        "ix_calendar_oauth_states_user_id",
        "calendar_oauth_states",
        ["user_id"],
    )
    op.create_table(
        "calendar_event_syncs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calendar_link_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("google_event_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["calendar_link_id"], ["calendar_links.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("calendar_link_id", "event_key"),
    )
    op.create_index(
        "ix_calendar_event_syncs_calendar_link_id",
        "calendar_event_syncs",
        ["calendar_link_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calendar_event_syncs_calendar_link_id",
        table_name="calendar_event_syncs",
    )
    op.drop_table("calendar_event_syncs")
    op.drop_index(
        "ix_calendar_oauth_states_user_id",
        table_name="calendar_oauth_states",
    )
    op.drop_table("calendar_oauth_states")
