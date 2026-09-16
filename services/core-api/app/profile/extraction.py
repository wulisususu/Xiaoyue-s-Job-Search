from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .registry import FIELD_REGISTRY

_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)(?![A-Za-z0-9-])")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")


@dataclass(frozen=True, slots=True)
class DraftCandidate:
    field_key: str
    value: Any
    value_type: str
    confidence: float
    extractor_name: str


class ProfileExtractionProvider(Protocol):
    def extract(self, text: str, registry: dict = FIELD_REGISTRY) -> list[DraftCandidate]: ...


def extract_deterministic(text: str) -> list[DraftCandidate]:
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
