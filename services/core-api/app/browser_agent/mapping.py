from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from .models import (
    ConfirmedProfileSnapshot,
    FillPlan,
    FillPlanItem,
    FormFieldDescriptor,
    FormScan,
    PlanFieldSummary,
)

_BLOCKED_TYPES = {"hidden", "password", "file", "submit", "button", "reset", "image", "checkbox"}
_HIGH_CONFIDENCE = 0.92


@dataclass(frozen=True, slots=True)
class _Rule:
    source_paths: tuple[str, ...]
    aliases: tuple[str, ...]
    weak_aliases: tuple[str, ...] = ()
    section_terms: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()


_RULES: tuple[_Rule, ...] = (
    _Rule(
        ("identity.name",),
        ("姓名", "真实姓名", "中文姓名", "full name", "fullname", "realname"),
        negative_terms=("紧急联系人", "联系人姓名", "推荐人", "父亲", "母亲", "家庭成员", "公司名称", "企业名称"),
    ),
    _Rule(
        ("contact.phone",),
        ("手机号码", "手机号", "手机", "联系电话", "移动电话", "mobile", "phone", "telephone"),
        negative_terms=("紧急联系人", "联系人电话", "公司电话", "单位电话"),
    ),
    _Rule(
        ("contact.email",),
        ("电子邮箱", "邮箱地址", "邮箱", "e-mail", "email"),
        negative_terms=("紧急联系人", "公司邮箱", "单位邮箱"),
    ),
    _Rule(
        ("collections.education[0].school", "education.school"),
        ("毕业院校", "就读院校", "学校名称", "院校名称", "学校", "院校", "university", "school"),
        section_terms=("教育", "学历", "education"),
    ),
    _Rule(
        ("collections.education[0].major", "education.major"),
        ("所学专业", "专业名称", "专业", "major"),
        section_terms=("教育", "学历", "education"),
    ),
    _Rule(
        ("collections.education[0].degree", "education.degree"),
        ("最高学历", "学历/学位", "学历", "学位", "degree", "education level"),
        section_terms=("教育", "学历", "education"),
    ),
    _Rule(
        ("education.graduation_date", "collections.education[0].end_date"),
        ("毕业时间", "毕业日期", "graduation date", "graduate date"),
        section_terms=("教育", "学历", "education"),
    ),
    _Rule(
        ("location.hukou",),
        ("户籍所在地", "户口所在地", "户籍地", "户籍", "户口"),
        weak_aliases=("生源地", "籍贯"),
    ),
    _Rule(
        ("location.current_city",),
        ("现居住地", "现居城市", "当前城市", "所在地", "current city", "city"),
        negative_terms=("户籍", "户口", "生源", "籍贯"),
    ),
    _Rule(
        ("collections.experience[0].organization",),
        ("实习单位", "工作单位", "公司名称", "单位名称", "organization", "company"),
        section_terms=("实习经历", "工作经历", "experience"),
    ),
    _Rule(
        ("collections.experience[0].role",),
        ("职位名称", "岗位名称", "担任职务", "职位", "岗位", "role", "position"),
        section_terms=("实习经历", "工作经历", "experience"),
    ),
    _Rule(
        ("collections.project[0].name",),
        ("项目名称", "project name"),
        section_terms=("项目经历", "项目", "project"),
    ),
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").strip().lower())


_COLLECTION_PATH_RE = re.compile(r"collections\.([a-z_]+)\[(\d+)]\.([a-z_]+)")


def _collection_template(path: str) -> tuple[str, str] | None:
    match = _COLLECTION_PATH_RE.fullmatch(path)
    if not match:
        return None
    kind, _index_text, field = match.groups()
    return kind, field


def _source_value(snapshot: ConfirmedProfileSnapshot, path: str) -> Any | None:
    if not path.startswith("collections."):
        value = snapshot.scalars.get(path)
        return value if value not in (None, "", []) else None

    match = _COLLECTION_PATH_RE.fullmatch(path)
    if not match:
        return None
    kind, index_text, field = match.groups()
    items = snapshot.collections.get(kind) or []
    index = int(index_text)
    if index >= len(items):
        return None
    value = items[index].get(field)
    return value if value not in (None, "", []) else None


def _resolve_rule_source(
    snapshot: ConfirmedProfileSnapshot,
    rule: _Rule,
    collection_offsets: dict[tuple[str, str], int],
) -> tuple[str, Any, tuple[str, str] | None] | None:
    collection_source = next(
        ((path, template) for path in rule.source_paths if (template := _collection_template(path)) is not None),
        None,
    )

    if collection_source is not None:
        path, (kind, field) = collection_source
        key = (kind, field)
        index = collection_offsets.get(key, 0)
        indexed_path = re.sub(r"\[\d+\]", f"[{index}]", path, count=1)
        value = _source_value(snapshot, indexed_path)
        if value is not None:
            return indexed_path, value, key

        # Once a repeated collection field advances past index 0, never fall
        # back to the scalar summary: duplicating the first education/work
        # record into later rows is worse than leaving the later row unmatched.
        if index > 0:
            return None

        for fallback_path in rule.source_paths:
            if _collection_template(fallback_path) is not None:
                continue
            fallback = _source_value(snapshot, fallback_path)
            if fallback is not None:
                return fallback_path, fallback, key
        return None

    for source_path in rule.source_paths:
        value = _source_value(snapshot, source_path)
        if value is not None:
            return source_path, value, None
    return None


def _field_text(field: FormFieldDescriptor) -> tuple[str, str]:
    primary = _normalize(field.label or field.aria_label or field.placeholder)
    combined = _normalize(
        " ".join(
            [
                field.label,
                field.aria_label,
                field.placeholder,
                field.name,
                field.section,
            ]
        )
    )
    return primary, combined


def _rule_score(field: FormFieldDescriptor, rule: _Rule) -> tuple[float, str] | None:
    primary, combined = _field_text(field)
    if not combined:
        return None
    if any(_normalize(term) in combined for term in rule.negative_terms):
        return None

    best: tuple[float, str] | None = None
    for alias in rule.aliases:
        normalized = _normalize(alias)
        if not normalized:
            continue
        if primary == normalized:
            candidate = (0.99, alias)
        elif len(normalized) >= 2 and normalized in primary:
            candidate = (0.96, alias)
        elif normalized in combined:
            candidate = (0.90, alias)
        else:
            continue
        if best is None or candidate[0] > best[0]:
            best = candidate

    for alias in rule.weak_aliases:
        normalized = _normalize(alias)
        if normalized and normalized in combined:
            candidate = (0.72, alias)
            if best is None or candidate[0] > best[0]:
                best = candidate

    if best is None:
        return None

    if rule.section_terms and any(_normalize(term) in _normalize(field.section) for term in rule.section_terms):
        best = (min(0.99, best[0] + 0.02), best[1])
    return best


def _summary(field: FormFieldDescriptor) -> PlanFieldSummary:
    return PlanFieldSummary(
        field_id=field.field_id,
        label=field.label or field.aria_label or field.placeholder or field.name or field.field_id,
        control_type=field.input_type or field.tag,
    )


def build_fill_plan(
    snapshot: ConfirmedProfileSnapshot,
    scan: FormScan,
    *,
    session_id: str = "",
    token: str | None = None,
) -> FillPlan:
    plan = FillPlan(
        token=token or uuid.uuid4().hex,
        session_id=session_id,
        page_url=scan.url,
    )

    collection_offsets: dict[tuple[str, str], int] = {}

    for field in scan.fields:
        input_type = (field.input_type or field.tag or "text").lower()
        if field.disabled or field.readonly or input_type in _BLOCKED_TYPES:
            plan.blocked.append(_summary(field))
            continue

        candidates: list[tuple[float, str, str, Any, tuple[str, str] | None]] = []
        for rule in _RULES:
            scored = _rule_score(field, rule)
            if scored is None:
                continue
            resolved = _resolve_rule_source(snapshot, rule, collection_offsets)
            if resolved is None:
                continue
            score, alias = scored
            source_path, value, collection_key = resolved
            candidates.append((score, alias, source_path, value, collection_key))

        if not candidates:
            plan.unmatched.append(_summary(field))
            continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        top = candidates[0]
        if len(candidates) > 1 and abs(candidates[1][0] - top[0]) < 0.01 and candidates[1][2] != top[2]:
            plan.unmatched.append(_summary(field))
            continue

        score, alias, source_path, value, collection_key = top
        if collection_key is not None:
            collection_offsets[collection_key] = collection_offsets.get(collection_key, 0) + 1
        control_needs_confirmation = (
            field.tag.lower() == "select"
            or input_type in {"radio", "radio_group", "combobox", "date_picker"}
        )
        plan.items.append(
            FillPlanItem(
                field_id=field.field_id,
                label=field.label or field.aria_label or field.placeholder or field.name or field.field_id,
                control_type=input_type,
                value=value,
                source_path=source_path,
                confidence=score,
                reason=alias,
                requires_confirmation=score < _HIGH_CONFIDENCE or control_needs_confirmation,
            )
        )

    return plan
