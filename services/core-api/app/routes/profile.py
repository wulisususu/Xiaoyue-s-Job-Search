from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import ProfileDraftField, ProfileField, ProfileFieldRevision, ResumeVersion
from ..profile.registry import get_field_definition
from ..profile.service import (
    ProfileDraftAlreadyReviewedError,
    ProfileDraftNotFoundError,
    accept_profile_draft,
    manual_upsert_profile_field,
    reject_profile_draft,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileFieldWrite(BaseModel):
    value: object


class ProfileFieldRead(BaseModel):
    field_key: str
    label: str
    category: str
    value: object
    value_type: str
    source_type: str
    source_ref: str | None = None
    confidence: float | None = None
    confirmed: bool
    created_at: str
    updated_at: str


class ProfileDraftRead(BaseModel):
    id: int
    resume_version_id: str
    resume_version_number: int
    resume_filename: str
    field_key: str
    label: str
    category: str
    value: object
    value_type: str
    confidence: float | None = None
    extractor_name: str
    status: str
    created_at: str
    reviewed_at: str | None = None


class ProfileRevisionRead(BaseModel):
    id: int
    field_key: str
    label: str
    category: str
    old_value: object | None = None
    new_value: object
    value_type: str
    source_type: str
    source_ref: str | None = None
    confidence: float | None = None
    confirmed: bool
    changed_at: str


def _field_read(field: ProfileField) -> ProfileFieldRead:
    definition = get_field_definition(field.field_key)
    return ProfileFieldRead(
        field_key=field.field_key,
        label=definition.label,
        category=definition.category,
        value=json.loads(field.value_json),
        value_type=field.value_type,
        source_type=field.source_type,
        source_ref=field.source_ref,
        confidence=field.confidence,
        confirmed=field.confirmed,
        created_at=field.created_at.isoformat(),
        updated_at=field.updated_at.isoformat(),
    )


def _draft_read(session: Session, draft: ProfileDraftField) -> ProfileDraftRead:
    resume = session.get(ResumeVersion, draft.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=500, detail="Profile draft references a missing resume version")
    definition = get_field_definition(draft.field_key)
    return ProfileDraftRead(
        id=draft.id,
        resume_version_id=draft.resume_version_id,
        resume_version_number=resume.version_number,
        resume_filename=resume.original_filename,
        field_key=draft.field_key,
        label=definition.label,
        category=definition.category,
        value=json.loads(draft.value_json),
        value_type=draft.value_type,
        confidence=draft.confidence,
        extractor_name=draft.extractor_name,
        status=draft.status,
        created_at=draft.created_at.isoformat(),
        reviewed_at=draft.reviewed_at.isoformat() if draft.reviewed_at else None,
    )


def _revision_read(revision: ProfileFieldRevision) -> ProfileRevisionRead:
    definition = get_field_definition(revision.field_key)
    return ProfileRevisionRead(
        id=revision.id,
        field_key=revision.field_key,
        label=definition.label,
        category=definition.category,
        old_value=json.loads(revision.old_value_json) if revision.old_value_json is not None else None,
        new_value=json.loads(revision.new_value_json),
        value_type=revision.value_type,
        source_type=revision.source_type,
        source_ref=revision.source_ref,
        confidence=revision.confidence,
        confirmed=revision.confirmed,
        changed_at=revision.changed_at.isoformat(),
    )


@router.get("/fields", response_model=list[ProfileFieldRead])
def list_profile_fields() -> list[ProfileFieldRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            fields = session.scalars(select(ProfileField).order_by(ProfileField.field_key)).all()
            return [_field_read(field) for field in fields]
    finally:
        engine.dispose()


@router.put("/fields/{field_key:path}", response_model=ProfileFieldRead)
def put_profile_field(field_key: str, body: ProfileFieldWrite) -> ProfileFieldRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                field = manual_upsert_profile_field(session, field_key, body.value)
                return _field_read(field)
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        engine.dispose()


@router.get("/drafts", response_model=list[ProfileDraftRead])
def list_profile_drafts(status: str | None = Query(default=None)) -> list[ProfileDraftRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            query = select(ProfileDraftField).order_by(ProfileDraftField.id)
            if status:
                query = query.where(ProfileDraftField.status == status)
            drafts = session.scalars(query).all()
            return [_draft_read(session, draft) for draft in drafts]
    finally:
        engine.dispose()


@router.post("/drafts/{draft_id}/accept", response_model=ProfileFieldRead)
def accept_draft(draft_id: int) -> ProfileFieldRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                field = accept_profile_draft(session, draft_id)
                return _field_read(field)
            except ProfileDraftNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ProfileDraftAlreadyReviewedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        engine.dispose()


@router.post("/drafts/{draft_id}/reject", response_model=ProfileDraftRead)
def reject_draft(draft_id: int) -> ProfileDraftRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                draft = reject_profile_draft(session, draft_id)
                return _draft_read(session, draft)
            except ProfileDraftNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ProfileDraftAlreadyReviewedError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        engine.dispose()


@router.get("/history", response_model=list[ProfileRevisionRead])
def profile_history(field_key: str | None = None) -> list[ProfileRevisionRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            query = select(ProfileFieldRevision)
            if field_key:
                query = query.where(ProfileFieldRevision.field_key == field_key)
            revisions = session.scalars(
                query.order_by(ProfileFieldRevision.changed_at.desc(), ProfileFieldRevision.id.desc())
            ).all()
            return [_revision_read(revision) for revision in revisions]
    finally:
        engine.dispose()
