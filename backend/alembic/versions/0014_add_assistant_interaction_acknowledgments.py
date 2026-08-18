"""add assistant_interaction_acknowledgments table

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_interaction_acknowledgments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assistant_interaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assistant_interactions.id"),
            nullable=False,
        ),
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
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "acknowledged_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("therapists.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_assistant_interaction_acknowledgments_interaction_id",
        "assistant_interaction_acknowledgments",
        ["assistant_interaction_id"],
        unique=True,
    )
    op.create_index(
        "ix_assistant_interaction_acknowledgments_patient_id",
        "assistant_interaction_acknowledgments",
        ["patient_id"],
    )
    op.create_index(
        "ix_assistant_interaction_acknowledgments_therapist_id",
        "assistant_interaction_acknowledgments",
        ["therapist_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_interaction_acknowledgments_therapist_id",
        table_name="assistant_interaction_acknowledgments",
    )
    op.drop_index(
        "ix_assistant_interaction_acknowledgments_patient_id",
        table_name="assistant_interaction_acknowledgments",
    )
    op.drop_index(
        "ix_assistant_interaction_acknowledgments_interaction_id",
        table_name="assistant_interaction_acknowledgments",
    )
    op.drop_table("assistant_interaction_acknowledgments")
