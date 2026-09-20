from __future__ import annotations

import pytest

from app.browser_agent.adapters import adapt_scan_for_browser_adapter, select_browser_adapter
from app.browser_agent.beisen import beisen_source_path
from app.browser_agent.mapping import build_fill_plan
from app.browser_agent.models import ConfirmedProfileSnapshot, FormFieldDescriptor, FormScan


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("personProfile.Name", "identity.name"),
        ("standardResume.personProfile.Mobile.value", "contact.phone"),
        ("personProfile[Birthday][value]", "identity.birth_date"),
        ("standardResume_personProfile_Polity_value", "identity.political_status"),
        ("education[0].schoolName", "collections.education[0].school"),
        ("standardResume.education[1].CollegeName.value", "collections.education[1].school"),
        ("education_2_majorName", "collections.education[2].major"),
        ("education[0].Degree.value", "collections.education[0].degree"),
        ("education[0].StartDate", "collections.education[0].start_date"),
        ("education[0].endDate", "collections.education[0].end_date"),
        ("workExperience[0].companyName", "collections.experience[0].organization"),
        ("workExperience[1].JobTitle.value", "collections.experience[1].role"),
        ("workExperience_2_jobDuty", "collections.experience[2].bullets"),
        ("project[0].projectName", "collections.project[0].name"),
        ("project[0].projectDescribe.value", "collections.project[0].description"),
        ("project_3_Duty", "collections.project[3].bullets"),
    ],
)
def test_beisen_source_path_maps_public_standard_resume_paths(raw_name, expected):
    assert beisen_source_path(raw_name) == expected


@pytest.mark.parametrize(
    "raw_name",
    [
        "",
        "internship[0].companyName",
        "family[0].name",
        "relativesDeclaration[0].name",
        "credentialsInfo[0].idNumber",
        "education[abc].schoolName",
        "education[0].unknownField",
        "customFields[0].value",
        "unrelated.Name",
    ],
)
def test_beisen_source_path_refuses_ambiguous_sensitive_or_unknown_modules(raw_name):
    assert beisen_source_path(raw_name) is None


def _field(
    field_id: str,
    name: str,
    label: str,
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
        section="标准简历",
        required=True,
        options=[],
        dom_id=dom_id,
    )


def test_beisen_indexed_native_paths_override_dom_occurrence_order():
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
        url="https://career.beisen.com/apply/123",
        title="职位申请",
        fields=[
            _field("school-second", "standardResume.education[1].schoolName", "学校"),
            _field("school-first", "education[0].schoolName", "学校"),
            _field("major-second", "", "专业", dom_id="standardResume_education_1_majorName"),
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
    assert all(item.reason == "北森 native field path" for item in mapped.values())


def test_beisen_sensitive_person_profile_mapping_still_requires_confirmation():
    snapshot = ConfirmedProfileSnapshot(
        scalars={"identity.political_status": "共青团员"},
        collections={},
    )
    raw_scan = FormScan(
        url="https://career.beisen.com/apply/123",
        title="职位申请",
        fields=[
            FormFieldDescriptor(
                field_id="polity",
                tag="input",
                input_type="text",
                label="政治面貌",
                name="standardResume.personProfile.Polity.value",
                placeholder="",
                aria_label="",
                section="基本信息",
                required=True,
                options=[],
            )
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

    assert len(plan.items) == 1
    assert plan.items[0].source_path == "identity.political_status"
    assert plan.items[0].requires_confirmation is True
