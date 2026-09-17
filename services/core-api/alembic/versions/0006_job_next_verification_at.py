"""job next_verification_at scheduler column

Revision ID: 0006_job_next_verification_at
Revises: 0005_company_unique_identity
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_job_next_verification_at"
down_revision = "0005_company_unique_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("next_verification_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing rows keep NULL = "due now", which is the safe default: the
    # next verification run will populate the column for every checked job.


def downgrade() -> None:
    op.drop_column("jobs", "next_verification_at")
