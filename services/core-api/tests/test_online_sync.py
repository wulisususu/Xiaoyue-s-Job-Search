import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Job, JobSource, SourceSnapshot, SourceSyncRun
from app.sources.sync import sync_tencent_source, sync_workfind_bundle


def _tencent_payload():
    return {
        'updated': '2026-09-16',
        'count': 1,
        'jobs': [{
            'c': '中国移动', 'p': '视觉设计', 'l': '南京', 'e': '',
            'w': '批次:27届秋招', 'd': '招满即止', 's': '腾讯文档校招雷达',
            't': '其他', 'ind': '通信运营商', 'u': 'https://example.com/apply',
        }],
    }


def test_tencent_sync_imports_new_snapshot_and_skips_unchanged(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = sync_tencent_source(session, payload_loader=_tencent_payload)
        second = sync_tencent_source(session, payload_loader=_tencent_payload)
        assert first.status == 'SUCCESS'
        assert first.jobs_created == 1
        assert second.status == 'UNCHANGED'
        assert second.jobs_created == 0
        assert len(session.scalars(select(SourceSnapshot)).all()) == 1
        assert len(session.scalars(select(Job)).all()) == 1
        source = session.scalar(select(JobSource))
        assert source is not None and source.source_name == 'tencent-sheet'


def test_tencent_sync_failure_keeps_last_known_good_snapshot(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ok = sync_tencent_source(session, payload_loader=_tencent_payload)
        failed = sync_tencent_source(session, payload_loader=lambda: (_ for _ in ()).throw(RuntimeError('offline')))
        assert ok.status == 'SUCCESS'
        assert failed.status == 'FAILED'
        assert failed.error == 'offline'
        assert len(session.scalars(select(SourceSnapshot)).all()) == 1
        runs = session.scalars(select(SourceSyncRun).order_by(SourceSyncRun.id)).all()
        assert [r.status for r in runs] == ['SUCCESS', 'FAILED']
        assert len(session.scalars(select(Job)).all()) == 1


def _workfind_db_bytes(path: Path) -> bytes:
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE provinces (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, province_id INTEGER, name TEXT NOT NULL, level TEXT);
        CREATE TABLE central_enterprises (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO provinces VALUES (1, '江苏')")
    con.execute("INSERT INTO companies VALUES (1, 1, '江苏省铁路集团有限公司', '省级')")
    con.execute("INSERT INTO central_enterprises VALUES (1, '中国移动通信集团有限公司')")
    con.commit(); con.close()
    return path.read_bytes()


def test_workfind_bundle_sync_uses_remote_bytes_and_is_idempotent(tmp_path):
    source_db = tmp_path / 'source.db'
    db_bytes = _workfind_db_bytes(source_db)
    relations = json.dumps([
        {'parent': '中国移动', 'name': '中移互联网有限公司(中国移动子公司)'}
    ], ensure_ascii=False).encode('utf-8')
    payloads = {'db': db_bytes, 'relations': relations}
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = sync_workfind_bundle(session, cache_dir=tmp_path / 'cache', fetch_bytes=lambda kind: payloads[kind])
        second = sync_workfind_bundle(session, cache_dir=tmp_path / 'cache', fetch_bytes=lambda kind: payloads[kind])
        assert first.status == 'SUCCESS'
        assert first.companies_created == 3
        assert second.status == 'UNCHANGED'
        assert second.companies_created == 0
        snapshot_dir = tmp_path / 'cache' / 'snapshots' / first.content_hash
        assert (snapshot_dir / '国企数据库.db').exists()
        assert (snapshot_dir / '央企二级子公司.json').exists()
        assert (tmp_path / 'cache' / 'current.txt').read_text(encoding='utf-8') == first.content_hash


def test_workfind_failed_sync_preserves_last_known_good_snapshot(tmp_path):
    source_db = tmp_path / 'source.db'
    good_db = _workfind_db_bytes(source_db)
    good_relations = b'[]'
    good_payloads = {'db': good_db, 'relations': good_relations}

    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        cache = tmp_path / 'cache'
        ok = sync_workfind_bundle(session, cache_dir=cache, fetch_bytes=lambda kind: good_payloads[kind])
        assert ok.status == 'SUCCESS'
        good_hash = ok.content_hash

        # A corrupt relations file arrives: import must fail WITHOUT
        # touching the last known good snapshot or the current pointer.
        bad_payloads = {'db': good_db, 'relations': b'not-json'}
        failed = sync_workfind_bundle(session, cache_dir=cache, fetch_bytes=lambda kind: bad_payloads[kind])
        assert failed.status == 'FAILED'
        assert (cache / 'current.txt').read_text(encoding='utf-8') == good_hash
        assert (cache / 'snapshots' / good_hash / '国企数据库.db').exists()
        assert not (cache / 'snapshots' / good_hash / '央企二级子公司.json').exists() or \
            (cache / 'snapshots' / good_hash / '央企二级子公司.json').read_bytes() == good_relations
        # The bad bundle must NOT have replaced the good snapshot dir.
        assert (cache / 'snapshots' / good_hash / '央企二级子公司.json').read_bytes() == good_relations
        # DB still points at the good snapshot.
        from app.models import SourceSnapshot
        snapshot = session.scalar(select(SourceSnapshot).where(SourceSnapshot.source_name == 'workfind-online'))
        assert snapshot.local_path.endswith(good_hash)


def test_sync_due_sources_only_refreshes_sources_past_their_interval(tmp_path, monkeypatch):
    import datetime as dt
    from app.sources.sync import sync_due_sources
    from app.sources.store import record_sync_success

    engine = create_engine(f"sqlite:///{tmp_path / 'due.db'}")
    Base.metadata.create_all(engine)
    now = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)
    with Session(engine) as session:
        tencent_run = record_sync_success(session, 'tencent-sheet', 'tencent-hash', '{"count":1}')
        workfind_run = record_sync_success(session, 'workfind-online', 'workfind-hash', '{"kind":"bundle"}')
        tencent_run.finished_at = now - dt.timedelta(hours=7)
        workfind_run.finished_at = now - dt.timedelta(hours=12)
        session.commit()

        called = []
        monkeypatch.setattr('app.sources.sync.sync_tencent_source', lambda session: called.append('tencent') or type('R', (), {'source_name':'tencent-sheet','status':'UNCHANGED'})())
        monkeypatch.setattr('app.sources.sync.sync_workfind_bundle', lambda session, cache_dir: called.append('workfind') or type('R', (), {'source_name':'workfind-online','status':'UNCHANGED'})())

        results = sync_due_sources(session, cache_dir=tmp_path / 'cache', now=now)
        assert called == ['tencent']
        assert [result.source_name for result in results] == ['tencent-sheet']
