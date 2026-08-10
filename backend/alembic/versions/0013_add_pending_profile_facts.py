"""add pending_profile_facts table, drop profile_fields contradiction flags

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_profile_facts",
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
        sa.Column(
            "source_document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_quote", sa.Text(), nullable=False),
        sa.Column(
            "is_contradiction", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "is_low_confidence", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("extractor_version", sa.String(length=64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("therapists.id"),
            nullable=True,
        ),
        sa.Column("resolved_value", sa.Text(), nullable=True),
        sa.Column(
            "resulting_profile_field_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profile_fields.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_pending_profile_facts_patient_id", "pending_profile_facts", ["patient_id"]
    )
    op.create_index(
        "ix_pending_profile_facts_therapist_id", "pending_profile_facts", ["therapist_id"]
    )
    op.create_index(
        "ix_pending_profile_facts_source_document_id",
        "pending_profile_facts",
        ["source_document_id"],
    )
    op.create_index(
        "ix_pending_profile_facts_field_name", "pending_profile_facts", ["field_name"]
    )
    op.create_index("ix_pending_profile_facts_status", "pending_profile_facts", ["status"])
    op.create_index(
        "ix_pending_profile_facts_document_field_status",
        "pending_profile_facts",
        ["source_document_id", "field_name", "status"],
    )

    op.drop_column("profile_fields", "is_contradiction")
    op.drop_column("profile_fields", "acknowledged_at")


def downgrade() -> None:
    op.add_column(
        "profile_fields",
        sa.Column(
            "is_contradiction", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "profile_fields",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_index(
        "ix_pending_profile_facts_document_field_status", table_name="pending_profile_facts"
    )
    op.drop_index("ix_pending_profile_facts_status", table_name="pending_profile_facts")
    op.drop_index("ix_pending_profile_facts_field_name", table_name="pending_profile_facts")
    op.drop_index(
        "ix_pending_profile_facts_source_document_id", table_name="pending_profile_facts"
    )
    op.drop_index(
        "ix_pending_profile_facts_therapist_id", table_name="pending_profile_facts"
    )
    op.drop_index("ix_pending_profile_facts_patient_id", table_name="pending_profile_facts")
    op.drop_table("pending_profile_facts")
