from __future__ import annotations

from app.browser_agent.models import FormFieldDescriptor
from app.browser_agent.value_normalization import normalize_value_for_control


def control(
    *,
    field_id: str = "f",
    input_type: str = "combobox",
    label: str = "",
    placeholder: str = "",
    options: list[str] | None = None,
) -> FormFieldDescriptor:
    return FormFieldDescriptor(
        field_id=field_id,
        tag="div" if input_type in {"combobox", "radio_group", "date_picker"} else "select",
        input_type=input_type,
        label=label,
        name="",
        placeholder=placeholder,
        aria_label="",
        section="",
        required=False,
        options=options or [],
    )


def test_option_normalization_returns_exact_page_option_for_known_profile_aliases():
    assert normalize_value_for_control(
        "identity.gender", "女",
        control(label="性别", options=["男性", "女性"]),
    ) == "女性"
    assert normalize_value_for_control(
        "identity.id_type", "居民身份证",
        control(label="证件类型", options=["身份证", "护照"]),
    ) == "身份证"
    assert normalize_value_for_control(
        "collections.education[0].degree", "本科",
        control(label="最高学历", options=["大学本科", "硕士研究生"]),
    ) == "大学本科"


def test_option_normalization_prefers_exact_match_and_refuses_ambiguous_or_unknown_values():
    assert normalize_value_for_control(
        "identity.political_status", "群众",
        control(label="政治面貌", options=["群众", "共青团员"]),
    ) == "群众"
    assert normalize_value_for_control(
        "collections.education[0].degree", "研究生",
        control(label="最高学历", options=["硕士研究生", "博士研究生"]),
    ) is None
    assert normalize_value_for_control(
        "identity.id_type", "其他证件",
        control(label="证件类型", options=["身份证", "护照"]),
    ) is None


def test_date_normalization_uses_page_placeholder_without_changing_the_source_value():
    assert normalize_value_for_control(
        "identity.birth_date", "2004-01-02",
        control(input_type="date_picker", label="出生日期", placeholder="YYYY/MM/DD"),
    ) == "2004/01/02"
    assert normalize_value_for_control(
        "identity.birth_date", "2004-01-02",
        control(input_type="date_picker", label="出生日期", placeholder="YYYY年MM月DD日"),
    ) == "2004年01月02日"
    assert normalize_value_for_control(
        "education.graduation_date", "2027-06",
        control(input_type="date_picker", label="毕业时间", placeholder="YYYY/MM"),
    ) == "2027/06"


def test_option_control_without_visible_options_keeps_original_value_for_runtime_exact_match():
    assert normalize_value_for_control(
        "identity.gender", "女",
        control(label="性别", options=[]),
    ) == "女"
