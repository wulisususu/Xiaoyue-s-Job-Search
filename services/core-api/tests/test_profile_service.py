from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, ProfileDraftField, ProfileField, ProfileFieldRevision, ResumeVersion
from app.profile.extraction import extract_deterministic
from app.profile.service import (
    accept_profile_draft,
    create_resume_drafts,
    manual_upsert_profile_field,
    reject_profile_draft,
)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile.db'}")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def make_resume(session: Session, text: str) -> ResumeVersion:
    resume = ResumeVersion(
        id=uuid.uuid4().hex,
        sha256=uuid.uuid4().hex * 2,
        original_filename="resume.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=len(text.encode()),
        vault_relpath="resumes/hash/original.pdf",
        version_number=1,
        extraction_status="EXTRACTED",
        extracted_text=text,
        parser_name="test",
        parser_version="1",
    )
    session.add(resume)
    session.commit()
    return resume


def test_deterministic_extractor_only_emits_strict_contact_candidates():
    candidates = extract_deterministic("三江学院 视觉传达设计 name@example.com 手机 13800138000")
    by_key = {candidate.field_key: candidate for candidate in candidates}

    assert set(by_key) == {"contact.email", "contact.phone"}
    assert by_key["contact.email"].value == "name@example.com"
    assert by_key["contact.phone"].value == "13800138000"
    assert by_key["contact.email"].extractor_name == "deterministic-contact-v1"


def test_resume_extraction_creates_pending_drafts_but_never_profile_fields(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com 13800138000")
        drafts = create_resume_drafts(session, resume)

        assert {draft.field_key for draft in drafts} == {"contact.email", "contact.phone"}
        assert all(draft.status == "PENDING" for draft in drafts)
        assert session.scalars(select(ProfileField)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_accepting_draft_confirms_profile_and_appends_revision_atomically(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        draft = create_resume_drafts(session, resume)[0]

        field = accept_profile_draft(session, draft.id)
        session.refresh(draft)
        revisions = session.scalars(select(ProfileFieldRevision)).all()

        assert field.field_key == "contact.email"
        assert json.loads(field.value_json) == "name@example.com"
        assert field.source_type == "resume"
        assert field.source_ref == resume.id
        assert field.confirmed is True
        assert draft.status == "ACCEPTED"
        assert draft.reviewed_at is not None
        assert len(revisions) == 1
        assert revisions[0].old_value_json is None
        assert json.loads(revisions[0].new_value_json) == "name@example.com"
    finally:
        session.close()
        engine.dispose()


def test_invalid_draft_acceptance_rolls_back_profile_and_review_state(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "irrelevant")
        draft = ProfileDraftField(
            resume_version_id=resume.id,
            field_key="contact.phone",
            value_json=json.dumps("123"),
            value_type="string",
            confidence=0.99,
            extractor_name="test",
            status="PENDING",
        )
        session.add(draft)
        session.commit()

        with pytest.raises(ValueError):
            accept_profile_draft(session, draft.id)

        session.expire_all()
        stored = session.get(ProfileDraftField, draft.id)
        assert stored is not None
        assert stored.status == "PENDING"
        assert stored.reviewed_at is None
        assert session.scalars(select(ProfileField)).all() == []
        assert session.scalars(select(ProfileFieldRevision)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_rejecting_draft_never_changes_profile(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        draft = create_resume_drafts(session, resume)[0]

        rejected = reject_profile_draft(session, draft.id)

        assert rejected.status == "REJECTED"
        assert rejected.reviewed_at is not None
        assert session.scalars(select(ProfileField)).all() == []
        assert session.scalars(select(ProfileFieldRevision)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_manual_edit_is_confirmed_and_preserves_old_and_new_revision_values(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        first = manual_upsert_profile_field(session, "identity.name", "赵新悦")
        second = manual_upsert_profile_field(session, "identity.name", "赵新悦（更新）")
        revisions = session.scalars(select(ProfileFieldRevision).order_by(ProfileFieldRevision.id)).all()

        assert first.id == second.id
        assert second.source_type == "manual"
        assert second.source_ref is None
        assert second.confidence == 1.0
        assert second.confirmed is True
        assert len(revisions) == 2
        assert revisions[0].old_value_json is None
        assert json.loads(revisions[0].new_value_json) == "赵新悦"
        assert json.loads(revisions[1].old_value_json) == "赵新悦"
        assert json.loads(revisions[1].new_value_json) == "赵新悦（更新）"
    finally:
        session.close()
        engine.dispose()
