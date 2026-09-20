from __future__ import annotations

import pytest

from app.browser_agent.adapters import adapt_scan_for_browser_adapter, select_browser_adapter
from app.browser_agent.feishu import feishu_source_path
from app.browser_agent.mapping import build_fill_plan
from app.browser_agent.models import ConfirmedProfileSnapshot, FormFieldDescriptor, FormScan


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("basic_info.name", "identity.name"),
        ("talent.basic_info.mobile", "contact.phone"),
        ("basic_info.email", "contact.email"),
        ("talent_basic_info_gender", "identity.gender"),
        ("talent_basic_info_birthday", "identity.birth_date"),
        ("basic_info.current_city", "location.current_city"),
        ("education_list[0].school", "collections.education[0].school"),
        ("education_list[1].field_of_study", "collections.education[1].major"),
        ("talent_education_list_2_degree", "collections.education[2].degree"),
        ("education_list[0].start_time", "collections.education[0].start_date"),
        ("education_list[0].end_time", "collections.education[0].end_date"),
        ("career_list[0].company", "collections.experience[0].organization"),
        ("career_list[1].title", "collections.experience[1].role"),
        ("talent_career_list_2_start_time", "collections.experience[2].start_date"),
        ("project_list[0].name", "collections.project[0].name"),
        ("project_list[0].role", "collections.project[0].role"),
        ("project_list[0].desc", "collections.project[0].description"),
        ("award_list[0].title", "collections.award[0].name"),
        ("award_list[0].award_time", "collections.award[0].date"),
        ("language_list[0].language", "collections.language[0].name"),
        ("language_list[0].proficiency", "collections.language[0].level"),
    ],
)
def test_feishu_source_path_maps_public_talent_schema(raw_name, expected):
    assert feishu_source_path(raw_name) == expected


@pytest.mark.parametrize(
    "raw_name",
    [
        "",
        "basic_info.identification_number",
        "basic_info.identification_type",
        "basic_info.hometown_city",
        "basic_info.customized_data_list",
        "education_list[0].customized_data_list",
        "works_list[0].name",
        "education_list[abc].school",
        "education_list[0].unknown_field",
        "unrelated.name",
    ],
)
def test_feishu_source_path_refuses_high_risk_custom_or_ambiguous_fields(raw_name):
    assert feishu_source_path(raw_name) is None


def _field(field_id: str, name: str, label: str, *, dom_id: str = "") -> FormFieldDescriptor:
    return FormFieldDescriptor(
        field_id=field_id,
        tag="input",
        input_type="text",
        label=label,
        name=name,
        placeholder="",
        aria_label="",
        section="人才简历",
        required=True,
        options=[],
        dom_id=dom_id,
    )


def test_feishu_indexed_paths_override_dom_occurrence_order():
    snapshot = ConfirmedProfileSnapshot(
        scalars={},
        collections={
            "education": [
                {"school": "三江学院", "major": "视觉传达设计"},
                {"school": "南京艺术学院", "major": "数字媒体"},
            ]
        },
    )
    raw_scan = FormScan(
        url="https://jobs.feishu.cn/apply/123",
        title="职位申请",
        fields=[
            _field("school-second", "education_list[1].school", "学校"),
            _field("school-first", "education_list[0].school", "学校"),
            _field("major-second", "", "专业", dom_id="talent_education_list_1_field_of_study"),
        ],
    )

    adapter = select_browser_adapter(raw_scan.url)
    scan = adapt_scan_for_browser_adapter(adapter, raw_scan)
    plan = build_fill_plan(
        snapshot,
        scan,
        adapter_id=adapter.id,
        adapter_display_name=adapter.display_name,
        adapter_implementation=adapter.implementation,
        adapter_capabilities=list(adapter.capabilities),
        adapter_limitations=list(adapter.limitations),
    )
    mapped = {item.field_id: item for item in plan.items}

    assert mapped["school-second"].source_path == "collections.education[1].school"
    assert mapped["school-second"].value == "南京艺术学院"
    assert mapped["school-first"].source_path == "collections.education[0].school"
    assert mapped["school-first"].value == "三江学院"
    assert mapped["major-second"].source_path == "collections.education[1].major"
    assert mapped["major-second"].value == "数字媒体"
    assert all(item.confidence == 1.0 for item in mapped.values())
    assert all(item.reason == "飞书招聘 native field path" for item in mapped.values())


def test_feishu_identification_number_never_gets_privileged_source_path():
    raw_scan = FormScan(
        url="https://jobs.feishu.cn/apply/123",
        title="职位申请",
        fields=[
            _field(
                "id-number",
                "basic_info.identification_number",
                "证件号码",
            )
        ],
    )

    adapter = select_browser_adapter(raw_scan.url)
    scan = adapt_scan_for_browser_adapter(adapter, raw_scan)

    assert scan.fields[0].adapter_source_path == ""
