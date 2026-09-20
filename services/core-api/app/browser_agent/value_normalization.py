from __future__ import annotations

import re
import unicodedata
from typing import Any

from .models import FormFieldDescriptor


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).strip().lower())


_OPTION_ALIAS_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    "identity.gender": (
        frozenset({"女", "女性", "female", "f"}),
        frozenset({"男", "男性", "male", "m"}),
    ),
    "identity.id_type": (
        frozenset({"身份证", "居民身份证", "中华人民共和国居民身份证", "二代身份证"}),
        frozenset({"护照", "passport"}),
    ),
    "collections.education[].degree": (
        frozenset({"本科", "大学本科", "本科生"}),
        frozenset({"专科", "大专", "大学专科", "专科生"}),
        frozenset({"硕士", "硕士研究生"}),
        frozenset({"博士", "博士研究生"}),
    ),
    "education.degree": (
        frozenset({"本科", "大学本科", "本科生"}),
        frozenset({"专科", "大专", "大学专科", "专科生"}),
        frozenset({"硕士", "硕士研究生"}),
        frozenset({"博士", "博士研究生"}),
    ),
}


def _path_template(source_path: str) -> str:
    return re.sub(r"\[\d+\]", "[]", source_path)


def _resolve_exact_option(value: Any, options: list[str]) -> str | None:
    normalized = _norm(value)
    matches = [option for option in options if _norm(option) == normalized]
    return matches[0] if len(matches) == 1 else None


def _resolve_alias_option(source_path: str, value: Any, options: list[str]) -> str | None:
    groups = _OPTION_ALIAS_GROUPS.get(_path_template(source_path), ())
    source = _norm(value)
    for group in groups:
        normalized_group = {_norm(alias) for alias in group}
        if source not in normalized_group:
            continue
        matches = [option for option in options if _norm(option) in normalized_group]
        return matches[0] if len(matches) == 1 else None
    return None


def _format_date(value: str, placeholder: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", value.strip())
    if not match:
        return value
    year, month, day = match.groups()
    hint = unicodedata.normalize("NFKC", placeholder or "").upper().replace(" ", "")

    if day is not None:
        if "YYYY年MM月DD日" in hint:
            return f"{year}年{month}月{day}日"
        if "YYYY/MM/DD" in hint:
            return f"{year}/{month}/{day}"
        if "YYYY-MM-DD" in hint:
            return f"{year}-{month}-{day}"

    if "YYYY年MM月" in hint:
        return f"{year}年{month}月"
    if "YYYY/MM" in hint:
        return f"{year}/{month}"
    if "YYYY-MM" in hint:
        return f"{year}-{month}"
    return value


def normalize_value_for_control(
    source_path: str,
    value: Any,
    field: FormFieldDescriptor,
) -> Any | None:
    """Return an exact value for the current control or None when ambiguous.

    Matching is deliberately conservative: exact page options win, then only
    path-specific equivalence groups are considered. Substring/fuzzy matching
    is intentionally excluded.
    """
    control_type = (field.input_type or field.tag or "text").lower()

    if control_type in {"date", "date_picker", "month"} and isinstance(value, str):
        return _format_date(value, field.placeholder)

    option_control = (
        bool(field.options)
        or field.tag.lower() == "select"
        or control_type in {"select", "radio", "radio_group", "combobox"}
    )
    if not option_control:
        return value

    if not field.options:
        return value

    exact = _resolve_exact_option(value, field.options)
    if exact is not None:
        return exact
    return _resolve_alias_option(source_path, value, field.options)
