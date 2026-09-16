import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.integrations.workfind import import_workfind
from app.jobs.company_resolver import resolve_company
from app.models import Base, Company, CompanyRelation


def _source_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE provinces (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, province_id INTEGER, name TEXT NOT NULL, level TEXT);
        CREATE TABLE central_enterprises (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO provinces VALUES (1, '江苏')")
    con.execute("INSERT INTO companies VALUES (1, 1, '江苏省铁路集团有限公司', '省级')")
    con.execute("INSERT INTO central_enterprises VALUES (1, '中国移动通信集团有限公司')")
    con.commit()
    con.close()


def test_import_workfind_builds_company_registry_and_relations(tmp_path: Path):
    source_db = tmp_path / 'workfind.db'
    _source_db(source_db)
    relations = tmp_path / 'relations.json'
    relations.write_text(json.dumps([
        {'parent': '中国移动', 'name': '中移互联网有限公司(中国移动子公司)'}
    ], ensure_ascii=False), encoding='utf-8')

    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        summary = import_workfind(session, source_db, relations)
        assert summary.companies_created == 3
        assert summary.relations_created == 1

        local = session.scalar(select(Company).where(Company.name == '江苏省铁路集团有限公司'))
        assert local is not None
        assert local.ownership == 'local_soe'
        assert local.province == '江苏'

        central = resolve_company(session, '中国移动', create_unknown=False)
        assert central is not None
        assert central.name == '中国移动通信集团有限公司'
        assert central.ownership == 'central_soe'

        child = resolve_company(session, '中移互联网有限公司', create_unknown=False)
        assert child is not None
        relation = session.scalar(select(CompanyRelation))
        assert relation is not None
        assert relation.parent_company_id == central.id
        assert relation.child_company_id == child.id


def test_import_workfind_is_idempotent(tmp_path: Path):
    source_db = tmp_path / 'workfind.db'
    _source_db(source_db)
    relations = tmp_path / 'relations.json'
    relations.write_text('[]', encoding='utf-8')

    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = import_workfind(session, source_db, relations)
        second = import_workfind(session, source_db, relations)
        assert first.companies_created == 2
        assert second.companies_created == 0
        assert session.scalars(select(Company)).all().__len__() == 2


def test_resolve_company_can_create_unknown_company(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        company = resolve_company(session, '某创新科技', create_unknown=True)
        assert company.name == '某创新科技'
        assert company.ownership == 'unknown'
        assert resolve_company(session, '某创新科技', create_unknown=False).id == company.id


def test_workfind_known_parent_alias_maps_to_official_central_company(tmp_path: Path):
    source_db = tmp_path / 'workfind.db'
    con = sqlite3.connect(source_db)
    con.executescript('''
        CREATE TABLE provinces (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE companies (id INTEGER PRIMARY KEY, province_id INTEGER, name TEXT NOT NULL, level TEXT);
        CREATE TABLE central_enterprises (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
    ''')
    con.execute("INSERT INTO central_enterprises VALUES (1, '中国铁路工程集团有限公司')")
    con.commit(); con.close()
    relations = tmp_path / 'relations.json'
    relations.write_text(json.dumps([
        {'parent': '中国中铁', 'name': '中铁五局(中国中铁子公司)'}
    ], ensure_ascii=False), encoding='utf-8')

    engine = create_engine(f"sqlite:///{tmp_path / 'target.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        summary = import_workfind(session, source_db, relations)
        assert summary.relations_created == 1
        parent = resolve_company(session, '中国中铁', create_unknown=False)
        child = resolve_company(session, '中铁五局', create_unknown=False)
        assert parent is not None and parent.name == '中国铁路工程集团有限公司'
        assert child is not None and child.ownership == 'central_soe'
