"""Application CRM lifecycle, de-duplication and event timeline contract."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationEvent, ApplicationSession, Company, Job, ResumeVersion


def _seed_verified_job() -> None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
            session.add(company)
            session.flush()
            session.add(
                Job(
                    id="job-apply",
                    company_id=company.id,
                    title="视觉设计",
                    location="南京",
                    industry="设计",
                    recruitment_batch="27届",
                    deadline_text="招满即止",
                    apply_url="https://source.example.com/apply",
                    canonical_url="https://ats.example.com/apply",
                    status="VERIFIED_OPEN",
                    fingerprint="fp-apply",
                )
            )
            session.commit()
    finally:
        engine.dispose()


def _seed_resume(resume_id: str, version_number: int) -> None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            session.add(
                ResumeVersion(
                    id=resume_id,
                    sha256=f"sha-{resume_id}",
                    original_filename=f"{resume_id}.pdf",
                    file_ext=".pdf",
                    mime_type="application/pdf",
                    size_bytes=100,
                    vault_relpath=f"resumes/{resume_id}/original.pdf",
                    version_number=version_number,
                )
            )
            session.commit()
    finally:
        engine.dispose()


def test_start_application_creates_event_and_reuses_entire_active_attempt(client):
    _seed_verified_job()
    first = client.post("/api/applications", json={"job_id": "job-apply"})
    assert first.status_code == 200
    data = first.json()
    assert data["status"] == "OPENED"
    assert data["allowed_next_statuses"] == ["IN_PROGRESS", "SUBMITTED", "ABANDONED"]
    assert data["channel"] == "manual"
    assert data["opened_url"] == "https://ats.example.com/apply"
    assert data["job_title"] == "视觉设计"

    moved = client.patch(
        f"/api/applications/{data['id']}",
        json={"status": "IN_PROGRESS"},
    )
    assert moved.status_code == 200

    second = client.post("/api/applications", json={"job_id": "job-apply"})
    assert second.status_code == 200
    assert second.json()["id"] == data["id"]
    assert second.json()["status"] == "IN_PROGRESS"

    submitted = client.patch(
        f"/api/applications/{data['id']}",
        json={"status": "SUBMITTED"},
    )
    assert submitted.status_code == 200

    third = client.post("/api/applications", json={"job_id": "job-apply"})
    assert third.status_code == 200
    assert third.json()["id"] == data["id"], "SUBMITTED is still the same active attempt"

    events = client.get(f"/api/applications/{data['id']}/events")
    assert events.status_code == 200
    assert [(event["event_type"], event["from_status"], event["to_status"]) for event in events.json()] == [
        ("CREATED", None, "OPENED"),
        ("STATUS_CHANGED", "OPENED", "IN_PROGRESS"),
        ("STATUS_CHANGED", "IN_PROGRESS", "SUBMITTED"),
    ]


def test_terminal_attempt_is_preserved_and_new_attempt_can_start(client):
    _seed_verified_job()
    created = client.post("/api/applications", json={"job_id": "job-apply"}).json()
    assert client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "SUBMITTED"},
    ).status_code == 200
    rejected = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "REJECTED", "note": "岗位已结束"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["allowed_next_statuses"] == []

    restarted = client.post("/api/applications", json={"job_id": "job-apply"})
    assert restarted.status_code == 200
    assert restarted.json()["id"] != created["id"]
    assert restarted.json()["status"] == "OPENED"

    listing = client.get("/api/applications").json()
    assert {row["status"] for row in listing} == {"OPENED", "REJECTED"}


def test_application_state_machine_rejects_backward_and_invalid_transitions(client):
    _seed_verified_job()
    created = client.post("/api/applications", json={"job_id": "job-apply"}).json()

    assert client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "SUBMITTED"},
    ).status_code == 200
    assert client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "OFFER"},
    ).status_code == 200

    backward = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "OPENED"},
    )
    assert backward.status_code == 409
    assert "OFFER -> OPENED" in backward.json()["detail"]

    invalid = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "NOT_A_STATUS"},
    )
    assert invalid.status_code == 422


def test_same_status_update_is_idempotent_and_does_not_append_event(client):
    _seed_verified_job()
    created = client.post("/api/applications", json={"job_id": "job-apply"}).json()

    same = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "OPENED", "note": "should not create an event"},
    )
    assert same.status_code == 200

    events = client.get(f"/api/applications/{created['id']}/events").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "CREATED"


def test_status_event_timeline_preserves_transition_note(client):
    _seed_verified_job()
    created = client.post("/api/applications", json={"job_id": "job-apply"}).json()

    updated = client.patch(
        f"/api/applications/{created['id']}",
        json={"status": "SUBMITTED", "note": "官网确认提交成功"},
    )
    assert updated.status_code == 200

    events = client.get(f"/api/applications/{created['id']}/events").json()
    assert events[-1]["event_type"] == "STATUS_CHANGED"
    assert events[-1]["from_status"] == "OPENED"
    assert events[-1]["to_status"] == "SUBMITTED"
    assert events[-1]["note"] == "官网确认提交成功"


def test_resume_version_linkage_is_validated_and_not_silently_changed(client):
    _seed_verified_job()
    _seed_resume("resume-a", 1)
    _seed_resume("resume-b", 2)

    missing = client.post(
        "/api/applications",
        json={"job_id": "job-apply", "resume_version_id": "missing-resume"},
    )
    assert missing.status_code == 422

    created = client.post(
        "/api/applications",
        json={"job_id": "job-apply", "resume_version_id": "resume-a"},
    )
    assert created.status_code == 200
    assert created.json()["resume_version_id"] == "resume-a"

    conflict = client.post(
        "/api/applications",
        json={"job_id": "job-apply", "resume_version_id": "resume-b"},
    )
    assert conflict.status_code == 409
    assert "different resume version" in conflict.json()["detail"]


def test_start_application_requires_existing_job_with_url(client):
    assert client.post("/api/applications", json={"job_id": "missing"}).status_code == 404

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            company = Company(name="无入口公司", normalized_name="无入口公司", ownership="unknown")
            session.add(company)
            session.flush()
            session.add(
                Job(
                    id="job-nourl",
                    company_id=company.id,
                    title="岗位",
                    location="",
                    industry="",
                    recruitment_batch="",
                    deadline_text="",
                    apply_url="",
                    canonical_url="",
                    status="DISCOVERED_NO_URL",
                    fingerprint="fp-nourl",
                )
            )
            session.commit()
    finally:
        engine.dispose()
    conflict = client.post("/api/applications", json={"job_id": "job-nourl"})
    assert conflict.status_code == 409


def test_browser_agent_application_channel_is_separate_from_manual_session(client):
    _seed_verified_job()
    manual = client.post("/api/applications", json={"job_id": "job-apply"}).json()
    agent = client.post(
        "/api/applications",
        json={"job_id": "job-apply", "channel": "browser_agent"},
    )

    assert agent.status_code == 200
    payload = agent.json()
    assert payload["channel"] == "browser_agent"
    assert payload["id"] != manual["id"]

    repeated = client.post(
        "/api/applications",
        json={"job_id": "job-apply", "channel": "browser_agent"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == payload["id"]

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            assert len(session.scalars(select(ApplicationSession)).all()) == 2
            assert len(session.scalars(select(ApplicationEvent)).all()) == 2
    finally:
        engine.dispose()
