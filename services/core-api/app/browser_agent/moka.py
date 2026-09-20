from __future__ import annotations

import re
from dataclasses import replace

from .models import FormFieldDescriptor, FormScan

# Moka's public application schema uses stable semantic modules such as
# basicInfo, educationInfo[], experienceInfo[], projectInfo[] and languageInfo[].
# When those paths are exposed through an input name, prefer them over label
# heuristics. This is deliberately conservative: unknown/custom fields stay
# unmatched instead of being guessed.

_SCALAR_FIELDS: dict[tuple[str, str], str] = {
    ("basicInfo", "name"): "identity.name",
    ("basicInfo", "gender"): "identity.gender",
    ("basicInfo", "phone"): "contact.phone",
    ("basicInfo", "email"): "contact.email",
    ("basicInfo", "political"): "identity.political_status",
}

_COLLECTION_FIELDS: dict[str, tuple[str, dict[str, str]]] = {
    "educationInfo": (
        "education",
        {
            "school": "school",
            "speciality": "major",
            "academicDegree": "degree",
            "startDate": "start_date",
            "endDate": "end_date",
        },
    ),
    "experienceInfo": (
        "experience",
        {
            "company": "organization",
            "title": "role",
            "location": "location",
            "startDate": "start_date",
            "endDate": "end_date",
            "summary": "bullets",
        },
    ),
    "projectInfo": (
        "project",
        {
            "projectName": "name",
            "title": "role",
            "startDate": "start_date",
            "endDate": "end_date",
            "projectDescription": "description",
            "responsibilities": "bullets",
        },
    ),
    "languageInfo": (
        "language",
        {
            "language": "name",
            "level": "level",
        },
    ),
    "awardInfo": (
        "award",
        {
            "awardName": "name",
            "awardDate": "date",
        },
    ),
}

_KNOWN_MODULES = {
    "basicInfo",
    "educationInfo",
    "experienceInfo",
    "projectInfo",
    "practiceInfo",
    "languageInfo",
    "awardInfo",
    "jobIntention",
    "selfDescription",
    "customFields",
}


def _tokens(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    # Support common browser form encodings:
    #   educationInfo[1].school
    #   educationInfo[1][school]
    #   educationInfo.1.school
    text = re.sub(r"\[([^\[\]]+)]", r".\1", text)
    tokens = [part for part in text.split(".") if part]
    if not tokens:
        return []

    # Some frameworks prefix the form model (values., candidateInfo., etc.).
    # Ignore only leading tokens; module/field names themselves must match
    # exactly so arbitrary custom fields cannot acquire a privileged mapping.
    for index, token in enumerate(tokens):
        if token in _KNOWN_MODULES:
            return tokens[index:]
    return []


def moka_source_path(raw_name: str) -> str | None:
    tokens = _tokens(raw_name)
    if len(tokens) == 2:
        return _SCALAR_FIELDS.get((tokens[0], tokens[1]))

    if len(tokens) != 3:
        return None

    module, index_text, field = tokens
    if not index_text.isdigit():
        return None

    definition = _COLLECTION_FIELDS.get(module)
    if definition is None:
        # practiceInfo is intentionally not mapped yet: the local SSOT merges
        # work and internship into one experience collection, so assigning a
        # Moka practice row to an arbitrary experience index would be unsafe.
        return None

    kind, field_map = definition
    local_field = field_map.get(field)
    if local_field is None:
        return None

    return f"collections.{kind}[{int(index_text)}].{local_field}"


def _adapt_field(field: FormFieldDescriptor) -> FormFieldDescriptor:
    if field.adapter_source_path:
        return field
    hint = moka_source_path(field.name)
    if hint is None:
        return field
    return replace(field, adapter_source_path=hint)


def apply_moka_scan_hints(scan: FormScan) -> FormScan:
    return FormScan(
        url=scan.url,
        title=scan.title,
        fields=[_adapt_field(field) for field in scan.fields],
        target_id=scan.target_id,
    )
