"""Extraction run orchestration: the one formal chain
``Resume → AIExtractionRun → provider → validated Drafts → review``.

The AI output is only ever persisted as PENDING drafts; Profile SSOT stays
reachable exclusively through human accept. Draft identity is the pair
``(extraction_run_id, candidate_fingerprint)`` so replaying the same run
never duplicates a candidate.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AIExtractionRun, ProfileCollectionDraft, ProfileDraftField, ResumeVersion, utcnow
from .collection_drafts import validate_collection_confidence
from .collections import validate_collection_payload
from .extraction import (
    CollectionDraftCandidate,
    DraftCandidate,
    ProfileExtractionBundle,
    ProfileExtractionProvider,
    collection_candidate_fingerprint,
    scalar_candidate_fingerprint,
)
from .registry import get_field_definition, validate_profile_value

__all__ = [
    "ResumeNotExtractableError",
    "execute_extraction_run",
    "persist_bundle_drafts",
    "start_extraction_run",
]


class ResumeNotExtractableError(ValueError):
    """Resume version has no extracted text available for provider runs."""


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def start_extraction_run(
    session: Session,
    resume_version: ResumeVersion,
    provider: ProfileExtractionProvider,
) -> AIExtractionRun:
    metadata = provider.metadata()
    run = AIExtractionRun(
        resume_version_id=resume_version.id,
        provider=metadata.provider,
        model=metadata.model,
        prompt_version=metadata.prompt_version,
        schema_version=metadata.schema_version,
        status="RUNNING",
        input_hash=_input_hash(resume_version.extracted_text or ""),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _fail_run(session: Session, run: AIExtractionRun, error: Exception) -> None:
    run.status = "FAILED"
    run.error = str(error)
    run.completed_at = utcnow()
    session.commit()


def persist_bundle_drafts(
    session: Session,
    resume_version: ResumeVersion,
    run: AIExtractionRun,
    bundle: ProfileExtractionBundle,
) -> None:
    """Idempotently turn a provider bundle into PENDING drafts.

    Candidates that fail registry/collection validation are dropped
    individually; the valid remainder survives. Candidates already stored
    under this run are skipped, backed by the partial unique index on
    ``(extraction_run_id, candidate_fingerprint)``.
    """
    existing_scalar = set(
        session.scalars(
            select(ProfileDraftField.candidate_fingerprint).where(
                ProfileDraftField.extraction_run_id == run.id
            )
        )
    )
    existing_collection = set(
        session.scalars(
            select(ProfileCollectionDraft.candidate_fingerprint).where(
                ProfileCollectionDraft.extraction_run_id == run.id
            )
        )
    )

    for candidate in bundle.fields:
        try:
            normalized = validate_profile_value(candidate.field_key, candidate.value)
            confidence = float(candidate.confidence)
        except (KeyError, ValueError, TypeError):
            continue
        definition = get_field_definition(candidate.field_key)
        if definition.sensitive:
            continue
        normalized_candidate = DraftCandidate(
            field_key=candidate.field_key,
            value=normalized,
            value_type=definition.value_type,
            confidence=confidence,
            extractor_name=candidate.extractor_name,
        )
        fingerprint = scalar_candidate_fingerprint(normalized_candidate)
        if fingerprint in existing_scalar:
            continue
        existing_scalar.add(fingerprint)
        session.add(
            ProfileDraftField(
                resume_version_id=resume_version.id,
                extraction_run_id=run.id,
                field_key=candidate.field_key,
                value_json=_dump(normalized),
                value_type=definition.value_type,
                confidence=confidence,
                extractor_name=candidate.extractor_name,
                candidate_fingerprint=fingerprint,
                status="PENDING",
            )
        )

    for candidate in bundle.collections:
        try:
            normalized_payload = validate_collection_payload(candidate.kind, candidate.payload)
            confidence = validate_collection_confidence(candidate.confidence)
        except (KeyError, ValueError, TypeError):
            continue
        normalized_candidate = CollectionDraftCandidate(
            kind=candidate.kind,
            payload=normalized_payload,
            confidence=confidence,
            extractor_name=candidate.extractor_name,
        )
        fingerprint = collection_candidate_fingerprint(normalized_candidate)
        if fingerprint in existing_collection:
            continue
        existing_collection.add(fingerprint)
        session.add(
            ProfileCollectionDraft(
                resume_version_id=resume_version.id,
                extraction_run_id=run.id,
                kind=candidate.kind,
                payload_json=_dump(normalized_payload),
                confidence=confidence,
                extractor_name=candidate.extractor_name,
                candidate_fingerprint=fingerprint,
                status="PENDING",
            )
        )
    session.commit()


def execute_extraction_run(
    session: Session,
    resume_version: ResumeVersion,
    provider: ProfileExtractionProvider,
) -> AIExtractionRun:
    """Run the full lifecycle: RUNNING run row → provider call → validated
    drafts → SUCCEEDED, or FAILED run + error and no drafts."""
    text = resume_version.extracted_text or ""
    if resume_version.extraction_status != "EXTRACTED" or not text:
        raise ResumeNotExtractableError(
            f"Resume version {resume_version.id} has no extracted text to run extraction on"
        )

    run = start_extraction_run(session, resume_version, provider)

    try:
        bundle = provider.extract(text)
    except Exception as error:
        _fail_run(session, run, error)
        raise

    try:
        persist_bundle_drafts(session, resume_version, run, bundle)
    except Exception as error:
        _fail_run(session, run, error)
        raise

    run.status = "SUCCEEDED"
    run.completed_at = utcnow()
    session.commit()
    session.refresh(run)
    return run
