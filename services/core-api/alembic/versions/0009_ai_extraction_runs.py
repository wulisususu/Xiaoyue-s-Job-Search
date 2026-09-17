"""ai extraction runs and draft linkage

Revision ID: 0009_ai_extraction_runs
Revises: 0008_profile_collection_drafts
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_ai_extraction_runs"
down_revision = "0008_profile_collection_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "resume_version_id",
            sa.String(length=32),
            sa.ForeignKey("resume_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=240), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_ai_extraction_runs_resume_version_id",
        "ai_extraction_runs",
        ["resume_version_id"],
    )
    op.create_index("ix_ai_extraction_runs_status", "ai_extraction_runs", ["status"])

    for table in ("profile_draft_fields", "profile_collection_drafts"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column(
                    "extraction_run_id",
                    sa.Integer(),
                    sa.ForeignKey(
                        "ai_extraction_runs.id",
                        ondelete="SET NULL",
                        name=f"fk_{table}_extraction_run_id",
                    ),
                    nullable=True,
                )
            )
            batch.add_column(sa.Column("candidate_fingerprint", sa.String(length=64), nullable=True))
        op.create_index(
            f"ix_{table}_extraction_run_id",
            table,
            ["extraction_run_id"],
        )
        op.create_index(
            f"uq_{table}_run_fingerprint",
            table,
            ["extraction_run_id", "candidate_fingerprint"],
            unique=True,
            sqlite_where=sa.text("extraction_run_id IS NOT NULL AND candidate_fingerprint IS NOT NULL"),
        )


def downgrade() -> None:
    for table in ("profile_draft_fields", "profile_collection_drafts"):
        op.drop_index(f"uq_{table}_run_fingerprint", table_name=table)
        op.drop_index(f"ix_{table}_extraction_run_id", table_name=table)
        op.drop_column(table, "candidate_fingerprint")
        op.drop_column(table, "extraction_run_id")
    op.drop_index("ix_ai_extraction_runs_status", table_name="ai_extraction_runs")
    op.drop_index("ix_ai_extraction_runs_resume_version_id", table_name="ai_extraction_runs")
    op.drop_table("ai_extraction_runs")
