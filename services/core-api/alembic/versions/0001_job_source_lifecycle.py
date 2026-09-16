"""job source lifecycle columns

Revision ID: 0001_job_source_lifecycle
Revises:
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_job_source_lifecycle"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("job_sources") as batch:
        batch.add_column(sa.Column("record_hash", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE")
        )
    op.create_index("ix_job_sources_status", "job_sources", ["status"])

    # Records imported before the stable-identity change used a whole-record
    # JSON hash as source_record_key. Backfill status so nothing is stranded.
    op.execute("UPDATE job_sources SET status = 'ACTIVE' WHERE status IS NULL OR status = ''")


def downgrade() -> None:
    op.drop_index("ix_job_sources_status", table_name="job_sources")
    with op.batch_alter_table("job_sources") as batch:
        batch.drop_column("status")
        batch.drop_column("record_hash")
