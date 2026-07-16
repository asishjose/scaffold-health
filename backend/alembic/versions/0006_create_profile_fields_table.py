"""create profile fields table

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_fields",
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
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=True,
        ),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_contradiction", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_profile_fields_patient_id", "profile_fields", ["patient_id"])
    op.create_index("ix_profile_fields_therapist_id", "profile_fields", ["therapist_id"])
    op.create_index("ix_profile_fields_field_name", "profile_fields", ["field_name"])


def downgrade() -> None:
    op.drop_index("ix_profile_fields_field_name", table_name="profile_fields")
    op.drop_index("ix_profile_fields_therapist_id", table_name="profile_fields")
    op.drop_index("ix_profile_fields_patient_id", table_name="profile_fields")
    op.drop_table("profile_fields")
