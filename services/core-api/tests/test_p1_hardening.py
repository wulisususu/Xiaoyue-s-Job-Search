"""P1 hardening: company resolver tri-state, dedupe granularity, DNS pinning."""

from __future__ import annotations

import socket

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.jobs.company_resolver import (
    AMBIGUOUS,
    NOT_FOUND,
    RESOLVED,
    resolve_company,
    resolve_company_detailed,
)
from app.jobs.deduper import find_job
from app.jobs.identity import is_generic_career_url, job_identity_url
from app.models import Base, Company, Job
from app.verification.verifier import _PinnedHTTPConnection, _resolve_pinned_ip
from app.verification.url_guard import validate_external_url


def _engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p1.db'}")
    Base.metadata.create_all(engine)
    return engine


# --- Company resolver tri-state -------------------------------------------


def test_resolver_ambiguity_never_creates_a_third_company(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        # Same normalized identity ("中国xx"), different ownership: allowed
        # by the identity constraint, but the resolver must treat it as
        # AMBIGUOUS. ("中国XX公司" normalizes to "中国xx" — strip 公司.)
        session.add(Company(name="中国XX集团", normalized_name="中国xx", ownership="central_soe"))
        session.add(Company(name="中国XX控股", normalized_name="中国xx", ownership="unknown"))
        session.commit()

        resolution = resolve_company_detailed(session, "中国XX公司", create_unknown=True)
        assert resolution.state == AMBIGUOUS
        assert len(resolution.candidates) == 2

        # Legacy helper: deterministic reuse, and NO new entity.
        reused = resolve_company(session, "中国XX公司", create_unknown=True)
        assert reused is not None
        companies = session.scalars(select(Company).where(Company.normalized_name == "中国xx")).all()
        assert len(companies) == 2
        assert reused.id == min(company.id for company in companies)

        # And the identity constraint itself blocks exact duplicates.
        session.add(Company(name="中国XX三四五", normalized_name="中国xx", ownership="central_soe"))
        with pytest.raises(Exception):
            session.flush()
        session.rollback()
    engine.dispose()


def test_resolver_states_are_distinguishable(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        assert resolve_company_detailed(session, "不存在公司", create_unknown=False).state == NOT_FOUND

        created = resolve_company_detailed(session, "某新公司", create_unknown=True)
        assert created.state == RESOLVED

        again = resolve_company_detailed(session, "某新公司", create_unknown=False)
        assert again.state == RESOLVED
        assert again.company.id == created.company.id
    engine.dispose()


# --- Dedupe granularity ----------------------------------------------------


def test_generic_career_urls_are_not_job_identity(tmp_path):
    assert is_generic_career_url("https://company.com/campus")
    assert is_generic_career_url("https://company.com/campus/")
    assert is_generic_career_url("https://company.com/jobs?x=1")
    assert not is_generic_career_url("https://company.com/campus/job/123")
    assert job_identity_url("https://company.com/campus") == ""
    assert job_identity_url("https://company.com/campus/job/123") != ""


def test_two_jobs_sharing_a_generic_portal_url_stay_separate(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
        session.add(company)
        session.flush()

        shared_portal = "https://company.com/campus"
        job1, _, _ = find_job(session, company_id=company.id, title="视觉设计", location="南京", recruitment_batch="27届", url=shared_portal)
        assert job1 is None  # first occurrence: nothing to merge with

        # Second, genuinely different job pointing at the SAME portal URL.
        job2, canonical2, _ = find_job(session, company_id=company.id, title="软件开发", location="北京", recruitment_batch="27届", url=shared_portal)
        assert job2 is None, "a generic careers URL must not merge different jobs"
        assert canonical2 == "", "generic URL must not become a canonical identity"
    engine.dispose()


def test_specific_urls_still_dedupe(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine) as session:
        company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
        session.add(company)
        session.flush()

        url = "https://company.com/campus/job/123"
        first = find_job(session, company_id=company.id, title="视觉设计", location="南京", recruitment_batch="27届", url=url)
        assert first[0] is None
        job = Job(
            id="job-x", company_id=company.id, title="视觉设计", location="南京", industry="",
            recruitment_batch="27届", deadline_text="", apply_url=url, canonical_url=first[1],
            status="DISCOVERED_URL_UNVERIFIED", fingerprint=first[2],
        )
        session.add(job)
        session.commit()

        again, canonical, _ = find_job(session, company_id=company.id, title="视觉设计", location="南京", recruitment_batch="27届", url=url + "?utm_source=x")
        assert again is not None and again.id == "job-x"
        assert canonical == first[1]
    engine.dispose()


# --- DNS pinning ------------------------------------------------------------


def test_pinned_ip_resolution_rejects_private_hosts():
    with pytest.raises(ValueError):
        _resolve_pinned_ip("localhost")
    with pytest.raises(ValueError):
        validate_external_url("http://127.0.0.1:8080/x")


def test_pinned_http_connection_connects_to_the_validated_ip(monkeypatch):
    attempted: list[tuple[str, int]] = []

    def fake_create_connection(address, *args, **kwargs):
        attempted.append((address[0], address[1]))
        raise OSError("stop before real network I/O")

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    connection = _PinnedHTTPConnection("example.com", pinned_ip="93.184.216.34")
    with pytest.raises(OSError):
        connection.connect()
    # The socket targeted the VALIDATED IP, not a second DNS resolution.
    assert attempted == [("93.184.216.34", 80)]
