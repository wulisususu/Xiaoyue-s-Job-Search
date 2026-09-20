from __future__ import annotations

import re
from dataclasses import replace

from .models import FormFieldDescriptor, FormScan

# Beisen's public RecruitV6 schema exposes stable Standard Resume modules such
# as personProfile, education, workExperience and project. When those paths are
# surfaced by DOM name/id attributes, use them as high-confidence structure.
#
# This adapter is intentionally conservative:
# - no family / relativesDeclaration / credentialsInfo mapping
# - no internship -> experience coercion (would collide with workExperience)
# - no arbitrary custom/sub-collection mapping
# - unknown fields fall back to the generic rule/AI layer

_SCALAR_FIELDS: dict[str, str] = {
    "Name": "identity.name",
    "name": "identity.name",
    "Mobile": "contact.phone",
    "mobile": "contact.phone",
    "Birthday": "identity.birth_date",
    "birthday": "identity.birth_date",
    "Polity": "identity.political_status",
    "polity": "identity.political_status",
}

_COLLECTION_FIELDS: dict[str, tuple[str, dict[str, str]]] = {
    "education": (
        "education",
        {
            "schoolName": "school",
            "SchoolName": "school",
            "collegeName": "school",
            "CollegeName": "school",
            "majorName": "major",
            "MajorName": "major",
            "degree": "degree",
            "Degree": "degree",
            "startDate": "start_date",
            "StartDate": "start_date",
            "endDate": "end_date",
            "EndDate": "end_date",
        },
    ),
    "workExperience": (
        "experience",
        {
            "companyName": "organization",
            "CompanyName": "organization",
            "jobTitle": "role",
            "JobTitle": "role",
            "job": "role",
            "Job": "role",
            "startDate": "start_date",
            "StartDate": "start_date",
            "endDate": "end_date",
            "EndDate": "end_date",
            "jobDuty": "bullets",
            "JobDuty": "bullets",
            "duty": "bullets",
            "Duty": "bullets",
        },
    ),
    "project": (
        "project",
        {
            "projectName": "name",
            "ProjectName": "name",
            "job": "role",
            "Job": "role",
            "startDate": "start_date",
            "StartDate": "start_date",
            "endDate": "end_date",
            "EndDate": "end_date",
            "projectDescribe": "description",
            "ProjectDescribe": "description",
            "duty": "bullets",
            "Duty": "bullets",
        },
    ),
}

_KNOWN_MODULES = {
    "personProfile",
    "education",
    "workExperience",
    "project",
    "internship",
    "lang",
    "skill",
    "family",
    "relativesDeclaration",
    "credentialsInfo",
    "attachments",
    "resumeFile",
    "question",
}


def _tokens(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    text = re.sub(r"\[([^\[\]]+)]", r".\1", text)

    # Typical nested-form ids may flatten paths with underscores, e.g.
    # standardResume_education_1_schoolName. Only decode this form when a
    # documented Beisen module marker is present.
    if "." not in text:
        for module in _KNOWN_MODULES:
            marker = module + "_"
            position = text.find(marker)
            if position >= 0:
                text = text[position:].replace("_", ".")
                break

    tokens = [part for part in text.split(".") if part]
    if not tokens:
        return []

    for index, token in enumerate(tokens):
        if token in _KNOWN_MODULES:
            tokens = tokens[index:]
            break
    else:
        return []

    # Beisen standard-resume JSON commonly wraps each field as
    # {"FieldName": {"value": ...}}. Browser form bindings may expose that
    # final ".value" segment; it is structure, not a separate field.
    if tokens and tokens[-1].lower() == "value":
        tokens = tokens[:-1]
    return tokens


def beisen_source_path(raw_name: str) -> str | None:
    tokens = _tokens(raw_name)
    if len(tokens) == 2 and tokens[0] == "personProfile":
        return _SCALAR_FIELDS.get(tokens[1])

    if len(tokens) != 3:
        return None

    module, index_text, field = tokens
    if not index_text.isdigit():
        return None

    definition = _COLLECTION_FIELDS.get(module)
    if definition is None:
        return None

    kind, field_map = definition
    local_field = field_map.get(field)
    if local_field is None:
        return None

    return f"collections.{kind}[{int(index_text)}].{local_field}"


def _adapt_field(field: FormFieldDescriptor) -> FormFieldDescriptor:
    if field.adapter_source_path:
        return field

    hint = beisen_source_path(field.name)
    if hint is None:
        hint = beisen_source_path(field.dom_id)
    if hint is None:
        return field
    return replace(field, adapter_source_path=hint)


def apply_beisen_scan_hints(scan: FormScan) -> FormScan:
    return FormScan(
        url=scan.url,
        title=scan.title,
        fields=[_adapt_field(field) for field in scan.fields],
        target_id=scan.target_id,
    )
