from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ResumeVersion
from app.profile.collection_drafts import CollectionDraftCandidate, create_collection_drafts


def seed_collection_drafts() -> tuple[str, list[int]]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resume = ResumeVersion(
                id=uuid.uuid4().hex,
                sha256=uuid.uuid4().hex * 2,
                original_filename="结构化简历.pdf",
                file_ext=".pdf",
                mime_type="application/pdf",
                size_bytes=128,
                vault_relpath="resumes/test/original.pdf",
                version_number=1,
                extraction_status="EXTRACTED",
                extracted_text="resume text",
                parser_name="test",
                parser_version="1",
            )
            session.add(resume)
            session.commit()
            drafts = create_collection_drafts(
                session,
                resume,
                [
                    CollectionDraftCandidate(
                        kind="education",
                        payload={"school": "三江学院", "major": "视觉传达设计"},
                        confidence=0.96,
                        extractor_name="openai-compatible-v1",
                    ),
                    CollectionDraftCandidate(
                        kind="project",
                        payload={"name": "荣巷历史文化视觉项目", "role": "视觉设计"},
                        confidence=0.84,
                        extractor_name="openai-compatible-v1",
                    ),
                ],
            )
            return resume.id, [draft.id for draft in drafts]
    finally:
        engine.dispose()


def test_collection_draft_review_api_keeps_ai_candidates_out_of_ssot_until_accept(client):
    resume_id, draft_ids = seed_collection_drafts()

    pending = client.get("/api/profile/collection-drafts", params={"status": "PENDING"})
    assert pending.status_code == 200
    body = pending.json()
    assert [item["id"] for item in body] == draft_ids
    assert body[0]["resume_version_id"] == resume_id
    assert body[0]["resume_version_number"] == 1
    assert body[0]["resume_filename"] == "结构化简历.pdf"
    assert body[0]["kind"] == "education"
    assert body[0]["label"] == "教育经历"
    assert body[0]["payload"] == {"school": "三江学院", "major": "视觉传达设计"}
    assert body[0]["confidence"] == 0.96
    assert body[0]["extractor_name"] == "openai-compatible-v1"
    assert body[0]["status"] == "PENDING"

    before = client.get("/api/profile/collections/education")
    assert before.status_code == 200
    assert before.json() == []

    accepted = client.post(f"/api/profile/collection-drafts/{draft_ids[0]}/accept")
    assert accepted.status_code == 200
    accepted_body = accepted.json()
    assert accepted_body["kind"] == "education"
    assert accepted_body["payload"]["school"] == "三江学院"
    assert accepted_body["source_type"] == "resume"
    assert accepted_body["source_ref"] == resume_id
    assert accepted_body["confidence"] == 0.96
    assert accepted_body["confirmed"] is True

    rejected = client.post(f"/api/profile/collection-drafts/{draft_ids[1]}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["reviewed_at"] is not None

    pending_after = client.get("/api/profile/collection-drafts", params={"status": "PENDING"})
    assert pending_after.status_code == 200
    assert pending_after.json() == []

    reviewed_again = client.post(f"/api/profile/collection-drafts/{draft_ids[0]}/accept")
    assert reviewed_again.status_code == 409
    missing = client.post("/api/profile/collection-drafts/999999/accept")
    assert missing.status_code == 404


def test_resume_pending_draft_count_includes_scalar_and_collection_candidates(client):
    resume_id, draft_ids = seed_collection_drafts()
    assert len(draft_ids) == 2

    detail = client.get(f"/api/resumes/{resume_id}")
    assert detail.status_code == 200
    assert detail.json()["pending_draft_count"] == 2

    client.post(f"/api/profile/collection-drafts/{draft_ids[0]}/accept")
    detail_after = client.get(f"/api/resumes/{resume_id}")
    assert detail_after.status_code == 200
    assert detail_after.json()["pending_draft_count"] == 1
