from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ProfileDraftField, ProfileField, ProfileFieldRevision, ResumeVersion
from app.profile import service as profile_service
from app.profile.extraction import DraftCandidate, ExtractionMetadata, ProfileExtractionBundle
from app.profile.extraction_runs import persist_bundle_drafts, start_extraction_run


class MemorySecretStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def set_secret(self, ref: str, value: str) -> None:
        self.values[ref] = value

    def get_secret(self, ref: str) -> str | None:
        return self.values.get(ref)

    def delete_secret(self, ref: str) -> None:
        self.values.pop(ref, None)


class FakeProvider:
    def metadata(self):
        return ExtractionMetadata(
            provider="fake",
            model="fake-model",
            prompt_version="v1",
            schema_version="v1",
        )

    def extract(self, text: str):
        raise AssertionError("not used")


def test_sensitive_profile_field_uses_keyring_and_never_persists_plaintext(client, monkeypatch):
    store = MemorySecretStore()
    monkeypatch.setattr(profile_service, "get_secret_store", lambda: store)

    raw = "TESTDOC-ABC1234"
    response = client.put("/api/profile/fields/identity.id_number", json={"value": raw})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["value"].endswith("1234")
    assert raw not in response.text
    assert payload["secret_configured"] is True

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            field = session.scalar(select(ProfileField).where(ProfileField.field_key == "identity.id_number"))
            assert field is not None
            assert field.secret_ref
            assert raw not in field.value_json
            assert store.get_secret(field.secret_ref) == raw

            revisions = session.scalars(
                select(ProfileFieldRevision).where(ProfileFieldRevision.field_key == "identity.id_number")
            ).all()
            assert len(revisions) == 1
            assert raw not in (revisions[0].new_value_json or "")
    finally:
        engine.dispose()

    listed = client.get("/api/profile/fields")
    assert listed.status_code == 200
    assert raw not in listed.text


def test_sensitive_field_never_becomes_ai_draft(tmp_path):
    from sqlalchemy import create_engine
    from app.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'sensitive.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            resume = ResumeVersion(
                id="rv-sensitive",
                sha256="a" * 64,
                original_filename="resume.pdf",
                file_ext=".pdf",
                mime_type="application/pdf",
                size_bytes=10,
                vault_relpath="resumes/a/original.pdf",
                version_number=1,
                extraction_status="EXTRACTED",
                extracted_text="document TESTDOC-ABC1234",
                parser_name="test",
                parser_version="1",
            )
            session.add(resume)
            session.commit()
            run = start_extraction_run(session, resume, FakeProvider())
            bundle = ProfileExtractionBundle(
                fields=[
                    DraftCandidate(
                        field_key="identity.id_number",
                        value="TESTDOC-ABC1234",
                        value_type="string",
                        confidence=0.99,
                        extractor_name="fake",
                    )
                ],
                collections=[],
                metadata=FakeProvider().metadata(),
            )
            persist_bundle_drafts(session, resume, run, bundle)
            assert session.scalars(select(ProfileDraftField)).all() == []
    finally:
        engine.dispose()
