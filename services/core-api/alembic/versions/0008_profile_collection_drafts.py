"""profile collection drafts

Revision ID: 0008_profile_collection_drafts
Revises: 0007_profile_structured_collections
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_profile_collection_drafts"
down_revision = "0007_profile_structured_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_collection_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resume_version_id",
            sa.String(length=32),
            sa.ForeignKey("resume_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_profile_collection_drafts_resume_version_id",
        "profile_collection_drafts",
        ["resume_version_id"],
    )
    op.create_index("ix_profile_collection_drafts_kind", "profile_collection_drafts", ["kind"])
    op.create_index("ix_profile_collection_drafts_status", "profile_collection_drafts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_profile_collection_drafts_status", table_name="profile_collection_drafts")
    op.drop_index("ix_profile_collection_drafts_kind", table_name="profile_collection_drafts")
    op.drop_index("ix_profile_collection_drafts_resume_version_id", table_name="profile_collection_drafts")
    op.drop_table("profile_collection_drafts")
