"""create briefs table

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "briefs",
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
        sa.Column("since_last_visit", sa.Text(), nullable=False),
        sa.Column("flags", postgresql.JSONB(), nullable=False),
        sa.Column("suggested_focus", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_briefs_patient_id", "briefs", ["patient_id"])
    op.create_index("ix_briefs_therapist_id", "briefs", ["therapist_id"])


def downgrade() -> None:
    op.drop_index("ix_briefs_therapist_id", table_name="briefs")
    op.drop_index("ix_briefs_patient_id", table_name="briefs")
    op.drop_table("briefs")
