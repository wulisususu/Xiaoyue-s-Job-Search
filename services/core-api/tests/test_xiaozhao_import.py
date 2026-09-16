import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.workfind import import_workfind
from app.integrations.xiaozhao import import_xiaozhao
from app.models import Base, Company, Job, JobSource


def _workfind_fixture(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / 'workfind.db'
    con = sqlite3.connect(db)
    con.executescript('''
        CREATE TABLE provinces (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, province_id INTEGER, name TEXT NOT NULL, level TEXT);
        CREATE TABLE central_enterprises (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO central_enterprises VALUES (1, '中国移动通信集团有限公司')")
    con.commit(); con.close()
    relations = tmp_path / 'relations.json'
    relations.write_text(json.dumps([
        {'parent': '中国移动', 'name': '中移互联网有限公司(中国移动子公司)'}
    ], ensure_ascii=False), encoding='utf-8')
    return db, relations


def _xiaozhao_fixture(path: Path) -> None:
    payload = {
        'updated': '2026-09-03',
        'count': 3,
        'jobs': [
            {
                'c': '中国移动', 'p': '视觉设计、宣传策划', 'l': '南京', 'e': '',
                'w': '批次:27届秋招正式批', 'd': '招满即止', 's': '校招信息聚合平台',
                't': '其他', 'ind': '通信', 'u': 'https://jobs.example.com/apply/1?utm_source=radar'
            },
            {
                'c': '某科技', 'p': '设计类', 'l': '上海', 'e': '',
                'w': '批次:27届秋招正式批', 'd': '2026-10-01', 's': '校招信息聚合平台',
                't': '其他', 'ind': '科技', 'u': ''
            },
            {
                'c': '中国移动', 'p': '另一个入口描述', 'l': '南京', 'e': '',
                'w': '批次:27届秋招正式批', 'd': '招满即止', 's': '校招信息聚合平台',
                't': '其他', 'ind': '通信', 'u': 'https://jobs.example.com/apply/1?utm_source=radar'
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')


def test_import_xiaozhao_maps_fields_status_and_reuses_workfind_company(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    source_db, relations = _workfind_fixture(tmp_path)
    jobs_json = tmp_path / 'jobs.json'
    _xiaozhao_fixture(jobs_json)

    with Session(engine) as session:
        import_workfind(session, source_db, relations)
        summary = import_xiaozhao(session, jobs_json)
        assert summary.records_seen == 3
        assert summary.jobs_created == 2
        assert summary.companies_created == 1

        jobs = session.scalars(select(Job).order_by(Job.title)).all()
        assert {job.status for job in jobs} == {'DISCOVERED_NO_URL', 'DISCOVERED_URL_UNVERIFIED'}

        mobile = session.scalar(select(Company).where(Company.name == '中国移动通信集团有限公司'))
        assert mobile is not None
        mobile_jobs = session.scalars(select(Job).where(Job.company_id == mobile.id)).all()
        assert len(mobile_jobs) == 1
        assert mobile_jobs[0].industry == '通信'
        assert mobile_jobs[0].source_updated_at == '2026-09-03'

        unknown = session.scalar(select(Company).where(Company.name == '某科技'))
        assert unknown is not None
        assert unknown.ownership == 'unknown'

        sources = session.scalars(select(JobSource)).all()
        assert len(sources) == 3
        assert all(source.source_name == 'xiaozhao-radar' for source in sources)


def test_import_xiaozhao_is_idempotent(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    jobs_json = tmp_path / 'jobs.json'
    _xiaozhao_fixture(jobs_json)

    with Session(engine) as session:
        first = import_xiaozhao(session, jobs_json)
        second = import_xiaozhao(session, jobs_json)
        assert first.jobs_created == 2
        assert first.companies_created == 2
        assert second.jobs_created == 0
        assert second.companies_created == 0
        assert len(session.scalars(select(Job)).all()) == 2
        assert len(session.scalars(select(JobSource)).all()) == 3
