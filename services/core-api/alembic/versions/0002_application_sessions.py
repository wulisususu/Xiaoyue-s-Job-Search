"""application sessions

Revision ID: 0002_application_sessions
Revises: 0001_job_source_lifecycle
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_application_sessions"
down_revision = "0001_job_source_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: create_all-built databases already carry this table.
    inspector = sa.inspect(op.get_bind())
    if "application_sessions" in inspector.get_table_names():
        return
    op.create_table(
        "application_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="OPENED"),
        sa.Column("channel", sa.String(length=40), nullable=False, server_default="manual"),
        sa.Column("opened_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_application_sessions_job_id", "application_sessions", ["job_id"])
    op.create_index("ix_application_sessions_status", "application_sessions", ["status"])
    op.create_index("ix_application_sessions_channel", "application_sessions", ["channel"])


def downgrade() -> None:
    op.drop_index("ix_application_sessions_channel", table_name="application_sessions")
    op.drop_index("ix_application_sessions_status", table_name="application_sessions")
    op.drop_index("ix_application_sessions_job_id", table_name="application_sessions")
    op.drop_table("application_sessions")
