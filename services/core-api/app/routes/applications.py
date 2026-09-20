from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import ApplicationEvent, ApplicationSession, Company, Job, ResumeVersion

router = APIRouter(prefix="/api/applications", tags=["applications"])

ALLOWED_STATUSES = {
    "OPENED",
    "IN_PROGRESS",
    "SUBMITTED",
    "INTERVIEWING",
    "OFFER",
    "REJECTED",
    "ABANDONED",
}

TERMINAL_STATUSES = {"REJECTED", "ABANDONED"}
ACTIVE_STATUSES = ALLOWED_STATUSES - TERMINAL_STATUSES

STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "OPENED": ("IN_PROGRESS", "SUBMITTED", "ABANDONED"),
    "IN_PROGRESS": ("SUBMITTED", "ABANDONED"),
    "SUBMITTED": ("INTERVIEWING", "OFFER", "REJECTED", "ABANDONED"),
    "INTERVIEWING": ("OFFER", "REJECTED", "ABANDONED"),
    "OFFER": ("ABANDONED",),
    "REJECTED": (),
    "ABANDONED": (),
}


class ApplicationStart(BaseModel):
    job_id: str = Field(min_length=1)
    channel: Literal["manual", "browser_agent"] = "manual"
    resume_version_id: str | None = Field(default=None, min_length=1)


class ApplicationStatusUpdate(BaseModel):
    status: str
    note: str | None = Field(default=None, max_length=1000)


class ApplicationRead(BaseModel):
    id: int
    job_id: str
    job_title: str
    company_name: str
    status: str
    allowed_next_statuses: list[str]
    channel: str
    resume_version_id: str | None
    opened_url: str
    opened_at: str
    updated_at: str


class ApplicationEventRead(BaseModel):
    id: int
    application_id: int
    event_type: str
    from_status: str | None
    to_status: str
    note: str | None
    created_at: str


def _read(session: Session, record: ApplicationSession) -> ApplicationRead:
    job = session.get(Job, record.job_id)
    company = session.get(Company, job.company_id) if job else None
    return ApplicationRead(
        id=record.id,
        job_id=record.job_id,
        job_title=job.title if job else "",
        company_name=company.name if company else "",
        status=record.status,
        allowed_next_statuses=list(STATUS_TRANSITIONS.get(record.status, ())),
        channel=record.channel,
        resume_version_id=record.resume_version_id,
        opened_url=record.opened_url,
        opened_at=record.opened_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _event_read(event: ApplicationEvent) -> ApplicationEventRead:
    return ApplicationEventRead(
        id=event.id,
        application_id=event.application_id,
        event_type=event.event_type,
        from_status=event.from_status,
        to_status=event.to_status,
        note=event.note,
        created_at=event.created_at.isoformat(),
    )


def _validate_resume_version(session: Session, resume_version_id: str | None) -> None:
    if resume_version_id is None:
        return
    if session.get(ResumeVersion, resume_version_id) is None:
        raise HTTPException(status_code=422, detail="resume_version_id does not exist")


@router.post("", response_model=ApplicationRead)
def start_application(body: ApplicationStart) -> ApplicationRead:
    """Create or reuse one active application attempt for job+channel.

    Terminal attempts remain immutable history. Repeated clicks while an
    application is still active reuse that attempt instead of creating
    duplicate CRM rows.
    """
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            job = session.get(Job, body.job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            entry_url = job.canonical_url or job.apply_url
            if not entry_url:
                raise HTTPException(status_code=409, detail="Job has no verified entry URL")
            _validate_resume_version(session, body.resume_version_id)

            existing = session.scalar(
                select(ApplicationSession)
                .where(
                    ApplicationSession.job_id == job.id,
                    ApplicationSession.status.in_(ACTIVE_STATUSES),
                    ApplicationSession.channel == body.channel,
                )
                .order_by(ApplicationSession.updated_at.desc(), ApplicationSession.id.desc())
                .limit(1)
            )
            if existing is not None:
                if (
                    body.resume_version_id is not None
                    and existing.resume_version_id != body.resume_version_id
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "An active application already exists for this job/channel "
                            "with a different resume version"
                        ),
                    )
                return _read(session, existing)

            record = ApplicationSession(
                job_id=job.id,
                opened_url=entry_url,
                channel=body.channel,
                resume_version_id=body.resume_version_id,
            )
            session.add(record)
            session.flush()
            session.add(
                ApplicationEvent(
                    application_id=record.id,
                    event_type="CREATED",
                    from_status=None,
                    to_status="OPENED",
                    note=None,
                )
            )
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
                select(ApplicationSession)
                .order_by(ApplicationSession.updated_at.desc(), ApplicationSession.id.desc())
            ).all()
            return [_read(session, record) for record in records]
    finally:
        engine.dispose()


@router.get("/{application_id}/events", response_model=list[ApplicationEventRead])
def list_application_events(application_id: int) -> list[ApplicationEventRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            if session.get(ApplicationSession, application_id) is None:
                raise HTTPException(status_code=404, detail="Application not found")
            events = session.scalars(
                select(ApplicationEvent)
                .where(ApplicationEvent.application_id == application_id)
                .order_by(ApplicationEvent.created_at.asc(), ApplicationEvent.id.asc())
            ).all()
            return [_event_read(event) for event in events]
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

            if body.status == record.status:
                return _read(session, record)

            allowed = STATUS_TRANSITIONS.get(record.status, ())
            if body.status not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Invalid application status transition {record.status} -> {body.status}; "
                        f"allowed next statuses: {list(allowed)}"
                    ),
                )

            previous = record.status
            record.status = body.status
            session.add(
                ApplicationEvent(
                    application_id=record.id,
                    event_type="STATUS_CHANGED",
                    from_status=previous,
                    to_status=body.status,
                    note=body.note.strip() if body.note and body.note.strip() else None,
                )
            )
            session.commit()
            session.refresh(record)
            return _read(session, record)
    finally:
        engine.dispose()
