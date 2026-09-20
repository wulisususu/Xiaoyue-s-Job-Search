"""application CRM event timeline and resume linkage

Revision ID: 0011_application_crm_events
Revises: 0010_profile_sensitive_fields
Create Date: 2026-09-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_application_crm_events"
down_revision = "0010_profile_sensitive_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_sessions") as batch:
        batch.add_column(sa.Column("resume_version_id", sa.String(length=32), nullable=True))
        batch.create_foreign_key(
            "fk_application_sessions_resume_version_id",
            "resume_versions",
            ["resume_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_application_sessions_resume_version_id",
        "application_sessions",
        ["resume_version_id"],
    )

    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("application_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=40), nullable=True),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_application_events_application_id", "application_events", ["application_id"])
    op.create_index("ix_application_events_event_type", "application_events", ["event_type"])
    op.create_index("ix_application_events_to_status", "application_events", ["to_status"])
    op.create_index("ix_application_events_created_at", "application_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_application_events_created_at", table_name="application_events")
    op.drop_index("ix_application_events_to_status", table_name="application_events")
    op.drop_index("ix_application_events_event_type", table_name="application_events")
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")

    op.drop_index("ix_application_sessions_resume_version_id", table_name="application_sessions")
    with op.batch_alter_table("application_sessions") as batch:
        batch.drop_constraint("fk_application_sessions_resume_version_id", type_="foreignkey")
        batch.drop_column("resume_version_id")
