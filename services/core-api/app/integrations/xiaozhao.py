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


def _source_key(record: dict) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def import_xiaozhao(session: Session, jobs_json_path: Path) -> ImportSummary:
    payload = json.loads(jobs_json_path.read_text(encoding="utf-8"))
    updated = str(payload.get("updated") or "") or None
    records = payload.get("jobs") or []
    summary = ImportSummary()

    for record in records:
        summary.records_seen += 1
        company_name = str(record.get("c") or "").strip()
        title = str(record.get("p") or "").strip() or "未标注岗位"
        location = str(record.get("l") or "").strip()
        batch = str(record.get("w") or "").strip()
        deadline = str(record.get("d") or "").strip()
        industry = str(record.get("ind") or record.get("t") or "").strip()
        url = str(record.get("u") or "").strip()

        company_label = company_name or "未知企业"
        company = resolve_company(session, company_label, create_unknown=False)
        if company is None:
            company = resolve_company(session, company_label, create_unknown=True)
            summary.companies_created += 1
        assert company is not None

        job, canonical_url, fingerprint = find_job(
            session,
            company_id=company.id,
            title=title,
            location=location,
            recruitment_batch=batch,
            url=url,
        )
        if job is None:
            status = "DISCOVERED_URL_UNVERIFIED" if url else "DISCOVERED_NO_URL"
            job = Job(
                id=new_job_id(canonical_url, fingerprint),
                company_id=company.id,
                title=title,
                location=location,
                industry=industry,
                recruitment_batch=batch,
                deadline_text=deadline,
                apply_url=url,
                canonical_url=canonical_url,
                status=status,
                fingerprint=fingerprint,
                source_updated_at=updated,
            )
            session.add(job)
            session.flush()
            summary.jobs_created += 1
        else:
            if not job.apply_url and url:
                job.apply_url = url
                job.canonical_url = canonical_url
                job.status = "DISCOVERED_URL_UNVERIFIED"
            if not job.industry and industry:
                job.industry = industry
            job.source_updated_at = updated or job.source_updated_at

        record_key = _source_key(record)
        source = session.scalar(
            select(JobSource).where(
                JobSource.source_name == "xiaozhao-radar",
                JobSource.source_record_key == record_key,
            )
        )
        if source is None:
            session.add(
                JobSource(
                    job_id=job.id,
                    source_name="xiaozhao-radar",
                    source_record_key=record_key,
                    source_url=url,
                    raw_json=json.dumps(record, ensure_ascii=False, sort_keys=True),
                )
            )
            summary.sources_created += 1
        else:
            source.last_seen_at = utcnow()

    session.commit()
    return summary
