"""create patients table

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "therapist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("therapists.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("injury", sa.String(length=64), nullable=False),
        sa.Column("surgery_date", sa.Date(), nullable=False),
        sa.Column("current_phase", sa.String(length=64), nullable=False),
        sa.Column("invite_token", sa.String(length=255), nullable=False),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invite_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("invite_token", name="uq_patients_invite_token"),
    )
    op.create_index("ix_patients_therapist_id", "patients", ["therapist_id"])
    op.create_index("ix_patients_invite_token", "patients", ["invite_token"])


def downgrade() -> None:
    op.drop_index("ix_patients_invite_token", table_name="patients")
    op.drop_index("ix_patients_therapist_id", table_name="patients")
    op.drop_table("patients")
