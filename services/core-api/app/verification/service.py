from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job, UrlObservation
from .rediscovery import extract_rediscovery_candidates, persist_rediscovery_candidates
from .scheduler import next_verification_interval
from .verifier import Transport, VerificationResult, verify_url

MAX_CONCURRENCY = 8


@dataclass(slots=True)
class VerificationBatchResult:
    checked: int = 0
    verified_open: int = 0
    rediscovery_required: int = 0
    blocked: int = 0
    failed: int = 0
    requires_browser: int = 0


def _apply_result(session: Session, job: Job, result: VerificationResult) -> None:
    """Apply an already-fetched verification result to the session (DB-only)."""
    checked_url = (job.canonical_url or job.apply_url or "").strip()
    session.add(UrlObservation(job_id=job.id, checked_url=result.checked_url, final_url=result.final_url, redirect_chain_json=json.dumps(result.redirect_chain, ensure_ascii=False), http_status=result.http_status, health=result.health, ats=result.ats, page_type=result.page_type, apply_evidence_json=json.dumps(result.apply_evidence, ensure_ascii=False), content_fingerprint=result.content_fingerprint, error=result.error))
    if result.health == "VERIFIED_APPLY":
        job.status = "VERIFIED_OPEN"
        if result.final_url: job.canonical_url = result.final_url
    elif result.health in {"BROKEN", "STALE"}:
        job.status = "REDISCOVERY_REQUIRED"
    elif result.health == "REQUIRES_BROWSER":
        # Do not promote and do not penalize; a JS-capable agent must look.
        pass
    elif job.status == "VERIFIED_OPEN":
        job.status = "DISCOVERED_URL_UNVERIFIED"
    if result.health != "VERIFIED_APPLY" and result.body:
        candidates = extract_rediscovery_candidates(result.final_url or checked_url, result.body)
        persist_rediscovery_candidates(session, job.id, candidates)


def verify_job(session: Session, job: Job, transport: Transport | None = None) -> VerificationResult:
    checked_url = (job.canonical_url or job.apply_url or "").strip()
    if not checked_url:
        raise ValueError("job has no URL to verify")
    result = verify_url(checked_url, transport=transport)
    _apply_result(session, job, result)
    session.commit()
    return result


def _is_due(session: Session, job: Job, now: dt.datetime) -> bool:
    latest = session.scalar(select(UrlObservation).where(UrlObservation.job_id == job.id).order_by(UrlObservation.observed_at.desc()).limit(1))
    if latest is None: return True
    observed_at = latest.observed_at
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=dt.timezone.utc)
    interval = next_verification_interval(job.status, job.deadline_text, now.date())
    return observed_at + interval <= now


def _domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def verify_due_jobs(session: Session, limit: int = 50, transport: Transport | None = None, now: dt.datetime | None = None) -> VerificationBatchResult:
    """Verify due jobs with bounded, per-domain serialized concurrency.

    The network phase (slow, GIL-free) runs on a thread pool; DB writes are
    applied strictly on the caller's session afterwards. Jobs targeting the
    same hostname are executed serially within one worker so a single ATS
    host is never hammered in parallel.
    """
    resolved_now = now or dt.datetime.now(dt.timezone.utc)
    jobs = session.scalars(select(Job).where(Job.apply_url != "").order_by(Job.updated_at.desc())).all()
    due: list[Job] = []
    for job in jobs:
        if len(due) >= limit:
            break
        if _is_due(session, job, resolved_now):
            due.append(job)

    # Partition by hostname: each group runs serially in one worker.
    groups: dict[str, list[Job]] = defaultdict(list)
    for job in due:
        groups[_domain_of(job.canonical_url or job.apply_url)].append(job)

    def run_group(group_jobs: list[Job]) -> list[tuple[Job, VerificationResult]]:
        results: list[tuple[Job, VerificationResult]] = []
        for job in group_jobs:
            url = (job.canonical_url or job.apply_url or "").strip()
            results.append((job, verify_url(url, transport=transport)))
        return results

    max_workers = min(MAX_CONCURRENCY, len(groups)) if groups else 0
    fetched: list[tuple[Job, VerificationResult]] = []
    if max_workers:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for group_results in pool.map(run_group, groups.values()):
                fetched.extend(group_results)
    else:
        fetched = [(job, verify_url((job.canonical_url or job.apply_url).strip(), transport=transport)) for job in due]

    summary = VerificationBatchResult(checked=len(fetched))
    for job, result in fetched:
        session.add(job)
        _apply_result(session, job, result)
        if result.health == "VERIFIED_APPLY": summary.verified_open += 1
        elif result.health in {"BROKEN", "STALE"}: summary.rediscovery_required += 1
        elif result.health == "ACCESS_BLOCKED": summary.blocked += 1
        elif result.health == "REQUIRES_BROWSER": summary.requires_browser += 1
        elif result.error: summary.failed += 1
    session.commit()
    return summary
