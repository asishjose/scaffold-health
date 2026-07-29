"""create assistant interactions table

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_interactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("patients.id"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("redirected", sa.Boolean(), nullable=False),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_assistant_interactions_patient_id", "assistant_interactions", ["patient_id"])
    op.create_index("ix_assistant_interactions_asked_at", "assistant_interactions", ["asked_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_interactions_asked_at", table_name="assistant_interactions")
    op.drop_index("ix_assistant_interactions_patient_id", table_name="assistant_interactions")
    op.drop_table("assistant_interactions")
