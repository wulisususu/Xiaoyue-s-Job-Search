from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .registry import FIELD_REGISTRY

_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)(?![A-Za-z0-9-])")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")

DETERMINISTIC_PROVIDER_ID = "deterministic"
DETERMINISTIC_MODEL = "deterministic-contact-v1"
DETERMINISTIC_PROMPT_VERSION = "none"
DETERMINISTIC_SCHEMA_VERSION = "deterministic-v1"


@dataclass(frozen=True, slots=True)
class DraftCandidate:
    field_key: str
    value: Any
    value_type: str
    confidence: float
    extractor_name: str


@dataclass(frozen=True, slots=True)
class CollectionDraftCandidate:
    kind: str
    payload: dict[str, object]
    confidence: float | None
    extractor_name: str


@dataclass(frozen=True, slots=True)
class ExtractionMetadata:
    provider: str
    model: str
    prompt_version: str
    schema_version: str


@dataclass(frozen=True, slots=True)
class ProfileExtractionBundle:
    """Unified provider output: scalar field candidates plus structured
    collection candidates plus the provenance needed by AIExtractionRun."""

    fields: list[DraftCandidate]
    collections: list[CollectionDraftCandidate]
    metadata: ExtractionMetadata


@runtime_checkable
class ProfileExtractionProvider(Protocol):
    """The one formal AI extraction contract.

    Implementations must be side-effect free, pure functions of the resume
    text: they never touch the database, never write Profile SSOT, and their
    output is only ever allowed to become PENDING drafts after validation.
    """

    def extract(self, text: str) -> ProfileExtractionBundle: ...


def _extract_contact_candidates(text: str) -> list[DraftCandidate]:
    """Extract only facts with strict textual syntax; never infer semantics."""
    candidates: list[DraftCandidate] = []
    seen: set[tuple[str, str]] = set()

    for match in _EMAIL_RE.finditer(text or ""):
        value = match.group(1)
        identity = ("contact.email", value.lower())
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(
            DraftCandidate(
                field_key="contact.email",
                value=value,
                value_type=FIELD_REGISTRY["contact.email"].value_type,
                confidence=0.99,
                extractor_name="deterministic-contact-v1",
            )
        )

    for match in _PHONE_RE.finditer(text or ""):
        value = match.group(1)
        identity = ("contact.phone", value)
        if identity in seen:
            continue
        seen.add(identity)
        candidates.append(
            DraftCandidate(
                field_key="contact.phone",
                value=value,
                value_type=FIELD_REGISTRY["contact.phone"].value_type,
                confidence=0.99,
                extractor_name="deterministic-contact-v1",
            )
        )

    return candidates


class DeterministicExtractionProvider:
    """Offline contact fact extractor conforming to the unified contract."""

    def extract(self, text: str) -> ProfileExtractionBundle:
        return ProfileExtractionBundle(
            fields=_extract_contact_candidates(text),
            collections=[],
            metadata=ExtractionMetadata(
                provider=DETERMINISTIC_PROVIDER_ID,
                model=DETERMINISTIC_MODEL,
                prompt_version=DETERMINISTIC_PROMPT_VERSION,
                schema_version=DETERMINISTIC_SCHEMA_VERSION,
            ),
        )


def extract_deterministic(text: str) -> list[DraftCandidate]:
    """Backward-compatible scalar-only view of the deterministic provider."""
    return DeterministicExtractionProvider().extract(text).fields


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scalar_candidate_fingerprint(candidate: DraftCandidate) -> str:
    """Stable candidate identity for replay-safe draft persistence.

    Callers must pass validated/normalized candidates (registry validation
    already ran), so that two deliveries of the same fact collapse to the
    same fingerprint instead of duplicate drafts.
    """
    return _fingerprint({"field_key": candidate.field_key, "value": candidate.value})


def collection_candidate_fingerprint(candidate: CollectionDraftCandidate) -> str:
    """Stable collection candidate identity for replay-safe persistence."""
    return _fingerprint({"kind": candidate.kind, "payload": candidate.payload})
