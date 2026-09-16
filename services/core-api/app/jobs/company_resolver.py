from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, CompanyAlias
from .identity import company_alias_candidates, normalize_company_name


def add_company_alias(session: Session, company: Company, alias: str, source_name: str) -> None:
    normalized = normalize_company_name(alias)
    if not normalized:
        return
    exists = session.scalar(
        select(CompanyAlias).where(
            CompanyAlias.company_id == company.id,
            CompanyAlias.normalized_alias == normalized,
            CompanyAlias.source_name == source_name,
        )
    )
    if exists is None:
        session.add(
            CompanyAlias(
                company_id=company.id,
                alias=alias.strip(),
                normalized_alias=normalized,
                source_name=source_name,
            )
        )


def add_default_aliases(session: Session, company: Company, source_name: str) -> None:
    for alias in sorted(company_alias_candidates(company.name)):
        add_company_alias(session, company, alias, source_name)


def resolve_company(session: Session, name: str, *, create_unknown: bool = True) -> Company | None:
    normalized = normalize_company_name(name)
    if not normalized:
        return None

    exact = session.scalars(select(Company).where(Company.normalized_name == normalized)).all()
    if len(exact) == 1:
        return exact[0]

    alias_company_ids = session.scalars(
        select(CompanyAlias.company_id).where(CompanyAlias.normalized_alias == normalized).distinct()
    ).all()
    if len(alias_company_ids) == 1:
        return session.get(Company, alias_company_ids[0])

    if not create_unknown:
        return None

    company = Company(name=name.strip(), normalized_name=normalized, ownership="unknown")
    session.add(company)
    session.flush()
    add_default_aliases(session, company, "runtime")
    session.flush()
    return company
