from __future__ import annotations

import pytest

from app.browser_agent.adapters import adapt_scan_for_browser_adapter, select_browser_adapter
from app.browser_agent.mapping import build_fill_plan
from app.browser_agent.moka import moka_source_path
from app.browser_agent.models import ConfirmedProfileSnapshot, FormFieldDescriptor, FormScan


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("basicInfo.name", "identity.name"),
        ("values.basicInfo.phone", "contact.phone"),
        ("basicInfo[email]", "contact.email"),
        ("educationInfo[0].school", "collections.education[0].school"),
        ("educationInfo[1][speciality]", "collections.education[1].major"),
        ("candidateInfo.educationInfo.2.academicDegree", "collections.education[2].degree"),
        ("experienceInfo[0].company", "collections.experience[0].organization"),
        ("experienceInfo[1].title", "collections.experience[1].role"),
        ("projectInfo[3].projectName", "collections.project[3].name"),
        ("languageInfo[0].language", "collections.language[0].name"),
        ("awardInfo[0].awardName", "collections.award[0].name"),
        ("educationInfo_1_school", "collections.education[1].school"),
        ("form_basicInfo_phone", "contact.phone"),
    ],
)
def test_moka_source_path_maps_documented_native_paths(raw_name, expected):
    assert moka_source_path(raw_name) == expected


@pytest.mark.parametrize(
    "raw_name",
    [
        "",
        "customFields[0].value",
        "practiceInfo[0].company",
        "educationInfo[abc].school",
        "educationInfo[0].unknownField",
        "unrelated.school",
    ],
)
def test_moka_source_path_refuses_ambiguous_or_unsupported_fields(raw_name):
    assert moka_source_path(raw_name) is None


def _field(
    field_id: str,
    name: str,
    label: str = "学校",
    *,
    dom_id: str = "",
) -> FormFieldDescriptor:
    return FormFieldDescriptor(
        field_id=field_id,
        tag="input",
        input_type="text",
        label=label,
        name=name,
        placeholder="",
        aria_label="",
        section="教育经历",
        required=True,
        options=[],
        dom_id=dom_id,
    )


def test_moka_native_indexes_override_dom_occurrence_order():
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
        url="https://app.mokahr.com/apply/acme/site#/job/1/apply",
        title="职位申请",
        fields=[
            # Deliberately reversed DOM order: path identity must win.
            _field("school-second", "educationInfo[1].school"),
            _field("school-first", "educationInfo[0].school"),
            _field("major-second", "educationInfo[1][speciality]", "专业"),
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
    assert all(item.reason == "Moka native field path" for item in mapped.values())


def test_moka_known_native_field_with_missing_ssot_value_stays_unmatched():
    snapshot = ConfirmedProfileSnapshot(
        scalars={},
        collections={"education": [{"school": "三江学院"}]},
    )
    raw_scan = FormScan(
        url="https://app.mokahr.com/apply/acme/site#/job/1/apply",
        title="职位申请",
        fields=[_field("major", "educationInfo[0].speciality", "专业")],
    )
    adapter = select_browser_adapter(raw_scan.url)
    scan = adapt_scan_for_browser_adapter(adapter, raw_scan)
    plan = build_fill_plan(snapshot, scan)

    assert plan.items == []
    assert [item.field_id for item in plan.unmatched] == ["major"]


def test_moka_scan_uses_dom_id_when_react_control_has_no_name_attribute():
    raw_scan = FormScan(
        url="https://app.mokahr.com/apply/acme/site#/job/1/apply",
        title="职位申请",
        fields=[
            _field(
                "school",
                "",
                dom_id="educationInfo_1_school",
            )
        ],
    )
    adapter = select_browser_adapter(raw_scan.url)
    adapted = adapt_scan_for_browser_adapter(adapter, raw_scan)

    assert adapted.fields[0].adapter_source_path == "collections.education[1].school"
