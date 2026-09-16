from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import Company, Job
from app.verification.service import VerificationBatchResult
from app.verification.verifier import VerificationResult


def _seed_job():
    engine = get_engine(get_settings())
    with Session(engine) as session:
        company = Company(name='测试央企', normalized_name='测试央企', ownership='central_soe')
        session.add(company); session.flush()
        session.add(Job(
            id='route-job', company_id=company.id, title='视觉设计', location='南京', industry='设计',
            recruitment_batch='27届秋招', deadline_text='招满即止', apply_url='https://example.com/job',
            canonical_url='https://example.com/job', status='DISCOVERED_URL_UNVERIFIED', fingerprint='route-fp'
        ))
        session.commit()
    engine.dispose()


def test_verify_single_job_endpoint(client, monkeypatch):
    _seed_job()
    import app.routes.verification as route

    def fake_verify(session, job):
        job.status = 'VERIFIED_OPEN'
        session.commit()
        return VerificationResult(
            checked_url=job.apply_url, final_url='https://app.mokahr.com/job/1', redirect_chain=[job.apply_url],
            http_status=200, health='VERIFIED_APPLY', ats='moka', page_type='job_detail',
            apply_evidence=['立即申请'], content_fingerprint='fp'
        )

    monkeypatch.setattr(route, 'verify_job', fake_verify)
    response = client.post('/api/verification/jobs/route-job')
    assert response.status_code == 200
    data = response.json()
    assert data['health'] == 'VERIFIED_APPLY'
    assert data['ats'] == 'moka'


def test_run_due_verification_endpoint(client, monkeypatch):
    import app.routes.verification as route
    monkeypatch.setattr(route, 'verify_due_jobs', lambda session, limit=50: VerificationBatchResult(
        checked=7, verified_open=3, rediscovery_required=2, blocked=1, failed=1
    ))
    response = client.post('/api/verification/run-due?limit=20')
    assert response.status_code == 200
    assert response.json() == {
        'checked': 7,
        'verified_open': 3,
        'rediscovery_required': 2,
        'blocked': 1,
        'failed': 1,
    }
