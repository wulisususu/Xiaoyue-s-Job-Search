from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import Job
from ..verification.service import verify_due_jobs, verify_job

router = APIRouter(prefix="/api/verification", tags=["verification"])


class VerificationRead(BaseModel):
    checked_url: str
    final_url: str
    redirect_chain: list[str]
    http_status: int | None
    health: str
    ats: str | None
    page_type: str
    apply_evidence: list[str]
    content_fingerprint: str | None
    error: str | None = None


class VerificationBatchRead(BaseModel):
    checked: int
    verified_open: int
    rediscovery_required: int
    blocked: int
    failed: int


@router.post("/jobs/{job_id}", response_model=VerificationRead)
def verify_single_job(job_id: str) -> VerificationRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="job not found")
            if not job.apply_url and not job.canonical_url:
                raise HTTPException(status_code=400, detail="job has no URL")
            result = verify_job(session, job)
            return VerificationRead(
                checked_url=result.checked_url,
                final_url=result.final_url,
                redirect_chain=result.redirect_chain,
                http_status=result.http_status,
                health=result.health,
                ats=result.ats,
                page_type=result.page_type,
                apply_evidence=result.apply_evidence,
                content_fingerprint=result.content_fingerprint,
                error=result.error,
            )
    finally:
        engine.dispose()


@router.post("/run-due", response_model=VerificationBatchRead)
def run_due_verification(limit: int = Query(default=50, ge=1, le=200)) -> VerificationBatchRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            result = verify_due_jobs(session, limit=limit)
            return VerificationBatchRead(
                checked=result.checked,
                verified_open=result.verified_open,
                rediscovery_required=result.rediscovery_required,
                blocked=result.blocked,
                failed=result.failed,
            )
    finally:
        engine.dispose()
