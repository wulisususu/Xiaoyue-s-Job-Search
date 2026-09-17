from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import (
    ProfileCollectionDraft,
    ProfileCollectionItem,
    ProfileDraftField,
    ProfileField,
    ProfileFieldRevision,
    ResumeVersion,
)
from ..profile.collection_drafts import (
    ProfileCollectionDraftAlreadyReviewedError,
    ProfileCollectionDraftNotFoundError,
    accept_collection_draft,
    reject_collection_draft,
)
from ..profile.collection_service import (
    DuplicateProfileCollectionValueError,
    ProfileCollectionItemNotFoundError,
    ProfileCollectionOrderError,
    create_collection_item,
    delete_collection_item,
    list_collection_items,
    reorder_collection_items,
    update_collection_item,
)
from ..profile.collections import COLLECTION_REGISTRY, get_collection_definition
from ..profile.registry import FIELD_REGISTRY, get_field_definition
from ..profile.service import (
    ProfileDraftAlreadyReviewedError,
    ProfileDraftNotFoundError,
    accept_profile_draft,
    manual_upsert_profile_field,
    reject_profile_draft,
)

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileDefinitionRead(BaseModel):
    field_key: str
    label: str
    category: str
    value_type: str
    multiple: bool


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
    extraction_run_id: int | None = None
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


class ProfileCollectionFieldDefinitionRead(BaseModel):
    key: str
    label: str
    value_type: str
    required: bool
    multiple: bool


class ProfileCollectionDefinitionRead(BaseModel):
    kind: str
    label: str
    fields: list[ProfileCollectionFieldDefinitionRead]


class ProfileCollectionWrite(BaseModel):
    payload: dict[str, object]


class ProfileCollectionOrderWrite(BaseModel):
    item_ids: list[int]


class ProfileCollectionItemRead(BaseModel):
    id: int
    kind: str
    position: int
    payload: dict[str, object]
    source_type: str
    source_ref: str | None = None
    confidence: float | None = None
    confirmed: bool
    created_at: str
    updated_at: str


class ProfileCollectionDraftRead(BaseModel):
    id: int
    resume_version_id: str
    resume_version_number: int
    resume_filename: str
    extraction_run_id: int | None = None
    kind: str
    label: str
    payload: dict[str, object]
    confidence: float | None = None
    extractor_name: str
    status: str
    created_at: str
    reviewed_at: str | None = None


class ProfileCollectionDeleteRead(BaseModel):
    deleted_id: int


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
        extraction_run_id=draft.extraction_run_id,
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


def _collection_definition_read(kind: str) -> ProfileCollectionDefinitionRead:
    definition = get_collection_definition(kind)
    return ProfileCollectionDefinitionRead(
        kind=definition.kind,
        label=definition.label,
        fields=[
            ProfileCollectionFieldDefinitionRead(
                key=field.key,
                label=field.label,
                value_type=field.value_type,
                required=field.required,
                multiple=field.multiple,
            )
            for field in definition.fields
        ],
    )


def _collection_read(item: ProfileCollectionItem) -> ProfileCollectionItemRead:
    return ProfileCollectionItemRead(
        id=item.id,
        kind=item.kind,
        position=item.position,
        payload=json.loads(item.payload_json),
        source_type=item.source_type,
        source_ref=item.source_ref,
        confidence=item.confidence,
        confirmed=item.confirmed,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


def _collection_draft_read(session: Session, draft: ProfileCollectionDraft) -> ProfileCollectionDraftRead:
    resume = session.get(ResumeVersion, draft.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=500, detail="Profile collection draft references a missing resume version")
    definition = get_collection_definition(draft.kind)
    return ProfileCollectionDraftRead(
        id=draft.id,
        resume_version_id=draft.resume_version_id,
        resume_version_number=resume.version_number,
        resume_filename=resume.original_filename,
        extraction_run_id=draft.extraction_run_id,
        kind=draft.kind,
        label=definition.label,
        payload=json.loads(draft.payload_json),
        confidence=draft.confidence,
        extractor_name=draft.extractor_name,
        status=draft.status,
        created_at=draft.created_at.isoformat(),
        reviewed_at=draft.reviewed_at.isoformat() if draft.reviewed_at else None,
    )


def _collection_validation_error(exc: KeyError | ValueError) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/definitions", response_model=list[ProfileDefinitionRead])
def list_profile_definitions() -> list[ProfileDefinitionRead]:
    return [
        ProfileDefinitionRead(
            field_key=definition.field_key,
            label=definition.label,
            category=definition.category,
            value_type=definition.value_type,
            multiple=definition.multiple,
        )
        for definition in FIELD_REGISTRY.values()
    ]


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


@router.get("/collection-drafts", response_model=list[ProfileCollectionDraftRead])
def list_profile_collection_drafts(
    status: str | None = Query(default=None),
) -> list[ProfileCollectionDraftRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            query = select(ProfileCollectionDraft).order_by(ProfileCollectionDraft.id)
            if status:
                query = query.where(ProfileCollectionDraft.status == status)
            drafts = session.scalars(query).all()
            return [_collection_draft_read(session, draft) for draft in drafts]
    finally:
        engine.dispose()


@router.post("/collection-drafts/{draft_id}/accept", response_model=ProfileCollectionItemRead)
def accept_profile_collection_draft(draft_id: int) -> ProfileCollectionItemRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                item = accept_collection_draft(session, draft_id)
                return _collection_read(item)
            except ProfileCollectionDraftNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (ProfileCollectionDraftAlreadyReviewedError, DuplicateProfileCollectionValueError) as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except (KeyError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        engine.dispose()


@router.post("/collection-drafts/{draft_id}/reject", response_model=ProfileCollectionDraftRead)
def reject_profile_collection_draft(draft_id: int) -> ProfileCollectionDraftRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                draft = reject_collection_draft(session, draft_id)
                return _collection_draft_read(session, draft)
            except ProfileCollectionDraftNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ProfileCollectionDraftAlreadyReviewedError as exc:
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


@router.get("/collections/definitions", response_model=list[ProfileCollectionDefinitionRead])
def list_profile_collection_definitions() -> list[ProfileCollectionDefinitionRead]:
    return [_collection_definition_read(kind) for kind in COLLECTION_REGISTRY]


@router.get("/collections/{kind}", response_model=list[ProfileCollectionItemRead])
def get_profile_collection(kind: str) -> list[ProfileCollectionItemRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                return [_collection_read(item) for item in list_collection_items(session, kind)]
            except KeyError as exc:
                raise _collection_validation_error(exc) from exc
    finally:
        engine.dispose()


@router.post("/collections/{kind}", response_model=ProfileCollectionItemRead)
def post_profile_collection_item(kind: str, body: ProfileCollectionWrite) -> ProfileCollectionItemRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                item = create_collection_item(session, kind, body.payload)
                return _collection_read(item)
            except DuplicateProfileCollectionValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except (KeyError, ValueError) as exc:
                raise _collection_validation_error(exc) from exc
    finally:
        engine.dispose()


@router.put("/collections/{kind}/order", response_model=list[ProfileCollectionItemRead])
def put_profile_collection_order(kind: str, body: ProfileCollectionOrderWrite) -> list[ProfileCollectionItemRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                items = reorder_collection_items(session, kind, body.item_ids)
                return [_collection_read(item) for item in items]
            except ProfileCollectionOrderError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except KeyError as exc:
                raise _collection_validation_error(exc) from exc
    finally:
        engine.dispose()


@router.put("/collections/{kind}/{item_id}", response_model=ProfileCollectionItemRead)
def put_profile_collection_item(kind: str, item_id: int, body: ProfileCollectionWrite) -> ProfileCollectionItemRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                item = update_collection_item(session, kind, item_id, body.payload)
                return _collection_read(item)
            except ProfileCollectionItemNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except DuplicateProfileCollectionValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except (KeyError, ValueError) as exc:
                raise _collection_validation_error(exc) from exc
    finally:
        engine.dispose()


@router.delete("/collections/{kind}/{item_id}", response_model=ProfileCollectionDeleteRead)
def remove_profile_collection_item(kind: str, item_id: int) -> ProfileCollectionDeleteRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            try:
                deleted_id = delete_collection_item(session, kind, item_id)
                return ProfileCollectionDeleteRead(deleted_id=deleted_id)
            except ProfileCollectionItemNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except (KeyError, ValueError) as exc:
                raise _collection_validation_error(exc) from exc
    finally:
        engine.dispose()
