from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine
from app.sources.store import record_sync_failure, record_sync_success
from app.sources.sync import SyncResult


def test_source_status_reports_latest_runs_and_last_good_snapshot(client):
    engine = get_engine(get_settings())
    with Session(engine) as session:
        record_sync_success(session, 'tencent-sheet', 'hash-1', '{"count":10}', remote_version='2026-09-16', items_seen=10)
        record_sync_failure(session, 'tencent-sheet', 'temporary outage')
        record_sync_success(session, 'workfind-online', 'hash-2', '{"kind":"bundle"}', items_seen=100)
    engine.dispose()

    response = client.get('/api/sources/status')
    assert response.status_code == 200
    data = {item['source_name']: item for item in response.json()}
    assert data['tencent-sheet']['last_run_status'] == 'FAILED'
    assert data['tencent-sheet']['last_good_version'] == '2026-09-16'
    assert data['tencent-sheet']['last_error'] == 'temporary outage'
    assert data['workfind-online']['last_run_status'] == 'SUCCESS'


def test_manual_tencent_sync_endpoint_returns_summary(client, monkeypatch):
    import app.routes.sources as route

    monkeypatch.setattr(route, 'sync_tencent_source', lambda session: SyncResult(
        source_name='tencent-sheet', status='SUCCESS', content_hash='abc', records_seen=25, jobs_created=4
    ))
    response = client.post('/api/sources/tencent/sync')
    assert response.status_code == 200
    assert response.json()['status'] == 'SUCCESS'
    assert response.json()['jobs_created'] == 4


def test_sync_due_endpoint_runs_scheduler(client, monkeypatch):
    import app.routes.sources as route

    monkeypatch.setattr(route, 'sync_due_sources', lambda session, cache_dir: [
        SyncResult(source_name='tencent-sheet', status='UNCHANGED', content_hash='abc')
    ])
    response = client.post('/api/sources/sync-due')
    assert response.status_code == 200
    assert response.json()[0]['source_name'] == 'tencent-sheet'
    assert response.json()[0]['status'] == 'UNCHANGED'
