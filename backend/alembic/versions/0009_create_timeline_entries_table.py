"""create timeline entries table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timeline_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id"),
            nullable=False,
        ),
        sa.Column(
            "therapist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("therapists.id"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entry_type IN ('phase_advance', 'milestone', 'document_extracted')",
            name="ck_timeline_entries_entry_type",
        ),
    )
    op.create_index("ix_timeline_entries_patient_id", "timeline_entries", ["patient_id"])
    op.create_index("ix_timeline_entries_therapist_id", "timeline_entries", ["therapist_id"])
    op.create_index("ix_timeline_entries_entry_type", "timeline_entries", ["entry_type"])
    op.create_index("ix_timeline_entries_occurred_at", "timeline_entries", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_timeline_entries_occurred_at", table_name="timeline_entries")
    op.drop_index("ix_timeline_entries_entry_type", table_name="timeline_entries")
    op.drop_index("ix_timeline_entries_therapist_id", table_name="timeline_entries")
    op.drop_index("ix_timeline_entries_patient_id", table_name="timeline_entries")
    op.drop_table("timeline_entries")
