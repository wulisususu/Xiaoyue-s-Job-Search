from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    ownership: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    province: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    level: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    aliases: Mapped[list["CompanyAlias"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_companies_identity", "normalized_name", "ownership", unique=True),)


class CompanyAlias(Base):
    __tablename__ = "company_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    company: Mapped[Company] = relationship(back_populates="aliases")
    __table_args__ = (UniqueConstraint("company_id", "normalized_alias", "source_name", name="uq_company_alias_source"),)


class CompanyRelation(Base):
    __tablename__ = "company_relations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    child_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False, default="subsidiary")
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    __table_args__ = (UniqueConstraint("parent_company_id", "child_company_id", "relation_type", name="uq_company_relation"),)


class CompanySource(Base):
    __tablename__ = "company_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(300), nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    __table_args__ = (UniqueConstraint("source_name", "source_key", name="uq_company_source_key"),)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(600), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    industry: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    recruitment_batch: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    deadline_text: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    apply_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    source_updated_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Scheduler hint maintained after every verification: NULL means "never
    # verified" (i.e. due). Lets verify_due_jobs select due jobs in ONE query
    # instead of an N+1 scan over URL observations.
    next_verification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class JobSource(Base):
    __tablename__ = "job_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False)
    source_record_key: Mapped[str] = mapped_column(String(96), nullable=False)
    record_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("source_name", "source_record_key", name="uq_job_source_record"),)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    remote_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    payload_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("source_name", "content_hash", name="uq_source_snapshot_hash"),)


class SourceSyncRun(Base):
    __tablename__ = "source_sync_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_snapshots.id", ondelete="SET NULL"), nullable=True)
    remote_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime] = mapped_column(default=utcnow)


class ApplicationSession(Base):
    """One application attempt for a job.

    A non-terminal attempt is reused on repeated clicks for the same
    job+channel. Every lifecycle change is recorded in application_events so
    the current status is a projection, not the only copy of history.
    """

    __tablename__ = "application_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="OPENED", index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="manual", index=True)
    resume_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    opened_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    opened_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ApplicationEvent(Base):
    """Immutable lifecycle audit event for an application attempt."""

    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("application_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class UrlCandidate(Base):
    """A new entry URL seen upstream for an existing canonical job.

    Upstream URL rewrites are NEVER applied directly to the canonical job:
    they land here as PENDING candidates, get verified by the verification
    engine, and are only promoted to job.apply_url/canonical_url on
    VERIFIED_APPLY evidence. Broken candidates are DISCARDED.
    """

    __tablename__ = "url_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    source_name: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    verified_health: Mapped[str | None] = mapped_column(String(50), nullable=True)
    discovered_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("job_id", "url", name="uq_url_candidate_job_url"),)


class UrlObservation(Base):
    __tablename__ = "url_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_url: Mapped[str] = mapped_column(Text, nullable=False)
    final_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    redirect_chain_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ats: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    page_type: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown", index=True)
    apply_evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    content_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class RediscoveryCandidate(Base):
    __tablename__ = "rediscovery_candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(60), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    discovered_at: Mapped[datetime] = mapped_column(default=utcnow)
    __table_args__ = (UniqueConstraint("job_id", "url", name="uq_rediscovery_job_url"),)


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(160), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    text_model: Mapped[str] = mapped_column(String(240), nullable=False)
    vision_model: Mapped[str | None] = mapped_column(String(240), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    supports_json_schema: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    secret_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AIExtractionRun(Base):
    """One execution of the unified ProfileExtractionProvider contract.

    The mandatory audit link between a resume version and every draft a
    provider produced: provider, model, prompt/schema versions, status and
    errors are recorded whether the run succeeds or fails.
    """

    __tablename__ = "ai_extraction_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(240), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING", index=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    file_ext: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    vault_relpath: Mapped[str] = mapped_column(Text, nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    extraction_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ProfileField(Base):
    __tablename__ = "profile_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(40), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class ProfileFieldRevision(Base):
    __tablename__ = "profile_field_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    old_value_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    changed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ProfileCollectionItem(Base):
    __tablename__ = "profile_collection_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    __table_args__ = (Index("ix_profile_collection_items_kind_position", "kind", "position", "id"),)


class ProfileCollectionRevision(Base):
    __tablename__ = "profile_collection_revisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Historical audit identity: deliberately not a foreign key, so deleting
    # the live SSOT item cannot rewrite old revisions to NULL.
    item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    old_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class ProfileDraftField(Base):
    __tablename__ = "profile_draft_fields"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_version_id: Mapped[str] = mapped_column(ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    extraction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "ai_extraction_runs.id",
            ondelete="SET NULL",
            name="fk_profile_draft_fields_extraction_run_id",
        ),
        nullable=True,
        index=True,
    )
    field_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Replay safety: the same extraction run cannot insert the same candidate
    # twice. Legacy rows (pre-0009) keep NULL linkage and stay untouched.
    __table_args__ = (
        Index(
            "uq_profile_draft_fields_run_fingerprint",
            "extraction_run_id",
            "candidate_fingerprint",
            unique=True,
            sqlite_where=text("extraction_run_id IS NOT NULL AND candidate_fingerprint IS NOT NULL"),
        ),
    )


class ProfileCollectionDraft(Base):
    __tablename__ = "profile_collection_drafts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_version_id: Mapped[str] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    extraction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "ai_extraction_runs.id",
            ondelete="SET NULL",
            name="fk_profile_collection_drafts_extraction_run_id",
        ),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    candidate_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    __table_args__ = (
        Index(
            "uq_profile_collection_drafts_run_fingerprint",
            "extraction_run_id",
            "candidate_fingerprint",
            unique=True,
            sqlite_where=text("extraction_run_id IS NOT NULL AND candidate_fingerprint IS NOT NULL"),
        ),
    )
