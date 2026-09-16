import json

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Company, Job, JobSource, UrlObservation
from app.verification.service import verify_job
from app.verification.verifier import HttpResponse


def _seed(session: Session) -> Job:
    company = Company(name='测试集团', normalized_name='测试集团', ownership='central_soe')
    session.add(company); session.flush()
    job = Job(
        id='job-1', company_id=company.id, title='视觉设计', location='南京', industry='设计',
        recruitment_batch='27届秋招', deadline_text='招满即止',
        apply_url='https://source.example.com/job/1',
        canonical_url='https://source.example.com/job/1',
        status='DISCOVERED_URL_UNVERIFIED', fingerprint='fp-1', source_updated_at='2026-09-16'
    )
    session.add(job); session.flush()
    session.add(JobSource(
        job_id=job.id, source_name='tencent-sheet', source_record_key='source-1',
        source_url='https://source.example.com/job/1', raw_json='{}'
    ))
    session.commit()
    return job


def test_verified_apply_promotes_canonical_url_but_preserves_source_url(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'verify.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = _seed(session)
        response = HttpResponse(
            200,
            'https://app.mokahr.com/campus-recruitment/acme/123',
            '<h1>职位详情</h1><button>立即申请</button>',
            ['https://source.example.com/job/1', 'https://app.mokahr.com/campus-recruitment/acme/123'],
        )
        result = verify_job(session, job, transport=lambda url: response)
        session.refresh(job)
        source = session.scalar(select(JobSource).where(JobSource.job_id == job.id))
        observation = session.scalar(select(UrlObservation).where(UrlObservation.job_id == job.id))

        assert result.health == 'VERIFIED_APPLY'
        assert job.status == 'VERIFIED_OPEN'
        assert job.apply_url == 'https://source.example.com/job/1'
        assert job.canonical_url == 'https://app.mokahr.com/campus-recruitment/acme/123'
        assert source is not None and source.source_url == 'https://source.example.com/job/1'
        assert observation is not None
        assert json.loads(observation.redirect_chain_json)[-1] == job.canonical_url
        assert observation.ats == 'moka'


def test_broken_url_marks_rediscovery_required_without_replacing_canonical(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'verify.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = _seed(session)
        original = job.canonical_url
        result = verify_job(
            session,
            job,
            transport=lambda url: HttpResponse(404, url, 'not found', [url]),
        )
        session.refresh(job)
        assert result.health == 'BROKEN'
        assert job.status == 'REDISCOVERY_REQUIRED'
        assert job.canonical_url == original


def test_career_home_does_not_unlock_application(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'verify.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        job = _seed(session)
        result = verify_job(
            session,
            job,
            transport=lambda url: HttpResponse(200, url, '<h1>校园招聘</h1><a>招聘职位</a>', [url]),
        )
        session.refresh(job)
        assert result.health == 'HEALTHY'
        assert job.status == 'DISCOVERED_URL_UNVERIFIED'
