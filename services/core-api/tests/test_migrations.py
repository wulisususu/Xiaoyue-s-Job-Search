"""Migration and schema-drift regression tests."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.config import AppSettings
from app.db import get_engine, init_db


def _settings(tmp_path) -> AppSettings:
    return AppSettings(data_dir=tmp_path / "data")


def test_fresh_db_is_created_and_stamped(tmp_path):
    settings = _settings(tmp_path)
    init_db(settings)
    engine = get_engine(settings)
    try:
        tables = set(inspect(engine).get_table_names())
        assert "job_sources" in tables
        assert "alembic_version" in tables
        cols = {c["name"] for c in inspect(engine).get_columns("job_sources")}
        assert {"record_hash", "status"} <= cols
    finally:
        engine.dispose()

    # Second init must be a clean no-op upgrade path.
    init_db(settings)


def test_pre_lifecycle_db_is_upgraded_by_migrations(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    db_file = settings.database_path

    # Simulate an "old user" database created before the lifecycle columns
    # existed: build current models, then strip the new columns.
    bootstrap = create_engine(f"sqlite:///{db_file}")
    from app.models import Base

    Base.metadata.create_all(bootstrap)
    with bootstrap.begin() as conn:
        # The index did not exist on genuinely old databases; drop it so the
        # simulated schema matches the pre-lifecycle shape exactly.
        conn.execute(text("DROP INDEX IF EXISTS ix_job_sources_status"))
        conn.execute(text("ALTER TABLE job_sources DROP COLUMN record_hash"))
        conn.execute(text("ALTER TABLE job_sources DROP COLUMN status"))
        conn.execute(text("DELETE FROM job_sources"))
    bootstrap.dispose()

    init_db(settings)

    engine = get_engine(settings)
    try:
        cols = {c["name"] for c in inspect(engine).get_columns("job_sources")}
        assert {"record_hash", "status"} <= cols
        # Foreign keys really enforced on the running connection.
        fk_on = engine.connect().exec_driver_sql("PRAGMA foreign_keys").scalar()
        assert fk_on == 1
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
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.models import Company, JobSource

    try:
        with Session(engine) as session:
            company = Company(name="测试集团", normalized_name="测试集团", ownership="central_soe")
            session.add(company)
            session.flush()
            job = __import__("app.models", fromlist=["Job"]).Job(
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
            assert session.get(__import__("app.models", fromlist=["Company"]).Company, company_id) is None
    finally:
        engine.dispose()
