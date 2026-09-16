from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import AppSettings
from app.models import Base, ResumeVersion
from app.resumes.vault import (
    MAX_RESUME_BYTES,
    InvalidResumeError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
    validate_and_store_resume,
)
from tests.test_resume_parsers import build_docx, build_pdf


def make_session(tmp_path):
    settings = AppSettings(data_dir=tmp_path)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{settings.database_path}")
    Base.metadata.create_all(engine)
    return settings, engine, Session(engine)


def test_same_content_is_deduplicated_and_version_is_immutable(tmp_path):
    settings, engine, session = make_session(tmp_path)
    try:
        data = build_pdf("resume text hello@example.com 13800138000")
        first, first_dedup = validate_and_store_resume(session, settings, "resume.pdf", "application/pdf", data)
        second, second_dedup = validate_and_store_resume(session, settings, "renamed.pdf", "application/pdf", data)

        assert first_dedup is False
        assert second_dedup is True
        assert first.id == second.id
        assert first.version_number == 1
        assert session.scalars(select(ResumeVersion)).all() == [first]
        assert first.vault_relpath == f"resumes/{first.sha256}/original.pdf"
        assert (settings.vault_dir / first.vault_relpath).read_bytes() == data
    finally:
        session.close()
        engine.dispose()


def test_different_content_creates_next_version_even_with_same_filename(tmp_path):
    settings, engine, session = make_session(tmp_path)
    try:
        first, _ = validate_and_store_resume(session, settings, "resume.pdf", "application/pdf", build_pdf("first resume content 12345678901234567890"))
        second, _ = validate_and_store_resume(session, settings, "resume.pdf", "application/pdf", build_pdf("second resume content 12345678901234567890"))
        assert second.id != first.id
        assert second.sha256 != first.sha256
        assert (first.version_number, second.version_number) == (1, 2)
    finally:
        session.close()
        engine.dispose()


def test_unsupported_and_corrupt_files_do_not_commit_versions(tmp_path):
    settings, engine, session = make_session(tmp_path)
    try:
        try:
            validate_and_store_resume(session, settings, "legacy.doc", "application/msword", b"legacy")
            raise AssertionError("expected UnsupportedResumeTypeError")
        except UnsupportedResumeTypeError:
            pass

        try:
            validate_and_store_resume(session, settings, "broken.pdf", "application/pdf", b"%PDF-not-a-real-document")
            raise AssertionError("expected InvalidResumeError")
        except InvalidResumeError:
            pass

        try:
            validate_and_store_resume(session, settings, "broken.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK-not-a-real-docx")
            raise AssertionError("expected InvalidResumeError")
        except InvalidResumeError:
            pass

        assert session.scalars(select(ResumeVersion)).all() == []
        assert not (settings.vault_dir / "resumes").exists()
    finally:
        session.close()
        engine.dispose()


def test_file_over_50_mib_is_rejected_before_vault_commit(tmp_path):
    settings, engine, session = make_session(tmp_path)
    try:
        data = b"%PDF-" + (b"x" * (MAX_RESUME_BYTES - 4))
        assert len(data) > MAX_RESUME_BYTES
        try:
            validate_and_store_resume(session, settings, "huge.pdf", "application/pdf", data)
            raise AssertionError("expected ResumeTooLargeError")
        except ResumeTooLargeError:
            pass
        assert session.scalars(select(ResumeVersion)).all() == []
        assert not (settings.vault_dir / "resumes").exists()
    finally:
        session.close()
        engine.dispose()
