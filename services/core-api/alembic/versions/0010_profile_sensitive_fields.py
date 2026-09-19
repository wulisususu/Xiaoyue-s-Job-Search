"""profile sensitive field secret references

Revision ID: 0010_profile_sensitive_fields
Revises: 0009_ai_extraction_runs
Create Date: 2026-09-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_profile_sensitive_fields"
down_revision = "0009_ai_extraction_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("profile_fields") as batch:
        batch.add_column(sa.Column("secret_ref", sa.String(length=240), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("profile_fields") as batch:
        batch.drop_column("secret_ref")
