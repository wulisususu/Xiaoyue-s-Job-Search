from __future__ import annotations

from fastapi import APIRouter, HTTPException
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import ApplicationSession, Company, Job

router = APIRouter(prefix="/api/applications", tags=["applications"])

ALLOWED_STATUSES = {"OPENED", "IN_PROGRESS", "SUBMITTED", "INTERVIEWING", "OFFER", "REJECTED", "ABANDONED"}


class ApplicationStart(BaseModel):
    job_id: str = Field(min_length=1)
    channel: Literal["manual", "browser_agent"] = "manual"


class ApplicationStatusUpdate(BaseModel):
    status: str


class ApplicationRead(BaseModel):
    id: int
    job_id: str
    job_title: str
    company_name: str
    status: str
    channel: str
    opened_url: str
    opened_at: str
    updated_at: str


def _read(session: Session, record: ApplicationSession) -> ApplicationRead:
    job = session.get(Job, record.job_id)
    company = session.get(Company, job.company_id) if job else None
    return ApplicationRead(
        id=record.id,
        job_id=record.job_id,
        job_title=job.title if job else "",
        company_name=company.name if company else "",
        status=record.status,
        channel=record.channel,
        opened_url=record.opened_url,
        opened_at=record.opened_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


@router.post("", response_model=ApplicationRead)
def start_application(body: ApplicationStart) -> ApplicationRead:
    """开始申请: record an OPENED session for a verified job and hand back
    the entry URL the shell should open. Reuses the existing OPENED session
    instead of spamming duplicates on repeated clicks."""
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            job = session.get(Job, body.job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            entry_url = job.canonical_url or job.apply_url
            if not entry_url:
                raise HTTPException(status_code=409, detail="Job has no verified entry URL")

            existing = session.scalar(
                select(ApplicationSession)
                .where(
                    ApplicationSession.job_id == job.id,
                    ApplicationSession.status == "OPENED",
                    ApplicationSession.channel == body.channel,
                )
                .order_by(ApplicationSession.id.desc())
                .limit(1)
            )
            if existing is not None:
                return _read(session, existing)

            record = ApplicationSession(job_id=job.id, opened_url=entry_url, channel=body.channel)
            session.add(record)
            session.commit()
            session.refresh(record)
            return _read(session, record)
    finally:
        engine.dispose()


@router.get("", response_model=list[ApplicationRead])
def list_applications() -> list[ApplicationRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            records = session.scalars(
                select(ApplicationSession).order_by(ApplicationSession.updated_at.desc(), ApplicationSession.id.desc())
            ).all()
            return [_read(session, record) for record in records]
    finally:
        engine.dispose()


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application_status(application_id: int, body: ApplicationStatusUpdate) -> ApplicationRead:
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            record = session.get(ApplicationSession, application_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Application not found")
            record.status = body.status
            session.commit()
            session.refresh(record)
            return _read(session, record)
    finally:
        engine.dispose()
