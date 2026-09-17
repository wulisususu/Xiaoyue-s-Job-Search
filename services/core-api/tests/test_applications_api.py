"""开始申请 / application session API contract."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationSession, Company, Job


def _seed_verified_job() -> None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
            session.add(company)
            session.flush()
            session.add(
                Job(
                    id="job-apply", company_id=company.id, title="视觉设计", location="南京", industry="设计",
                    recruitment_batch="27届", deadline_text="招满即止",
                    apply_url="https://source.example.com/apply", canonical_url="https://ats.example.com/apply",
                    status="VERIFIED_OPEN", fingerprint="fp-apply",
                )
            )
            session.commit()
    finally:
        engine.dispose()


def test_start_application_creates_session_and_reuses_opened_one(client):
    _seed_verified_job()
    first = client.post("/api/applications", json={"job_id": "job-apply"})
    assert first.status_code == 200
    data = first.json()
    assert data["status"] == "OPENED"
    assert data["channel"] == "manual"
    assert data["opened_url"] == "https://ats.example.com/apply"
    assert data["job_title"] == "视觉设计"

    second = client.post("/api/applications", json={"job_id": "job-apply"})
    assert second.status_code == 200
    assert second.json()["id"] == data["id"], "repeated clicks must reuse the OPENED session"

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            assert len(session.scalars(__import__("sqlalchemy").select(ApplicationSession)).all()) == 1
    finally:
        engine.dispose()


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
                    id="job-nourl", company_id=company.id, title="岗位", location="", industry="",
                    recruitment_batch="", deadline_text="", apply_url="", canonical_url="",
                    status="DISCOVERED_NO_URL", fingerprint="fp-nourl",
                )
            )
            session.commit()
    finally:
        engine.dispose()
    conflict = client.post("/api/applications", json={"job_id": "job-nourl"})
    assert conflict.status_code == 409


def test_application_status_timeline_updates(client):
    _seed_verified_job()
    created = client.post("/api/applications", json={"job_id": "job-apply"}).json()

    updated = client.patch(f"/api/applications/{created['id']}", json={"status": "SUBMITTED"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "SUBMITTED"

    invalid = client.patch(f"/api/applications/{created['id']}", json={"status": "NOT_A_STATUS"})
    assert invalid.status_code == 422

    listing = client.get("/api/applications").json()
    assert [item["status"] for item in listing] == ["SUBMITTED"]
