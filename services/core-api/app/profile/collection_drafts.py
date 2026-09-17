from __future__ import annotations

import json
import math

from sqlalchemy.orm import Session

from ..models import ProfileCollectionDraft, ProfileCollectionItem, ResumeVersion, utcnow
from .collection_service import create_collection_item_uncommitted
from .collections import validate_collection_payload
from .extraction import CollectionDraftCandidate

__all__ = [
    "CollectionDraftCandidate",
    "ProfileCollectionDraftAlreadyReviewedError",
    "ProfileCollectionDraftNotFoundError",
    "accept_collection_draft",
    "create_collection_drafts",
    "reject_collection_draft",
]


class ProfileCollectionDraftNotFoundError(LookupError):
    pass


class ProfileCollectionDraftAlreadyReviewedError(RuntimeError):
    pass


def _dump(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def validate_collection_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("collection draft confidence must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0 or normalized > 1:
        raise ValueError("collection draft confidence must be between 0 and 1")
    return normalized


def _pending_draft(session: Session, draft_id: int) -> ProfileCollectionDraft:
    draft = session.get(ProfileCollectionDraft, draft_id)
    if draft is None:
        raise ProfileCollectionDraftNotFoundError(f"Profile collection draft {draft_id} not found")
    if draft.status != "PENDING":
        raise ProfileCollectionDraftAlreadyReviewedError(
            f"Profile collection draft {draft_id} has already been reviewed"
        )
    return draft


def create_collection_drafts(
    session: Session,
    resume_version: ResumeVersion,
    candidates: list[CollectionDraftCandidate],
) -> list[ProfileCollectionDraft]:
    try:
        prepared: list[tuple[CollectionDraftCandidate, dict[str, object], float | None, str]] = []
        for candidate in candidates:
            normalized_payload = validate_collection_payload(candidate.kind, candidate.payload)
            confidence = validate_collection_confidence(candidate.confidence)
            extractor_name = candidate.extractor_name.strip()
            if not extractor_name:
                raise ValueError("collection draft extractor_name is required")
            prepared.append((candidate, normalized_payload, confidence, extractor_name))

        drafts: list[ProfileCollectionDraft] = []
        for candidate, normalized_payload, confidence, extractor_name in prepared:
            draft = ProfileCollectionDraft(
                resume_version_id=resume_version.id,
                kind=candidate.kind,
                payload_json=_dump(normalized_payload),
                confidence=confidence,
                extractor_name=extractor_name,
                status="PENDING",
            )
            session.add(draft)
            drafts.append(draft)

        session.commit()
        for draft in drafts:
            session.refresh(draft)
        return drafts
    except Exception:
        session.rollback()
        raise


def accept_collection_draft(session: Session, draft_id: int) -> ProfileCollectionItem:
    try:
        draft = _pending_draft(session, draft_id)
        payload = json.loads(draft.payload_json)
        item = create_collection_item_uncommitted(
            session,
            draft.kind,
            payload,
            source_type="resume",
            source_ref=draft.resume_version_id,
            confidence=draft.confidence,
            confirmed=True,
        )
        draft.status = "ACCEPTED"
        draft.reviewed_at = utcnow()
        session.commit()
        session.refresh(draft)
        session.refresh(item)
        return item
    except Exception:
        session.rollback()
        raise


def reject_collection_draft(session: Session, draft_id: int) -> ProfileCollectionDraft:
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
