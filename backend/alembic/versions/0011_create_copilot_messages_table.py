"""create copilot messages table

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "copilot_messages",
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
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('therapist', 'assistant')", name="ck_copilot_messages_role"
        ),
    )
    op.create_index("ix_copilot_messages_patient_id", "copilot_messages", ["patient_id"])
    op.create_index("ix_copilot_messages_therapist_id", "copilot_messages", ["therapist_id"])
    op.create_index("ix_copilot_messages_posted_at", "copilot_messages", ["posted_at"])


def downgrade() -> None:
    op.drop_index("ix_copilot_messages_posted_at", table_name="copilot_messages")
    op.drop_index("ix_copilot_messages_therapist_id", table_name="copilot_messages")
    op.drop_index("ix_copilot_messages_patient_id", table_name="copilot_messages")
    op.drop_table("copilot_messages")
