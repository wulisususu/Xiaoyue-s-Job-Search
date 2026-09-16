from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..jobs.company_resolver import add_company_alias, add_default_aliases, resolve_company
from ..jobs.identity import normalize_company_name
from ..models import Company, CompanyRelation, CompanySource
from .types import ImportSummary

_CHILD_NOTE = re.compile(r"[（(][^）)]*子公司[^）)]*[）)]")

_KNOWN_PARENT_OFFICIAL_NAMES = {
    "中交集团": "中国交通建设集团有限公司",
    "中国中铁": "中国铁路工程集团有限公司",
    "中国建筑": "中国建筑集团有限公司",
    "中国电科": "中国电子科技集团有限公司",
    "中国联通": "中国联合网络通信集团有限公司",
    "中国铁建": "中国铁道建筑集团有限公司",
    "中石油": "中国石油天然气集团有限公司",
}


def _clean_child_name(value: str) -> str:
    return _CHILD_NOTE.sub("", value or "").strip()


def _source_company(session: Session, source_key: str) -> Company | None:
    company_id = session.scalar(
        select(CompanySource.company_id).where(
            CompanySource.source_name == "workfind",
            CompanySource.source_key == source_key,
        )
    )
    return session.get(Company, company_id) if company_id is not None else None


def _create_source_company(
    session: Session,
    *,
    source_key: str,
    name: str,
    ownership: str,
    province: str | None = None,
    level: str | None = None,
    raw: dict | None = None,
) -> tuple[Company, bool]:
    existing = _source_company(session, source_key)
    if existing is not None:
        return existing, False

    resolved = resolve_company(session, name, create_unknown=False)
    if resolved is None:
        resolved = Company(
            name=name.strip(),
            normalized_name=normalize_company_name(name),
            ownership=ownership,
            province=province,
            level=level,
        )
        session.add(resolved)
        session.flush()
    else:
        if resolved.ownership == "unknown":
            resolved.ownership = ownership
        resolved.province = resolved.province or province
        resolved.level = resolved.level or level

    add_default_aliases(session, resolved, "workfind")
    session.add(
        CompanySource(
            company_id=resolved.id,
            source_name="workfind",
            source_key=source_key,
            raw_json=json.dumps(raw or {}, ensure_ascii=False, sort_keys=True),
        )
    )
    session.flush()
    return resolved, True


def _resolve_parent_alias(session: Session, parent_alias: str) -> Company | None:
    resolved = resolve_company(session, parent_alias, create_unknown=False)
    if resolved is not None:
        return resolved

    official_name = _KNOWN_PARENT_OFFICIAL_NAMES.get(parent_alias.strip())
    if official_name:
        official_normalized = normalize_company_name(official_name)
        official = session.scalar(
            select(Company).where(
                Company.ownership == "central_soe",
                Company.normalized_name == official_normalized,
            )
        )
        if official is not None:
            add_company_alias(session, official, parent_alias, "workfind_relation")
            session.flush()
            return official

    normalized = normalize_company_name(parent_alias)
    central = session.scalars(select(Company).where(Company.ownership == "central_soe")).all()
    matches = [item for item in central if normalized and normalized in item.normalized_name]
    if len(matches) == 1:
        add_company_alias(session, matches[0], parent_alias, "workfind_relation")
        session.flush()
        return matches[0]
    return None


def import_workfind(session: Session, company_db_path: Path, relations_json_path: Path) -> ImportSummary:
    summary = ImportSummary()
    con = sqlite3.connect(company_db_path)
    con.row_factory = sqlite3.Row
    try:
        provinces = {row["id"]: row["name"] for row in con.execute("SELECT id, name FROM provinces")}
        for row in con.execute("SELECT id, province_id, name, level FROM companies"):
            summary.records_seen += 1
            _, created = _create_source_company(
                session,
                source_key=f"local:{row['id']}",
                name=row["name"],
                ownership="local_soe",
                province=provinces.get(row["province_id"]),
                level=row["level"],
                raw=dict(row),
            )
            summary.companies_created += int(created)
            summary.sources_created += int(created)

        for row in con.execute("SELECT id, name FROM central_enterprises"):
            summary.records_seen += 1
            _, created = _create_source_company(
                session,
                source_key=f"central:{row['id']}",
                name=row["name"],
                ownership="central_soe",
                level="central",
                raw=dict(row),
            )
            summary.companies_created += int(created)
            summary.sources_created += int(created)
    finally:
        con.close()

    relations = json.loads(relations_json_path.read_text(encoding="utf-8"))
    for index, item in enumerate(relations):
        summary.records_seen += 1
        parent = _resolve_parent_alias(session, str(item.get("parent") or ""))
        if parent is None:
            continue
        child_name = _clean_child_name(str(item.get("name") or ""))
        if not child_name:
            continue
        child, created = _create_source_company(
            session,
            source_key=f"relation-child:{index}:{normalize_company_name(child_name)}",
            name=child_name,
            ownership="central_soe",
            level="subsidiary",
            raw=item,
        )
        summary.companies_created += int(created)
        summary.sources_created += int(created)
        add_company_alias(session, parent, str(item.get("parent") or ""), "workfind_relation")
        existing_relation = session.scalar(
            select(CompanyRelation).where(
                CompanyRelation.parent_company_id == parent.id,
                CompanyRelation.child_company_id == child.id,
                CompanyRelation.relation_type == "subsidiary",
            )
        )
        if existing_relation is None:
            session.add(
                CompanyRelation(
                    parent_company_id=parent.id,
                    child_company_id=child.id,
                    relation_type="subsidiary",
                    source_name="workfind",
                )
            )
            summary.relations_created += 1
    session.commit()
    return summary
