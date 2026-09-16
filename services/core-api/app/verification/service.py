from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, UrlObservation
from .rediscovery import extract_rediscovery_candidates, persist_rediscovery_candidates
from .scheduler import next_verification_interval
from .verifier import Transport, VerificationResult, verify_url


@dataclass(slots=True)
class VerificationBatchResult:
    checked: int = 0
    verified_open: int = 0
    rediscovery_required: int = 0
    blocked: int = 0
    failed: int = 0


def verify_job(session: Session, job: Job, transport: Transport | None = None) -> VerificationResult:
    checked_url = (job.canonical_url or job.apply_url or "").strip()
    if not checked_url:
        raise ValueError("job has no URL to verify")
    result = verify_url(checked_url, transport=transport)
    session.add(UrlObservation(job_id=job.id, checked_url=result.checked_url, final_url=result.final_url, redirect_chain_json=json.dumps(result.redirect_chain, ensure_ascii=False), http_status=result.http_status, health=result.health, ats=result.ats, page_type=result.page_type, apply_evidence_json=json.dumps(result.apply_evidence, ensure_ascii=False), content_fingerprint=result.content_fingerprint, error=result.error))
    if result.health == "VERIFIED_APPLY":
        job.status = "VERIFIED_OPEN"
        if result.final_url: job.canonical_url = result.final_url
    elif result.health in {"BROKEN", "STALE"}:
        job.status = "REDISCOVERY_REQUIRED"
    elif job.status == "VERIFIED_OPEN":
        job.status = "DISCOVERED_URL_UNVERIFIED"
    if result.health != "VERIFIED_APPLY" and result.body:
        candidates = extract_rediscovery_candidates(result.final_url or checked_url, result.body)
        persist_rediscovery_candidates(session, job.id, candidates)
    session.commit(); return result


def _is_due(session: Session, job: Job, now: dt.datetime) -> bool:
    latest = session.scalar(select(UrlObservation).where(UrlObservation.job_id == job.id).order_by(UrlObservation.observed_at.desc()).limit(1))
    if latest is None: return True
    observed_at = latest.observed_at
    if observed_at.tzinfo is None: observed_at = observed_at.replace(tzinfo=dt.timezone.utc)
    interval = next_verification_interval(job.status, job.deadline_text, now.date())
    return observed_at + interval <= now


def verify_due_jobs(session: Session, limit: int = 50, transport: Transport | None = None, now: dt.datetime | None = None) -> VerificationBatchResult:
    resolved_now = now or dt.datetime.now(dt.timezone.utc)
    jobs = session.scalars(select(Job).where(Job.apply_url != "").order_by(Job.updated_at.desc())).all()
    summary = VerificationBatchResult()
    for job in jobs:
        if summary.checked >= limit: break
        if not _is_due(session, job, resolved_now): continue
        result = verify_job(session, job, transport=transport); summary.checked += 1
        if result.health == "VERIFIED_APPLY": summary.verified_open += 1
        elif result.health in {"BROKEN", "STALE"}: summary.rediscovery_required += 1
        elif result.health == "ACCESS_BLOCKED": summary.blocked += 1
        elif result.error: summary.failed += 1
    return summary
