"""create events table

Revision ID: 0001
Revises:
Create Date: 2026-07-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stream_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_type", sa.String(length=64), nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("stream_id", "stream_version", name="uq_events_stream_version"),
        sa.UniqueConstraint("idempotency_key", name="uq_events_idempotency_key"),
    )
    op.create_index("ix_events_stream_id", "events", ["stream_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])

    # Append-only enforcement at the database level, not just app convention:
    # once written, an event row can never be changed or removed.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_event_mutation() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'events table is append-only: % is not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER events_no_update
        BEFORE UPDATE ON events
        FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER events_no_delete
        BEFORE DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();
        """
    )
    # Row-level triggers never fire for TRUNCATE, so it needs its own
    # statement-level trigger to keep the table truly append-only.
    op.execute(
        """
        CREATE TRIGGER events_no_truncate
        BEFORE TRUNCATE ON events
        FOR EACH STATEMENT EXECUTE FUNCTION prevent_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS events_no_truncate ON events")
    op.execute("DROP TRIGGER IF EXISTS events_no_delete ON events")
    op.execute("DROP TRIGGER IF EXISTS events_no_update ON events")
    op.execute("DROP FUNCTION IF EXISTS prevent_event_mutation")
    op.drop_index("ix_events_event_type", table_name="events")
    op.drop_index("ix_events_stream_id", table_name="events")
    op.drop_table("events")
