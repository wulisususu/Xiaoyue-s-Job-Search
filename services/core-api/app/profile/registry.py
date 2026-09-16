from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
_EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    field_key: str
    label: str
    category: str
    value_type: str
    multiple: bool = False


_DEFINITIONS = [
    FieldDefinition("identity.name", "姓名", "身份信息", "string"),
    FieldDefinition("contact.phone", "手机号", "联系方式", "string"),
    FieldDefinition("contact.email", "邮箱", "联系方式", "string"),
    FieldDefinition("education.school", "学校", "教育经历", "string"),
    FieldDefinition("education.major", "专业", "教育经历", "string"),
    FieldDefinition("education.degree", "学历/学位", "教育经历", "string"),
    FieldDefinition("education.graduation_date", "毕业时间", "教育经历", "string"),
    FieldDefinition("location.hukou", "户籍地", "地点信息", "string"),
    FieldDefinition("location.current_city", "当前城市", "地点信息", "string"),
    FieldDefinition("job.target_roles", "目标岗位", "求职偏好", "string_list", multiple=True),
    FieldDefinition("skills.summary", "技能概述", "能力经历", "string"),
    FieldDefinition("experience.summary", "经历概述", "能力经历", "string"),
    FieldDefinition("awards.summary", "获奖概述", "能力经历", "string"),
]

FIELD_REGISTRY: dict[str, FieldDefinition] = {item.field_key: item for item in _DEFINITIONS}


def get_field_definition(field_key: str) -> FieldDefinition:
    try:
        return FIELD_REGISTRY[field_key]
    except KeyError as exc:
        raise KeyError(f"Unknown profile field: {field_key}") from exc


def _non_empty_string(value: Any, field_key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_key} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_key} cannot be empty")
    return normalized


def validate_profile_value(field_key: str, value: Any) -> Any:
    definition = get_field_definition(field_key)

    if definition.multiple:
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field_key} must be a non-empty list")
        normalized_items = [_non_empty_string(item, field_key) for item in value]
        if len(set(normalized_items)) != len(normalized_items):
            raise ValueError(f"{field_key} contains duplicate values")
        return normalized_items

    normalized = _non_empty_string(value, field_key)
    if field_key == "contact.phone" and not _PHONE_RE.fullmatch(normalized):
        raise ValueError("contact.phone must be a valid mainland China mobile number")
    if field_key == "contact.email" and not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("contact.email must be a valid email address")
    return normalized
