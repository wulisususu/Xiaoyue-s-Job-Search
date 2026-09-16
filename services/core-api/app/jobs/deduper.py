from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job
from .identity import job_fingerprint, normalize_job_url


def _job_id(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def find_job(
    session: Session,
    *,
    company_id: int,
    title: str,
    location: str,
    recruitment_batch: str,
    url: str = "",
) -> tuple[Job | None, str, str]:
    canonical_url = normalize_job_url(url, provider="company") if url else ""
    if canonical_url:
        by_url = session.scalar(select(Job).where(Job.canonical_url == canonical_url))
        if by_url is not None:
            return by_url, canonical_url, by_url.fingerprint

    fingerprint = job_fingerprint(str(company_id), title, location, recruitment_batch)
    by_fingerprint = session.scalar(select(Job).where(Job.fingerprint == fingerprint))
    return by_fingerprint, canonical_url, fingerprint


def new_job_id(canonical_url: str, fingerprint: str) -> str:
    return _job_id(f"url:{canonical_url}" if canonical_url else f"fp:{fingerprint}")
