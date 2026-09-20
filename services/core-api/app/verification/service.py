from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Job, UrlCandidate, UrlObservation
from .rediscovery import extract_rediscovery_candidates, persist_rediscovery_candidates
from .scheduler import next_verification_interval
from .verifier import Transport, VerificationResult, verify_url

MAX_CONCURRENCY = 8
MAX_CANDIDATE_CHECKS_PER_RUN = 2


def _observe(session: Session, job_id: str, result: VerificationResult) -> None:
    session.add(UrlObservation(job_id=job_id, checked_url=result.checked_url, final_url=result.final_url, redirect_chain_json=json.dumps(result.redirect_chain, ensure_ascii=False), http_status=result.http_status, health=result.health, ats=result.ats, page_type=result.page_type, apply_evidence_json=json.dumps(result.apply_evidence, ensure_ascii=False), content_fingerprint=result.content_fingerprint, error=result.error))


def _promote_url_candidates(session: Session, job: Job, transport: Transport | None) -> bool:
    """URL promotion policy, decision side.

    Verify PENDING candidates for this job; a candidate that proves
    VERIFIED_APPLY is promoted to apply_url/canonical_url and flips the job
    to VERIFIED_OPEN. Broken candidates are DISCARDED. Returns True when a
    promotion happened.
    """
    candidates = session.scalars(
        select(UrlCandidate)
        .where(UrlCandidate.job_id == job.id, UrlCandidate.status == "PENDING")
        .order_by(UrlCandidate.discovered_at.desc(), UrlCandidate.id.desc())
        .limit(MAX_CANDIDATE_CHECKS_PER_RUN)
    ).all()
    for candidate in candidates:
        result = verify_url(candidate.url, transport=transport)
        _observe(session, job.id, result)
        candidate.verified_health = result.health
        if result.health == "VERIFIED_APPLY":
            job.apply_url = candidate.url
            job.canonical_url = result.final_url or candidate.url
            job.status = "VERIFIED_OPEN"
            candidate.status = "PROMOTED"
            return True
        if result.health in {"BROKEN", "STALE"}:
            candidate.status = "DISCARDED"
    return False


def promote_browser_verified(
    session: Session,
    job: Job,
    *,
    checked_url: str,
    final_url: str,
    evidence: list[str],
    content_fingerprint: str,
) -> None:
    """Promote a job after a user-visible browser proves an application form.

    Browser verification is intentionally separate from static HTTP
    verification. The observed browser URL is recorded for audit, but is not
    persisted as canonical_url because authenticated SPA URLs may contain
    short-lived session state.
    """
    session.add(
        UrlObservation(
            job_id=job.id,
            checked_url=checked_url,
            final_url=final_url,
            redirect_chain_json="[]",
            http_status=None,
            health="BROWSER_VERIFIED",
            ats=None,
            page_type="application_form",
            apply_evidence_json=json.dumps(evidence, ensure_ascii=False),
            content_fingerprint=content_fingerprint,
            error=None,
        )
    )
    job.status = "VERIFIED_OPEN"
    interval = next_verification_interval(
        job.status,
        job.deadline_text,
        dt.datetime.now(dt.timezone.utc).date(),
    )
    job.next_verification_at = dt.datetime.now(dt.timezone.utc) + interval


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
    elif result.health in {"ACCESS_BLOCKED", "LOGIN_REQUIRED", "REQUIRES_BROWSER"}:
        # Transient / inconclusive: WAF, anti-bot, rate limiting or a JS
        # shell say nothing about whether the job is closed. A VERIFIED_OPEN
        # job keeps its verified status; the observation records the detail.
        pass
    elif job.status == "VERIFIED_OPEN":
        job.status = "DISCOVERED_URL_UNVERIFIED"
    if result.health != "VERIFIED_APPLY" and result.body:
        candidates = extract_rediscovery_candidates(result.final_url or checked_url, result.body)
        persist_rediscovery_candidates(session, job.id, candidates)
    # Maintain the scheduler hint: next due time per the interval policy.
    interval = next_verification_interval(
        job.status,
        job.deadline_text,
        dt.datetime.now(dt.timezone.utc).date(),
    )
    job.next_verification_at = dt.datetime.now(dt.timezone.utc) + interval


def verify_job(session: Session, job: Job, transport: Transport | None = None) -> VerificationResult:
    checked_url = (job.canonical_url or job.apply_url or "").strip()
    if not checked_url:
        raise ValueError("job has no URL to verify")
    result = verify_url(checked_url, transport=transport)
    _apply_result(session, job, result)
    # Candidates are evaluated on every verify run regardless of the main
    # result: an upstream URL rewrite must get its chance even while the old
    # portal is still technically alive.
    _promote_url_candidates(session, job, transport)
    session.commit()
    return result


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
    # Single-query due selection: jobs.next_verification_at is maintained on
    # every verification, so there is no per-job observation scan here.
    # NULL next_verification_at = never verified = due.
    due = session.scalars(
        select(Job)
        .where(
            Job.apply_url != "",
            or_(Job.next_verification_at.is_(None), Job.next_verification_at <= resolved_now),
        )
        .order_by(Job.updated_at.desc())
        .limit(limit)
    ).all()

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
        _promote_url_candidates(session, job, transport)
        if result.health == "VERIFIED_APPLY": summary.verified_open += 1
        elif result.health in {"BROKEN", "STALE"}: summary.rediscovery_required += 1
        elif result.health == "ACCESS_BLOCKED": summary.blocked += 1
        elif result.health == "REQUIRES_BROWSER": summary.requires_browser += 1
        elif result.error: summary.failed += 1
    session.commit()
    return summary
