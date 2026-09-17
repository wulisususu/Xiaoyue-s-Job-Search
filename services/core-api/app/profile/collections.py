from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CollectionFieldDefinition:
    key: str
    label: str
    value_type: str = "string"
    required: bool = False
    multiple: bool = False


@dataclass(frozen=True, slots=True)
class CollectionDefinition:
    kind: str
    label: str
    fields: tuple[CollectionFieldDefinition, ...]


def _s(key: str, label: str, *, required: bool = False) -> CollectionFieldDefinition:
    return CollectionFieldDefinition(key=key, label=label, required=required)


def _l(key: str, label: str, *, required: bool = False) -> CollectionFieldDefinition:
    return CollectionFieldDefinition(
        key=key,
        label=label,
        value_type="string_list",
        required=required,
        multiple=True,
    )


COLLECTION_REGISTRY: dict[str, CollectionDefinition] = {
    "education": CollectionDefinition(
        kind="education",
        label="教育经历",
        fields=(
            _s("school", "学校", required=True),
            _s("degree", "学历/学位"),
            _s("major", "专业"),
            _s("start_date", "开始时间"),
            _s("end_date", "结束时间"),
            _s("gpa", "GPA"),
            _s("ranking", "排名"),
        ),
    ),
    "experience": CollectionDefinition(
        kind="experience",
        label="工作/实习经历",
        fields=(
            _s("organization", "组织/公司", required=True),
            _s("role", "职位/角色", required=True),
            _s("location", "地点"),
            _s("start_date", "开始时间"),
            _s("end_date", "结束时间"),
            _l("bullets", "经历要点"),
        ),
    ),
    "project": CollectionDefinition(
        kind="project",
        label="项目经历",
        fields=(
            _s("name", "项目名称", required=True),
            _s("role", "角色"),
            _s("start_date", "开始时间"),
            _s("end_date", "结束时间"),
            _s("description", "项目描述"),
            _l("bullets", "项目要点"),
        ),
    ),
    "award": CollectionDefinition(
        kind="award",
        label="奖项荣誉",
        fields=(
            _s("name", "奖项名称", required=True),
            _s("issuer", "颁发方"),
            _s("date", "获奖时间"),
            _s("level", "级别"),
            _s("description", "说明"),
        ),
    ),
    "certificate": CollectionDefinition(
        kind="certificate",
        label="证书",
        fields=(
            _s("name", "证书名称", required=True),
            _s("issuer", "颁发机构"),
            _s("date", "获得时间"),
            _s("credential_id", "证书编号"),
        ),
    ),
    "language": CollectionDefinition(
        kind="language",
        label="语言能力",
        fields=(
            _s("name", "语言", required=True),
            _s("level", "等级"),
            _s("score", "成绩"),
        ),
    ),
    "skill": CollectionDefinition(
        kind="skill",
        label="技能",
        fields=(
            _s("name", "技能名称", required=True),
            _s("level", "熟练度"),
            _s("description", "说明"),
        ),
    ),
}


def get_collection_definition(kind: str) -> CollectionDefinition:
    try:
        return COLLECTION_REGISTRY[kind]
    except KeyError as exc:
        raise KeyError(f"Unknown profile collection kind: {kind}") from exc


def _normalize_string(value: Any, *, key: str, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{key} is required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    normalized = value.strip()
    if not normalized:
        if required:
            raise ValueError(f"{key} is required")
        return None
    return normalized


def _normalize_string_list(value: Any, *, key: str, required: bool) -> list[str] | None:
    if value is None:
        if required:
            raise ValueError(f"{key} is required")
        return None
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain only strings")
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    if required and not normalized:
        raise ValueError(f"{key} is required")
    return normalized or None


def validate_collection_payload(kind: str, payload: Any) -> dict[str, Any]:
    definition = get_collection_definition(kind)
    if not isinstance(payload, dict):
        raise ValueError("collection payload must be an object")

    fields_by_key = {field.key: field for field in definition.fields}
    unknown = sorted(set(payload) - set(fields_by_key))
    if unknown:
        raise ValueError(f"unknown fields for {kind}: {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for field in definition.fields:
        raw = payload.get(field.key)
        if field.multiple:
            value = _normalize_string_list(raw, key=field.key, required=field.required)
        else:
            value = _normalize_string(raw, key=field.key, required=field.required)
        if value is not None:
            normalized[field.key] = value

    return normalized
