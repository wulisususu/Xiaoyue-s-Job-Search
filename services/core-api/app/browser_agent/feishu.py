from __future__ import annotations

import re
from dataclasses import replace

from .models import FormFieldDescriptor, FormScan

# Feishu Hire's public talent schema exposes stable modules such as basic_info,
# education_list, career_list, project_list, award_list and language_list.
# Only exact documented module/field paths receive privileged mapping.
#
# Deliberately excluded:
# - identification / identification_number
# - hometown_city -> hukou coercion (not equivalent semantics)
# - customized_data_list
# - attachments
# - works_list -> project coercion (could collide with project_list indexes)

_SCALAR_FIELDS: dict[str, str] = {
    "name": "identity.name",
    "mobile": "contact.phone",
    "email": "contact.email",
    "gender": "identity.gender",
    "birthday": "identity.birth_date",
    "current_city": "location.current_city",
}

_COLLECTION_FIELDS: dict[str, tuple[str, dict[str, str]]] = {
    "education_list": (
        "education",
        {
            "school": "school",
            "field_of_study": "major",
            "degree": "degree",
            "start_time": "start_date",
            "end_time": "end_date",
            "academic_ranking": "ranking",
        },
    ),
    "career_list": (
        "experience",
        {
            "company": "organization",
            "title": "role",
            "desc": "bullets",
            "start_time": "start_date",
            "end_time": "end_date",
        },
    ),
    "project_list": (
        "project",
        {
            "name": "name",
            "role": "role",
            "desc": "description",
            "start_time": "start_date",
            "end_time": "end_date",
        },
    ),
    "award_list": (
        "award",
        {
            "title": "name",
            "award_time": "date",
            "desc": "description",
        },
    ),
    "language_list": (
        "language",
        {
            "language": "name",
            "proficiency": "level",
        },
    ),
}

_KNOWN_MODULES = {
    "basic_info",
    "education_list",
    "career_list",
    "project_list",
    "award_list",
    "language_list",
    "works_list",
    "customized_data_list",
}


def _tokens(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []

    text = re.sub(r"\[([^\[\]]+)]", r".\1", text)
    tokens = [part for part in text.split(".") if part]

    if len(tokens) > 1:
        for index, token in enumerate(tokens):
            if token in _KNOWN_MODULES:
                return tokens[index:]
        return []

    # Flattened React/form ids may look like:
    #   talent_basic_info_name
    #   talent_education_list_1_school
    # Module names themselves contain underscores, so split only the suffix
    # after the exact documented module marker.
    for module in sorted(_KNOWN_MODULES, key=len, reverse=True):
        marker = module + "_"
        position = text.find(marker)
        if position < 0:
            continue
        suffix = text[position + len(marker):]
        if module == "basic_info":
            return [module, suffix] if suffix else []
        match = re.fullmatch(r"(\d+)_(.+)", suffix)
        if match:
            return [module, match.group(1), match.group(2)]
        return []

    return []


def feishu_source_path(raw_name: str) -> str | None:
    tokens = _tokens(raw_name)

    if len(tokens) == 2 and tokens[0] == "basic_info":
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

    hint = feishu_source_path(field.name)
    if hint is None:
        hint = feishu_source_path(field.dom_id)
    if hint is None:
        return field
    return replace(field, adapter_source_path=hint)


def apply_feishu_scan_hints(scan: FormScan) -> FormScan:
    return FormScan(
        url=scan.url,
        title=scan.title,
        fields=[_adapt_field(field) for field in scan.fields],
        target_id=scan.target_id,
    )
