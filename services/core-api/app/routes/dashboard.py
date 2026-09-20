from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import ApplicationSession, Company, Job

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class DashboardSummaryRead(BaseModel):
    total_jobs: int
    new_jobs_today: int
    verified_open: int
    central_soe_jobs: int
    applications_total: int
    in_progress: int
    submitted: int
    interviewing: int
    offers: int


def _local_day_start_utc() -> dt.datetime:
    local_now = dt.datetime.now().astimezone()
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(dt.timezone.utc)


@router.get("/summary", response_model=DashboardSummaryRead)
def dashboard_summary() -> DashboardSummaryRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            day_start = _local_day_start_utc()
            job_row = session.execute(
                select(
                    func.count(Job.id),
                    func.sum(case((Job.created_at >= day_start, 1), else_=0)),
                    func.sum(case((Job.status == "VERIFIED_OPEN", 1), else_=0)),
                    func.sum(case((Company.ownership == "central_soe", 1), else_=0)),
                ).select_from(Job).join(Company, Company.id == Job.company_id)
            ).one()

            application_row = session.execute(
                select(
                    func.count(ApplicationSession.id),
                    func.sum(case((ApplicationSession.status == "IN_PROGRESS", 1), else_=0)),
                    func.sum(case((ApplicationSession.status == "SUBMITTED", 1), else_=0)),
                    func.sum(case((ApplicationSession.status == "INTERVIEWING", 1), else_=0)),
                    func.sum(case((ApplicationSession.status == "OFFER", 1), else_=0)),
                )
            ).one()

            return DashboardSummaryRead(
                total_jobs=int(job_row[0] or 0),
                new_jobs_today=int(job_row[1] or 0),
                verified_open=int(job_row[2] or 0),
                central_soe_jobs=int(job_row[3] or 0),
                applications_total=int(application_row[0] or 0),
                in_progress=int(application_row[1] or 0),
                submitted=int(application_row[2] or 0),
                interviewing=int(application_row[3] or 0),
                offers=int(application_row[4] or 0),
            )
    finally:
        engine.dispose()
