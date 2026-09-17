"""initial schema (pre-lifecycle shape)

This is the true historical starting point: the schema exactly as it existed
before job-source lifecycle columns, application sessions and URL candidates
were introduced. Fresh databases are built by walking the whole chain.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=200), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("ownership", sa.String(length=40), nullable=False, server_default="unknown"),
        sa.Column("province", sa.String(length=80), nullable=True),
        sa.Column("level", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"])
    op.create_index("ix_companies_ownership", "companies", ["ownership"])
    op.create_index("ix_companies_province", "companies", ["province"])
    op.create_index("ix_companies_identity", "companies", ["normalized_name", "ownership"])

    op.create_table(
        "company_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(length=300), nullable=False),
        sa.Column("normalized_alias", sa.String(length=300), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("company_id", "normalized_alias", "source_name", name="uq_company_alias_source"),
    )
    op.create_index("ix_company_aliases_company_id", "company_aliases", ["company_id"])
    op.create_index("ix_company_aliases_normalized_alias", "company_aliases", ["normalized_alias"])

    op.create_table(
        "company_relations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("parent_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=80), nullable=False, server_default="subsidiary"),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.UniqueConstraint("parent_company_id", "child_company_id", "relation_type", name="uq_company_relation"),
    )
    op.create_index("ix_company_relations_parent_company_id", "company_relations", ["parent_company_id"])
    op.create_index("ix_company_relations_child_company_id", "company_relations", ["child_company_id"])

    op.create_table(
        "company_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=300), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.UniqueConstraint("source_name", "source_key", name="uq_company_source_key"),
    )
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=600), nullable=False),
        sa.Column("location", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("industry", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("recruitment_batch", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("deadline_text", sa.String(length=240), nullable=False, server_default=""),
        sa.Column("apply_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("canonical_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("fingerprint", sa.String(length=32), nullable=False),
        sa.Column("source_updated_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])
    op.create_index("ix_jobs_industry", "jobs", ["industry"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_canonical_url", "jobs", ["canonical_url"])
    op.create_index("ix_jobs_fingerprint", "jobs", ["fingerprint"], unique=True)

    op.create_table(
        "job_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("source_record_key", sa.String(length=96), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_name", "source_record_key", name="uq_job_source_record"),
    )
    op.create_index("ix_job_sources_job_id", "job_sources", ["job_id"])

    op.create_table(
        "source_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("remote_version", sa.String(length=160), nullable=True),
        sa.Column("payload_text", sa.Text(), nullable=True),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_name", "content_hash", name="uq_source_snapshot_hash"),
    )
    op.create_index("ix_source_snapshots_source_name", "source_snapshots", ["source_name"])

    op.create_table(
        "source_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("remote_version", sa.String(length=160), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_source_sync_runs_source_name", "source_sync_runs", ["source_name"])
    op.create_index("ix_source_sync_runs_status", "source_sync_runs", ["status"])

    op.create_table(
        "url_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("checked_url", sa.Text(), nullable=False),
        sa.Column("final_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("redirect_chain_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("health", sa.String(length=50), nullable=False),
        sa.Column("ats", sa.String(length=50), nullable=True),
        sa.Column("page_type", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("apply_evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_url_observations_job_id", "url_observations", ["job_id"])
    op.create_index("ix_url_observations_health", "url_observations", ["health"])
    op.create_index("ix_url_observations_ats", "url_observations", ["ats"])
    op.create_index("ix_url_observations_page_type", "url_observations", ["page_type"])
    op.create_index("ix_url_observations_observed_at", "url_observations", ["observed_at"])

    op.create_table(
        "rediscovery_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=32), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(length=60), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="PENDING"),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("job_id", "url", name="uq_rediscovery_job_url"),
    )
    op.create_index("ix_rediscovery_candidates_job_id", "rediscovery_candidates", ["job_id"])
    op.create_index("ix_rediscovery_candidates_status", "rediscovery_candidates", ["status"])

    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("provider_name", sa.String(length=160), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("text_model", sa.String(length=240), nullable=False),
        sa.Column("vision_model", sa.String(length=240), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("supports_json_schema", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("secret_ref", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "resume_versions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=300), nullable=False),
        sa.Column("file_ext", sa.String(length=16), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("vault_relpath", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("parser_name", sa.String(length=80), nullable=True),
        sa.Column("parser_version", sa.String(length=80), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_resume_versions_sha256", "resume_versions", ["sha256"], unique=True)
    op.create_index("ix_resume_versions_version_number", "resume_versions", ["version_number"], unique=True)
    op.create_index("ix_resume_versions_extraction_status", "resume_versions", ["extraction_status"])
    op.create_index("ix_resume_versions_created_at", "resume_versions", ["created_at"])

    op.create_table(
        "profile_fields",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("field_key", sa.String(length=160), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profile_fields_field_key", "profile_fields", ["field_key"], unique=True)
    op.create_index("ix_profile_fields_confirmed", "profile_fields", ["confirmed"])

    op.create_table(
        "profile_field_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("field_key", sa.String(length=160), nullable=False),
        sa.Column("old_value_json", sa.Text(), nullable=True),
        sa.Column("new_value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_ref", sa.String(length=160), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_profile_field_revisions_field_key", "profile_field_revisions", ["field_key"])
    op.create_index("ix_profile_field_revisions_changed_at", "profile_field_revisions", ["changed_at"])

    op.create_table(
        "profile_draft_fields",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("resume_version_id", sa.String(length=32), sa.ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_key", sa.String(length=160), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("extractor_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_profile_draft_fields_resume_version_id", "profile_draft_fields", ["resume_version_id"])
    op.create_index("ix_profile_draft_fields_field_key", "profile_draft_fields", ["field_key"])
    op.create_index("ix_profile_draft_fields_status", "profile_draft_fields", ["status"])


def downgrade() -> None:
    for table in (
        "profile_draft_fields", "profile_field_revisions", "profile_fields",
        "resume_versions", "ai_provider_configs", "rediscovery_candidates",
        "url_observations", "source_sync_runs", "source_snapshots",
        "job_sources", "jobs", "company_sources", "company_relations",
        "company_aliases", "companies", "app_settings",
    ):
        op.drop_table(table)
