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
}

_KNOWN_MODULES = {
    "basicInfo",
    "educationInfo",
    "experienceInfo",
    "projectInfo",
    "practiceInfo",
    "languageInfo",
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

    # Ant Design frequently derives DOM ids from nested form names, e.g.
    # educationInfo_1_school. Only accept underscore encoding when a known
    # Moka module is present, keeping arbitrary element ids out of the mapper.
    if "." not in text:
        for module in _KNOWN_MODULES:
            marker = module + "_"
            position = text.find(marker)
            if position >= 0:
                suffix = text[position:].replace("_", ".")
                text = suffix
                break

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


def _moka_file_action(field: FormFieldDescriptor) -> str:
    if (field.input_type or "").lower() != "file":
        return ""
    for raw in (field.name, field.dom_id):
        value = (raw or "").strip().lower()
        if value == "resume" or value.endswith(".resume") or value.endswith("_resume"):
            if "attachment" not in value:
                return "resume_upload"
    return ""


def _adapt_field(field: FormFieldDescriptor) -> FormFieldDescriptor:
    action = _moka_file_action(field)
    if action:
        return replace(field, adapter_action=action)

    if field.adapter_source_path:
        return field

    hint = moka_source_path(field.name)
    if hint is None:
        hint = moka_source_path(field.dom_id)
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
