"""Scope calendar sync history to the verified Google account and calendar.

Revision ID: b6c1_calendar_account_scope
Revises: 9f2e_calendar_oauth_sync
"""

import sqlalchemy as sa
from alembic import op

revision = "b6c1_calendar_account_scope"
down_revision = "9f2e_calendar_oauth_sync"
branch_labels = None
depends_on = None

SYNC_TABLE = "calendar_event_syncs"
ACCOUNT_CONSTRAINT = "uq_calendar_event_syncs_account_calendar_event"
LEGACY_CONSTRAINT = "uq_calendar_event_syncs_calendar_link_id_event_key"
NAMING_CONVENTION = {
    "uq": "uq_%(table_name)s_%(column_0_name)s_%(column_1_name)s"
}


def upgrade() -> None:
    op.add_column(
        "calendar_links",
        sa.Column("google_account_fingerprint", sa.String(length=64)),
    )

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(
            SYNC_TABLE, naming_convention=NAMING_CONVENTION
        ) as batch:
            batch.drop_constraint(LEGACY_CONSTRAINT, type_="unique")
            batch.add_column(
                sa.Column("google_account_fingerprint", sa.String(length=64))
            )
            batch.add_column(sa.Column("calendar_id", sa.String(length=255)))
            batch.create_unique_constraint(
                ACCOUNT_CONSTRAINT,
                [
                    "calendar_link_id",
                    "google_account_fingerprint",
                    "calendar_id",
                    "event_key",
                ],
            )
        return

    old_constraint = next(
        constraint
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints(
            SYNC_TABLE
        )
        if set(constraint["column_names"]) == {"calendar_link_id", "event_key"}
    )
    op.drop_constraint(old_constraint["name"], SYNC_TABLE, type_="unique")
    op.add_column(
        SYNC_TABLE,
        sa.Column("google_account_fingerprint", sa.String(length=64)),
    )
    op.add_column(SYNC_TABLE, sa.Column("calendar_id", sa.String(length=255)))
    op.create_unique_constraint(
        ACCOUNT_CONSTRAINT,
        SYNC_TABLE,
        [
            "calendar_link_id",
            "google_account_fingerprint",
            "calendar_id",
            "event_key",
        ],
    )


def downgrade() -> None:
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT calendar_link_id, event_key FROM calendar_event_syncs "
                "GROUP BY calendar_link_id, event_key HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    if duplicate:
        raise RuntimeError(
            "Cannot downgrade account-scoped sync rows with duplicate legacy keys"
        )

    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(
            SYNC_TABLE, naming_convention=NAMING_CONVENTION
        ) as batch:
            batch.drop_constraint(ACCOUNT_CONSTRAINT, type_="unique")
            batch.drop_column("google_account_fingerprint")
            batch.drop_column("calendar_id")
            batch.create_unique_constraint(
                LEGACY_CONSTRAINT, ["calendar_link_id", "event_key"]
            )
    else:
        op.drop_constraint(ACCOUNT_CONSTRAINT, SYNC_TABLE, type_="unique")
        op.drop_column(SYNC_TABLE, "google_account_fingerprint")
        op.drop_column(SYNC_TABLE, "calendar_id")
        op.create_unique_constraint(
            LEGACY_CONSTRAINT,
            SYNC_TABLE,
            ["calendar_link_id", "event_key"],
        )

    op.drop_column("calendar_links", "google_account_fingerprint")
