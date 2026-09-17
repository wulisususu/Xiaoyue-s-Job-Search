from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Company, CompanyAlias
from .identity import company_alias_candidates, normalize_company_name

RESOLVED = "RESOLVED"
AMBIGUOUS = "AMBIGUOUS"
NOT_FOUND = "NOT_FOUND"


@dataclass(slots=True)
class CompanyResolution:
    """Tri-state resolver outcome.

    AMBIGUOUS means several existing companies match the name. Callers MUST
    NOT create a new entity in that state: doing so compounds the ambiguity
    on every future resolve. Pick deterministically from `candidates`
    (lowest id) if a company is required, or skip and surface the conflict.
    """

    company: Company | None
    state: str
    candidates: list[Company] = field(default_factory=list)


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


def resolve_company_detailed(session: Session, name: str, *, create_unknown: bool = False) -> CompanyResolution:
    normalized = normalize_company_name(name)
    if not normalized:
        return CompanyResolution(None, NOT_FOUND)

    exact = session.scalars(
        select(Company).where(Company.normalized_name == normalized).order_by(Company.id)
    ).all()
    if len(exact) == 1:
        return CompanyResolution(exact[0], RESOLVED)
    if len(exact) > 1:
        # Never auto-create on ambiguity.
        return CompanyResolution(None, AMBIGUOUS, list(exact))

    alias_company_ids = session.scalars(
        select(CompanyAlias.company_id)
        .where(CompanyAlias.normalized_alias == normalized)
        .distinct()
        .order_by(CompanyAlias.company_id)
    ).all()
    if len(alias_company_ids) == 1:
        return CompanyResolution(session.get(Company, alias_company_ids[0]), RESOLVED)
    if len(alias_company_ids) > 1:
        candidates = [session.get(Company, company_id) for company_id in alias_company_ids]
        return CompanyResolution(None, AMBIGUOUS, [c for c in candidates if c is not None])

    if not create_unknown:
        return CompanyResolution(None, NOT_FOUND)

    company = Company(name=name.strip(), normalized_name=normalized, ownership="unknown")
    session.add(company)
    session.flush()
    add_default_aliases(session, company, "runtime")
    session.flush()
    return CompanyResolution(company, RESOLVED)


def resolve_company(session: Session, name: str, *, create_unknown: bool = True) -> Company | None:
    """Backwards-compatible resolver.

    On AMBIGUOUS it deterministically reuses the LOWEST-ID existing match and
    never creates a new entity, so repeated resolves can no longer spawn
    duplicate companies. Use resolve_company_detailed when the caller needs
    to distinguish the three states.
    """
    resolution = resolve_company_detailed(session, name, create_unknown=create_unknown)
    if resolution.state == RESOLVED:
        return resolution.company
    if resolution.state == AMBIGUOUS and resolution.candidates:
        return min(resolution.candidates, key=lambda company: company.id)
    return None
