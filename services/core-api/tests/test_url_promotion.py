"""URL promotion policy: upstream URL changes never touch the canonical job
until the new URL proves VERIFIED_APPLY."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.xiaozhao import import_xiaozhao_payload
from app.models import Base, Job, UrlCandidate
from app.verification.service import verify_job
from app.verification.verifier import HttpResponse


def _payload(url: str) -> dict:
    return {
        "updated": "2026-09-17",
        "count": 1,
        "jobs": [{
            "c": "中国移动", "p": "视觉设计师", "l": "南京", "e": "",
            "w": "批次:27届秋招", "d": "招满即止", "s": "腾讯文档校招雷达",
            "t": "其他", "ind": "通信", "u": url,
        }],
    }


VERIFY_BODY = "<h1>职位详情</h1><button>立即申请</button>"


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'promote.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_upstream_url_change_creates_candidate_without_touching_canonical(tmp_path):
    engine = _engine(tmp_path)
    old_url = "https://company.com/campus/2026"
    new_url = "https://career.company.com/campus/2027"
    with Session(engine) as session:
        import_xiaozhao_payload(session, _payload(old_url))
        job = session.scalar(select(Job))
        assert job.apply_url == old_url

        summary = import_xiaozhao_payload(session, _payload(new_url))
        assert summary.url_candidates_created == 1

        session.refresh(job)
        # Canonical job untouched: the old URL stays until the new one proves itself.
        assert job.apply_url == old_url
        assert job.canonical_url == old_url
        candidate = session.scalar(select(UrlCandidate))
        assert candidate is not None
        assert candidate.status == "PENDING"
        assert candidate.job_id == job.id
    engine.dispose()


def test_verified_candidate_is_promoted(tmp_path):
    engine = _engine(tmp_path)
    old_url = "https://company.com/campus/2026"
    new_url = "https://career.company.com/campus/2027"
    with Session(engine) as session:
        import_xiaozhao_payload(session, _payload(old_url))
        import_xiaozhao_payload(session, _payload(new_url))

        def transport(url: str) -> HttpResponse:
            if url == "https://career.company.com/campus/2027":
                return HttpResponse(200, url, VERIFY_BODY, [url])
            # Old portal is dead now.
            return HttpResponse(404, url, "not found", [url])

        verify_job(session, session.scalar(select(Job)), transport=transport)
        job = session.scalar(select(Job))
        assert job.apply_url == new_url
        assert job.canonical_url == new_url
        assert job.status == "VERIFIED_OPEN"
        candidate = session.scalar(select(UrlCandidate))
        assert candidate.status == "PROMOTED"
    engine.dispose()


def test_broken_candidate_is_discarded_and_canonical_untouched(tmp_path):
    engine = _engine(tmp_path)
    old_url = "https://company.com/campus/2026"
    new_url = "https://career.company.com/campus/2027"
    with Session(engine) as session:
        import_xiaozhao_payload(session, _payload(old_url))
        import_xiaozhao_payload(session, _payload(new_url))

        def transport(url: str) -> HttpResponse:
            if url == old_url:
                return HttpResponse(200, url, VERIFY_BODY, [url])
            return HttpResponse(404, url, "not found", [url])

        verify_job(session, session.scalar(select(Job)), transport=transport)
        job = session.scalar(select(Job))
        assert job.apply_url == old_url
        assert job.canonical_url == old_url
        candidate = session.scalar(select(UrlCandidate))
        assert candidate.status == "DISCARDED"
        assert candidate.verified_health == "BROKEN"
    engine.dispose()


def test_identical_url_does_not_create_duplicate_candidates(tmp_path):
    engine = _engine(tmp_path)
    url = "https://company.com/campus/2026"
    with Session(engine) as session:
        import_xiaozhao_payload(session, _payload(url))
        summary = import_xiaozhao_payload(session, _payload(url))
        assert summary.url_candidates_created == 0
        assert session.scalars(select(UrlCandidate)).all() == []
    engine.dispose()
