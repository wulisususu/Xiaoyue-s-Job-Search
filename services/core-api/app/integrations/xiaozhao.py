from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..jobs.company_resolver import resolve_company
from ..jobs.deduper import find_job, new_job_id
from ..models import Job, JobSource, utcnow
from .types import ImportSummary

SOURCE_ACTIVE = "ACTIVE"
SOURCE_STALE = "STALE"


def _identity_key(company_name: str, title: str, url: str, batch: str) -> str:
    """Stable per-record identity.

    URL is the anchor when present so that title/location/deadline edits do
    NOT spawn a new JobSource. Records without a URL fall back to
    company+title+batch, which matches the canonical-job fingerprint basis.
    """
    if url:
        identity = f"url|{company_name}|{url}"
    else:
        identity = f"nourl|{company_name}|{title}|{batch}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _record_hash(record: dict) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


def _merge_job_fields(job: Job, values: dict[str, str | None]) -> bool:
    changed = False
    for key, value in values.items():
        if value and getattr(job, key) != value:
            setattr(job, key, value)
            changed = True
    return changed


def _stale_unseen_sources(session: Session, source_name: str, seen_ids: set[int]) -> tuple[int, int]:
    """Mark ACTIVE sources of this run's source that disappeared upstream as
    STALE, and downgrade jobs whose every source is now STALE."""
    stale_candidates = session.scalars(
        select(JobSource).where(
            JobSource.source_name == source_name,
            JobSource.status == SOURCE_ACTIVE,
        )
    ).all()
    sources_staled = 0
    for source in stale_candidates:
        if source.id in seen_ids:
            continue
        source.status = SOURCE_STALE
        sources_staled += 1
    if sources_staled == 0:
        return 0, 0

    affected_job_ids = {
        source.job_id
        for source in stale_candidates
        if source.status == SOURCE_STALE
    }
    jobs_staled = 0
    for job_id in affected_job_ids:
        still_active = session.scalar(
            select(JobSource.id).where(
                JobSource.job_id == job_id,
                JobSource.status == SOURCE_ACTIVE,
            )
        )
        if still_active is None:
            job = session.get(Job, job_id)
            if job is not None and job.status != "STALE":
                job.status = "STALE"
                jobs_staled += 1
    return sources_staled, jobs_staled


def import_xiaozhao_payload(session: Session, payload: dict, source_name: str = "xiaozhao-radar") -> ImportSummary:
    updated = str(payload.get("updated") or "") or None
    records = payload.get("jobs") or []
    summary = ImportSummary()
    seen_source_ids: set[int] = set()
    for record in records:
        summary.records_seen += 1
        company_name = str(record.get("c") or "").strip()
        title = str(record.get("p") or "").strip() or "未标注岗位"
        location = str(record.get("l") or "").strip()
        batch = str(record.get("w") or "").strip()
        deadline = str(record.get("d") or "").strip()
        industry = str(record.get("ind") or record.get("t") or "").strip()
        url = str(record.get("u") or "").strip()
        company = resolve_company(session, company_name or "未知企业", create_unknown=False)
        if company is None:
            company = resolve_company(session, company_name or "未知企业", create_unknown=True)
            summary.companies_created += 1

        job, canonical_url, fingerprint = find_job(session, company_id=company.id, title=title, location=location, recruitment_batch=batch, url=url)
        if job is None:
            status = "DISCOVERED_URL_UNVERIFIED" if url else "DISCOVERED_NO_URL"
            job = Job(id=new_job_id(canonical_url, fingerprint), company_id=company.id, title=title, location=location, industry=industry, recruitment_batch=batch, deadline_text=deadline, apply_url=url, canonical_url=canonical_url, status=status, fingerprint=fingerprint, source_updated_at=updated)
            session.add(job)
            session.flush()
            summary.jobs_created += 1
        else:
            # Upstream edits must propagate to the canonical job even when the
            # record already exists: title rewrites, deadline extensions and
            # new locations all arrive through this branch.
            if not job.apply_url and url:
                job.apply_url = url
                job.canonical_url = canonical_url
                job.status = "DISCOVERED_URL_UNVERIFIED"
            _merge_job_fields(job, {
                "title": title,
                "location": location,
                "industry": industry,
                "recruitment_batch": batch,
                "deadline_text": deadline,
            })
            job.source_updated_at = updated or job.source_updated_at
            if job.status == "STALE":
                # A stale job just re-appeared upstream: revive it.
                job.status = "DISCOVERED_URL_UNVERIFIED" if url else "DISCOVERED_NO_URL"

        record_key = _identity_key(company_name or "未知企业", title, url, batch)
        new_hash = _record_hash(record)
        source = session.scalar(select(JobSource).where(JobSource.source_name == source_name, JobSource.source_record_key == record_key))
        if source is None:
            source = JobSource(
                job_id=job.id,
                source_name=source_name,
                source_record_key=record_key,
                record_hash=new_hash,
                source_url=url,
                raw_json=json.dumps(record, ensure_ascii=False, sort_keys=True),
                status=SOURCE_ACTIVE,
            )
            session.add(source)
            session.flush()
            summary.sources_created += 1
        else:
            source.last_seen_at = utcnow()
            if source.status == SOURCE_STALE:
                # Previously-stale record seen again: back to ACTIVE.
                source.status = SOURCE_ACTIVE
                job.status = "DISCOVERED_URL_UNVERIFIED" if url else "DISCOVERED_NO_URL"
            if source.record_hash != new_hash:
                summary.sources_updated += 1
            source.record_hash = new_hash
            source.raw_json = json.dumps(record, ensure_ascii=False, sort_keys=True)
            source.source_url = url or source.source_url
        seen_source_ids.add(source.id)

    summary.sources_staled, summary.jobs_staled = _stale_unseen_sources(session, source_name, seen_source_ids)
    session.commit()
    return summary


def import_xiaozhao(session: Session, jobs_json_path: Path) -> ImportSummary:
    payload = json.loads(jobs_json_path.read_text(encoding="utf-8"))
    return import_xiaozhao_payload(session, payload)
