from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProfileDraftField, ProfileField, ProfileFieldRevision, ResumeVersion, utcnow
from .extraction import DeterministicExtractionProvider
from .extraction_runs import execute_extraction_run
from .registry import get_field_definition, validate_profile_value


class ProfileDraftNotFoundError(LookupError):
    pass


class ProfileDraftAlreadyReviewedError(RuntimeError):
    pass


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _upsert_confirmed_field(
    session: Session,
    *,
    field_key: str,
    value,
    source_type: str,
    source_ref: str | None,
    confidence: float | None,
) -> ProfileField:
    definition = get_field_definition(field_key)
    normalized = validate_profile_value(field_key, value)
    value_json = _dump(normalized)
    field = session.scalar(select(ProfileField).where(ProfileField.field_key == field_key))
    old_value_json = field.value_json if field is not None else None

    if field is None:
        field = ProfileField(
            field_key=field_key,
            value_json=value_json,
            value_type=definition.value_type,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            confirmed=True,
        )
        session.add(field)
    else:
        field.value_json = value_json
        field.value_type = definition.value_type
        field.source_type = source_type
        field.source_ref = source_ref
        field.confidence = confidence
        field.confirmed = True
        field.updated_at = utcnow()

    session.add(
        ProfileFieldRevision(
            field_key=field_key,
            old_value_json=old_value_json,
            new_value_json=value_json,
            value_type=definition.value_type,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            confirmed=True,
        )
    )
    return field


def create_resume_drafts(session: Session, resume_version: ResumeVersion) -> list[ProfileDraftField]:
    """Deterministic import extraction, now running through the one formal
    chain: an AIExtractionRun row records provenance, drafts link to it."""
    if resume_version.extraction_status != "EXTRACTED" or not resume_version.extracted_text:
        return []

    run = execute_extraction_run(session, resume_version, DeterministicExtractionProvider())
    return list(
        session.scalars(
            select(ProfileDraftField)
            .where(ProfileDraftField.extraction_run_id == run.id)
            .order_by(ProfileDraftField.id)
        )
    )


def manual_upsert_profile_field(session: Session, field_key: str, value) -> ProfileField:
    try:
        field = _upsert_confirmed_field(
            session,
            field_key=field_key,
            value=value,
            source_type="manual",
            source_ref=None,
            confidence=1.0,
        )
        session.commit()
        session.refresh(field)
        return field
    except Exception:
        session.rollback()
        raise


def _pending_draft(session: Session, draft_id: int) -> ProfileDraftField:
    draft = session.get(ProfileDraftField, draft_id)
    if draft is None:
        raise ProfileDraftNotFoundError(f"Profile draft {draft_id} not found")
    if draft.status != "PENDING":
        raise ProfileDraftAlreadyReviewedError(f"Profile draft {draft_id} is already {draft.status}")
    return draft


def accept_profile_draft(session: Session, draft_id: int) -> ProfileField:
    try:
        draft = _pending_draft(session, draft_id)
        value = json.loads(draft.value_json)
        field = _upsert_confirmed_field(
            session,
            field_key=draft.field_key,
            value=value,
            source_type="resume",
            source_ref=draft.resume_version_id,
            confidence=draft.confidence,
        )
        draft.status = "ACCEPTED"
        draft.reviewed_at = utcnow()
        session.commit()
        session.refresh(field)
        return field
    except Exception:
        session.rollback()
        raise


def reject_profile_draft(session: Session, draft_id: int) -> ProfileDraftField:
    try:
        draft = _pending_draft(session, draft_id)
        draft.status = "REJECTED"
        draft.reviewed_at = utcnow()
        session.commit()
        session.refresh(draft)
        return draft
    except Exception:
        session.rollback()
        raise
