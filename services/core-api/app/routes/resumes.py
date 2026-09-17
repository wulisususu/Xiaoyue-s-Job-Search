from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import ProfileCollectionDraft, ProfileDraftField, ResumeVersion
from ..profile.registry import get_field_definition
from ..profile.service import create_resume_drafts
from ..resumes.vault import (
    InvalidResumeError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
    append_upload_chunk,
    discard_upload_spool,
    finalize_streamed_upload,
    open_upload_spool,
)

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class ResumeRead(BaseModel):
    id: str
    sha256: str
    original_filename: str
    file_ext: str
    mime_type: str
    size_bytes: int
    version_number: int
    extraction_status: str
    parser_name: str | None = None
    parser_version: str | None = None
    extraction_error: str | None = None
    created_at: str
    pending_draft_count: int


class ResumeImportRead(ResumeRead):
    deduplicated: bool


class ResumeDraftRead(BaseModel):
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


def _pending_draft_count(session: Session, resume_id: str) -> int:
    scalar_count = int(
        session.scalar(
            select(func.count(ProfileDraftField.id)).where(
                ProfileDraftField.resume_version_id == resume_id,
                ProfileDraftField.status == "PENDING",
            )
        )
        or 0
    )
    collection_count = int(
        session.scalar(
            select(func.count(ProfileCollectionDraft.id)).where(
                ProfileCollectionDraft.resume_version_id == resume_id,
                ProfileCollectionDraft.status == "PENDING",
            )
        )
        or 0
    )
    return scalar_count + collection_count


def _resume_read(session: Session, resume: ResumeVersion) -> ResumeRead:
    return ResumeRead(
        id=resume.id,
        sha256=resume.sha256,
        original_filename=resume.original_filename,
        file_ext=resume.file_ext,
        mime_type=resume.mime_type,
        size_bytes=resume.size_bytes,
        version_number=resume.version_number,
        extraction_status=resume.extraction_status,
        parser_name=resume.parser_name,
        parser_version=resume.parser_version,
        extraction_error=resume.extraction_error,
        created_at=resume.created_at.isoformat(),
        pending_draft_count=_pending_draft_count(session, resume.id),
    )


def _draft_read(session: Session, draft: ProfileDraftField) -> ResumeDraftRead:
    resume = session.get(ResumeVersion, draft.resume_version_id)
    if resume is None:
        raise HTTPException(status_code=500, detail="Resume draft references a missing resume version")
    definition = get_field_definition(draft.field_key)
    return ResumeDraftRead(
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


@router.post("/import", response_model=ResumeImportRead)
async def import_resume(file: UploadFile = File(...)) -> ResumeImportRead:
    settings = get_settings()
    engine = get_engine(settings)
    temp_path: Path | None = None
    try:
        # True streaming ingest: chunks go straight to a spool file while
        # the hash updates incrementally. The body never lands in memory.
        try:
            display_name, temp_path, hash_obj = open_upload_spool(settings, file.filename or "resume")
        except UnsupportedResumeTypeError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        received = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                received = append_upload_chunk(temp_path, hash_obj, chunk, received)
        except ResumeTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        except UnsupportedResumeTypeError as exc:
            discard_upload_spool(temp_path)
            temp_path = None
            raise HTTPException(status_code=415, detail=str(exc)) from exc

        with Session(engine) as session:
            try:
                resume, deduplicated = finalize_streamed_upload(
                    session,
                    settings,
                    display_name,
                    temp_path,
                    received,
                    hash_obj.hexdigest(),
                )
                temp_path = None
                if not deduplicated and resume.extraction_status == "EXTRACTED" and resume.extracted_text:
                    create_resume_drafts(session, resume)
                payload = _resume_read(session, resume)
                return ResumeImportRead(**payload.model_dump(), deduplicated=deduplicated)
            except ResumeTooLargeError as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            except UnsupportedResumeTypeError as exc:
                raise HTTPException(status_code=415, detail=str(exc)) from exc
            except InvalidResumeError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if temp_path is not None:
            discard_upload_spool(temp_path)
        engine.dispose()


@router.get("", response_model=list[ResumeRead])
def list_resumes() -> list[ResumeRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resumes = session.scalars(
                select(ResumeVersion).order_by(ResumeVersion.version_number.desc())
            ).all()
            return [_resume_read(session, resume) for resume in resumes]
    finally:
        engine.dispose()


@router.get("/{resume_id}", response_model=ResumeRead)
def get_resume(resume_id: str) -> ResumeRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resume = session.get(ResumeVersion, resume_id)
            if resume is None:
                raise HTTPException(status_code=404, detail="Resume version not found")
            return _resume_read(session, resume)
    finally:
        engine.dispose()


@router.get("/{resume_id}/drafts", response_model=list[ResumeDraftRead])
def get_resume_drafts(resume_id: str) -> list[ResumeDraftRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resume = session.get(ResumeVersion, resume_id)
            if resume is None:
                raise HTTPException(status_code=404, detail="Resume version not found")
            drafts = session.scalars(
                select(ProfileDraftField)
                .where(ProfileDraftField.resume_version_id == resume_id)
                .order_by(ProfileDraftField.id)
            ).all()
            return [_draft_read(session, draft) for draft in drafts]
    finally:
        engine.dispose()
