from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationSession, Company, Job


def _job(
    *,
    job_id: str,
    company_id: int,
    status: str,
    fingerprint: str,
    created_at: dt.datetime,
) -> Job:
    return Job(
        id=job_id,
        company_id=company_id,
        title=f"岗位 {job_id}",
        location="南京",
        industry="设计",
        recruitment_batch="27届",
        deadline_text="招满即止",
        apply_url=f"https://example.com/{job_id}",
        canonical_url=f"https://example.com/{job_id}",
        status=status,
        fingerprint=fingerprint,
        created_at=created_at,
    )


def test_dashboard_summary_uses_real_job_and_application_counts(client):
    engine = get_engine(get_settings())
    now = dt.datetime.now(dt.timezone.utc)
    old = now - dt.timedelta(days=3)
    try:
        with Session(engine) as session:
            central = Company(
                name="央企集团",
                normalized_name="央企集团",
                ownership="central_soe",
            )
            local = Company(
                name="地方国企",
                normalized_name="地方国企",
                ownership="local_soe",
            )
            session.add_all([central, local])
            session.flush()

            session.add_all(
                [
                    _job(
                        job_id="dash-1",
                        company_id=central.id,
                        status="VERIFIED_OPEN",
                        fingerprint="dash-fp-1",
                        created_at=now,
                    ),
                    _job(
                        job_id="dash-2",
                        company_id=central.id,
                        status="DISCOVERED_URL_UNVERIFIED",
                        fingerprint="dash-fp-2",
                        created_at=now,
                    ),
                    _job(
                        job_id="dash-3",
                        company_id=local.id,
                        status="VERIFIED_OPEN",
                        fingerprint="dash-fp-3",
                        created_at=old,
                    ),
                ]
            )
            session.flush()

            session.add_all(
                [
                    ApplicationSession(
                        job_id="dash-1",
                        status="IN_PROGRESS",
                        channel="manual",
                        opened_url="https://example.com/dash-1",
                    ),
                    ApplicationSession(
                        job_id="dash-1",
                        status="SUBMITTED",
                        channel="browser_agent",
                        opened_url="https://example.com/dash-1",
                    ),
                    ApplicationSession(
                        job_id="dash-3",
                        status="INTERVIEWING",
                        channel="manual",
                        opened_url="https://example.com/dash-3",
                    ),
                    ApplicationSession(
                        job_id="dash-3",
                        status="OFFER",
                        channel="manual",
                        opened_url="https://example.com/dash-3",
                    ),
                ]
            )
            session.commit()
    finally:
        engine.dispose()

    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()

    assert payload["total_jobs"] == 3
    assert payload["new_jobs_today"] == 2
    assert payload["verified_open"] == 2
    assert payload["central_soe_jobs"] == 2
    assert payload["applications_total"] == 4
    assert payload["in_progress"] == 1
    assert payload["submitted"] == 1
    assert payload["interviewing"] == 1
    assert payload["offers"] == 1


def test_dashboard_summary_is_zero_safe(client):
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    assert response.json() == {
        "total_jobs": 0,
        "new_jobs_today": 0,
        "verified_open": 0,
        "central_soe_jobs": 0,
        "applications_total": 0,
        "in_progress": 0,
        "submitted": 0,
        "interviewing": 0,
        "offers": 0,
    }
