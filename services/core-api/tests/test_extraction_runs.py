from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.errors import ProviderResponseError
from app.db import _configure_sqlite_connection
from app.models import (
    AIExtractionRun,
    Base,
    ProfileCollectionDraft,
    ProfileCollectionItem,
    ProfileDraftField,
    ProfileField,
    ResumeVersion,
)
from app.profile.extraction import (
    CollectionDraftCandidate,
    DraftCandidate,
    ExtractionMetadata,
    ProfileExtractionBundle,
    DeterministicExtractionProvider,
)
from app.profile.extraction_runs import (
    ResumeNotExtractableError,
    execute_extraction_run,
    persist_bundle_drafts,
)
from app.profile.service import create_resume_drafts


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'runs.db'}")
    # Same connection pragmas as production get_engine() so FK semantics
    # (ON DELETE SET NULL / CASCADE) actually apply in tests.
    event.listen(engine, "connect", _configure_sqlite_connection)
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def make_resume(session: Session, text: str, *, status: str = "EXTRACTED") -> ResumeVersion:
    resume = ResumeVersion(
        id=uuid.uuid4().hex,
        sha256=uuid.uuid4().hex * 2,
        original_filename="resume.pdf",
        file_ext=".pdf",
        mime_type="application/pdf",
        size_bytes=len(text.encode()),
        vault_relpath="resumes/hash/original.pdf",
        version_number=1,
        extraction_status=status,
        extracted_text=text if status == "EXTRACTED" else None,
        parser_name="test",
        parser_version="1",
    )
    session.add(resume)
    session.commit()
    return resume


FAKE_METADATA = ExtractionMetadata(
    provider="fake",
    model="fake-model",
    prompt_version="fake-prompt-1",
    schema_version="fake-schema-1",
)


class FakeProvider:
    def __init__(self, bundle: ProfileExtractionBundle | None = None, error: Exception | None = None):
        self.bundle = bundle
        self.error = error
        self.received_texts: list[str] = []

    def metadata(self) -> ExtractionMetadata:
        return FAKE_METADATA

    def extract(self, text: str) -> ProfileExtractionBundle:
        self.received_texts.append(text)
        if self.error is not None:
            raise self.error
        if self.bundle is None:
            raise AssertionError("FakeProvider configured without a bundle")
        return self.bundle


def make_bundle() -> ProfileExtractionBundle:
    return ProfileExtractionBundle(
        fields=[
            DraftCandidate(
                field_key="contact.email",
                value="name@example.com",
                value_type="string",
                confidence=0.97,
                extractor_name="openai_compatible",
            ),
            # Semantically invalid against the registry -> must be dropped.
            DraftCandidate(
                field_key="contact.phone",
                value="not-a-phone",
                value_type="string",
                confidence=0.9,
                extractor_name="openai_compatible",
            ),
        ],
        collections=[
            CollectionDraftCandidate(
                kind="education",
                payload={"school": "三江学院", "major": "视觉传达设计"},
                confidence=0.96,
                extractor_name="openai_compatible",
            ),
        ],
        metadata=FAKE_METADATA,
    )


def test_deterministic_import_creates_a_successful_run_and_links_drafts(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        text = "name@example.com 13800138000"
        resume = make_resume(session, text)

        drafts = create_resume_drafts(session, resume)

        assert {draft.field_key for draft in drafts} == {"contact.email", "contact.phone"}
        runs = session.scalars(select(AIExtractionRun)).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.resume_version_id == resume.id
        assert run.provider == "deterministic"
        assert run.model == "deterministic-contact-v1"
        assert run.prompt_version == "none"
        assert run.schema_version == "deterministic-v1"
        assert run.status == "SUCCEEDED"
        assert run.error is None
        assert run.input_hash == hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert run.completed_at is not None
        for draft in drafts:
            assert draft.extraction_run_id == run.id
            assert draft.candidate_fingerprint is not None
            assert len(draft.candidate_fingerprint) == 64
        assert session.scalars(select(ProfileField)).all() == []
        assert session.scalars(select(ProfileCollectionItem)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_provider_run_persists_validated_scalar_and_collection_drafts(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com 学校：三江学院")
        provider = FakeProvider(bundle=make_bundle())

        run = execute_extraction_run(session, resume, provider)

        assert run.status == "SUCCEEDED"
        assert run.provider == "fake"
        assert run.model == "fake-model"
        assert run.prompt_version == "fake-prompt-1"
        assert run.schema_version == "fake-schema-1"
        assert provider.received_texts == ["name@example.com 学校：三江学院"]

        scalar_drafts = session.scalars(
            select(ProfileDraftField).where(ProfileDraftField.extraction_run_id == run.id)
        ).all()
        assert [(draft.field_key, draft.value_json) for draft in scalar_drafts] == [
            ("contact.email", '"name@example.com"')
        ]

        collection_drafts = session.scalars(
            select(ProfileCollectionDraft).where(
                ProfileCollectionDraft.extraction_run_id == run.id
            )
        ).all()
        assert [(draft.kind, draft.payload_json) for draft in collection_drafts] == [
            ("education", '{"school":"三江学院","major":"视觉传达设计"}')
        ]
        assert all(draft.status == "PENDING" for draft in scalar_drafts + collection_drafts)

        # AI output never reaches SSOT without human accept.
        assert session.scalars(select(ProfileField)).all() == []
        assert session.scalars(select(ProfileCollectionItem)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_replaying_the_same_run_and_bundle_inserts_nothing_new(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        run = execute_extraction_run(session, resume, FakeProvider(bundle=make_bundle()))

        before_scalar = session.scalars(select(ProfileDraftField)).all()
        before_collection = session.scalars(select(ProfileCollectionDraft)).all()

        persist_bundle_drafts(session, resume, run, make_bundle())

        assert session.scalars(select(ProfileDraftField)).all() == before_scalar
        assert session.scalars(select(ProfileCollectionDraft)).all() == before_collection
    finally:
        session.close()
        engine.dispose()


def test_duplicate_candidates_inside_one_bundle_collapse_into_one_draft(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        bundle = ProfileExtractionBundle(
            fields=[
                DraftCandidate("contact.email", "name@example.com", "string", 0.9, "openai_compatible"),
                DraftCandidate("contact.email", "name@example.com", "string", 0.8, "openai_compatible"),
            ],
            collections=[
                CollectionDraftCandidate("skill", {"name": "Python"}, 0.9, "openai_compatible"),
                CollectionDraftCandidate("skill", {"name": "Python"}, 0.8, "openai_compatible"),
                CollectionDraftCandidate("skill", {"name": "SQL"}, 0.7, "openai_compatible"),
            ],
            metadata=FAKE_METADATA,
        )

        run = execute_extraction_run(session, resume, FakeProvider(bundle=bundle))

        scalar_drafts = session.scalars(
            select(ProfileDraftField).where(ProfileDraftField.extraction_run_id == run.id)
        ).all()
        collection_drafts = session.scalars(
            select(ProfileCollectionDraft).where(ProfileCollectionDraft.extraction_run_id == run.id)
        ).all()
        assert len(scalar_drafts) == 1
        assert len(collection_drafts) == 2
    finally:
        session.close()
        engine.dispose()


def test_provider_failure_records_failed_run_and_creates_no_drafts(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        provider = FakeProvider(error=ProviderResponseError("AI provider completion content is not valid JSON"))

        with pytest.raises(ProviderResponseError):
            execute_extraction_run(session, resume, provider)

        runs = session.scalars(select(AIExtractionRun)).all()
        assert len(runs) == 1
        run = runs[0]
        assert run.status == "FAILED"
        assert "not valid JSON" in (run.error or "")
        assert run.completed_at is not None
        assert session.scalars(select(ProfileDraftField)).all() == []
        assert session.scalars(select(ProfileCollectionDraft)).all() == []
        assert session.scalars(select(ProfileField)).all() == []
    finally:
        session.close()
        engine.dispose()


def test_unextractable_resumes_never_start_a_run(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "irrelevant", status="OCR_REQUIRED")
        provider = FakeProvider(bundle=make_bundle())

        with pytest.raises(ResumeNotExtractableError):
            execute_extraction_run(session, resume, provider)

        assert session.scalars(select(AIExtractionRun)).all() == []
        assert provider.received_texts == []
    finally:
        session.close()
        engine.dispose()


def test_partial_unique_index_rejects_duplicate_run_fingerprints(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        run = execute_extraction_run(session, resume, FakeProvider(bundle=make_bundle()))
        original = session.scalars(select(ProfileDraftField)).all()[0]

        duplicate = ProfileDraftField(
            resume_version_id=resume.id,
            extraction_run_id=run.id,
            field_key=original.field_key,
            value_json=original.value_json,
            value_type=original.value_type,
            confidence=original.confidence,
            extractor_name="openai_compatible",
            candidate_fingerprint=original.candidate_fingerprint,
            status="PENDING",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def test_deleting_a_run_keeps_draft_rows_but_clears_linkage(tmp_path):
    engine, session = make_session(tmp_path)
    try:
        resume = make_resume(session, "name@example.com")
        run = execute_extraction_run(session, resume, FakeProvider(bundle=make_bundle()))
        run_id = run.id

        session.delete(run)
        session.commit()

        drafts = session.scalars(
            select(ProfileDraftField).where(ProfileDraftField.extraction_run_id == run_id)
        ).all()
        assert drafts == []
        survivors = session.scalars(select(ProfileDraftField)).all()
        assert len(survivors) == 1
        assert survivors[0].extraction_run_id is None
        assert survivors[0].field_key == "contact.email"
    finally:
        session.close()
        engine.dispose()


def test_deterministic_provider_satisfies_contract_and_reports_metadata():
    provider = DeterministicExtractionProvider()
    assert provider.metadata() == provider.extract("name@example.com").metadata
