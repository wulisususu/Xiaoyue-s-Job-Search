from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import Company, Job, JobSource, UrlObservation

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class CompanyRead(BaseModel):
    id: int
    name: str
    ownership: str
    province: str | None = None
    level: str | None = None


class JobRead(BaseModel):
    id: str
    company: CompanyRead
    title: str
    location: str
    industry: str
    recruitment_batch: str
    deadline_text: str
    apply_url: str
    canonical_url: str
    status: str
    verification_health: str | None = None
    ats: str | None = None
    last_verified_at: str | None = None
    source_updated_at: str | None = None
    sources: list[str]


class JobListRead(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int


class JobStatsRead(BaseModel):
    total: int
    with_url_unverified: int
    without_url: int
    verified_open: int
    rediscovery_required: int
    central_soe: int
    local_soe: int
    unknown: int


def _filters(
    q: str | None,
    ownership: str | None,
    status: str | None,
    industry: str | None,
    location: str | None,
):
    clauses = []
    if q:
        needle = f"%{q.strip()}%"
        clauses.append(or_(Job.title.like(needle), Company.name.like(needle)))
    if ownership:
        clauses.append(Company.ownership == ownership)
    if status:
        clauses.append(Job.status == status)
    if industry:
        clauses.append(Job.industry == industry)
    if location:
        clauses.append(Job.location.like(f"%{location.strip()}%"))
    return clauses


@router.get("/stats", response_model=JobStatsRead)
def job_stats() -> JobStatsRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            total = session.scalar(select(func.count(Job.id))) or 0
            with_url = session.scalar(
                select(func.count(Job.id)).where(Job.status == "DISCOVERED_URL_UNVERIFIED")
            ) or 0
            without_url = session.scalar(
                select(func.count(Job.id)).where(Job.status == "DISCOVERED_NO_URL")
            ) or 0
            verified_open = session.scalar(
                select(func.count(Job.id)).where(Job.status == "VERIFIED_OPEN")
            ) or 0
            rediscovery_required = session.scalar(
                select(func.count(Job.id)).where(Job.status == "REDISCOVERY_REQUIRED")
            ) or 0

            def ownership_count(value: str) -> int:
                return int(
                    session.scalar(
                        select(func.count(Job.id))
                        .join(Company, Company.id == Job.company_id)
                        .where(Company.ownership == value)
                    )
                    or 0
                )

            return JobStatsRead(
                total=int(total),
                with_url_unverified=int(with_url),
                without_url=int(without_url),
                verified_open=int(verified_open),
                rediscovery_required=int(rediscovery_required),
                central_soe=ownership_count("central_soe"),
                local_soe=ownership_count("local_soe"),
                unknown=ownership_count("unknown"),
            )
    finally:
        engine.dispose()


@router.get("", response_model=JobListRead)
def list_jobs(
    q: str | None = None,
    ownership: str | None = None,
    status: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JobListRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            clauses = _filters(q, ownership, status, industry, location)
            base = select(Job, Company).join(Company, Company.id == Job.company_id)
            count_query = select(func.count(Job.id)).join(Company, Company.id == Job.company_id)
            if clauses:
                base = base.where(*clauses)
                count_query = count_query.where(*clauses)
            total = int(session.scalar(count_query) or 0)
            rows = session.execute(
                base.order_by(Job.source_updated_at.desc(), Company.name, Job.title).offset(offset).limit(limit)
            ).all()
            items: list[JobRead] = []
            for job, company in rows:
                sources = session.scalars(
                    select(JobSource.source_name)
                    .where(JobSource.job_id == job.id)
                    .distinct()
                    .order_by(JobSource.source_name)
                ).all()
                latest_observation = session.scalar(
                    select(UrlObservation)
                    .where(UrlObservation.job_id == job.id)
                    .order_by(UrlObservation.observed_at.desc(), UrlObservation.id.desc())
                    .limit(1)
                )
                items.append(
                    JobRead(
                        id=job.id,
                        company=CompanyRead(
                            id=company.id,
                            name=company.name,
                            ownership=company.ownership,
                            province=company.province,
                            level=company.level,
                        ),
                        title=job.title,
                        location=job.location,
                        industry=job.industry,
                        recruitment_batch=job.recruitment_batch,
                        deadline_text=job.deadline_text,
                        apply_url=job.apply_url,
                        canonical_url=job.canonical_url,
                        status=job.status,
                        verification_health=latest_observation.health if latest_observation else None,
                        ats=latest_observation.ats if latest_observation else None,
                        last_verified_at=latest_observation.observed_at.isoformat() if latest_observation else None,
                        source_updated_at=job.source_updated_at,
                        sources=list(sources),
                    )
                )
            return JobListRead(items=items, total=total, limit=limit, offset=offset)
    finally:
        engine.dispose()
