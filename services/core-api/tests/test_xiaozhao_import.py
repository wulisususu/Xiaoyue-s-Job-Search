import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.workfind import import_workfind
from app.integrations.xiaozhao import import_xiaozhao, import_xiaozhao_payload
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
        # Records 1 and 3 share the same URL, so they share ONE stable source
        # identity; record 2 has no URL and gets its own.
        assert len(sources) == 2
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
        assert len(session.scalars(select(JobSource)).all()) == 2


def test_upstream_edits_propagate_to_canonical_job(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    url = 'https://jobs.example.com/apply/9'

    def payload(title, location, deadline, updated):
        return {
            'updated': updated,
            'count': 1,
            'jobs': [{
                'c': '中国移动', 'p': title, 'l': location, 'e': '',
                'w': '批次:27届秋招', 'd': deadline, 's': '腾讯文档校招雷达',
                't': '其他', 'ind': '通信', 'u': url,
            }],
        }

    with Session(engine) as session:
        import_xiaozhao_payload(session, payload('视觉设计师', '南京', '9月20日', '2026-09-10'))
        job = session.scalar(select(Job))
        source = session.scalar(select(JobSource))
        assert job.title == '视觉设计师' and job.deadline_text == '9月20日'
        assert source.status == 'ACTIVE'

        # Same URL, completely rewritten record: must UPDATE, not duplicate.
        summary = import_xiaozhao_payload(
            session, payload('视觉设计师（品牌视觉方向）', '南京 / 上海', '10月10日', '2026-09-17')
        )
        assert summary.jobs_created == 0
        assert summary.sources_created == 0
        assert summary.sources_updated == 1

        jobs = session.scalars(select(Job)).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.title == '视觉设计师（品牌视觉方向）'
        assert job.location == '南京 / 上海'
        assert job.deadline_text == '10月10日'
        assert job.source_updated_at == '2026-09-17'
        assert len(session.scalars(select(JobSource)).all()) == 1


def test_removed_record_is_staled_and_reappearing_record_is_revived(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)

    def payload(*titles):
        return {
            'updated': '2026-09-17',
            'count': len(titles),
            'jobs': [{
                'c': '中国移动', 'p': title, 'l': '南京', 'e': '',
                'w': '批次:27届秋招', 'd': '招满即止', 's': '腾讯文档校招雷达',
                't': '其他', 'ind': '通信', 'u': f'https://jobs.example.com/apply/{idx}',
            } for idx, title in enumerate(titles)],
        }

    with Session(engine) as session:
        import_xiaozhao_payload(session, payload('岗位A', '岗位B'))
        assert len(session.scalars(select(JobSource)).all()) == 2

        # 岗位B disappears upstream.
        summary = import_xiaozhao_payload(session, payload('岗位A'))
        assert summary.sources_staled == 1
        assert summary.jobs_staled == 1
        staled = session.scalars(select(Job).where(Job.title == '岗位B')).one()
        assert staled.status == 'STALE'
        staled_source = session.scalars(select(JobSource).where(JobSource.status == 'STALE')).one()
        assert staled_source.job_id == staled.id

        # 岗位B comes back: both source and job return to ACTIVE.
        summary = import_xiaozhao_payload(session, payload('岗位A', '岗位B'))
        assert summary.sources_created == 0
        revived = session.scalars(select(Job).where(Job.title == '岗位B')).one()
        assert revived.status == 'DISCOVERED_URL_UNVERIFIED'
        assert session.scalar(select(JobSource).where(JobSource.status == 'STALE')) is None


def test_missing_upstream_job_fields_do_not_erase_existing_canonical_values(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    url = "https://jobs.example.com/apply/missing-semantics"

    first = {
        "updated": "2026-09-18",
        "count": 1,
        "jobs": [{
            "c": "中国移动",
            "p": "视觉设计师",
            "l": "南京",
            "w": "27届秋招",
            "d": "2026-10-01",
            "ind": "通信",
            "u": url,
        }],
    }
    # p/l/w/d/ind are omitted entirely. They mean "no update", not clear.
    second = {
        "updated": "2026-09-19",
        "count": 1,
        "jobs": [{
            "c": "中国移动",
            "u": url,
        }],
    }

    with Session(engine) as session:
        import_xiaozhao_payload(session, first)
        import_xiaozhao_payload(session, second)

        job = session.scalar(select(Job))
        assert job is not None
        assert job.title == "视觉设计师"
        assert job.location == "南京"
        assert job.recruitment_batch == "27届秋招"
        assert job.deadline_text == "2026-10-01"
        assert job.industry == "通信"
        assert job.source_updated_at == "2026-09-19"


def test_explicit_blank_or_null_upstream_job_fields_clear_canonical_values(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    url = "https://jobs.example.com/apply/clear-semantics"

    first = {
        "updated": "2026-09-18",
        "count": 1,
        "jobs": [{
            "c": "中国移动",
            "p": "视觉设计师",
            "l": "南京",
            "w": "27届秋招",
            "d": "2026-10-01",
            "ind": "通信",
            "u": url,
        }],
    }
    second = {
        "updated": "2026-09-19",
        "count": 1,
        "jobs": [{
            "c": "中国移动",
            "p": "",
            "l": None,
            "w": "",
            "d": None,
            # Explicit ind=None must clear rather than fall back to legacy t.
            "ind": None,
            "t": "其他",
            "u": url,
        }],
    }

    with Session(engine) as session:
        import_xiaozhao_payload(session, first)
        import_xiaozhao_payload(session, second)

        jobs = session.scalars(select(Job)).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.title == ""
        assert job.location == ""
        assert job.recruitment_batch == ""
        assert job.deadline_text == ""
        assert job.industry == ""
        assert job.source_updated_at == "2026-09-19"


def test_missing_structured_industry_falls_back_to_legacy_type_only_on_new_input(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    payload = {
        "updated": "2026-09-19",
        "count": 1,
        "jobs": [{
            "c": "中国移动",
            "p": "设计类",
            "l": "南京",
            "w": "27届秋招",
            "d": "招满即止",
            "t": "通信运营商",
            "u": "https://jobs.example.com/apply/legacy-industry",
        }],
    }

    with Session(engine) as session:
        import_xiaozhao_payload(session, payload)
        job = session.scalar(select(Job))
        assert job is not None
        assert job.industry == "通信运营商"
