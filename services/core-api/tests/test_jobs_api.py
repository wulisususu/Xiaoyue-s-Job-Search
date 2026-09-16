from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.models import Company, Job, JobSource, UrlObservation


def _seed_jobs() -> None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            central = Company(name='中国移动通信集团有限公司', normalized_name='中国移动通信集团', ownership='central_soe', province='北京')
            local = Company(name='江苏省铁路集团有限公司', normalized_name='江苏省铁路集团', ownership='local_soe', province='江苏')
            session.add_all([central, local]); session.flush()
            job1 = Job(
                id='job-central', company_id=central.id, title='视觉设计、宣传策划', location='南京', industry='通信',
                recruitment_batch='27届秋招', deadline_text='招满即止', apply_url='https://example.com/1',
                canonical_url='https://example.com/1', status='DISCOVERED_URL_UNVERIFIED', fingerprint='fp-central'
            )
            job2 = Job(
                id='job-local', company_id=local.id, title='品牌视觉设计', location='苏州', industry='交通',
                recruitment_batch='27届秋招', deadline_text='2026-10-01', apply_url='', canonical_url='',
                status='DISCOVERED_NO_URL', fingerprint='fp-local'
            )
            session.add_all([job1, job2]); session.flush()
            session.add(JobSource(job_id=job1.id, source_name='xiaozhao-radar', source_record_key='src-1', source_url=job1.apply_url))
            session.add(UrlObservation(job_id=job1.id, checked_url=job1.apply_url, final_url='https://app.mokahr.com/job/1', redirect_chain_json='[]', http_status=200, health='REDIRECTED', ats='moka', page_type='career_home', apply_evidence_json='[]'))
            session.commit()
    finally:
        engine.dispose()


def test_jobs_api_returns_company_and_provenance(client):
    _seed_jobs()
    response = client.get('/api/jobs')
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    first = next(item for item in data['items'] if item['id'] == 'job-central')
    assert first['company']['name'] == '中国移动通信集团有限公司'
    assert first['company']['ownership'] == 'central_soe'
    assert first['sources'] == ['xiaozhao-radar']
    assert first['status'] == 'DISCOVERED_URL_UNVERIFIED'
    assert first['verification_health'] == 'REDIRECTED'
    assert first['ats'] == 'moka'
    assert first['canonical_url'] == 'https://example.com/1'


def test_jobs_api_filters_by_ownership_status_query_and_location(client):
    _seed_jobs()
    assert client.get('/api/jobs?ownership=central_soe').json()['total'] == 1
    assert client.get('/api/jobs?status=DISCOVERED_NO_URL').json()['items'][0]['id'] == 'job-local'
    assert client.get('/api/jobs?q=宣传').json()['items'][0]['id'] == 'job-central'
    assert client.get('/api/jobs?location=苏州').json()['items'][0]['id'] == 'job-local'
    assert client.get('/api/jobs?industry=通信').json()['items'][0]['id'] == 'job-central'


def test_jobs_api_paginates(client):
    _seed_jobs()
    data = client.get('/api/jobs?limit=1&offset=1').json()
    assert data['total'] == 2
    assert len(data['items']) == 1
    assert data['limit'] == 1
    assert data['offset'] == 1


def test_job_stats_reports_verification_state_and_ownership(client):
    _seed_jobs()
    data = client.get('/api/jobs/stats').json()
    assert data == {
        'total': 2,
        'with_url_unverified': 1,
        'without_url': 1,
        'verified_open': 0,
        'rediscovery_required': 0,
        'central_soe': 1,
        'local_soe': 1,
        'unknown': 0,
    }
