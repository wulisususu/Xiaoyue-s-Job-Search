"""Migration chain as schema source-of-truth.

The startup path is empty DB -> alembic upgrade head. These tests verify:
- a fresh database built ONLY by migrations matches the ORM models
  (drift guard in both directions)
- historical databases upgrade cleanly to head
- the SQLite pragmas and FK cascades really apply
"""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.config import AppSettings
from app.db import _alembic_config, get_engine, init_db


def _settings(tmp_path) -> AppSettings:
    return AppSettings(data_dir=tmp_path / "data")


def test_fresh_db_is_built_by_migration_chain_and_is_idempotent(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    engine = get_engine(settings)
    try:
        tables = set(inspect(engine).get_table_names())
        for expected in (
            "app_settings", "companies", "company_aliases", "company_relations",
            "company_sources", "jobs", "job_sources", "source_snapshots",
            "source_sync_runs", "url_observations", "rediscovery_candidates",
            "ai_provider_configs", "resume_versions", "profile_fields",
            "profile_field_revisions", "profile_draft_fields",
            "profile_collection_items", "profile_collection_revisions",
            "ai_extraction_runs",
            "application_sessions", "url_candidates", "alembic_version",
        ):
            assert expected in tables, f"missing table {expected}"
    finally:
        engine.dispose()

    # Second init must be a clean no-op upgrade path.
    init_db(settings)


def test_migration_schema_matches_models(tmp_path):
    """Schema source-of-truth guard: the migration-built schema and the ORM
    metadata must agree on every table's column set. If a model change ships
    without a migration (or vice versa), this fails."""
    settings = _settings(tmp_path)
    init_db(settings)

    migration_engine = get_engine(settings)
    model_engine = create_engine("sqlite:///:memory:")
    from app.models import Base

    Base.metadata.create_all(model_engine)
    try:
        model_tables = {
            name: {column.name for column in table.columns}
            for name, table in Base.metadata.tables.items()
        }
        inspector = inspect(migration_engine)
        for table, model_columns in model_tables.items():
            migration_columns = {c["name"] for c in inspector.get_columns(table)}
            missing_in_migration = model_columns - migration_columns
            extra_in_migration = migration_columns - model_columns
            assert not missing_in_migration, f"{table}: model columns missing from migrations: {missing_in_migration}"
            assert not extra_in_migration, f"{table}: migration columns not in models: {extra_in_migration}"
        migrated_tables = set(inspect(engine := migration_engine).get_table_names()) - {"alembic_version"}
        assert migrated_tables == set(model_tables), (
            f"table drift: models={set(model_tables)} migrations={migrated_tables}"
        )
    finally:
        migration_engine.dispose()
        model_engine.dispose()


def test_first_revision_db_upgrades_to_head(tmp_path):
    """A database from the INITIAL revision (before lifecycle columns,
    application sessions and URL candidates existed) must upgrade to head."""
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    command.upgrade(_alembic_config(settings), "0001_initial_schema")

    db_file = settings.database_path
    engine = create_engine(f"sqlite:///{db_file}")
    job_source_columns = {c["name"] for c in inspect(engine).get_columns("job_sources")}
    tables = set(inspect(engine).get_table_names())
    assert "record_hash" not in job_source_columns
    assert "status" not in job_source_columns
    assert "application_sessions" not in tables
    assert "url_candidates" not in tables
    engine.dispose()

    init_db(settings)

    engine = get_engine(settings)
    try:
        job_source_columns = {c["name"] for c in inspect(engine).get_columns("job_sources")}
        tables = set(inspect(engine).get_table_names())
        assert {"record_hash", "status"} <= job_source_columns
        assert "application_sessions" in tables
        assert "url_candidates" in tables
        assert "profile_collection_items" in tables
        assert "profile_collection_revisions" in tables
    finally:
        engine.dispose()


def test_pre_collection_db_upgrades_to_structured_profile_head(tmp_path):
    """A real 0006 database must gain collection tables without rewriting
    the existing scalar Profile SSOT."""
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(settings), "0006_job_next_verification_at")

    engine = create_engine(f"sqlite:///{settings.database_path}")
    try:
        before = set(inspect(engine).get_table_names())
        assert "profile_fields" in before
        assert "profile_collection_items" not in before
        assert "profile_collection_revisions" not in before
    finally:
        engine.dispose()

    init_db(settings)

    engine = get_engine(settings)
    try:
        after = set(inspect(engine).get_table_names())
        assert "profile_fields" in after
        assert "profile_collection_items" in after
        assert "profile_collection_revisions" in after
    finally:
        engine.dispose()


def test_0008_db_upgrades_to_0009_with_extraction_run_linkage(tmp_path):
    """A real 0008 database gains ai_extraction_runs plus draft linkage and
    idempotency columns, while existing draft rows stay untouched."""
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    command.upgrade(_alembic_config(settings), "0008_profile_collection_drafts")

    engine = create_engine(f"sqlite:///{settings.database_path}")
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO resume_versions (id, sha256, original_filename, file_ext,"
                " mime_type, size_bytes, vault_relpath, version_number, extraction_status,"
                " created_at) VALUES ('rv-legacy', 'legacyhash', 'legacy.pdf', '.pdf',"
                " 'application/pdf', 1, 'resumes/hash/original.pdf', 1, 'EXTRACTED',"
                " '2026-01-01 00:00:00')"
            ))
            conn.execute(text(
                "INSERT INTO profile_draft_fields (resume_version_id, field_key,"
                " value_json, value_type, confidence, extractor_name, status, created_at)"
                " VALUES ('rv-legacy', 'contact.email', '\"a@b.com\"', 'string', 0.9,"
                " 'deterministic-contact-v1', 'PENDING', '2026-01-01 00:00:00')"
            ))
        assert "ai_extraction_runs" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    init_db(settings)

    engine = get_engine(settings)
    try:
        inspector = inspect(engine)
        assert "ai_extraction_runs" in set(inspector.get_table_names())
        run_columns = {c["name"] for c in inspector.get_columns("ai_extraction_runs")}
        assert {
            "id", "resume_version_id", "provider", "model", "prompt_version",
            "schema_version", "status", "input_hash", "error",
            "created_at", "completed_at",
        } <= run_columns
        for table in ("profile_draft_fields", "profile_collection_drafts"):
            columns = {c["name"] for c in inspector.get_columns(table)}
            assert {"extraction_run_id", "candidate_fingerprint"} <= columns, table
            unique_pairs = {
                tuple(index["column_names"])
                for index in inspector.get_indexes(table)
                if index.get("unique")
            }
            assert ("extraction_run_id", "candidate_fingerprint") in unique_pairs, table

        with Session(engine) as session:
            legacy = session.execute(
                text(
                    "SELECT resume_version_id, field_key, extraction_run_id,"
                    " candidate_fingerprint, status FROM profile_draft_fields"
                )
            ).all()
        assert legacy == [("rv-legacy", "contact.email", None, None, "PENDING")]
    finally:
        engine.dispose()


def test_sqlite_pragmas_are_enforced_on_every_connection(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    engine = get_engine(settings)
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
            mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
            assert str(mode).lower() == "wal"
    finally:
        engine.dispose()


def test_foreign_key_cascade_actually_deletes(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    engine = get_engine(settings)

    from app.models import Company, Job, JobSource

    try:
        with Session(engine) as session:
            company = Company(name="测试集团", normalized_name="测试集团", ownership="central_soe")
            session.add(company)
            session.flush()
            job = Job(
                id="job-cascade", company_id=company.id, title="岗位", location="", industry="",
                recruitment_batch="", deadline_text="", apply_url="", canonical_url="",
                status="DISCOVERED_NO_URL", fingerprint="fp-cascade",
            )
            session.add(job)
            session.flush()
            session.add(JobSource(job_id=job.id, source_name="tencent-sheet", source_record_key="k1"))
            session.commit()
            company_id = company.id

            session.delete(company)
            session.commit()
            assert session.scalar(select(JobSource.id)) is None
            assert session.get(Company, company_id) is None
    finally:
        engine.dispose()
