from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    Base,
    ProfileCollectionDraft,
    ProfileCollectionItem,
    ProfileCollectionRevision,
    ResumeVersion,
)
from app.profile.collection_drafts import (
    CollectionDraftCandidate,
    accept_collection_draft,
    create_collection_drafts,
    reject_collection_draft,
)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'profile-collection-drafts.db'}")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def make_resume(session: Session, text: str = "resume text") -> ResumeVersion:
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


def test_ai_collection_candidates_become_pending_drafts_without_touching_ssot(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session)
        drafts = create_collection_drafts(
            session,
            resume,
            [
                CollectionDraftCandidate(
                    kind="education",
                    payload={"school": " 三江学院 ", "major": "视觉传达设计"},
                    confidence=0.96,
                    extractor_name="openai-compatible-v1",
                ),
                CollectionDraftCandidate(
                    kind="skill",
                    payload={"name": "Python", "level": "熟练"},
                    confidence=0.88,
                    extractor_name="openai-compatible-v1",
                ),
            ],
        )

        assert [draft.kind for draft in drafts] == ["education", "skill"]
        assert json.loads(drafts[0].payload_json) == {"school": "三江学院", "major": "视觉传达设计"}
        assert all(draft.status == "PENDING" for draft in drafts)
        assert session.scalars(select(ProfileCollectionItem)).all() == []
        assert session.scalars(select(ProfileCollectionRevision)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_accepting_collection_draft_creates_confirmed_item_and_revision_atomically(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session)
        draft = create_collection_drafts(
            session,
            resume,
            [
                CollectionDraftCandidate(
                    kind="education",
                    payload={"school": "三江学院", "major": "视觉传达设计"},
                    confidence=0.96,
                    extractor_name="openai-compatible-v1",
                )
            ],
        )[0]

        item = accept_collection_draft(session, draft.id)
        session.refresh(draft)
        revisions = session.scalars(select(ProfileCollectionRevision)).all()

        assert item.kind == "education"
        assert item.position == 0
        assert json.loads(item.payload_json) == {"school": "三江学院", "major": "视觉传达设计"}
        assert item.source_type == "resume"
        assert item.source_ref == resume.id
        assert item.confidence == 0.96
        assert item.confirmed is True
        assert draft.status == "ACCEPTED"
        assert draft.reviewed_at is not None
        assert len(revisions) == 1
        assert revisions[0].item_id == item.id
        assert revisions[0].operation == "CREATE"
        assert revisions[0].source_type == "resume"
        assert revisions[0].source_ref == resume.id
    finally:
        session.close()
        engine.dispose()


def test_rejecting_collection_draft_never_changes_ssot(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session)
        draft = create_collection_drafts(
            session,
            resume,
            [
                CollectionDraftCandidate(
                    kind="project",
                    payload={"name": "课程项目"},
                    confidence=0.8,
                    extractor_name="openai-compatible-v1",
                )
            ],
        )[0]

        rejected = reject_collection_draft(session, draft.id)

        assert rejected.status == "REJECTED"
        assert rejected.reviewed_at is not None
        assert session.scalars(select(ProfileCollectionItem)).all() == []
        assert session.scalars(select(ProfileCollectionRevision)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_invalid_collection_draft_acceptance_rolls_back_review_and_ssot(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session)
        draft = ProfileCollectionDraft(
            resume_version_id=resume.id,
            kind="education",
            payload_json=json.dumps({"major": "视觉传达设计"}, ensure_ascii=False),
            confidence=0.9,
            extractor_name="test",
            status="PENDING",
        )
        session.add(draft)
        session.commit()

        with pytest.raises(ValueError):
            accept_collection_draft(session, draft.id)

        session.expire_all()
        stored = session.get(ProfileCollectionDraft, draft.id)
        assert stored is not None
        assert stored.status == "PENDING"
        assert stored.reviewed_at is None
        assert session.scalars(select(ProfileCollectionItem)).all() == []
        assert session.scalars(select(ProfileCollectionRevision)).all() == []
    finally:
        session.close()
        engine.dispose()
