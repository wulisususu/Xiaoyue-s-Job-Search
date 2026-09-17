"""url candidates for canonical URL promotion

Revision ID: 0004_url_candidates
Revises: 0003_application_sessions
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_url_candidates"
down_revision = "0003_application_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "url_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("source_name", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("verified_health", sa.String(length=50), nullable=True),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", "url", name="uq_url_candidate_job_url"),
    )
    op.create_index("ix_url_candidates_job_id", "url_candidates", ["job_id"])
    op.create_index("ix_url_candidates_status", "url_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_url_candidates_status", table_name="url_candidates")
    op.drop_index("ix_url_candidates_job_id", table_name="url_candidates")
    op.drop_table("url_candidates")
