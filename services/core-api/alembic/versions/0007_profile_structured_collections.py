"""profile structured collections

Revision ID: 0007_profile_structured_collections
Revises: 0006_job_next_verification_at
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_profile_structured_collections"
down_revision = "0006_job_next_verification_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "profile_collection_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profile_collection_items_kind", "profile_collection_items", ["kind"])
    op.create_index("ix_profile_collection_items_confirmed", "profile_collection_items", ["confirmed"])
    op.create_index(
        "ix_profile_collection_items_kind_position",
        "profile_collection_items",
        ["kind", "position", "id"],
    )

    op.create_table(
        "profile_collection_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("profile_collection_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("old_payload_json", sa.Text(), nullable=True),
        sa.Column("new_payload_json", sa.Text(), nullable=True),
        sa.Column("old_position", sa.Integer(), nullable=True),
        sa.Column("new_position", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profile_collection_revisions_item_id", "profile_collection_revisions", ["item_id"])
    op.create_index("ix_profile_collection_revisions_kind", "profile_collection_revisions", ["kind"])
    op.create_index("ix_profile_collection_revisions_changed_at", "profile_collection_revisions", ["changed_at"])


def downgrade() -> None:
    op.drop_index("ix_profile_collection_revisions_changed_at", table_name="profile_collection_revisions")
    op.drop_index("ix_profile_collection_revisions_kind", table_name="profile_collection_revisions")
    op.drop_index("ix_profile_collection_revisions_item_id", table_name="profile_collection_revisions")
    op.drop_table("profile_collection_revisions")

    op.drop_index("ix_profile_collection_items_kind_position", table_name="profile_collection_items")
    op.drop_index("ix_profile_collection_items_confirmed", table_name="profile_collection_items")
    op.drop_index("ix_profile_collection_items_kind", table_name="profile_collection_items")
    op.drop_table("profile_collection_items")
